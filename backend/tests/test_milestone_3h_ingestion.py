"""Milestone 3H Test Suite — Live Databricks Financial Ingestion & Warehouse Gate.

Verifies:
1. Environment-driven SQL service initialization, configuration, and credential redaction.
2. Warehouse stopped check (`check_warehouse_status`) returning WAREHOUSE_STOPPED without SQL execution.
3. Read-only statement validator rejecting SQL mutations (INSERT, UPDATE, DELETE, DROP, etc.).
4. Strict approval gate enforcement (raising ApprovalRequiredError and returning 8-point approval payload).
5. Billing usage ingestion: idempotency by record_id, negative usage preservation for retractions,
   and strict unit separation (DBU, BYTE_HOURS, TOKEN_COUNT).
6. Deterministic pricing rate card matching with date validity intervals and unmatched handling.
7. Exact resource scope attribution and rejection of unknown IDs with NO_DATA.
8. Complete REST API contract validation for all 9 /api/v1/finops/ endpoints.
"""

import pytest

from cloud_recommender.api.routes.finops import (
    execute_ingestion_run,
    get_billing_pricing,
    get_billing_reconciliation,
    get_billing_summary,
    get_billing_usage,
    get_ingestion_runs,
    get_ingestion_status,
    preview_ingestion,
    validate_ingestion,
)
from cloud_recommender.schemas.billing_ingestion import (
    BillingUsageRecord,
    IngestionRunCreateRequest,
)
from cloud_recommender.services.databricks.billing_ingestion_service import (
    BillingIngestionService,
)
from cloud_recommender.services.databricks.sql_client import (
    ApprovalRequiredError,
    DatabricksSqlService,
    MutationProhibitedError,
)
from tests.fixtures.billing_baseline import load_baseline_usage


@pytest.fixture
def sql_service() -> DatabricksSqlService:
    return DatabricksSqlService(
        host="https://adb-642006393507276.16.azuredatabricks.net",
        warehouse_id="05ed10a52697a344",
        auth_type="mock",
        profile="azure-dev",
    )


@pytest.fixture
def ingestion_service(sql_service: DatabricksSqlService) -> BillingIngestionService:
    svc = BillingIngestionService(sql_service=sql_service)
    load_baseline_usage(svc)  # synthetic TEST-ONLY rows; the application never seeds usage
    return svc


# =============================================================================
# 1. SQL Service Configuration, Redaction & Security Validation
# =============================================================================


def test_sql_service_credential_redaction() -> None:
    """Verify that sensitive client credentials are redacted in string/repr outputs."""
    service_with_secret = DatabricksSqlService(
        host="https://adb-642006393507276.16.azuredatabricks.net",
        warehouse_id="05ed10a52697a344",
        client_secret="super-secret-databricks-key-999",
    )
    repr_str = repr(service_with_secret)
    assert "super-secret" not in repr_str
    assert "REDACTED" in repr_str or "client_secret" in repr_str
    assert repr_str.startswith("<DatabricksSqlService")


def test_read_only_statement_validation(sql_service: DatabricksSqlService) -> None:
    """Verify that pure read queries pass and any mutation statements are rejected."""
    # Valid read queries
    sql_service.validate_read_only_statement("SELECT * FROM system.billing.usage LIMIT 10")
    sql_service.validate_read_only_statement(
        "WITH aggregated AS (SELECT sku_name, SUM(usage_quantity) FROM system.billing.usage GROUP BY sku_name) SELECT * FROM aggregated"
    )

    # Prohibited mutations
    prohibited = [
        "INSERT INTO system.billing.usage VALUES ('1')",
        "UPDATE system.billing.usage SET usage_quantity = 0",
        "DELETE FROM system.billing.usage WHERE record_id = '1'",
        "DROP TABLE system.billing.usage",
        "TRUNCATE TABLE system.billing.usage",
        "ALTER TABLE system.billing.usage ADD COLUMN x INT",
        "CREATE TABLE fake_table (id INT)",
        "GRANT SELECT ON system.billing.usage TO `user`",
    ]
    for mutation_sql in prohibited:
        with pytest.raises(MutationProhibitedError):
            sql_service.validate_read_only_statement(mutation_sql)

    # Hardened security: multiple statements, comments, unsafe functions, and table allowlists
    hardened_attacks = [
        "SELECT * FROM system.billing.usage; DROP TABLE system.billing.usage;",
        "SELECT * FROM system.billing.usage /* comment */ ; SELECT 1",
        "SELECT secret('app-scope', 'db-key') FROM system.billing.usage",
        "SELECT * FROM system.forbidden_schema.sensitive_table",
    ]
    for attack in hardened_attacks:
        with pytest.raises(MutationProhibitedError):
            sql_service.validate_read_only_statement(attack)


