"""Milestone 3J.2 Test Suite — Final Hardening, RBAC, Fail-Closed SQL & Durable Tokens.

Verifies:
1. Role-based token issuance (Admin, FinOpsAdministrator, PlatformAdministrator vs. unauthorized roles).
2. Fail-closed SQL validation:
   - Strict allowlist: only system.billing.usage and system.billing.list_prices.
   - Comments rejection (-- and /* */).
   - Semicolons rejection (;).
   - Prohibited DDL/DML and unsafe reflection functions.
3. Durable database-backed approval token persistence and cross-restart replay prevention.
4. Zero-execution decoupling: warehouse startup is completely separated from ingestion execution.
5. REST API contract for POST /api/v1/finops/ingestion/approval-token.
"""

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from cloud_recommender.api.routes.finops import issue_approval_token
from cloud_recommender.db.models import Base, BillingApprovalTokenModel
from cloud_recommender.schemas.billing_ingestion import (
    BillingApprovalTokenRequest,
    IngestionRunCreateRequest,
)
from cloud_recommender.services.databricks.billing_ingestion_service import (
    BillingIngestionService,
)
from cloud_recommender.services.databricks.sql_client import (
    DatabricksSqlService,
    MutationProhibitedError,
)


@pytest.fixture
def sql_service() -> DatabricksSqlService:
    return DatabricksSqlService(
        host="https://adb-642006393507276.16.azuredatabricks.net",
        warehouse_id="05ed10a52697a344",
        auth_type="mock",
        profile="azure-dev",
    )


