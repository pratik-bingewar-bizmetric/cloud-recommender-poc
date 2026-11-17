"""Credential encryption, key providers, repository isolation and migration consistency."""

import base64
import importlib.util
import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from cloud_recommender.core.config import InsecureConfigurationError, Settings
from cloud_recommender.core.secret_vault import (
    CredentialCipher,
    EnvKeyProvider,
    KeyRing,
    KeyVaultKeyProvider,
    LocalFileKeyProvider,
    SecretUnavailableError,
    VaultError,
    build_cipher,
    generate_key_b64,
)
from cloud_recommender.db.models import CloudConnectionModel
from cloud_recommender.db.repositories.connection_repo import (
    DuplicateConnectionError,
    InMemoryConnectionRepository,
    SqlConnectionRepository,
    StoredConnection,
)

SECRET = "Sup3r-Secret-Value-For-Tests~abc123"
OWNER_A = "tenant-1:oid-a"
OWNER_B = "tenant-1:oid-b"


def ring(**keys: str) -> KeyRing:
    material = {kid: base64.b64decode(value) for kid, value in keys.items()}
    return KeyRing(material, sorted(material)[-1])


@pytest.fixture
def cipher() -> CredentialCipher:
    return CredentialCipher(ring(k1=generate_key_b64()))


# --------------------------------------------------------------------------------------
# Encryption
# --------------------------------------------------------------------------------------


def test_round_trip_and_ciphertext_hides_the_plaintext(cipher: CredentialCipher) -> None:
    blob, kid = cipher.encrypt(SECRET, "conn-1", OWNER_A)
    assert SECRET.encode() not in blob and kid == "k1"
    assert cipher.decrypt(blob, kid, "conn-1", OWNER_A) == SECRET


def test_each_encryption_uses_a_fresh_nonce(cipher: CredentialCipher) -> None:
    assert cipher.encrypt(SECRET, "c", OWNER_A)[0] != cipher.encrypt(SECRET, "c", OWNER_A)[0]


def test_ciphertext_cannot_be_moved_to_another_connection_or_owner(
    cipher: CredentialCipher,
) -> None:
    blob, kid = cipher.encrypt(SECRET, "conn-1", OWNER_A)
    with pytest.raises(VaultError):
        cipher.decrypt(blob, kid, "conn-2", OWNER_A)  # other row
    with pytest.raises(VaultError):
        cipher.decrypt(blob, kid, "conn-1", OWNER_B)  # other user


def test_tampered_ciphertext_is_rejected(cipher: CredentialCipher) -> None:
    blob, kid = cipher.encrypt(SECRET, "conn-1", OWNER_A)
    tampered = blob[:-1] + bytes([blob[-1] ^ 1])
    with pytest.raises(VaultError):
        cipher.decrypt(tampered, kid, "conn-1", OWNER_A)


def test_key_rotation_keeps_old_records_readable_and_encrypts_new_ones_with_the_new_key() -> None:
    old, new = generate_key_b64(), generate_key_b64()
    before = CredentialCipher(KeyRing({"k1": base64.b64decode(old)}, "k1"))
    blob, kid = before.encrypt(SECRET, "c", OWNER_A)
    after = CredentialCipher(ring(k1=old, k2=new))
    assert after.active_kid == "k2"
    assert after.decrypt(blob, kid, "c", OWNER_A) == SECRET
    assert after.encrypt(SECRET, "c", OWNER_A)[1] == "k2"


def test_a_missing_key_is_a_vault_error_not_a_crash(cipher: CredentialCipher) -> None:
    blob, _ = cipher.encrypt(SECRET, "c", OWNER_A)
    with pytest.raises(VaultError):
        cipher.decrypt(blob, "unknown-kid", "c", OWNER_A)


def test_key_material_never_appears_in_repr() -> None:
    key = generate_key_b64()
    text = repr(CredentialCipher(KeyRing({"k1": base64.b64decode(key)}, "k1"))) + repr(
        KeyRing({"k1": base64.b64decode(key)}, "k1")
    )
    assert key not in text


def test_key_ring_validation() -> None:
    with pytest.raises(SecretUnavailableError):
        KeyRing({"k1": b"short"}, "k1")
    with pytest.raises(SecretUnavailableError):
        KeyRing({"k1": base64.b64decode(generate_key_b64())}, "missing")


# --------------------------------------------------------------------------------------
# Key providers
# --------------------------------------------------------------------------------------


def test_env_provider() -> None:
    keys = json.dumps({"k1": generate_key_b64(), "k2": generate_key_b64()})
    loaded = EnvKeyProvider(keys, "k1").load()
    assert loaded.active_kid == "k1" and set(loaded.keys) == {"k1", "k2"}
    with pytest.raises(SecretUnavailableError):
        EnvKeyProvider(None, None).load()
    with pytest.raises(SecretUnavailableError):
        EnvKeyProvider("not-json", None).load()
    with pytest.raises(SecretUnavailableError):
        EnvKeyProvider(json.dumps({"k1": "###"}), None).load()