def test_hmac_approval_token_and_replay_prevention(sql_service: DatabricksSqlService) -> None:
    """Verify cryptographic HMAC token verification, expiration, and server-side replay prevention."""
    valid_query = "SELECT * FROM system.billing.usage LIMIT 10"
    token = sql_service.issue_approval_token(
        query=valid_query,
        warehouse_id=sql_service.warehouse_id,
        start_date="2026-10-01",
        end_date="2026-11-04",
        ttl_seconds=300,
        approver_roles=["FinOpsAdministrator"],
    )

    # 1. Valid token verification passes
    assert sql_service.verify_approval_token(token, valid_query, sql_service.warehouse_id) is True

    # 2. Tampered query fails
    tampered_query = "SELECT * FROM system.billing.usage LIMIT 999"
    assert (
        sql_service.verify_approval_token(token, tampered_query, sql_service.warehouse_id) is False
    )

    # 3. Tampered warehouse fails
    assert sql_service.verify_approval_token(token, valid_query, "fake-warehouse-999") is False

    # 4. Expired token fails
    expired_token = sql_service.issue_approval_token(
        query=valid_query,
        warehouse_id=sql_service.warehouse_id,
        ttl_seconds=-10,  # Already expired
        approver_roles=["FinOpsAdministrator"],
    )
    assert (
        sql_service.verify_approval_token(expired_token, valid_query, sql_service.warehouse_id)
        is False
    )

    # 5. Token consumption and replay prevention
    # Consume token
    sql_service._consumed_tokens.add(token)
    # Immediate replay must fail
    assert sql_service.verify_approval_token(token, valid_query, sql_service.warehouse_id) is False


# =============================================================================
# 2. Warehouse State & Approval Gate Enforcement
# =============================================================================


def test_warehouse_stopped_check(sql_service: DatabricksSqlService) -> None:
    """Verify check_warehouse_status identifies STOPPED state without executing queries."""
    health = sql_service.check_warehouse_status()
    assert health.status == "WAREHOUSE_STOPPED"
    assert health.warehouse_id == "05ed10a52697a344"
    assert health.can_execute is False
    assert "Zero-execution policy" in health.message


def test_approval_gate_enforcement(sql_service: DatabricksSqlService) -> None:
    """Verify execute_read_only_statement raises ApprovalRequiredError without approval."""
    with pytest.raises(ApprovalRequiredError) as exc_info:
        sql_service.execute_read_only_statement(
            "SELECT * FROM system.billing.usage",
            is_approved=False,
        )

    approval_payload = exc_info.value.approval_request
    assert approval_payload is not None
    assert approval_payload["warehouse_id"] == "05ed10a52697a344"
    assert approval_payload["status"] == "STOPPED"
    assert "explicit_approval_required" in approval_payload

    # Verify all 8 mandatory approval points
    points = approval_payload["explicit_approval_required"]
    assert "action" in points
    assert "target_compute" in points
    assert "state_transition" in points
    assert "auto_stop_configured" in points
    assert "estimated_cost" in points
    assert "data_mutation" in points
    assert "rollback_procedure" in points
    assert "local_fixture_fallback" in points


# =============================================================================
# 3. Billing Ingestion Unit Separation, Deduplication & Retractions
# =============================================================================


def test_idempotent_deduplication(
    ingestion_service: BillingIngestionService,
) -> None:
    """Verify that ingesting identical records does not inflate count or financial totals."""
    initial_records = ingestion_service.list_usage_records()
    assert len(initial_records) == 11

    # Duplicate an existing canonical record
    dup_record = BillingUsageRecord(
        record_id="rec-usage-sql-01",
        workspace_id="642006393507276",
        sku_name="SERVERLESS_SQL_COMPUTE",
        cloud="azure",
        usage_start_time="2026-11-01T00:00:00Z",
        usage_end_time="2026-11-01T23:59:59Z",
        usage_date="2026-11-01",
        usage_unit="DBU",
        usage_quantity=4793.0,
        record_type="original",
    )

    stats = ingestion_service.ingest_records([dup_record])
    assert stats["extracted_count"] == 1
    assert stats["inserted_count"] == 0
    assert stats["duplicate_count"] == 1

    # Total stored records remains unchanged
    records_after = ingestion_service.list_usage_records()
    assert len(records_after) == 11


