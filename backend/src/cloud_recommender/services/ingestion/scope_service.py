"""Effective scope enforcement service.

Calculates deterministic effective selected resource IDs from saved configurations.
Enforces scope restrictions server-side before provider API dispatch and before data persistence.
Strict rule: Deselected resources are strictly excluded even if parent has all_children.
"""

from typing import Any
from uuid import UUID

import structlog

from cloud_recommender.schemas.configuration import (
    ResourceConfigurationResponse,
    ScopeType,
    SelectionState,
)
from cloud_recommender.schemas.ingestion import IngestionScope
from cloud_recommender.services.configuration.configuration_service import (
    ConfigurationService,
)

logger = structlog.get_logger(__name__)


class ScopeEnforcementService:
    """Service to calculate and enforce effective resource selection scopes."""

    def __init__(self, configuration_service: ConfigurationService | None = None) -> None:
        self.config_service = configuration_service or ConfigurationService()

    async def calculate_effective_scope(self, connection_id: str) -> IngestionScope:
        """Calculate the exact effective scope for ingestion from the active saved configuration.

        Resolution Rules:
        - Parent with 'all_children' includes child resources, UNLESS explicitly excluded.
        - Child with 'excluded' is strictly omitted, overriding any parent 'all_children'.
        - Individual item with 'included' is retained even if parent container was not selected.
        - Child items under an unselected parent without explicit 'included' are omitted.
        - Databricks workspaces are tracked as first-class workspace identifiers.
        """
        active_config = await self.config_service.get_active_configuration(connection_id)
        if not active_config:
            logger.warning("no_active_configuration_for_scope", connection_id=connection_id)
            return IngestionScope(
                connection_id=connection_id,
                provider="unknown",
                configuration_id=UUID("00000000-0000-0000-0000-000000000000"),
                configuration_version=0,
                effective_resource_ids=[],
                effective_workspace_ids=[],
                subscriptions=[],
                resource_groups=[],
            )

        return self.resolve_scope_from_config(active_config)

    def resolve_scope_from_config(self, config: ResourceConfigurationResponse) -> IngestionScope:
        """Resolve IngestionScope directly from a ResourceConfigurationResponse."""
        explicit_exclusions: set[str] = set()
        explicit_inclusions: set[str] = set()
        parent_all_children: set[str] = set()
        selected_subscriptions: set[str] = set()
        selected_resource_groups: set[str] = set()
        selected_workspaces: set[str] = set()

        all_items = config.scope_items or []

        # Phase 1: Categorize states
        for item in all_items:
            ident = item.scope_identifier
            state = (item.selection_state or "included").lower()
            scope_type = (item.scope_type or "").lower()

            if state == SelectionState.EXCLUDED.value:
                explicit_exclusions.add(ident)
            elif state == SelectionState.ALL_CHILDREN.value:
                parent_all_children.add(ident)
                if scope_type == ScopeType.SUBSCRIPTION.value:
                    selected_subscriptions.add(ident)
                elif scope_type == ScopeType.RESOURCE_GROUP.value:
                    selected_resource_groups.add(ident)
            elif state == SelectionState.INCLUDED.value:
                explicit_inclusions.add(ident)
                if scope_type == ScopeType.SUBSCRIPTION.value:
                    selected_subscriptions.add(ident)
                elif scope_type == ScopeType.RESOURCE_GROUP.value:
                    selected_resource_groups.add(ident)

        # Phase 2: Resolve leaf resources and Databricks workspaces
        effective_resource_ids: list[str] = []

        for item in all_items:
            ident = item.scope_identifier
            parent_id = item.parent_scope_identifier or ""
            scope_type = (item.scope_type or "").lower()

            # Rule: Deselected or explicitly excluded items are strictly excluded
            if ident in explicit_exclusions:
                continue

            # Determine if this item qualifies as a resource or workspace
            is_resource = scope_type in (
                ScopeType.RESOURCE.value,
                ScopeType.DATABRICKS_WORKSPACE.value,
            )

            # Inclusion condition:
            # 1. Explicitly included
            # 2. Parent has 'all_children'
            included = False
            if ident in explicit_inclusions:
                included = True
            elif parent_id and parent_id in parent_all_children:
                included = True

            if included and is_resource:
                if ident not in effective_resource_ids:
                    effective_resource_ids.append(ident)
                if scope_type == ScopeType.DATABRICKS_WORKSPACE.value:
                    selected_workspaces.add(ident)

        logger.info(
            "effective_scope_calculated",
            connection_id=config.connection_id,
            configuration_version=config.configuration_version,
            effective_resources=len(effective_resource_ids),
            effective_workspaces=len(selected_workspaces),
        )

        return IngestionScope(
            connection_id=config.connection_id,
            provider=config.provider.lower(),
            configuration_id=config.configuration_id,
            configuration_version=config.configuration_version,
            effective_resource_ids=effective_resource_ids,
            effective_workspace_ids=sorted(selected_workspaces),
            subscriptions=sorted(selected_subscriptions),
            resource_groups=sorted(selected_resource_groups),
        )

    @staticmethod
    def is_resource_in_scope(resource_id: str, scope: IngestionScope) -> bool:
        """Server-side check: verify if a given resource ID is admitted in the effective scope."""
        target = resource_id.lower().strip()
        for admitted in scope.effective_resource_ids:
            if admitted.lower().strip() == target:
                return True
        return False

    @staticmethod
    def filter_records_by_scope(
        records: list[dict[str, Any]],
        resource_id_field: str,
        scope: IngestionScope,
    ) -> list[dict[str, Any]]:
        """Server-side filter: strictly drop any extracted record outside the effective scope."""
        admitted_set = {r.lower().strip() for r in scope.effective_resource_ids}
        filtered: list[dict[str, Any]] = []
        for rec in records:
            res_id = str(rec.get(resource_id_field, "")).lower().strip()
            if res_id in admitted_set:
                filtered.append(rec)
            else:
                logger.debug("record_excluded_outside_scope", resource_id=res_id)
        return filtered
