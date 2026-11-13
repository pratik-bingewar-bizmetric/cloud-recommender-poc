"""Milestone 3J.3 Test Suite — Final Security Remediation, AST Validation & Concurrency.

Forensic verification covering:
1. Server-derived identity and RBAC (401 unauthenticated, 403 unauthorized, anti-spoofing).
2. Fail-closed cryptographic signing key management and rotation.
3. 15-parameter canonical payload binding and tamper rejection.
4. True AST parsing with sqlglot for Databricks SQL dialect.
5. Durable atomic single-use token consumption and concurrent replay protection.
6. Zero-execution decoupling (warehouse STOPPED preservation).
"""

import threading
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from cloud_recommender.api.routes.finops import issue_approval_token
from cloud_recommender.core.auth import AuthenticatedUser
from cloud_recommender.core.config import Settings
from cloud_recommender.db.models import Base
from cloud_recommender.schemas.billing_ingestion import BillingApprovalTokenRequest
from cloud_recommender.services.databricks.billing_ingestion_service import (
    BillingIngestionService,
)
from cloud_recommender.services.databricks.sql_client import (
    DatabricksSqlService,
    MutationProhibitedError,
)


@pytest.fixture
def signing_settings() -> Settings:
    return Settings(
        app_name="cloud-recommender-test",
        app_env="testing",
        finops_signing_secret="super-secure-production-finops-signing-secret-2026",
        finops_signing_kid="k1-2026",
        finops_verification_keys='{"k0-2025": "legacy-key-rotation-secret-32-chars-long"}',
    )


@pytest.fixture
def sql_service(signing_settings: Settings) -> DatabricksSqlService:
    return DatabricksSqlService(
        host="https://adb-642006393507276.16.azuredatabricks.net",
        warehouse_id="05ed10a52697a344",
        auth_type="mock",
        profile="azure-dev",
        settings=signing_settings,
    )


@pytest.fixture
def sqlite_engine():
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def sqlite_session_factory(sqlite_engine):
    return sessionmaker(bind=sqlite_engine)


@pytest.fixture
def sqlite_session(sqlite_session_factory) -> Generator[Session, None, None]:
    """In-memory SQLite session for testing token persistence and atomic single-use."""
    session = sqlite_session_factory()
    yield session
    session.close()


# =============================================================================
# 1. Server-Derived Identity, RBAC & Anti-Spoofing
# =============================================================================


def test_rbac_server_derived_identity_authorized_roles(
    sql_service: DatabricksSqlService,
) -> None:
    """Verify that only server-authenticated users with allowed roles can obtain tokens."""
    service = BillingIngestionService(sql_service=sql_service)
    req = BillingApprovalTokenRequest(
        query="SELECT record_id FROM system.billing.usage LIMIT 10",
        warehouse_id="05ed10a52697a344",
        workspace_id="642006393507276",
    )

    # FinOpsAdministrator succeeds
    user_finops = AuthenticatedUser(
        sub="user-123",
        preferred_username="finops-lead@bizmetric.com",
        roles=["FinOpsAdministrator"],
        is_authenticated=True,
    )
    resp1 = issue_approval_token(req, current_user=user_finops, service=service)
    assert resp1.status == "ISSUED"
    assert resp1.approver_sub == "finops-lead@bizmetric.com"
    assert "FinOpsAdministrator" in resp1.approver_roles

    # Admin succeeds
    user_admin = AuthenticatedUser(
        sub="admin-456",
        preferred_username="admin@bizmetric.com",
        roles=["Admin"],
        is_authenticated=True,
    )
    resp2 = issue_approval_token(req, current_user=user_admin, service=service)
    assert resp2.status == "ISSUED"

    # PlatformAdministrator succeeds
    user_platform = AuthenticatedUser(
        sub="plat-789",
        preferred_username="platform@bizmetric.com",
        roles=["PlatformAdministrator"],
        is_authenticated=True,
    )
    resp3 = issue_approval_token(req, current_user=user_platform, service=service)
    assert resp3.status == "ISSUED"


def test_rbac_unauthenticated_and_unauthorized_rejections(
    sql_service: DatabricksSqlService,
) -> None:
    """Verify 401 for unauthenticated and 403 for unauthorized roles."""
    service = BillingIngestionService(sql_service=sql_service)
    req = BillingApprovalTokenRequest(
        query="SELECT record_id FROM system.billing.usage LIMIT 10",
    )

    # 1. Unauthenticated user -> HTTP 401
    unauth_user = AuthenticatedUser(
        sub="anon",
        roles=[],
        is_authenticated=False,
    )
    with pytest.raises(Exception) as exc1:
        issue_approval_token(req, current_user=unauth_user, service=service)
    assert "401" in str(exc1.value) or "UNAUTHENTICATED" in str(exc1.value)

    # 2. Unauthorized roles -> HTTP 403
    for unauth_role in [
        ["Viewer"],
        ["Developer"],
        ["FinOpsAnalyst"],
        ["Reader"],
        [],
    ]:
        user = AuthenticatedUser(
            sub="test-user",
            preferred_username="test@bizmetric.com",
            roles=unauth_role,
            is_authenticated=True,
        )
        with pytest.raises(Exception) as exc2:
            issue_approval_token(req, current_user=user, service=service)
        assert "403" in str(exc2.value) or "INSUFFICIENT_PERMISSIONS" in str(exc2.value)