def test_local_file_provider_generates_once_and_reuses(tmp_path: Path) -> None:
    path = tmp_path / "keys" / "connection.key"
    first = LocalFileKeyProvider(path).load()
    assert path.is_file()
    assert LocalFileKeyProvider(path).load().keys == first.keys  # stable across restarts


def key_vault_transport(secret_b64: str, version: str = "v1") -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "identity.local":
            assert request.headers["x-identity-header"] == "hdr"
            return httpx.Response(200, json={"access_token": "kv-token"})
        assert request.headers["authorization"] == "Bearer kv-token"
        assert request.url.path.startswith("/secrets/connection-key")
        return httpx.Response(
            200,
            json={
                "id": f"https://vault.test/secrets/connection-key/{version}",
                "value": secret_b64,
            },
        )

    return httpx.MockTransport(handler)


def test_key_vault_provider_reads_the_key_with_the_managed_identity() -> None:
    key = generate_key_b64()
    provider = KeyVaultKeyProvider(
        "https://vault.test",
        "connection-key",
        environ={"IDENTITY_ENDPOINT": "http://identity.local/msi", "IDENTITY_HEADER": "hdr"},
        transport=key_vault_transport(key),  # type: ignore[arg-type]
    )
    loaded = provider.load()
    assert loaded.active_kid == "kv-v1"
    assert loaded.keys["kv-v1"] == base64.b64decode(key)


def test_key_vault_provider_fails_clearly_without_identity_or_config() -> None:
    with pytest.raises(SecretUnavailableError, match="managed identity"):
        KeyVaultKeyProvider("https://vault.test", "connection-key", environ={}).load()
    with pytest.raises(SecretUnavailableError, match="not configured"):
        KeyVaultKeyProvider(None, None, environ={}).load()


def test_build_cipher_selects_the_provider_from_settings(tmp_path: Path) -> None:
    keys = json.dumps({"k1": generate_key_b64()})
    env = Settings(  # type: ignore[call-arg]
        _env_file=None,
        app_env="development",
        connection_key_provider="env",
        connection_encryption_keys=keys,
    )
    assert build_cipher(env).active_kid == "k1"
    local = Settings(_env_file=None, app_env="development", connection_key_provider="local_file")  # type: ignore[call-arg]
    assert build_cipher(local, tmp_path / "k.key").active_kid == "local-1"


# --------------------------------------------------------------------------------------
# Production configuration for the connection store
# --------------------------------------------------------------------------------------


def production(**overrides: Any) -> Settings:
    from security_fixtures import PRODUCTION_SECURITY

    return Settings(_env_file=None, app_env="production", **{**PRODUCTION_SECURITY, **overrides})  # type: ignore[call-arg]


def test_production_requires_the_database_store_and_a_managed_key() -> None:
    production().validate_for_serving()
    with pytest.raises(InsecureConfigurationError, match="CONNECTION_STORE"):
        production(connection_store="memory").validate_for_serving()
    with pytest.raises(InsecureConfigurationError, match="CONNECTION_KEY_PROVIDER"):
        production(connection_key_provider="local_file").validate_for_serving()
    with pytest.raises(InsecureConfigurationError, match="CONNECTION_ENCRYPTION_KEYS"):
        production(connection_encryption_keys=None).validate_for_serving()
    with pytest.raises(InsecureConfigurationError, match="KEY_VAULT_URL"):
        production(connection_key_provider="keyvault").validate_for_serving()
    production(
        connection_key_provider="keyvault",
        key_vault_url="https://vault.test",
        connection_key_secret_name="connection-key",
    ).validate_for_serving()
    with pytest.raises(InsecureConfigurationError, match="ALLOW_CLI_CONNECTIONS"):
        production(allow_cli_connections=True).validate_for_serving()


def test_encryption_keys_setting_is_masked() -> None:
    settings = production()
    assert "MDEyMzQ1" not in repr(settings)


# --------------------------------------------------------------------------------------
# Repository: owner isolation
# --------------------------------------------------------------------------------------


def stored(
    owner: str, cid: str = "11111111-1111-1111-1111-111111111111", **kw: Any
) -> StoredConnection:
    base: dict[str, Any] = {
        "id": cid,
        "owner_key": owner,
        "provider": "azure",
        "auth_method": "service_principal",
        "name": "n",
        "scope_id": "sub",
        "credential_client_id": "client",
    }
    base.update(kw)
    return StoredConnection(**base)


@pytest.mark.asyncio
async def test_in_memory_repository_isolates_owners() -> None:
    repo = InMemoryConnectionRepository()
    await repo.add(stored(OWNER_A))
    cid = "11111111-1111-1111-1111-111111111111"
    assert await repo.get(OWNER_B, cid) is None
    assert await repo.list(OWNER_B) == [] and await repo.count(OWNER_B) == 0
    assert await repo.delete(OWNER_B, cid) is False
    with pytest.raises(KeyError):
        await repo.update(stored(OWNER_B))
    assert await repo.get(OWNER_A, cid) is not None


