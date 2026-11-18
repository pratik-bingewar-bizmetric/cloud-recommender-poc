"""Read-only Azure Resource Manager client bound to one access token.

Only GET is allowed, plus the Cost Management *query* POST (a read operation). A pagination
``nextLink`` is followed only when it stays on the ARM host, so the bearer token can never be sent
to another host.
"""

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

logger = structlog.get_logger(__name__)

COST_QUERY_SUFFIX = "/providers/Microsoft.CostManagement/query"
MAX_ERROR_MESSAGE = 300
MAX_PAGES = 100


@dataclass
class ArmResponse:
    """Normalized outcome of one ARM call."""

    status_code: int | None  # None => network failure
    body: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    retry_after: int | None = None
    network_error: bool = False

    @property
    def ok(self) -> bool:
        return self.status_code == 200 and self.body is not None


class AzureArmClient:
    """Minimal read-only ARM client."""

    def __init__(
        self,
        token: str,
        base_url: str,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._host = urlparse(self._base_url).netloc.lower()
        self._timeout = timeout
        self._transport = transport

    def __repr__(self) -> str:  # never expose the token
        return f"AzureArmClient(base_url={self._base_url!r})"

    async def _send(
        self,
        method: str,
        url: str,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> ArmResponse:
        if method == "POST":
            if not url.split("?")[0].endswith(COST_QUERY_SUFFIX):
                raise PermissionError("Only the Cost Management query may use POST.")
        elif method != "GET":
            raise PermissionError("Azure access is read-only.")
        if urlparse(url).netloc.lower() != self._host:
            raise PermissionError("Refusing to send credentials to a different host.")

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport, follow_redirects=False
            ) as client:
                response = await client.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers={
                        "Authorization": f"Bearer {self._token}",
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            logger.warning("arm_request_failed", error_type=type(exc).__name__)
            return ArmResponse(status_code=None, network_error=True)

        body: dict[str, Any] | None = None
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                body = parsed
        except ValueError:
            body = None

        retry_after: int | None = None
        for name, value in response.headers.items():
            if name.lower().endswith("retry-after"):
                try:
                    retry_after = max(1, int(float(value)))
                except ValueError:
                    continue
                break

        if response.status_code == 200:
            return ArmResponse(status_code=200, body=body if body is not None else {})

        code: str | None = None
        message: str | None = None
        if body and isinstance(body.get("error"), dict):
            err = body["error"]
            code = str(err.get("code")) if err.get("code") else None
            message = str(err.get("message"))[:MAX_ERROR_MESSAGE] if err.get("message") else None
        return ArmResponse(
            status_code=response.status_code,
            body=body,
            error_code=code,
            error_message=message,
            retry_after=retry_after,
        )

    async def get(
        self, path: str, api_version: str, params: dict[str, str] | None = None
    ) -> ArmResponse:
        merged = {"api-version": api_version, **(params or {})}
        return await self._send("GET", f"{self._base_url}{path}", merged)

    async def get_paged(
        self,
        path: str,
        api_version: str,
        params: dict[str, str] | None = None,
        max_items: int = 5000,
    ) -> tuple[list[dict[str, Any]], bool, ArmResponse | None]:
        """Return (items, truncated, error). ``error`` is set when the *first* page failed."""
        items: list[dict[str, Any]] = []
        truncated = False
        response = await self.get(path, api_version, params)
        if not response.ok:
            return items, False, response
        pages = 0
        while True:
            body = response.body or {}
            items.extend(i for i in body.get("value", []) if isinstance(i, dict))
            next_link = body.get("nextLink")
            pages += 1
            if len(items) >= max_items:
                truncated = bool(next_link) or len(items) > max_items
                items = items[:max_items]
                break
            if not next_link or pages >= MAX_PAGES:
                truncated = bool(next_link)
                break
            if not str(next_link).startswith(self._base_url + "/"):
                logger.warning("arm_next_link_rejected")
                truncated = True
                break
            response = await self._send("GET", str(next_link))
            if not response.ok:  # later-page failure: keep what we have, flag as truncated
                truncated = True
                break
        return items, truncated, None

    async def post_cost_query(
        self, path: str, api_version: str, body: dict[str, Any]
    ) -> ArmResponse:
        return await self._send(
            "POST", f"{self._base_url}{path}", {"api-version": api_version}, body
        )
