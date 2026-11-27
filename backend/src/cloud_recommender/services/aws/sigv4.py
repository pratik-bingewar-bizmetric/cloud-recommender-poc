"""Pure-Python AWS Signature Version 4 (SigV4) request signer.

Follows official AWS Signature Version 4 specification without requiring boto3 or external C-extensions.
Supports signing arbitrary HTTP requests for STS, EC2, S3, IAM, CloudWatch, RDS, Lambda, ECS, EKS, and Cost Explorer.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from urllib.parse import parse_qsl, quote, urlsplit

from cloud_recommender.services.aws.operation_validator import (
    validate_outbound_aws_request,
)


def _sign_key(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def get_signature_key(key: str, date_stamp: str, region_name: str, service_name: str) -> bytes:
    """Derive HMAC-SHA256 signing key for AWS SigV4."""
    k_date = _sign_key(("AWS4" + key).encode("utf-8"), date_stamp)
    k_region = hmac.new(k_date, region_name.encode("utf-8"), hashlib.sha256).digest()
    k_service = hmac.new(k_region, service_name.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()


def _validate_outbound_aws_request(
    url: str,
    method: str,
    headers: dict[str, str] | None = None,
    body: bytes | str | None = None,
    service: str = "sts",
    region: str = "us-east-1",
) -> None:
    """Enforce strict centralized action allowlist and reject mutating HTTP actions."""
    validate_outbound_aws_request(
        method=method,
        url=url,
        headers=headers,
        body=body,
        service=service,
        region=region,
    )


def sign_aws_request(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: bytes | str | None = None,
    access_key_id: str = "",
    secret_access_key: str = "",
    region: str = "us-east-1",
    service: str = "sts",
    session_token: str | None = None,
    timestamp: datetime | None = None,
) -> dict[str, str]:
    """Sign an HTTP request using AWS SigV4 and return the signed headers dict."""
    _validate_outbound_aws_request(
        url=url,
        method=method,
        headers=headers,
        body=body,
        service=service,
        region=region,
    )

    if timestamp is None:
        timestamp = datetime.now(UTC)

    amz_date = timestamp.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = timestamp.strftime("%Y%m%d")

    parsed_url = urlsplit(url)
    host = parsed_url.hostname or "amazonaws.com"
    if parsed_url.port and parsed_url.port not in (80, 443):
        host = f"{host}:{parsed_url.port}"

    canonical_uri = parsed_url.path or "/"
    # Encode URI path according to RFC 3986, preserving slashes
    canonical_uri = quote(canonical_uri, safe="/-_.~")

    # Canonical query string
    if parsed_url.query:
        query_pairs = parse_qsl(parsed_url.query, keep_blank_values=True)
        # Sort query parameters by key, then value
        sorted_pairs = sorted(
            [(quote(k, safe="-_.~"), quote(v, safe="-_.~")) for k, v in query_pairs]
        )
        canonical_querystring = "&".join(f"{k}={v}" for k, v in sorted_pairs)
    else:
        canonical_querystring = ""

    # Payload hash
    if body is None:
        body_bytes = b""
    elif isinstance(body, str):
        body_bytes = body.encode("utf-8")
    else:
        body_bytes = body
    payload_hash = hashlib.sha256(body_bytes).hexdigest()

    # Headers to sign
    signed_headers_map: dict[str, str] = {
        "host": host,
        "x-amz-date": amz_date,
        "x-amz-content-sha256": payload_hash,
    }
    if session_token:
        signed_headers_map["x-amz-security-token"] = session_token

    # Include user headers if present (lowercased)
    if headers:
        for k, v in headers.items():
            k_lower = k.lower().strip()
            if k_lower not in ("authorization", "connection"):
                signed_headers_map[k_lower] = " ".join(v.strip().split())

    sorted_header_names = sorted(signed_headers_map.keys())
    canonical_headers = "".join(f"{h}:{signed_headers_map[h]}\n" for h in sorted_header_names)
    signed_headers_str = ";".join(sorted_header_names)

    # Canonical request
    canonical_request = (
        f"{method.upper()}\n"
        f"{canonical_uri}\n"
        f"{canonical_querystring}\n"
        f"{canonical_headers}\n"
        f"{signed_headers_str}\n"
        f"{payload_hash}"
    )

    # String to sign
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    canonical_request_hash = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    string_to_sign = f"AWS4-HMAC-SHA256\n{amz_date}\n{credential_scope}\n{canonical_request_hash}"

    # Calculate signature
    signing_key = get_signature_key(secret_access_key, date_stamp, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    # Authorization header
    authorization_header = (
        f"AWS4-HMAC-SHA256 "
        f"Credential={access_key_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers_str}, "
        f"Signature={signature}"
    )

    # Assemble return headers
    result_headers = dict(headers or {})
    result_headers["x-amz-date"] = amz_date
    result_headers["x-amz-content-sha256"] = payload_hash
    if session_token:
        result_headers["x-amz-security-token"] = session_token
    result_headers["Authorization"] = authorization_header

    return result_headers
