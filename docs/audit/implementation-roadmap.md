# FinOps & Infrastructure Intelligence Platform — Implementation Roadmap

> **Status:** Prioritized Backlog (Post-Audit Action Plan)  
> **Repository:** `cloud-recommender-poc`  
> **Evaluation Date:** October 2026  

---

## 1. Prioritization Framework

All identified work items are ranked according to business and operational urgency:

- **P0 — Critical Correctness & Telemetry Truthfulness:** Direct defect fixes affecting live metrics or preventing false conclusions.
- **P1 — Code Health & Strict CI Standards:** Test typing cleanup and formatting conformance.
- **P2 — Feature Enhancements & UX Polish:** Exposing hidden capabilities or adding user workflow conveniences.
- **P3 — Long-Term Strategic Capabilities:** Multi-cloud AWS discovery and Microsoft Fabric Lakehouse pipelines.

---

## 2. Prioritized Backlog & Action Items

| Priority | Item ID | Task Title & Scope | Target Files | Dependencies | Estimated Effort | Acceptance Criteria |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **P0** | **TASK-01** | Fix Azure OpenAI Platform Metric Query Names | `backend/src/cloud_recommender/services/monitoring/monitoring_service.py` | Live Azure OpenAI Resource | 1.5 Hours | Replace `InputTokens,OutputTokens` with `ProcessedPromptTokens,ProcessedCompletionTokens,TotalProcessedTokens`. Azure Monitor returns active token series for live deployments. |
| **P1** | **TASK-02** | Test Typing Annotations & Format Conformance | `backend/tests/test_connections_and_tokens.py`, `backend/tests/test_gcp_inventory_and_comparison.py` | None | 0.5 Hours | Fix 5 mypy errors in test file (`Decimal`, `datetime`, generic types). `ruff format` exits with 0 modified files. `mypy backend/` exits 0. |
| **P1** | **TASK-03** | Persist Custom User Cloud Connections | `backend/src/cloud_recommender/services/connections/connection_service.py`, `backend/src/cloud_recommender/db/` | PostgreSQL / SQLite session | 2.0 Hours | Custom-registered Service Principals persist in encrypted session database across backend service restarts. |
| **P2** | **TASK-04** | AI Cloud Architect Navigation Re-Integration | `frontend/src/config/features.ts`, `frontend/src/components/Sidebar.tsx` | None | 0.5 Hours | Enable `ENABLE_AI_ARCHITECT = true` to surface requirements-to-architecture workflow in primary sidebar. |
| **P2** | **TASK-05** | GCP Cloud Monitoring Ops Agent In-Guest Metric Detection | `backend/src/cloud_recommender/services/inventory/gcp_inventory.py` | GCP Compute Engine VM | 3.0 Hours | Query Cloud Monitoring v3 metric descriptors for `agent.googleapis.com/memory/percent_used` when VMs are present. |
| **P3** | **TASK-06** | Microsoft Fabric Lakehouse Analytics Integration | `backend/src/cloud_recommender/services/analytics/`, `frontend/src/config/features.ts` | Microsoft Fabric Workspace | 8.0 Hours | Ingest Azure & GCP daily cost exports into Fabric Bronze delta tables; build FinOps Lakehouse queries. |
| **P3** | **TASK-07** | Amazon Web Services (AWS) Live Discovery & Cost Explorer | `backend/src/cloud_recommender/services/inventory/aws_inventory.py` | AWS IAM Role | 8.0 Hours | Implement read-only AWS Cost Explorer and Pricing List API integration for tri-cloud parity. |

---

## 3. Immediate P0/P1 Implementation Plan (Next Phase)

### Step 1: Fix Token Economics Telemetry Query (TASK-01)
Update `_query_azure_resource_metrics` in `backend/src/cloud_recommender/services/monitoring/monitoring_service.py`:
```python
# Updated ARM Platform Metric Query
params = {
    "metricnames": "ProcessedPromptTokens,ProcessedCompletionTokens,TotalProcessedTokens",
    "timespan": f"{start_time.isoformat()}/{end_time.isoformat()}",
    "interval": eff_interval,
    "aggregation": "Total",
    "api-version": "2023-10-01",
}
```

### Step 2: Clean Mypy Test Typing Annotations (TASK-02)
Update `tests/test_connections_and_tokens.py`:
- Use `from cloud_recommender.schemas.common import ServiceCategory`
- Pass `Decimal("120.00")` instead of `"120.00"`
- Pass `datetime.now(UTC)` instead of ISO string
- Add `dict[str, Any]` to generic mocks

### Step 3: Run Full Verification Suite
Execute:
1. `uv run --directory backend pytest tests/` -> 156+ passed
2. `uv run --directory backend ruff check src/ tests/` -> 0 errors
3. `uv run --directory backend ruff format --check src/ tests/` -> 0 unformatted
4. `uv run --directory backend mypy src/ tests/` -> 0 errors across 78 files
5. `npm --prefix frontend run typecheck` -> 0 errors
6. `npm --prefix frontend run lint` -> 0 errors