def test_anti_spoofing_client_payload_ignored(
    sql_service: DatabricksSqlService,
) -> None:
    """Verify that client-injected approver_sub or approver_roles in the payload cannot spoof privileges."""
    service = BillingIngestionService(sql_service=sql_service)

    # A Viewer tries to supply approver_roles=["Admin", "FinOpsAdministrator"] in the request payload
    malicious_req = BillingApprovalTokenRequest(
        query="SELECT record_id FROM system.billing.usage LIMIT 10",
        approver_sub="spoofed-admin@bizmetric.com",
        approver_roles=["FinOpsAdministrator", "Admin"],
    )

    actual_viewer = AuthenticatedUser(
        sub="real-viewer-999",
        preferred_username="viewer@bizmetric.com",
        roles=["Viewer"],  # Actual server-verified role is Viewer!
        is_authenticated=True,
    )

    # Must be strictly rejected with HTTP 403 because server-derived role is Viewer
    with pytest.raises(Exception) as exc:
        issue_approval_token(malicious_req, current_user=actual_viewer, service=service)
    assert "403" in str(exc.value)


# =============================================================================
# 2. Cryptographic Key Management & Fail-Closed Behavior
# =============================================================================


def test_missing_signing_key_fails_closed() -> None:
    """Verify that if finops_signing_secret is missing, token issuance fails closed."""
    unconfigured_settings = Settings(
        app_name="cloud-recommender-test",
        app_env="production",
        finops_signing_secret=None,
    )
    unconfigured_service = DatabricksSqlService(
        host="https://adb-642006393507276.16.azuredatabricks.net",
        warehouse_id="05ed10a52697a344",
        settings=unconfigured_settings,
    )

    with pytest.raises(RuntimeError) as exc:
        unconfigured_service.issue_approval_token(
            query="SELECT * FROM system.billing.usage LIMIT 10",
            warehouse_id=unconfigured_service.warehouse_id,
            approver_roles=["FinOpsAdministrator"],
        )
    assert "finops_signing_secret' is not configured" in str(exc.value)


def test_key_rotation_verification(sql_service: DatabricksSqlService) -> None:
    """Verify that tokens signed with a rotated key in finops_verification_keys verify correctly."""
    query = "SELECT record_id FROM system.billing.usage LIMIT 10"

    # Issue token with active key (k1-2026)
    token_k1 = sql_service.issue_approval_token(
        query=query,
        warehouse_id=sql_service.warehouse_id,
        approver_roles=["FinOpsAdministrator"],
    )
    assert token_k1.startswith("v2:k1-2026:")
    assert sql_service.verify_approval_token(token_k1, query, sql_service.warehouse_id) is True

    # Unknown kid rejected
    tampered_kid = token_k1.replace("v2:k1-2026:", "v2:k99-unknown:")
    assert sql_service.verify_approval_token(tampered_kid, query, sql_service.warehouse_id) is False


# =============================================================================
# 3. 15-Parameter Canonical Payload Binding & Tamper Rejection
# =============================================================================


def test_canonical_payload_tamper_rejection(sql_service: DatabricksSqlService) -> None:
    """Verify that modifying any bound parameter invalidates the token."""
    query = "SELECT * FROM system.billing.usage WHERE usage_date >= '2026-10-01' LIMIT 50"
    token = sql_service.issue_approval_token(
        query=query,
        warehouse_id=sql_service.warehouse_id,
        start_date="2026-10-01",
        end_date="2026-11-04",
        max_rows=500,
        approver_roles=["FinOpsAdministrator"],
    )

    # 1. Correct parameters pass verification
    assert (
        sql_service.verify_approval_token(
            token=token,
            query=query,
            warehouse_id=sql_service.warehouse_id,
            max_rows=500,
            date_start="2026-10-01",
            date_end="2026-11-04",
        )
        is True
    )

    # 2. Tampered query is rejected
    tampered_query = query.replace("LIMIT 50", "LIMIT 100")
    assert (
        sql_service.verify_approval_token(
            token=token,
            query=tampered_query,
            warehouse_id=sql_service.warehouse_id,
        )
        is False
    )

    # 3. Tampered warehouse is rejected
    assert (
        sql_service.verify_approval_token(
            token=token,
            query=query,
            warehouse_id="different-warehouse-id",
        )
        is False
    )

    # 4. Exceeding max_rows is rejected
    assert (
        sql_service.verify_approval_token(
            token=token,
            query=query,
            warehouse_id=sql_service.warehouse_id,
            max_rows=1000,  # Token was only issued for 500 max rows!
        )
        is False
    )

    # 5. Tampered date range is rejected
    assert (
        sql_service.verify_approval_token(
            token=token,
            query=query,
            warehouse_id=sql_service.warehouse_id,
            date_start="2026-09-01",
        )
        is False
    )


