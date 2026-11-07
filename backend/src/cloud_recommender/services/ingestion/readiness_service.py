"""Ingestion readiness service.

Performs pre-flight validation before starting ingestion runs:
- Verifies connection validity and credentials.
- Verifies saved configuration presence and versioning.
- Calculates effective selected resource IDs.
- Validates provider-specific required scopes and Databricks workspaces.
- Strictly blocks ingestion if any readiness check fails.
"""

from datetime import UTC, datetime

import structlog

from cloud_recommender.schemas.common import CloudProvider
from cloud_recommender.schemas.ingestion import (
    IngestionReadinessResponse,
    IngestionReadinessState,
)
from cloud_recommender.services.configuration.configuration_service import (
    ConfigurationService,
)
from cloud_recommender.services.connections.connection_service import ConnectionService
from cloud_recommender.services.ingestion.scope_service import ScopeEnforcementService

logger = structlog.get_logger(__name__)


class IngestionReadinessService:
    """Pre-flight validation engine for scope-aware ingestion runs."""

    def __init__(
        self,
        config_service: ConfigurationService | None = None,
        scope_service: ScopeEnforcementService | None = None,
        connection_service: ConnectionService | None = None,
    ) -> None:
        self.config_service = config_service or ConfigurationService()
        self.scope_service = scope_service or ScopeEnforcementService(
            configuration_service=self.config_service
        )
        self.connection_service = connection_service or ConnectionService()

    async def validate_readiness(self, connection_id: str) -> IngestionReadinessResponse:
        """Evaluate complete pre-flight ingestion readiness for a given connection."""
        now = datetime.now(UTC)

        # 1. Saved configuration check
        active_config = await self.config_service.get_active_configuration(connection_id)
        if not active_config:
            logger.info("readiness_check_not_configured", connection_id=connection_id)
            return IngestionReadinessResponse(
                connection_id=connection_id,
                provider="unknown",
                readiness_state=IngestionReadinessState.NOT_CONFIGURED,
                can_start_ingestion=False,
                has_configuration=False,
                details=(
                    f"No active resource configuration found for connection '{connection_id}'. "
                    "Discover resources and save a configuration scope before starting ingestion."
                ),
                missing_requirements=["saved_configuration"],
                checked_at=now,
            )

        provider = active_config.provider.lower()

        # 2. Configuration version and integrity check
        if active_config.configuration_version < 1 or not active_config.scope_items:
            return IngestionReadinessResponse(
                connection_id=connection_id,
                provider=provider,
                readiness_state=IngestionReadinessState.CONFIGURATION_INVALID,
                can_start_ingestion=False,
                has_configuration=True,
                configuration_id=active_config.configuration_id,
                configuration_version=active_config.configuration_version,
                details="Configuration version is invalid or contains an empty scope item set.",
                missing_requirements=["valid_configuration_version", "scope_items"],
                checked_at=now,
            )

        # 3. Provider-specific unsupported check (e.g. AWS)
        if provider == "aws":
            return IngestionReadinessResponse(
                connection_id=connection_id,
                provider=provider,
                readiness_state=IngestionReadinessState.CONNECTION_ERROR,
                can_start_ingestion=False,
                has_configuration=True,
                configuration_id=active_config.configuration_id,
                configuration_version=active_config.configuration_version,
                details="AWS provider integration is not configured in this deployment.",
                missing_requirements=["aws_provider_support"],
                checked_at=now,
            )

        # 4. Effective scope calculation
        scope = self.scope_service.resolve_scope_from_config(active_config)
        selected_count = len(scope.effective_resource_ids)
        selected_workspaces_count = len(scope.effective_workspace_ids)

        if selected_count == 0:
            logger.info("readiness_check_no_resources_selected", connection_id=connection_id)
            return IngestionReadinessResponse(
                connection_id=connection_id,
                provider=provider,
                readiness_state=IngestionReadinessState.NO_RESOURCES_SELECTED,
                can_start_ingestion=False,
                has_configuration=True,
                configuration_id=active_config.configuration_id,
                configuration_version=active_config.configuration_version,
                selected_resource_count=0,
                selected_workspace_count=0,
                effective_resource_ids=[],
                effective_workspace_ids=[],
                details=(
                    f"Configuration revision v{active_config.configuration_version} has 0 effective resources selected. "
                    "Select at least one resource, resource group, or Databricks workspace to ingest."
                ),
                missing_requirements=["selected_resources"],
                checked_at=now,
            )

        # 5. Connection and permission validation
        provider_enum = (
            CloudProvider.AZURE
            if provider == "azure"
            else (CloudProvider.GCP if provider == "gcp" else CloudProvider.AWS)
        )
        primary_scope_id = (
            scope.subscriptions[0].split("/")[-1]
            if scope.subscriptions
            else connection_id.replace("azure-", "").replace("gcp-", "")
        )

        conn_validation = await self.connection_service.validate_connection(
            provider=provider_enum,
            scope_id=primary_scope_id,
            connection_id=connection_id,
        )
        if conn_validation.status == "permission_denied":
            return IngestionReadinessResponse(
                connection_id=connection_id,
                provider=provider,
                readiness_state=IngestionReadinessState.PERMISSION_DENIED,
                can_start_ingestion=False,
                has_configuration=True,
                configuration_id=active_config.configuration_id,
                configuration_version=active_config.configuration_version,
                selected_resource_count=selected_count,
                selected_workspace_count=selected_workspaces_count,
                effective_resource_ids=scope.effective_resource_ids,
                effective_workspace_ids=scope.effective_workspace_ids,
                details=(
                    f"Cloud permission check failed: {conn_validation.details}. "
                    "Ensure service principal or credentials have 'Reader' and 'Cost Management Reader' roles."
                ),
                missing_requirements=["azure_reader_role", "cost_management_reader_role"],
                checked_at=now,
            )

        # If live connection auth failed on a custom live connection
        if (
            not conn_validation.success
            and conn_validation.status == "auth_failed"
            and conn_validation.is_live
        ):
            return IngestionReadinessResponse(
                connection_id=connection_id,
                provider=provider,
                readiness_state=IngestionReadinessState.CONNECTION_ERROR,
                can_start_ingestion=False,
                has_configuration=True,
                configuration_id=active_config.configuration_id,
                configuration_version=active_config.configuration_version,
                selected_resource_count=selected_count,
                selected_workspace_count=selected_workspaces_count,
                effective_resource_ids=scope.effective_resource_ids,
                effective_workspace_ids=scope.effective_workspace_ids,
                details=f"Connection authentication probe failed: {conn_validation.details}",
                missing_requirements=["valid_credentials"],
                checked_at=now,
            )

        # 6. All pre-flight checks passed -> READY
        logger.info(
            "readiness_check_ready",
            connection_id=connection_id,
            version=active_config.configuration_version,
            resources=selected_count,
            workspaces=selected_workspaces_count,
        )
        return IngestionReadinessResponse(
            connection_id=connection_id,
            provider=provider,
            readiness_state=IngestionReadinessState.READY,
            can_start_ingestion=True,
            has_configuration=True,
            configuration_id=active_config.configuration_id,
            configuration_version=active_config.configuration_version,
            selected_resource_count=selected_count,
            selected_workspace_count=selected_workspaces_count,
            effective_resource_ids=scope.effective_resource_ids,
            effective_workspace_ids=scope.effective_workspace_ids,
            details=(
                f"Ready for scope-aware ingestion. Configuration v{active_config.configuration_version} "
                f"has {selected_count} resources and {selected_workspaces_count} Databricks workspaces in scope."
            ),
            missing_requirements=[],
            checked_at=now,
        )
