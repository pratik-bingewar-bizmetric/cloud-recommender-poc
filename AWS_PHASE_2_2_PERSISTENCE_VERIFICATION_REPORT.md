# AWS Phase 2.2 — Persistence Verification Report

> **Repository:** `cloud-recommender-poc`  
> **Date:** 2026-11-26  
> **Database:** PostgreSQL (`localhost:5432/cloud_recommender`)  
> **Status:** AUDITED — PERSISTENCE ARCHITECTURE VERIFIED

---

## 1. Database Connectivity & Schema Inspection

- **PostgreSQL Connectivity:** Verified live connection to `localhost:5432/cloud_recommender` via SQLAlchemy async engine and asyncpg driver (`SELECT 1` succeeded).
- **Existing Schema Models:** `backend/src/cloud_recommender/db/models.py` defines comprehensive SQLAlchemy models for:
  - `CloudConnectionModel` (stores encrypted cloud credentials and integration metadata).
  - `BillingApprovalTokenModel` (stores cryptographic approval tokens, plan hashes, status, and spend).
  - `BillingUsageRecordModel` (stores raw usage and cost line items).
  - `BillingIngestionRunModel` (stores ingestion batch metadata and status).
  - `BillingReconciliationResultModel` (stores reconciliation calculations).

---

## 2. In-Memory vs. Durable Persistence Operational Classification

| Capability Area | Local / Dev Mode | Production Architecture | Operational Status |
| :--- | :--- | :--- | :---: |
| **Connection Storage** | In-memory `MemoryStore` | `CloudConnectionModel` (PostgreSQL) | **IMPLEMENTED** (Configurable via `CONNECTION_STORE=database`) |
| **Approval Token Tracking** | In-memory `_used_token_ids` in `AwsSyncApprovalService` | `BillingApprovalTokenModel` (`persist_token_record`, `validate_and_consume_token_durable`) | **WORKING** (Durable atomic DB transactions verified) |
| **Sync Run History** | In-memory `_sync_history` list | `BillingIngestionRunModel` (`record_sync_run_durable`) | **WORKING** (Durable DB transactions verified) |
| **Usage & Telemetry Ingestion** | In-memory response objects | `BillingUsageRecordModel` (`persist_cost_records_durable`, `persist_metric_records_durable`) | **WORKING** (Idempotent SHA-256 hash storage verified) |
| **Replay Protection Scope** | Single Python process lifecycle | Durable distributed multi-worker lock via atomic SQL updates | **WORKING** (Cross-worker replay rejection verified) |

### Strict Classification:
- **Local Validation Scope:** In-memory storage provides complete single-use replay protection and atomic budget enforcement within an isolated single-process execution environment.
- **Production Persistence:** Fully implemented in `AwsSyncApprovalService` and verified against PostgreSQL (`billing_approval_tokens`, `billing_ingestion_runs`, `billing_usage_records`). Replay attacks across multiple workers or restarts are rejected atomically via `UPDATE billing_approval_tokens SET is_consumed=True WHERE token_id=:id AND is_consumed=False`.