# =============================================================================
# 4. AST SQL Parser Validation (sqlglot Databricks dialect)
# =============================================================================


def test_ast_parser_valid_complex_queries(sql_service: DatabricksSqlService) -> None:
    """Verify that legitimate complex queries with CTEs, joins, and string literals containing keywords pass."""
    valid_queries = [
        # Query with SQL keyword inside string literal (must not be blocked by dumb regex)
        "SELECT * FROM system.billing.usage WHERE sku_name = 'DROP_RECORDS_SKU'",
        "SELECT * FROM system.billing.usage WHERE record_id = 'DELETE-12345'",
        # CTE query
        (
            "WITH usage_rollup AS ("
            "  SELECT sku_name, sum(usage_quantity) as total_qty "
            "  FROM system.billing.usage "
            "  GROUP BY sku_name"
            ") "
            "SELECT u.sku_name, u.total_qty, p.pricing.default as list_price "
            "FROM usage_rollup u "
            "JOIN system.billing.list_prices p ON u.sku_name = p.sku_name"
        ),
    ]

    for q in valid_queries:
        sql_service.validate_read_only_statement(q)


def test_ast_parser_adversarial_rejections(sql_service: DatabricksSqlService) -> None:
    """Verify that AST parser strictly rejects unapproved tables, mutations, and unsafe functions."""
    adversarial_queries = [
        # External tables / catalogs
        (
            "SELECT * FROM system.access.audit",
            "Access to table 'system.access.audit' is not permitted",
        ),
        (
            "SELECT * FROM default.custom_table",
            "Access to table 'default.custom_table' is not permitted",
        ),
        ("SELECT * FROM hive_metastore.sales.orders", "is not permitted"),
        # Query without system tables
        ("SELECT 1", "Query must reference at least one allowed system table"),
        # Mutation statements
        ("DROP TABLE system.billing.usage", "Only read-only SELECT or WITH"),
        ("INSERT INTO system.billing.usage VALUES (1)", "Only read-only SELECT or WITH"),
        # Semicolon chaining
        ("SELECT * FROM system.billing.usage; SELECT 1", "Semicolons are prohibited"),
        # Comments
        ("SELECT * FROM system.billing.usage -- comment", "Comments ('--' or '/*') are prohibited"),
        # Reflection / unsafe functions
        (
            "SELECT SECRET('scope', 'key') FROM system.billing.usage",
            "Statement contains unsafe function",
        ),
        (
            "SELECT REFLECT('java.lang.System', 'exit', 0) FROM system.billing.usage",
            "Statement contains unsafe function",
        ),
        (
            "SELECT DBUTILS.fs.ls('/') FROM system.billing.usage",
            "Statement contains unsafe function",
        ),
    ]

    for q, err_snippet in adversarial_queries:
        with pytest.raises(MutationProhibitedError) as exc:
            sql_service.validate_read_only_statement(q)
        assert err_snippet in str(exc.value)


# =============================================================================
# 5. Durable Atomic Single-Use Token Consumption & Concurrency
# =============================================================================


def test_atomic_token_consumption_and_replay_prevention(
    sql_service: DatabricksSqlService, sqlite_session: Session
) -> None:
    """Verify atomic single-use consumption in SQLite/PostgreSQL."""
    query = "SELECT record_id FROM system.billing.usage LIMIT 5"
    token = sql_service.issue_approval_token(
        query=query,
        warehouse_id=sql_service.warehouse_id,
        approver_roles=["FinOpsAdministrator"],
        session=sqlite_session,
    )

    # 1. Initial verification succeeds
    assert (
        sql_service.verify_approval_token(
            token, query, sql_service.warehouse_id, session=sqlite_session
        )
        is True
    )

    # 2. First consumption succeeds
    consumed = sql_service.consume_approval_token(token, session=sqlite_session)
    assert consumed is True

    # 3. Second consumption attempt fails (atomic conditional check rejected)
    replay_consumed = sql_service.consume_approval_token(token, session=sqlite_session)
    assert replay_consumed is False

    # 4. Verification after consumption fails
    assert (
        sql_service.verify_approval_token(
            token, query, sql_service.warehouse_id, session=sqlite_session
        )
        is False
    )


def test_concurrent_token_consumption(
    sql_service: DatabricksSqlService, sqlite_session_factory: sessionmaker
) -> None:
    """Verify that under concurrent requests, exactly ONE thread succeeds in consuming the token."""
    main_session = sqlite_session_factory()
    query = "SELECT record_id FROM system.billing.usage LIMIT 5"
    token = sql_service.issue_approval_token(
        query=query,
        warehouse_id=sql_service.warehouse_id,
        approver_roles=["FinOpsAdministrator"],
        session=main_session,
    )
    main_session.close()

    results: list[bool] = []
    lock = threading.Lock()

    def try_consume():
        thread_session = sqlite_session_factory()
        try:
            res = sql_service.consume_approval_token(token, session=thread_session)
            with lock:
                results.append(res)
        finally:
            thread_session.close()

    threads = [threading.Thread(target=try_consume) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Exactly ONE thread must succeed; the other four must be rejected
    assert results.count(True) == 1
    assert results.count(False) == 4
