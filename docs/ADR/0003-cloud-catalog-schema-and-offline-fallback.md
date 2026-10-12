# ADR 0003: Analytics Layer Architecture (Microsoft Fabric Lakehouse & OneLake)

| Status | Accepted |
| :--- | :--- |
| **Date** | 2026-10-12 |
| **Authors** | Architecture Working Group |
| **Deciders** | Lead Cloud Architect, Data Engineering Lead |

---

## Context & Problem Statement

Phase B (Existing Application Optimization) requires analyzing large volumes of semi-structured cloud telemetry:
- Detailed Azure Resource Graph inventory dumps.
- Historical Azure Monitor time-series metrics (CPU, memory, IOPS over 30–90 days).
- Granular daily Azure Cost Management billing logs.

Storing millions of high-frequency metric records in an operational relational database (PostgreSQL) leads to database bloat, performance degradation, and cumbersome analytics querying. The project requires an enterprise-grade analytics storage and transformation layer, specifically aligned with the enterprise Microsoft data ecosystem.

---

## Decision

We designate **Microsoft Fabric** as the planned analytics storage and transformation layer:

1. **OneLake & Lakehouse Tables:**
   - Raw Azure inventory, billing data, and performance metrics will be stored in a **Microsoft Fabric Lakehouse** using the open **Delta Parquet** format.
   - Separate tables are provisioned: `raw_azure_inventory`, `raw_azure_metrics`, `raw_azure_billing`, and aggregated analytical views.
2. **Fabric Data Transformations:**
   - Transformation and aggregation routines (e.g. computing 30-day P95 CPU utilization, identifying idle disks) execute via Fabric Notebooks / Spark jobs or scheduled Dataflows Gen2.
3. **Local / Offline Fallback Mode:**
   - To adhere to our core principle that the POC must be runnable offline without paid cloud subscriptions, the backend implements a local Lakehouse abstraction using DuckDB and local Parquet files when `FABRIC_ENABLED=false`.

---

## Consequences

### Positive
- Enterprise-grade scalability for large telemetry and FinOps datasets.
- Native alignment with customer Microsoft enterprise environments.
- Zero impact on the operational PostgreSQL database.
- Complete offline testability via the local DuckDB/Parquet fallback.

### Negative / Trade-offs
- Connecting to live Fabric environments requires active Fabric capacity (F-SKU or Trial) and Azure AD App Registration permissions for OneLake.
