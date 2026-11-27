# AWS Phase 2.2 — Preflight Verification Report

> **Repository:** `cloud-recommender-poc`  
> **Date:** 2026-11-26  
> **Git Branch:** `feature/gcp-service-account-integration`  
> **Status:** PREFLIGHT VERIFIED & PASSED (STOPPED AT LIVE CHARGEABLE AUTHORIZATION CHECKPOINT)

---

## 1. Executive Summary

In accordance with `AGENTS.md` and Phase 2.2 preflight requirements, all security validators, action allowlists, cryptographic approval mechanisms, budget guards, protocol classifications, and test warning resolutions were rigorously audited, hardened, and verified prior to any chargeable AWS execution.

---

## 2. Security Preflight & Outbound Validation Audit

### 2.1 Action Allowlist & Multi-Protocol Extraction (`operation_validator.py`)
- **Centralized Pre-Network Interception:** Verified that every outbound request must pass `validate_outbound_aws_request(...)` before SigV4 signing in `sign_aws_request(...)`.
- **Duplicate & Conflicting Action Detection:** Hardened `_extract_query_action(...)` and `_extract_json_target_action(...)` to detect and reject conflicting Action parameters in query string/body or conflicting `X-Amz-Target` headers (`ValueError: Conflicting Action parameters detected`).
- **Approved Plan Scope Enforcement:** Added `approved_operations` parameter to `validate_outbound_aws_request(...)`. Operations falling outside the authorized synchronization plan scope are rejected with `PermissionError` even if present on the global read-only allowlist.
- **Protocol & Authority Guardrails:**
  - Strict HTTPS scheme enforcement (`http://` rejected).
  - Port 443 enforcement (arbitrary ports rejected).
  - Authority userinfo rejection (`user:pass@host` rejected).
  - Host suffix allowlist enforcement (`*.amazonaws.com`, `*.amazonaws.com.cn`).
- **EKS Protocol Correction:** Corrected architectural classification of AWS EKS. EKS uses a resource-oriented RESTful HTTP API (e.g. `GET /clusters`, `GET /clusters/{name}`) over HTTPS, distinct from AWS Query or JSON-RPC protocols.

---

## 3. Approval Token & Budget Guard Audit

### 3.1 Concurrency & Persistence Semantics
- **Concurrency Model Clarification:** Clarified that `asyncio.Lock` provides coroutine synchronization within a single Python asyncio event loop process.
- **Durable PostgreSQL Persistence Implemented:** Implemented atomic token consumption and persistence in `AwsSyncApprovalService` (`persist_token_record`, `validate_and_consume_token_durable`, `record_sync_run_durable`, `persist_cost_records_durable`, `persist_metric_records_durable`) backed by PostgreSQL tables `billing_approval_tokens`, `billing_ingestion_runs`, and `billing_usage_records`. Single-use replay protection is enforced atomically via SQL: `UPDATE billing_approval_tokens SET is_consumed=True WHERE token_id=:id AND is_consumed=False`. Cross-worker replay attempts are permanently rejected.

### 3.2 Transport-Level Budget Accounting
- Atomic reservation occurs before every chargeable HTTP dispatch.
- Cost Explorer requests are reserved at \$0.0100 per request.
- CloudWatch requests account for actual metric query count ($4 \times \$0.00001 = \$0.00004$).
- Client budget overrides are validated against the \$0.05 USD system cap and server-calculated request ceilings.
- Reservations are retained on network failures if the request may have reached AWS.

---

## 4. Test Warnings Classification & Resolution

| Warning Location | Category | Root Cause | Resolution | Status |
| :--- | :--- | :--- | :--- | :---: |
| `backend/src/cloud_recommender/api/routes/aws.py:474` | `RuntimeWarning` | Synchronous `parse_profile_credentials` called on `AsyncMock` | Mocked `cost_mock.auth_service` as `MagicMock()` with dict return | **RESOLVED** |
| `backend/src/cloud_recommender/api/routes/aws.py:496` | `RuntimeWarning` | Unawaited mock coroutine on synchronous helper | Mocked `cost_mock.auth_service` as `MagicMock()` with dict return | **RESOLVED** |
| `backend/src/cloud_recommender/api/routes/aws.py:548` | `RuntimeWarning` | Unawaited mock coroutine on synchronous helper | Mocked `cost_mock.auth_service` as `MagicMock()` with dict return | **RESOLVED** |

All tests execute with `-W error::RuntimeWarning` producing **zero warnings**.

