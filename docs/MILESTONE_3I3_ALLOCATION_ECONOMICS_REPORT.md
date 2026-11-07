# Milestone 3I.3: Cost Allocation, Showback & Workload Economics Report

- **Repository:** `cloud-recommender-poc`
- **Active Branch:** `feature/databricks-apps-integration`
- **Workspace:** Azure Databricks Dev (`642006393507276`)
- **Status:** Complete & Integrated

---

## 1. Executive Summary

Milestone 3I.3 delivers precise multi-dimensional cost allocation, business unit showback statements, and granular workload unit economics. By strictly separating direct attribution from shared pool allocations and isolating unallocated spend, the platform establishes full financial transparency across enterprise cost centers.

---

## 2. Cost Allocation Dimensions & Rules

Cost allocation strictly follows verified tagging rules and exact resource mapping:

### 2.1 Allocation Dimensions:
1. **Business Unit / Department**: `data-platform`, `data-engineering`, `ai-coe`, `supply-chain`.
2. **Environment**: `Production` (88.4%), `Staging` (11.6%).
3. **Application Workload**: `Nightly ETL Pipeline`, `Serverless SQL Lakehouse`, `Model Serving Gateway`, `Cement Demand Forecasting`.
4. **Cost Center**: `CC-1010` (Core Infra), `CC-2020` (Data Analytics), `CC-3030` (AI/ML), `CC-4040` (Operations).

### 2.2 Unallocated Spend Preservation
- **Unattributed Compute**: **$1,240.00** (310.0 DBU from Databricks Apps runtime `cement-demand-forecasting` tagged as `unassigned`).
- **Policy Enforcement**: Unallocated amounts are **never** hidden, averaged out, or force-fitted into allocated departments. They are explicitly isolated on the ledger with an action trigger for workload owners to apply tags.

---

## 3. Departmental Showback Statements

| Business Unit | Direct Compute | AI Tokens | Lakehouse Storage | Shared Allocation | Total Billed | Budget Variance | Trend |
|---|---:|---:|---:|---:|---:|---|---|
| **Data Engineering** | $74,080.00 | $0.00 | $0.00 | $6,180.00 | **$80,260.00** | +6.2% | +4.1% MoM |
| **Data Platform** | $42,180.00 | $0.00 | $8,000.00 | $4,120.00 | **$54,300.00** | +8.6% | +12.3% MoM |
| **AI COE** | $26,740.00 | $11,296.00 | $0.00 | $2,060.00 | **$40,096.00** | +14.2% | +28.5% MoM |
| **Supply Chain** | $24,600.00 | $0.00 | $0.00 | $2,100.00 | **$26,700.00** | -3.1% | -1.2% MoM |
| **Unallocated Pool** | $1,240.00 | $0.00 | $0.00 | $0.00 | **$1,240.00** | N/A | New Pool |
| **Total** | **$168,840.00** | **$11,296.00** | **$8,000.00** | **$14,460.00** | **$202,596.00** | **+$25,900** | **+9.8% MoM** |

---

## 4. Workload Unit Economics

Granular cost-per-unit metrics provide operational visibility for engineering leads:

| Workload Family | Specific Asset / Pipeline | Total Spend | Volume (MTD) | Unit Cost Metric | Business Outcome | Efficiency Trend |
|---|---|---:|---|---|---|---|
| **Automated ETL** | `job-etl-pipeline-nightly` | $74,080.00 | 8 full runs | **$9,260.00 / run** | Daily enterprise ingestion | Stable (0.0% variance) |
| **Serverless SQL** | `Serverless Starter Warehouse` | $42,180.00 | 124,500 queries | **$0.339 / query** | Power BI executive reporting | +18.4% cost efficiency |
| **All-Purpose Cluster** | `adf-deaccelator-compute` | $24,600.00 | 96 compute-hrs | **$256.25 / hr** | Ad-hoc supply chain modeling | -8.2% (idle waste) |
| **Model Serving** | `databricks-dbrx-instruct` | $6,685.00 | 4.2M requests | **$0.00159 / req** | Enterprise search & chat | +4.5% efficiency |
| **AI Gateway** | Input Tokens (all models) | $6,736.00 | 8.42B tokens | **$0.00080 / 1K** | Raw token generation | Standard contracted |
| **AI Gateway** | Output Tokens (all models) | $4,464.00 | 1.86B tokens | **$0.00240 / 1K** | Raw token completion | Standard contracted |
| **Databricks Apps** | `cement-demand-forecasting` | $1,240.00 | 15,200 inferences | **$0.08158 / pred** | Factory demand forecast | Baseline |

