"""Authenticated encryption for stored cloud credentials.

Design
- AES-256-GCM with a random 96-bit nonce per record. The associated data (AAD) binds each
  ciphertext to its connection id and owner, so a ciphertext copied to another row or user fails
  to decrypt.
- A *key ring* ({key id: 32-byte key}) with one active key supports rotation: records remember the
  key id that encrypted them; new writes use the active key; old keys stay available for decrypt.
- Where the master key comes from is a provider choice, identical code in every environment:
    * ``keyvault``  production: the key is an Azure Key Vault *secret* read with the App Service /
                    Container Apps managed identity (no key material in configuration).
    * ``env``       the key ring is supplied through ``CONNECTION_ENCRYPTION_KEYS`` (for
                    environments that inject secrets as app settings / Key Vault references).
    * ``local_file`` development/testing only: a random key is generated once into a git-ignored
                    file. Refused in production/staging.
- Plaintext secrets exist only inside ``encrypt``/``decrypt`` call frames; nothing here logs them.
"""

import base64
import json
import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import httpx
import structlog
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

if TYPE_CHECKING:
    from cloud_recommender.core.config import Settings

logger = structlog.get_logger(__name__)

KEY_BYTES = 32
NONCE_BYTES = 12


class VaultError(Exception):
    """Encryption infrastructure problem. Messages never contain key material or plaintext."""


class SecretUnavailableError(VaultError):
    """No usable encryption key is configured (credentials cannot be stored or read)."""


@dataclass(frozen=True)
class KeyRing:
    keys: Mapping[str, bytes]
    active_kid: str

    def __post_init__(self) -> None:
        if self.active_kid not in self.keys:
            raise SecretUnavailableError("The active encryption key id is not in the key ring.")
        for key in self.keys.values():
            if len(key) != KEY_BYTES:
                raise SecretUnavailableError("Encryption keys must be exactly 32 bytes.")

    def __repr__(self) -> str:  # never print key material
        return f"KeyRing(kids={sorted(self.keys)}, active={self.active_kid!r})"


class KeyProvider(Protocol):
    def load(self) -> KeyRing: ...


def _decode_key(value: str) -> bytes:
    try:
        raw = base64.b64decode(value.strip(), validate=True)
    except ValueError as exc:
        raise SecretUnavailableError("An encryption key is not valid base64.") from exc
    return raw


class EnvKeyProvider:
    """Key ring from ``CONNECTION_ENCRYPTION_KEYS`` = JSON ``{"k1": "<base64 32 bytes>", ...}``."""

    def __init__(self, keys_json: str | None, active_kid: str | None) -> None:
        self._keys_json = keys_json
        self._active_kid = active_kid

    def load(self) -> KeyRing:
        if not self._keys_json:
            raise SecretUnavailableError("CONNECTION_ENCRYPTION_KEYS is not configured.")
        try:
            parsed = json.loads(self._keys_json)
            keys = {str(kid): _decode_key(str(value)) for kid, value in parsed.items()}
        except (ValueError, AttributeError) as exc:
            raise SecretUnavailableError(
                "CONNECTION_ENCRYPTION_KEYS is not a valid key map."
            ) from exc
        active = self._active_kid or sorted(keys)[-1]
        return KeyRing(keys, active)