def test_retraction_preservation(
    ingestion_service: BillingIngestionService,
) -> None:
    """Verify negative usage quantities are preserved as retractions and reduce net DBU."""
    # Ingest a retraction record
    retraction_rec = BillingUsageRecord(
        record_id="rec-retraction-test-01",
        workspace_id="642006393507276",
        sku_name="SERVERLESS_SQL_COMPUTE",
        cloud="azure",
        usage_start_time="2026-11-01T00:00:00Z",
        usage_end_time="2026-11-01T23:59:59Z",
        usage_date="2026-11-01",
        usage_unit="DBU",
        usage_quantity=-20.0,
        record_type="retraction",
    )
    ingestion_service.ingest_records([retraction_rec])

    records = ingestion_service.list_usage_records()
    retractions = [r for r in records if r.usage_quantity < 0]
    assert len(retractions) == 1
    assert retractions[0].record_type == "retraction"
    assert retractions[0].usage_quantity == -20.0
    assert retractions[0].effective_cost == -44.0

    summary = ingestion_service.get_billing_summary()
    assert summary.retraction_dbu == 20.0
    assert summary.total_dbu == 88420.0
    assert summary.net_dbu == 88400.0


def test_strict_unit_separation(
    ingestion_service: BillingIngestionService,
) -> None:
    """Verify strict unit separation: non-DBU units are not conflated with DBU pricing."""
    records = ingestion_service.list_usage_records()
    dbu_records = [r for r in records if r.usage_unit == "DBU"]
    assert len(dbu_records) == len(records)
    assert all(r.usage_unit == "DBU" for r in dbu_records)

    # Ingest a BYTE_HOURS storage metric
    storage_rec = BillingUsageRecord(
        record_id="STORAGE-TEST-001",
        workspace_id="642006393507276",
        sku_name="DELTA_STORAGE",
        cloud="azure",
        usage_start_time="2026-11-01T00:00:00Z",
        usage_end_time="2026-11-01T01:00:00Z",
        usage_date="2026-11-01",
        usage_unit="BYTE_HOURS",
        usage_quantity=10000000.0,
        record_type="original",
    )
    ingestion_service.ingest_records([storage_rec])

    # Storage record has no DBU price match
    updated_records = ingestion_service.list_usage_records()
    stored = next(r for r in updated_records if r.record_id == "STORAGE-TEST-001")
    assert stored.usage_unit == "BYTE_HOURS"
    assert stored.pricing_matched is False
    assert stored.effective_cost is None


# =============================================================================
# 4. Pricing Matching & Mathematical Reconciliation Engine
# =============================================================================


def test_pricing_rate_card_matching(
    ingestion_service: BillingIngestionService,
) -> None:
    """Verify list price validity interval matching and cost calculation."""
    price_records = ingestion_service.list_price_records()
    assert len(price_records) >= 4

    sql_rate = next(p for p in price_records if p.sku_name == "SERVERLESS_SQL_COMPUTE")
    assert sql_rate.price_per_unit == 2.20

    summary = ingestion_service.get_billing_summary()
    assert summary.matched_pricing_count == 11
    assert summary.total_spend_verified == 168834.25


def test_mathematical_reconciliation(
    ingestion_service: BillingIngestionService,
) -> None:
    """Verify gross, retraction, and net cost reconciliation matches to 2 decimal places."""
    recon = ingestion_service.get_billing_reconciliation()
    assert recon.reconciliation_status == "RECONCILED"
    assert recon.gross_dbu == 88420.0
    assert recon.retraction_dbu == 0.0
    assert recon.net_dbu == 88420.0
    assert recon.gross_cost == 168834.25
    assert recon.net_cost == 168834.25
    assert recon.unmatched_records_count == 0
    assert len(recon.audit_notes) >= 3


# =============================================================================
# 5. Exact Resource Scope Attribution & Rejection
# =============================================================================


def test_exact_resource_scope_attribution(
    ingestion_service: BillingIngestionService,
) -> None:
    """Verify exact resource ID filtering attributes only genuine associated records."""
    # Warehouse 05ed10a52697a344 has 4 records totaling 19,172 DBU ($42,178.40)
    summary = ingestion_service.get_billing_summary(resource_id="05ed10a52697a344")
    assert summary.resource_id == "05ed10a52697a344"
    assert summary.net_dbu == 19172.0
    assert summary.total_spend_verified == 42178.4
    assert summary.data_status == "INGESTED"


