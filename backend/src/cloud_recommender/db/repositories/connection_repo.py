"""Owner-scoped persistence for cloud connections.

Every operation takes the ``owner_key`` (``"<tid>:<oid>"`` derived from the validated token) and
only ever touches rows of that owner: there is no API to read or modify another owner's row.
Two interchangeable implementations share one protocol:

- ``SqlConnectionRepository``: PostgreSQL (``cloud_connections``), the persistent store.
- ``InMemoryConnectionRepository``: process-local, NOT persistent; development/testing only.
"""

import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cloud_recommender.db.models import CloudConnectionModel


class DuplicateConnectionError(Exception):
    """A connection for the same owner/provider/scope/client already exists."""


def split_owner(owner_key: str) -> tuple[str, str]:
    tid, _, oid = owner_key.partition(":")
    return tid, oid


@dataclass
class StoredConnection:
    """Persistence-layer view of a connection (includes the ciphertext, never the plaintext)."""

    id: str
    owner_key: str
    provider: str
    auth_method: str
    name: str
    scope_id: str
    credential_tenant_id: str | None = None
    credential_client_id: str | None = None
    secret_ciphertext: bytes | None = field(default=None, repr=False)
    secret_kid: str | None = None
    integration_config: dict[str, Any] = field(default_factory=dict)
    last_validation: dict[str, Any] | None = None
    status: str = "connected"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_validated_at: datetime | None = None


class ConnectionRepository(Protocol):
    async def add(self, record: StoredConnection) -> StoredConnection: ...
    async def get(self, owner_key: str, connection_id: str) -> StoredConnection | None: ...
    async def list(self, owner_key: str) -> list[StoredConnection]: ...
    async def count(self, owner_key: str) -> int: ...
    async def update(self, record: StoredConnection) -> StoredConnection: ...
    async def delete(self, owner_key: str, connection_id: str) -> bool: ...


def _to_record(row: CloudConnectionModel) -> StoredConnection:
    return StoredConnection(
        id=str(row.id),
        owner_key=f"{row.owner_tid}:{row.owner_oid}",
        provider=row.provider,
        auth_method=row.auth_method,
        name=row.name,
        scope_id=row.scope_id,
        credential_tenant_id=row.credential_tenant_id,
        credential_client_id=row.credential_client_id,
        secret_ciphertext=row.secret_ciphertext,
        secret_kid=row.secret_kid,
        integration_config=dict(row.integration_config or {}),
        last_validation=row.last_validation,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
        last_validated_at=row.last_validated_at,
    )


def _uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


class SqlConnectionRepository:
    """PostgreSQL implementation; each call commits its own transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _owned(self, owner_key: str) -> tuple[Any, ...]:
        tid, oid = split_owner(owner_key)
        return (CloudConnectionModel.owner_tid == tid, CloudConnectionModel.owner_oid == oid)

    async def add(self, record: StoredConnection) -> StoredConnection:
        tid, oid = split_owner(record.owner_key)
        row = CloudConnectionModel(
            id=uuid.UUID(record.id),
            owner_tid=tid,
            owner_oid=oid,
            provider=record.provider,
            auth_method=record.auth_method,
            name=record.name,
            scope_id=record.scope_id,
            credential_tenant_id=record.credential_tenant_id,
            credential_client_id=record.credential_client_id,
            secret_ciphertext=record.secret_ciphertext,
            secret_kid=record.secret_kid,
            integration_config=record.integration_config,
            last_validation=record.last_validation,
            status=record.status,
            last_validated_at=record.last_validated_at,
        )
        self._session.add(row)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise DuplicateConnectionError from exc
        await self._session.refresh(row)
        return _to_record(row)

    async def get(self, owner_key: str, connection_id: str) -> StoredConnection | None:
        parsed = _uuid(connection_id)
        if parsed is None:
            return None
        result = await self._session.execute(
            select(CloudConnectionModel).where(
                CloudConnectionModel.id == parsed, *self._owned(owner_key)
            )
        )
        row = result.scalar_one_or_none()
        return _to_record(row) if row else None

    async def list(self, owner_key: str) -> list[StoredConnection]:
        result = await self._session.execute(
            select(CloudConnectionModel)
            .where(*self._owned(owner_key))
            .order_by(CloudConnectionModel.created_at)
        )
        return [_to_record(r) for r in result.scalars()]

    async def count(self, owner_key: str) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(CloudConnectionModel).where(*self._owned(owner_key))
        )
        return int(result.scalar_one())

    async def update(self, record: StoredConnection) -> StoredConnection:
        parsed = _uuid(record.id)
        result = await self._session.execute(
            select(CloudConnectionModel).where(
                CloudConnectionModel.id == parsed, *self._owned(record.owner_key)
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise KeyError(record.id)
        for attr in (
            "name",
            "auth_method",
            "scope_id",
            "credential_tenant_id",
            "credential_client_id",
            "secret_ciphertext",
            "secret_kid",
            "integration_config",
            "last_validation",
            "status",
            "last_validated_at",
        ):
            setattr(row, attr, getattr(record, attr))
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise DuplicateConnectionError from exc
        await self._session.refresh(row)
        return _to_record(row)

    async def delete(self, owner_key: str, connection_id: str) -> bool:
        parsed = _uuid(connection_id)
        if parsed is None:
            return False
        result = await self._session.execute(
            delete(CloudConnectionModel).where(
                CloudConnectionModel.id == parsed, *self._owned(owner_key)
            )
        )
        await self._session.commit()
        return bool(getattr(result, "rowcount", 0))


class InMemoryConnectionRepository:
    """Non-persistent store for development/testing (selected with CONNECTION_STORE=memory)."""

    def __init__(self) -> None:
        self._rows: dict[str, StoredConnection] = {}

    @staticmethod
    def _identity(r: StoredConnection) -> tuple[str, str, str, str | None]:
        return (r.owner_key, r.provider, r.scope_id, r.credential_client_id)

    async def add(self, record: StoredConnection) -> StoredConnection:
        if any(self._identity(r) == self._identity(record) for r in self._rows.values()):
            raise DuplicateConnectionError
        self._rows[record.id] = replace(record)
        return replace(record)

    async def get(self, owner_key: str, connection_id: str) -> StoredConnection | None:
        row = self._rows.get(connection_id)
        return replace(row) if row and row.owner_key == owner_key else None

    async def list(self, owner_key: str) -> list[StoredConnection]:
        return [replace(r) for r in self._rows.values() if r.owner_key == owner_key]

    async def count(self, owner_key: str) -> int:
        return sum(1 for r in self._rows.values() if r.owner_key == owner_key)

    async def update(self, record: StoredConnection) -> StoredConnection:
        current = self._rows.get(record.id)
        if current is None or current.owner_key != record.owner_key:
            raise KeyError(record.id)
        record.updated_at = datetime.now(UTC)
        self._rows[record.id] = replace(record)
        return replace(record)

    async def delete(self, owner_key: str, connection_id: str) -> bool:
        row = self._rows.get(connection_id)
        if row is None or row.owner_key != owner_key:
            return False
        del self._rows[connection_id]
        return True

    def clear(self) -> None:
        self._rows.clear()


# Process-wide instance used when CONNECTION_STORE=memory (development/testing only).
in_memory_connection_repository = InMemoryConnectionRepository()