class LocalFileKeyProvider:
    """Development/testing key stored in a git-ignored file (created with a random key)."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> KeyRing:
        if not self._path.is_file():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                base64.b64encode(secrets.token_bytes(KEY_BYTES)).decode(), encoding="ascii"
            )
            try:
                os.chmod(self._path, 0o600)
            except OSError:  # pragma: no cover - not supported on every platform
                pass
            logger.warning(
                "local_encryption_key_created", note="development only; not for production"
            )
        return KeyRing({"local-1": _decode_key(self._path.read_text(encoding="ascii"))}, "local-1")


class KeyVaultKeyProvider:
    """Master key stored as an Azure Key Vault secret, read with the platform managed identity.

    Uses the App Service / Container Apps identity endpoint (``IDENTITY_ENDPOINT`` +
    ``IDENTITY_HEADER``). The secret value must be base64 of 32 random bytes. The secret version
    becomes the key id, so rotating the secret in Key Vault creates a new key without losing the
    ability to decrypt older records (list prior versions in ``extra_versions``).
    """

    VAULT_RESOURCE = "https://vault.azure.net"

    def __init__(
        self,
        vault_url: str | None,
        secret_name: str | None,
        environ: Mapping[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,
        extra_versions: tuple[str, ...] = (),
    ) -> None:
        self._vault_url = (vault_url or "").rstrip("/")
        self._secret_name = secret_name
        self._environ = os.environ if environ is None else environ
        self._transport = transport
        self._extra_versions = extra_versions

    def _managed_identity_token(self, client: httpx.Client) -> str:
        endpoint = self._environ.get("IDENTITY_ENDPOINT")
        header = self._environ.get("IDENTITY_HEADER")
        if not endpoint or not header:
            raise SecretUnavailableError("No managed identity is available in this environment.")
        response = client.get(
            endpoint,
            params={"api-version": "2019-08-01", "resource": self.VAULT_RESOURCE},
            headers={"X-IDENTITY-HEADER": header},
        )
        if response.status_code != 200:
            raise SecretUnavailableError("The managed identity could not obtain a Key Vault token.")
        return str(response.json()["access_token"])

    def _read_secret(
        self, client: httpx.Client, token: str, version: str = ""
    ) -> tuple[str, bytes]:
        path = f"/secrets/{self._secret_name}" + (f"/{version}" if version else "")
        response = client.get(
            f"{self._vault_url}{path}",
            params={"api-version": "7.4"},
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code != 200:
            raise SecretUnavailableError("The encryption key could not be read from Key Vault.")
        body = response.json()
        secret_id = str(body["id"]).rstrip("/").rsplit("/", 1)[-1]
        return f"kv-{secret_id}", _decode_key(str(body["value"]))

    def load(self) -> KeyRing:
        if not self._vault_url or not self._secret_name:
            raise SecretUnavailableError(
                "KEY_VAULT_URL / CONNECTION_KEY_SECRET_NAME are not configured."
            )
        try:
            with httpx.Client(timeout=10.0, transport=self._transport) as client:
                token = self._managed_identity_token(client)
                active_kid, active_key = self._read_secret(client, token)
                keys = {active_kid: active_key}
                for version in self._extra_versions:
                    kid, key = self._read_secret(client, token, version)
                    keys[kid] = key
        except httpx.HTTPError as exc:
            raise SecretUnavailableError("Key Vault could not be reached.") from exc
        return KeyRing(keys, active_kid)


class CredentialCipher:
    """Encrypts/decrypts credentials with the active key of a key ring."""

    def __init__(self, ring: KeyRing) -> None:
        self._ring = ring

    @property
    def active_kid(self) -> str:
        return self._ring.active_kid

    @staticmethod
    def _aad(connection_id: str, owner_key: str) -> bytes:
        return f"{connection_id}|{owner_key}".encode()

    def encrypt(self, plaintext: str, connection_id: str, owner_key: str) -> tuple[bytes, str]:
        nonce = secrets.token_bytes(NONCE_BYTES)
        key = self._ring.keys[self._ring.active_kid]
        ciphertext = AESGCM(key).encrypt(
            nonce, plaintext.encode(), self._aad(connection_id, owner_key)
        )
        return nonce + ciphertext, self._ring.active_kid

    def decrypt(self, blob: bytes, kid: str, connection_id: str, owner_key: str) -> str:
        key = self._ring.keys.get(kid)
        if key is None:
            raise VaultError("The key that encrypted this credential is not available.")
        try:
            plaintext = AESGCM(key).decrypt(
                blob[:NONCE_BYTES], blob[NONCE_BYTES:], self._aad(connection_id, owner_key)
            )
        except InvalidTag:
            raise VaultError("The stored credential could not be authenticated.") from None
        return plaintext.decode()

    def __repr__(self) -> str:
        return f"CredentialCipher(active={self._ring.active_kid!r})"


def generate_key_b64() -> str:
    """A new random master key (base64) for operators to place in Key Vault or app settings."""
    return base64.b64encode(secrets.token_bytes(KEY_BYTES)).decode()


def build_key_provider(settings: "Settings", local_key_path: Path | None = None) -> KeyProvider:
    """Choose the key provider from settings (same code path in every environment)."""
    if settings.connection_key_provider == "keyvault":
        return KeyVaultKeyProvider(settings.key_vault_url, settings.connection_key_secret_name)
    if settings.connection_key_provider == "env":
        keys = settings.connection_encryption_keys
        return EnvKeyProvider(
            keys.get_secret_value() if keys else None, settings.connection_active_key_id
        )
    default_path = Path(__file__).resolve().parents[3] / ".local-secrets" / "connection.key"
    return LocalFileKeyProvider(local_key_path or default_path)


def build_cipher(settings: "Settings", local_key_path: Path | None = None) -> CredentialCipher:
    return CredentialCipher(build_key_provider(settings, local_key_path).load())