def test_adversarial_unknown_resource_scope(
    ingestion_service: BillingIngestionService,
) -> None:
    """Unknown or heuristic resource IDs return NO_DATA with null (unknown, not zero) DBU."""
    adversarial_ids = [
        "fake-cluster-999",
        "sample1",  # Substring of 1024-080000-sample1 (must be rejected)
        "fake-warehouse-05ed10a52697a344",
        "unknown-guid-00000000",
    ]
    for bad_id in adversarial_ids:
        summary = ingestion_service.get_billing_summary(resource_id=bad_id)
        assert summary.data_status == "NO_DATA"
        assert summary.total_dbu is None
        assert summary.net_dbu is None
        assert summary.total_spend_verified is None


# =============================================================================
# 6. REST API Endpoint Integration Tests
# =============================================================================


def test_api_ingestion_status(ingestion_service: BillingIngestionService) -> None:
    """Verify GET /api/v1/finops/ingestion/status returns comprehensive status."""
    data = get_ingestion_status(workspace_id="642006393507276", service=ingestion_service)
    assert data.warehouse_status == "WAREHOUSE_STOPPED"
    assert data.warehouse_id == "05ed10a52697a344"
    assert data.system_tables_status == "APPROVAL_REQUIRED"
    assert data.total_dbu_consumed == 88420.0


def test_api_ingestion_runs(ingestion_service: BillingIngestionService) -> None:
    """Verify GET /api/v1/finops/ingestion/runs returns run history."""
    data = get_ingestion_runs(workspace_id="642006393507276", service=ingestion_service)
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0].source_table == "system.billing.usage"


def test_api_ingestion_validate(ingestion_service: BillingIngestionService) -> None:
    """Verify POST /api/v1/finops/ingestion/validate returns readiness diagnosis."""
    data = validate_ingestion(workspace_id="642006393507276", service=ingestion_service)
    assert data.valid is True
    assert data.warehouse_state == "STOPPED"
    assert len(data.diagnostic_messages) >= 3


def test_api_ingestion_preview(ingestion_service: BillingIngestionService) -> None:
    """Verify POST /api/v1/finops/ingestion/preview previews records without starting compute."""
    data = preview_ingestion(workspace_id="642006393507276", limit=5, service=ingestion_service)
    assert data.status == "PREVIEW_READY"
    assert len(data.preview_records) == 5
    assert data.preview_records[0].workspace_id == "642006393507276"


def test_api_ingestion_run_gated(ingestion_service: BillingIngestionService) -> None:
    """Verify POST /api/v1/finops/ingestion/run returns approval_required without approval."""
    req = IngestionRunCreateRequest(is_approved=False)
    data = execute_ingestion_run(request=req, service=ingestion_service)
    assert data.status == "approval_required"
    assert data.approval_request is not None
    assert "explicit_approval_required" in data.approval_request


def test_api_billing_summary(ingestion_service: BillingIngestionService) -> None:
    """Verify GET /api/v1/finops/billing/summary returns verified baseline figures."""
    data = get_billing_summary(workspace_id="642006393507276", service=ingestion_service)
    assert data.total_dbu == 88420.0
    assert data.net_dbu == 88420.0
    assert data.total_spend_verified == 168834.25
    assert data.currency == "USD"
    assert len(data.dbu_by_product) >= 3


def test_api_billing_usage(ingestion_service: BillingIngestionService) -> None:
    """Verify GET /api/v1/finops/billing/usage returns paginated usage records."""
    data = get_billing_usage(workspace_id="642006393507276", limit=10, service=ingestion_service)
    assert isinstance(data, list)
    assert len(data) == 10
    assert data[0].usage_unit == "DBU"


def test_api_billing_pricing(ingestion_service: BillingIngestionService) -> None:
    """Verify GET /api/v1/finops/billing/pricing returns published price records."""
    data = get_billing_pricing(service=ingestion_service)
    assert isinstance(data, list)
    assert len(data) >= 4
    assert any(p.sku_name == "SERVERLESS_SQL_COMPUTE" for p in data)


def test_api_billing_reconciliation(ingestion_service: BillingIngestionService) -> None:
    """Verify GET /api/v1/finops/billing/reconciliation returns reconciled ledger."""
    data = get_billing_reconciliation(workspace_id="642006393507276", service=ingestion_service)
    assert data.reconciliation_status == "RECONCILED"
    assert data.net_cost == 168834.25
    assert data.net_dbu == 88420.0
    assert data.retraction_dbu == 0.0
    assert data.usage_record_count == 11