@pytest.fixture
def sqlite_session() -> Generator[Session, None, None]:
    """In-memory SQLite session with tables for testing durable token persistence."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


# =============================================================================
# 1. Role-Based Token Issuance (RBAC)
# =============================================================================


def test_rbac_token_issuance_allowed_roles(sql_service: DatabricksSqlService) -> None:
    """Verify that FinOpsAdministrator, Admin, and PlatformAdministrator can issue tokens."""
    query = "SELECT record_id FROM system.billing.usage LIMIT 5"

    # 1. FinOpsAdministrator succeeds
    token1 = sql_service.issue_approval_token(
        query=query,
        warehouse_id=sql_service.warehouse_id,
        approver_sub="finops-lead@bizmetric.com",
        approver_roles=["FinOpsAdministrator"],
    )
    assert token1 is not None and (token1.startswith("v2:") or len(token1.split(":")) == 7)

    # 2. Admin succeeds
    token2 = sql_service.issue_approval_token(
        query=query,
        warehouse_id=sql_service.warehouse_id,
        approver_sub="admin@bizmetric.com",
        approver_roles=["Admin"],
    )
    assert token2 is not None

    # 3. PlatformAdministrator succeeds
    token3 = sql_service.issue_approval_token(
        query=query,
        warehouse_id=sql_service.warehouse_id,
        approver_sub="platform-eng@bizmetric.com",
        approver_roles=["PlatformAdministrator"],
    )
    assert token3 is not None


def test_rbac_token_issuance_unauthorized_roles(sql_service: DatabricksSqlService) -> None:
    """Verify that unauthorized roles are rejected with PermissionError."""
    query = "SELECT record_id FROM system.billing.usage LIMIT 5"

    unauthorized_roles = [
        ["Viewer"],
        ["Developer"],
        ["CostViewer"],
        ["Contributor"],
        [],
    ]

    for roles in unauthorized_roles:
        with pytest.raises(PermissionError) as exc_info:
            sql_service.issue_approval_token(
                query=query,
                warehouse_id=sql_service.warehouse_id,
                approver_sub="unauthorized-user@bizmetric.com",
                approver_roles=roles,
            )
        assert "not authorized to issue approval tokens" in str(exc_info.value)


# =============================================================================
# 2. Fail-Closed SQL Validation
# =============================================================================


def test_sql_validation_comment_blocking(sql_service: DatabricksSqlService) -> None:
    """Verify that comments are blocked to prevent comment-hiding evasion."""
    comment_queries = [
        "SELECT * FROM system.billing.usage -- inline comment",
        "-- leading comment\nSELECT * FROM system.billing.usage",
        "SELECT * FROM system.billing.usage /* block comment */",
        "/* multi-line\ncomment */ SELECT * FROM system.billing.usage",
    ]
    for q in comment_queries:
        with pytest.raises(MutationProhibitedError) as exc:
            sql_service.validate_read_only_statement(q)
        assert "Comments ('--' or '/*') are prohibited" in str(exc.value)


def test_sql_validation_semicolon_blocking(sql_service: DatabricksSqlService) -> None:
    """Verify that semicolons are prohibited to prevent chained statement injection."""
    queries_with_semicolon = [
        "SELECT * FROM system.billing.usage;",
        "SELECT * FROM system.billing.usage; SELECT 1",
        "SELECT * FROM system.billing.usage ; DROP TABLE x",
    ]
    for q in queries_with_semicolon:
        with pytest.raises(MutationProhibitedError) as exc:
            sql_service.validate_read_only_statement(q)
        assert "Semicolons are prohibited" in str(exc.value)


def test_sql_validation_system_tables_strict_allowlist(sql_service: DatabricksSqlService) -> None:
    """Verify that ONLY system.billing.usage and system.billing.list_prices are permitted."""
    # Permitted queries
    sql_service.validate_read_only_statement(
        "SELECT * FROM system.billing.usage WHERE usage_date >= '2026-10-01'"
    )
    sql_service.validate_read_only_statement("SELECT * FROM system.billing.list_prices")
    sql_service.validate_read_only_statement(
        "SELECT u.record_id, p.price_per_unit FROM system.billing.usage u "
        "JOIN system.billing.list_prices p ON u.sku_name = p.sku_name"
    )

    # Prohibited tables (previously allowed or arbitrary tables)
    prohibited_tables = [
        "SELECT * FROM system.access.audit",
        "SELECT * FROM system.compute.clusters",
        "SELECT * FROM system.compute.warehouses",
        "SELECT * FROM default.customer_data",
        "SELECT * FROM hive_metastore.sales.orders",
        "SELECT 1",  # No system table referenced
    ]
    for q in prohibited_tables:
        with pytest.raises(MutationProhibitedError):
            sql_service.validate_read_only_statement(q)


def test_sql_validation_unsafe_reflection_functions(sql_service: DatabricksSqlService) -> None:
    """Verify that dangerous introspection and reflection functions are blocked."""
    prohibited_functions = [
        "SELECT CURRENT_USER() FROM system.billing.usage",
        "SELECT USER() FROM system.billing.usage",
        "SELECT SESSION_USER() FROM system.billing.usage",
        "SELECT VERSION() FROM system.billing.usage",
        "SELECT PASSWORD('foo') FROM system.billing.usage",
        "SELECT DBUTILS.fs.ls('/') FROM system.billing.usage",
        "SELECT SECRET('scope', 'key') FROM system.billing.usage",
        "SELECT REFLECT('java.lang.System', 'exit', 0) FROM system.billing.usage",
        "SELECT JAVA_METHOD('java.lang.Runtime', 'getRuntime') FROM system.billing.usage",
        "SELECT INPUT_FILE_NAME() FROM system.billing.usage",
        "SELECT * FROM SYS.TABLES JOIN system.billing.usage ON 1=1",
    ]
    for q in prohibited_functions:
        with pytest.raises(MutationProhibitedError):
            sql_service.validate_read_only_statement(q)


# =============================================================================
# 3. Durable Database-Backed Approval Token Persistence & Replay Prevention
# =============================================================================


def test_durable_token_persistence_and_cross_restart_replay(
    sql_service: DatabricksSqlService, sqlite_session: Session
) -> None:
    """Verify database-backed token issuance, verification, atomic consumption, and cross-restart replay rejection."""
    valid_query = "SELECT record_id FROM system.billing.usage LIMIT 10"

    # 1. Issue token and persist in SQLite
    token = sql_service.issue_approval_token(
        query=valid_query,
        warehouse_id=sql_service.warehouse_id,
        start_date="2026-10-01",
        end_date="2026-11-04",
        ttl_seconds=600,
        approver_sub="finops-admin@bizmetric.com",
        approver_roles=["FinOpsAdministrator"],
        session=sqlite_session,
    )

    # 2. Verify row exists in DB
    db_tokens = sqlite_session.query(BillingApprovalTokenModel).all()
    assert len(db_tokens) == 1
    record = db_tokens[0]
    assert record.approver_sub == "finops-admin@bizmetric.com"
    assert record.is_consumed is False
    assert record.warehouse_id == sql_service.warehouse_id

    # 3. Verify token against DB
    assert (
        sql_service.verify_approval_token(
            token, valid_query, sql_service.warehouse_id, session=sqlite_session
        )
        is True
    )

    # 4. Consume token atomically in DB
    sql_service.consume_approval_token(token, session=sqlite_session)
    sqlite_session.refresh(record)
    assert record.is_consumed is True
    assert record.consumed_at is not None

    # 5. Simulate application server restart:
    # A fresh service instance with an EMPTY in-memory _consumed_tokens set
    fresh_service = DatabricksSqlService(
        host="https://adb-642006393507276.16.azuredatabricks.net",
        warehouse_id="05ed10a52697a344",
        auth_type="mock",
        profile="azure-dev",
    )
    assert len(fresh_service._consumed_tokens) == 0

    # Verification against the database must still REJECT the token as already consumed!
    is_valid = fresh_service.verify_approval_token(
        token, valid_query, fresh_service.warehouse_id, session=sqlite_session
    )
    assert is_valid is False, (
        "Cross-restart replay of consumed token must be rejected via database check!"
    )


# =============================================================================
# 4. Decoupled Compute & Zero-Execution Policy
# =============================================================================


def test_warehouse_startup_decoupled_from_ingestion(sql_service: DatabricksSqlService) -> None:
    """Verify that when the warehouse is STOPPED, ingestion fails cleanly without attempting compute resume."""
    ingestion_service = BillingIngestionService(sql_service=sql_service)

    # Issue a valid approval token
    valid_query = (
        "SELECT * FROM system.billing.usage "
        "WHERE workspace_id = '642006393507276' AND usage_date >= '2026-10-01' "
        "AND usage_date <= '2026-11-04' LIMIT 10"
    )
    token = sql_service.issue_approval_token(
        query=valid_query,
        warehouse_id=sql_service.warehouse_id,
        approver_roles=["FinOpsAdministrator"],
    )

    request = IngestionRunCreateRequest(
        workspace_id="642006393507276",
        start_date="2026-10-01",
        end_date="2026-11-04",
        is_approved=True,
        approval_token=token,
        limit=10,
    )

    # In mock/offline mode with warehouse STOPPED, execution must fail cleanly without starting warehouse
    response = ingestion_service.run_ingestion(request)
    assert response.status == "failed"
    assert "Execution blocked: Target SQL Warehouse 05ed10a52697a344 is STOPPED" in str(
        response.error_message
    )
    assert "Automatic startup is disabled" in str(response.error_message)

    # Verify warehouse state remains STOPPED
    status = sql_service.check_warehouse_status()
    assert status.warehouse_state == "STOPPED"


# =============================================================================
# 5. REST API Approval Token Endpoint
# =============================================================================


def test_approval_token_api_endpoint(sql_service: DatabricksSqlService) -> None:
    """Verify POST /api/v1/finops/ingestion/approval-token behaves according to RBAC."""
    service = BillingIngestionService(sql_service=sql_service)

    # Valid request with FinOpsAdministrator
    valid_req = BillingApprovalTokenRequest(
        query="SELECT * FROM system.billing.usage LIMIT 50",
        warehouse_id="05ed10a52697a344",
        workspace_id="642006393507276",
        approver_sub="lead-operator@bizmetric.com",
        approver_roles=["FinOpsAdministrator"],
        ttl_seconds=300,
    )
    resp = issue_approval_token(valid_req, service=service)
    assert resp.status == "ISSUED"
    assert resp.approver_sub == "lead-operator@bizmetric.com"
    assert resp.query_hash is not None
    assert resp.token is not None

    # Invalid request with unauthorized role -> raises 403
    unauth_req = BillingApprovalTokenRequest(
        query="SELECT * FROM system.billing.usage LIMIT 50",
        approver_sub="analyst@bizmetric.com",
        approver_roles=["Viewer"],
    )
    with pytest.raises(Exception) as exc:
        issue_approval_token(unauth_req, service=service)
    assert "403" in str(exc.value) or "not authorized" in str(exc.value)

    # Unsafe query with comments -> raises 400
    unsafe_req = BillingApprovalTokenRequest(
        query="SELECT * FROM system.billing.usage -- comment",
        approver_sub="lead-operator@bizmetric.com",
        approver_roles=["FinOpsAdministrator"],
    )
    with pytest.raises(Exception) as exc:
        issue_approval_token(unsafe_req, service=service)
    assert "400" in str(exc.value) or "Comments" in str(exc.value)
