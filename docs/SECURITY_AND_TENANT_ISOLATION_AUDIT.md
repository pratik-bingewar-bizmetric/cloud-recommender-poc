# Security Controls & Tenant Isolation Architecture Audit

> **Document:** `docs/SECURITY_AND_TENANT_ISOLATION_AUDIT.md`  
> **Repository:** `cloud-recommender-poc`  
> **Branch:** `feature/databricks-apps-integration`  
> **Audit Type:** Forensic Application Security & Multi-Tenant Isolation Review  
> **Status:** AUDITED — EVIDENCE-BASED ASSESSMENT  
> **Overall Classification:** **1. IMPLEMENTED & VERIFIED (ENTRA ID AUTH, RBAC, ZERO-EXECUTION, SECRET SCRUBBING) / 5. NOT IMPLEMENTED (DATABASE-LEVEL MULTI-TENANT ROW ISOLATION)**  

---

## 1. Executive Summary

This audit forensically evaluates the security controls, credential protections, authentication mechanisms, and multi-tenant isolation boundaries implemented within the platform.

### Key Security Strengths:
1. **Entra ID Cryptographic JWT Verification:** Implemented using PyJWKClient with RS256 signature verification, issuer validation, audience checks, and tenant ID enforcement ([`backend/src/cloud_recommender/core/auth.py:41–230`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/core/auth.py#L41-L230)).
2. **Zero-Execution & Read-Only Governance:** Strict architectural boundary enforced. All Azure connections request `Reader` and `Cost Management Reader` roles only. SQL Warehouse `05ed10a52697a344` is protected against autonomous execution via cryptographic HMAC approval tokens ([`backend/src/cloud_recommender/services/databricks/sql_client.py:220–290`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/services/databricks/sql_client.py#L220-L290)).
3. **Zero Secret Leakage:** Credentials, secrets, tokens, and private keys are scrubbed before structured logging and never returned in API payloads ([`backend/tests/test_connections_and_tokens.py:29–41`](file:///c:/Users/pratik.bingewar/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/tests/test_connections_and_tokens.py#L29-L41)).

### Critical Security Gap:
- **No Database-Level Multi-Tenant Isolation:** PostgreSQL tables (`billing_usage_records`, `resource_configurations`, `workload_profiles`, etc.) do **NOT** have a `tenant_id` column. There is no Row-Level Security (RLS) enabled in PostgreSQL. The backend assumes a single-tenant deployment per instance.

---

## 2. Security Control Implementation Matrix

| Security Control | Implementation Location | Enforcement Mechanism | Test Evidence | Operational Status |
|:---|:---|:---|:---|:---:|
| **Entra ID JWT Authentication** | `core/auth.py:41–230` | RS256 signature validation via JWKS, token expiration, issuer matching | `backend/tests/test_entra_auth.py` (10 test cases) | **IMPLEMENTED AND VERIFIED** |
| **Role-Based Access Control (RBAC)** | `core/auth.py:262–304` (`require_roles`) | FastAPI dependency verifying `roles` or `scp` claims against `Admin`, `FinOpsAdmin`, `Reader` | `test_entra_auth.py::test_create_connection_requires_admin_role` | **IMPLEMENTED AND VERIFIED** |
| **Zero-Execution Guardrail** | `services/databricks/sql_client.py` | Warehouse state inspection blocks live execution; raises `WarehouseStoppedError` unless HMAC approved | `test_databricks_sql_approval.py` & `test_ingestion_enforcement.py` | **IMPLEMENTED AND VERIFIED** |
| **HMAC Approval Tokens** | `services/databricks/sql_client.py:220` | SHA-256 HMAC signature with single-use replay-prevention in DB table `billing_approval_tokens` | `test_billing_approval_tokens.py` | **IMPLEMENTED AND VERIFIED** |
| **Least-Privilege Cloud Roles** | `services/inventory/azure_inventory.py` | ARM queries scoped strictly to `Reader` and `Cost Management Reader`; write permissions blocked | `test_azure_inventory.py` | **IMPLEMENTED AND VERIFIED** |
| **Zero Credential Exposure** | `api/routes/connections.py` & `schemas/` | Output schemas omit secrets; Pydantic serializers reject private fields | `test_connections_and_tokens.py` | **IMPLEMENTED AND VERIFIED** |
| **PostgreSQL TLS/SSL** | `core/config.py` & `db/session.py` | `ssl=require` injected into asyncpg connection pool | `docs/PRODUCTION_DATABASE_CONFIGURATION.md` | **IMPLEMENTED AND VERIFIED** |
| **Databricks Secret Scopes** | `app.yaml` & `docs/` | Credentials retrieved from `finops-secrets` scope rather than environment plaintext | `docs/PRODUCTION_SECRETS_AND_SECURITY.md` | **CONFIGURED & CERTIFIED** |
| **Multi-Tenant Row-Level Security** | `db/models.py` | N/A | None (Tables lack `tenant_id` columns) | **NOT IMPLEMENTED** |
| **Customer Data Isolation** | Data Access Layer | N/A | Queries filter by `workspace_id`, not by customer tenant | **SINGLE-TENANT ONLY** |
| **Automated Credential Rotation** | Cloud Connectors | N/A | Secrets are static until updated by administrator | **NOT IMPLEMENTED** |
| **AWS IAM Role Assumption** | N/A | N/A (`ENABLE_AWS = False`) | None | **NOT IMPLEMENTED** |

---

## 3. Forensic Tenant Isolation Audit Across Stack Layers

| Stack Layer | Is Tenant / Customer ID Enforced? | Mechanism Observed | Forensic Finding / Leakage Risk |
|:---|:---:|:---|:---|
| **Authentication Claims** | **YES** | `core/auth.py:200–212` checks `token_tid == self.tenant_id`. | Rejects tokens from external Azure AD tenants. Validates caller belongs to configured tenant. |
| **API Request Context** | **PARTIAL** | FastAPI dependencies inject `AuthenticatedUser`. | `user.tid` is extracted into memory, but not passed down to database repositories. |
| **Database Queries** | **NO** | Repository queries in `db/repositories/`. | **Zero tenant filtering.** Queries filter on `workspace_id` or `connection_id`. |
| **PostgreSQL Schema (RLS)** | **NO** | `models.py` Declarative Base. | **Zero `tenant_id` foreign keys.** No PostgreSQL RLS policies defined. |
| **Fabric / OneLake Access** | **PARTIAL** | ADLS Gen2 path contains workspace GUID (`672a6995-...`). | Path partitioning is by Fabric workspace, not multi-tenant customer ID. |
| **In-Memory Cache Keys** | **NO** | `_discovery_cache` in services. | Keyed by `connection_id` (e.g. `databricks-azure-dev`), not tenant ID. |
| **Background Ingestion** | **NO** | `BillingIngestionService` store. | Keyed by `record_id` and filtered by `workspace_id`. |
| **Export / CSV Generation** | **NO** | `export_cost_ledger_csv`. | Generates CSV for active workspace without tenant boundary assertion. |

---

## 4. Cross-Tenant Leakage Risk Assessment

- **Risk Level in Single-Tenant Deployments (Current Target):** **LOW / ACCEPTABLE**.  
  When deployed as a dedicated container inside Azure Databricks Apps for workspace `642006393507276` and dedicated Azure PostgreSQL Flexible Server, the physical compute and database boundary isolates customer data.
- **Risk Level in Shared Multi-Tenant SaaS Deployments:** **CRITICAL**.  
  If the current codebase were deployed to serve multiple commercial customers from a shared database, **cross-tenant data leakage would occur** because database tables and in-memory caches lack tenant foreign keys and RLS policies.