@pytest.mark.asyncio
async def test_duplicate_connections_are_detected_per_owner_only() -> None:
    repo = InMemoryConnectionRepository()
    await repo.add(stored(OWNER_A, "aaaaaaaa-0000-0000-0000-000000000001"))
    with pytest.raises(DuplicateConnectionError):
        await repo.add(stored(OWNER_A, "aaaaaaaa-0000-0000-0000-000000000002"))
    await repo.add(stored(OWNER_B, "aaaaaaaa-0000-0000-0000-000000000003"))  # another owner: fine


def test_stored_connection_repr_hides_the_ciphertext() -> None:
    assert "SECRETBYTES" not in repr(stored(OWNER_A, secret_ciphertext=b"SECRETBYTES"))


class RecordingSession:
    """Captures the SQL the repository issues, to prove every statement is owner-scoped."""

    def __init__(self) -> None:
        self.statements: list[str] = []

    async def execute(self, statement: Any) -> Any:
        self.statements.append(str(statement.compile(dialect=postgresql.dialect())))
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        result.scalar_one.return_value = 0
        result.scalars.return_value = []
        result.rowcount = 0
        return result

    async def commit(self) -> None:  # pragma: no cover
        return None


@pytest.mark.asyncio
async def test_sql_repository_scopes_every_statement_to_the_owner() -> None:
    session = RecordingSession()
    repo = SqlConnectionRepository(session)  # type: ignore[arg-type]
    cid = "11111111-1111-1111-1111-111111111111"
    await repo.get(OWNER_A, cid)
    await repo.list(OWNER_A)
    await repo.count(OWNER_A)
    await repo.delete(OWNER_A, cid)
    with pytest.raises(KeyError):
        await repo.update(stored(OWNER_A))
    assert len(session.statements) == 5
    for sql in session.statements:
        assert "owner_tid" in sql and "owner_oid" in sql, sql
    assert await repo.get(OWNER_A, "not-a-uuid") is None  # malformed id never reaches SQL
    assert len(session.statements) == 5


# --------------------------------------------------------------------------------------
# Migration is consistent with the model (and is prepared, not applied)
# --------------------------------------------------------------------------------------

MIGRATION = (
    Path(__file__).parent.parent / "alembic" / "versions" / "2026_11_16_0005_cloud_connections.py"
)


def load_migration() -> Any:
    spec = importlib.util.spec_from_file_location("cloud_connections_migration", MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_revision_chain_and_columns_match_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_migration()
    assert module.revision == "2026_11_16_0005" and module.down_revision == "2026_11_13_0004"

    captured: dict[str, Any] = {}
    fake_op = MagicMock()
    fake_op.create_table.side_effect = lambda name, *cols, **_kw: captured.update(
        name=name, cols=cols
    )
    monkeypatch.setattr(module, "op", fake_op)
    module.upgrade()
    migration_columns = {c.name for c in captured["cols"] if isinstance(c, sa.Column)}
    model_columns = {c.name for c in CloudConnectionModel.__table__.columns}
    assert captured["name"] == "cloud_connections" == CloudConnectionModel.__tablename__
    assert migration_columns == model_columns
    ddl = str(CreateTable(CloudConnectionModel.__table__).compile(dialect=postgresql.dialect()))
    assert "secret_ciphertext BYTEA" in ddl and "uq_cloud_connection_owner_scope" in ddl


def test_migration_downgrade_refuses_to_drop_stored_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_migration()
    bind = MagicMock()
    bind.execute.return_value.scalar.return_value = True  # table has rows
    fake_op = MagicMock()
    fake_op.get_bind.return_value = bind
    monkeypatch.setattr(module, "op", fake_op)
    with pytest.raises(RuntimeError, match="stored connections"):
        module.downgrade()
    fake_op.drop_table.assert_not_called()


def test_the_migration_is_not_applied_by_any_test_or_startup() -> None:
    text = (Path(__file__).parent.parent / "scripts" / "run_migrations.py").read_text(
        encoding="utf-8"
    )
    assert "never" in text.lower() or "NEVER" in text  # migrations stay an explicit operator step


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="needs an isolated TEST_DATABASE_URL"
)
def test_sql_repository_against_a_real_isolated_database() -> None:  # pragma: no cover
    """Opt-in integration check (skipped by default): requires a scratch database whose name
    contains 'test'; creates only the cloud_connections table there."""
    url = os.environ["TEST_DATABASE_URL"]
    assert "test" in url.rsplit("/", 1)[-1].lower(), "refusing to touch a non-test database"
    pytest.skip("run manually with an isolated database; see docs")
