"""Repository for ResourceConfiguration and ConfiguredScopeItems persistence.

Provides atomic versioned persistence, active configuration retrieval,
and scope item management for multi-cloud resource selection.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from cloud_recommender.db.models import (
    ConfiguredScopeItemModel,
    ResourceConfigurationModel,
)
from cloud_recommender.schemas.configuration import ConfiguredScopeItemCreate


class ResourceConfigurationRepository:
    """Async repository for resource configuration versioning and scope persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_active_configuration(
        self, connection_id: str
    ) -> ResourceConfigurationModel | None:
        """Retrieve the currently active resource configuration for a connection."""
        stmt = (
            select(ResourceConfigurationModel)
            .options(selectinload(ResourceConfigurationModel.scope_items))
            .where(
                ResourceConfigurationModel.connection_id == connection_id,
                ResourceConfigurationModel.active_status == "active",
            )
            .order_by(ResourceConfigurationModel.configuration_version.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_id(self, configuration_id: UUID) -> ResourceConfigurationModel | None:
        """Retrieve a specific configuration version by its primary UUID."""
        stmt = (
            select(ResourceConfigurationModel)
            .options(selectinload(ResourceConfigurationModel.scope_items))
            .where(ResourceConfigurationModel.configuration_id == configuration_id)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_versions(self, connection_id: str) -> Sequence[ResourceConfigurationModel]:
        """List all configuration revisions for an onboarding connection."""
        stmt = (
            select(ResourceConfigurationModel)
            .options(selectinload(ResourceConfigurationModel.scope_items))
            .where(ResourceConfigurationModel.connection_id == connection_id)
            .order_by(ResourceConfigurationModel.configuration_version.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def save_configuration(
        self,
        connection_id: str,
        provider: str,
        scope_items: list[ConfiguredScopeItemCreate],
        created_by: str = "system",
    ) -> ResourceConfigurationModel:
        """Atomically create a new configuration version and archive previous active ones."""
        # 1. Determine next version number
        ver_stmt = select(
            func.coalesce(func.max(ResourceConfigurationModel.configuration_version), 0)
        ).where(ResourceConfigurationModel.connection_id == connection_id)
        ver_result = await self.session.execute(ver_stmt)
        current_max = ver_result.scalar_one() or 0
        new_version = current_max + 1

        # 2. Archive existing active configurations for this connection
        archive_stmt = (
            update(ResourceConfigurationModel)
            .where(
                ResourceConfigurationModel.connection_id == connection_id,
                ResourceConfigurationModel.active_status == "active",
            )
            .values(
                active_status="archived",
                updated_at=datetime.now(UTC),
            )
        )
        await self.session.execute(archive_stmt)

        # 3. Create new configuration entity
        config_id = uuid4()
        config_model = ResourceConfigurationModel(
            configuration_id=config_id,
            connection_id=connection_id,
            provider=provider.lower(),
            configuration_version=new_version,
            active_status="active",
            created_by=created_by,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # 4. Create child scope items
        items_to_add: list[ConfiguredScopeItemModel] = []
        for item in scope_items:
            item_model = ConfiguredScopeItemModel(
                item_id=uuid4(),
                configuration_id=config_id,
                scope_type=item.scope_type.lower(),
                scope_identifier=item.scope_identifier,
                parent_scope_identifier=item.parent_scope_identifier,
                display_name=item.display_name,
                resource_type=item.resource_type,
                region=item.region,
                selection_state=item.selection_state,
                metadata_json=item.metadata,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            items_to_add.append(item_model)

        config_model.scope_items = items_to_add
        self.session.add(config_model)
        await self.session.commit()
        await self.session.refresh(config_model)
        return config_model
