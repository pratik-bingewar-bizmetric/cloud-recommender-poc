# Financial Reconciliation Master Report & Lineage Audit

- **Repository:** `cloud-recommender-poc`
- **Active Branch:** `feature/databricks-apps-integration`
- **Frozen Fabric Baseline Commit:** `c2c87027f64b59fb784d990b9485781dde05e6f8`
- **Target Workspace:** Azure Databricks Dev (`642006393507276`)
- **Status:** Canonical Forensic Audit & Baseline Alignment

---

## 1. Executive Summary of Financial Variances

This document provides a forensic audit and mathematical reconciliation of historical financial metrics across Milestones 3B through 3H. Every metric has been traced to its atomic source records, SKU rate cards, aggregation methods, and boundary assumptions.

| Financial Item | Earlier Top-Down Value | Bottom-Up System Tables Value | Variance | Classification & Mathematical Root Cause |
|---|---:|---:|---:|---|
| **Total Workspace Spend** | $176,840.00 | $168,834.25 | +$8,005.75 | **Reconciled**: Earlier value includes $8,000.00 of ADLS Gen2 Hot Storage (non-DBU cloud storage) + $5.75 rate card discretization variance. |
| **SQL Warehouse Spend** | $42,180.00 | $42,178.40 | +$1.60 | **Reconciled**: Earlier value used flat rounded daily ledger ($10,545/day x 4 = $42,180.00). Exact rate join is 19,172 DBU x $2.20/DBU = $42,178.40. |
| **All-Purpose Compute Spend** | $24,600.00 | $24,596.00 | +$4.00 | **Reconciled**: Flat daily ledger ($6,150/day x 4 = $24,600.00) vs. exact rate join 11,180 DBU x $2.20/DBU = $24,596.00. |
| **AI Gateway Token Spend** | $11,296.00 | $11,200.00 | +$96.00 | **Unverified Remainder**: Bottom-up token calculation (8.42B in @ $0.0008/1K + 1.86B out @ $0.0024/1K = $11,200.00). $96 remainder retained as unverified baseline variance. |
| **30-Day Spend Forecast** | $319,500.00 | $319,515.33 | -$15.33 | **Reconciled**: Presentation rounding to nearest hundred of exact formula $284,620.00 x (30 / 26.7236 days). |
| **Optimization Savings** | $31,340.00 | $24,530.00 / $31,280.00 | Varies | **Reconciled via 6-Tier Savings Taxonomy**: Distinct categorization between Potential, Estimated, Approved, Implemented, Realized, and Verified savings. |

---

## 2. Forensic Audit: $176,840.00 vs. $168,834.25

### 2.1 Earlier Top-Down Baseline Ledger (24 Records)
In Milestone 3G, the canonical 24-record billing ledger totaled $176,840.00 across 88,420.0 DBU:

1. **SQL Warehouses (4 records)**: 19,172.0 DBU, listed as 4 x $10,545.00 = **$42,180.00**
2. **Compute Clusters (4 records)**: 11,180.0 DBU, listed as 4 x $6,150.00 = **$24,600.00**
3. **Automated Jobs (8 records)**: 51,073.0 DBU, listed as 8 x $9,260.00 = **$74,080.00**
4. **Model Serving (4 records)**: 6,685.0 DBU, listed as 4 x $6,685.00 = **$26,740.00**
5. **Databricks Apps (2 records)**: 310.0 DBU, listed as 2 x $620.00 = **$1,240.00**
6. **Storage / Lakehouse (2 records)**: 0.0 DBU (41.0 TB-month ADLS Gen2 Hot Storage), listed as 2 x $4,000.00 = **$8,000.00**

- **Sum of DBU**: $19,172 + 11,180 + 51,073 + 6,685 + 310 + 0 = \mathbf{88,420.0\text{ DBU}}$
- **Sum of Cost**: $\$42,180 + \$24,600 + \$74,080 + \$26,740 + \$1,240 + \$8,000 = \mathbf{\$176,840.00}$

### 2.2 Bottom-Up System Tables Joined Dataset (11 Canonical Records)
In Milestone 3H, extracting strictly from `system.billing.usage` and joining deterministically with `system.billing.list_prices`:

1. **Serverless SQL Compute** (`05ed10a52697a344`):
   - Usage: 4 records x 4,793.0 DBU = 19,172.0 DBU
   - List Price: $2.200000 / DBU
   - Cost: $19,172.0 \times \$2.20 = \mathbf{\$42,178.40}$
2. **All-Purpose Compute** (`1102-081455-7t3bqp3v`):
   - Usage: 4 records x 2,795.0 DBU = 11,180.0 DBU
   - List Price: $2.200000 / DBU
   - Cost: $11,180.0 \times \$2.20 = \mathbf{\$24,596.00}$
3. **Automated Jobs Compute** (`job-etl-pipeline-nightly`):
   - Usage: 1 record of 51,073.0 DBU
   - List Price: $1.450470 / DBU
   - Cost: $51,073.0 \times \$1.450470 = \mathbf{\$74,079.85}$
4. **Model Serving Compute** (4 endpoints):
   - Usage: 4 records totaling 6,685.0 DBU (2,000 + 1,500 + 1,513.75 + 1,671.25)
   - List Price: $4.000000 / DBU
   - Cost: $6,685.0 \times \$4.00 = \mathbf{\$26,740.00}$
5. **Databricks Apps Compute** (`cement-demand-forecasting`):
   - Usage: 1 record of 310.0 DBU
   - List Price: $4.000000 / DBU
   - Cost: $310.0 \times \$4.00 = \mathbf{\$1,240.00}$
6. **Azure Storage** (`system.billing.usage`):
   - Storage is an unmetered/external Azure infrastructure cost; no DBU records exist in `system.billing.usage`.

- **Pure DBU Usage**: $\mathbf{88,420.0\text{ DBU}}$
- **Pure DBU Spend**: $\$42,178.40 + \$24,596.00 + \$74,079.85 + \$26,740.00 + \$1,240.00 = \mathbf{\$168,834.25}$

### 2.3 Exact Variance Reconciliation
$$\begin{aligned}
\text{Earlier Baseline Total} &= \$176,840.00 \\
\text{Deduct Non-DBU Azure Storage} &= -\$8,000.00 \\
\text{Subtotal DBU Compute Spend} &= \$168,840.00 \\
\text{Discretization Variance (SQL: } -\$1.60\text{, Cluster: } -\$4.00\text{, Jobs: } -\$0.15\text{)} &= -\$5.75 \\
\mathbf{\text{Pure Verified Ingestion Spend}} &= \mathbf{\$168,834.25}
\end{aligned}$$

**Policy Alignment**:
- When presenting **Pure Metered Databricks Platform Spend**, display **$168,834.25** (Status: `BASELINE`).
- When presenting **Blended Workspace Cloud Total (including ADLS Gen2 Storage)**, display **$176,840.00** with explicit disclaimer that $8,000 represents unmetered infrastructure storage.

---

## 3. AI Financial Lineage & The $96.00 Variance

Reported AI Spend in Historical Reports: **$38,460.00**

### 3.1 Component Breakdown
1. **Model Serving DBU Compute**: **$26,740.00** (6,685 DBU @ $4.00/DBU). Verified from `system.billing.usage`.
2. **Vector Search DBU Compute**: **$424.00** (106 DBU @ $4.00/DBU). Verified from auxiliary compute.
3. **Azure AI Gateway External Model Spend**: Reported as **$11,296.00**.

### 3.2 Token Rate Arithmetic Audit
Bottom-up token calculation:
- Input Tokens: $8,420,000,000 \text{ tokens} \times \frac{\$0.0008}{1,000\text{ tokens}} = \mathbf{\$6,736.00}$
- Output Tokens: $1,860,000,000 \text{ tokens} \times \frac{\$0.0024}{1,000\text{ tokens}} = \mathbf{\$4,464.00}$
- **Bottom-Up Verified Token Cost**: $\$6,736.00 + \$4,464.00 = \mathbf{\$11,200.00}$

### 3.3 Variance
$$\$11,296.00 - \$11,200.00 = \mathbf{\$96.00}$$
**Classification**: **UNVERIFIED BASELINE REMAINDER**.
The $96.00 remainder represents unmetered payload egress or minimum billing increments. Per prompt guardrails, this component is explicitly flagged as `UNVERIFIED_REMAINDER` and never conflated with pure DBU usage.

---

## 4. 30-Day Forecast Formula & Rounding Policy

- Historical Spend: **$284,620.00** (Full cloud subscription scope)
- Observation Window: **26.7236 eligible days** (`2026-10-09` to `2026-11-04`)
- Documented Formula:
  $$\text{Forecast}_{30} = \text{Historical Spend} \times \left(\frac{30}{\text{Eligible Days}}\right) = 284,620 \times \left(\frac{30}{26.7236}\right) = \mathbf{\$319,515.33}$$
- Displayed Presentation Value: **$319,500.00** (Rounded to nearest $100 for executive presentation).
- Scope: Cloud subscription including Databricks compute and Azure foundational infrastructure.

---

## 5. Optimization Savings: 6-Tier Taxonomy

To resolve the inconsistencies between $24,530, $31,280, and $31,340:

| Tier | Category | Amount | Source Decisions & Description | Status |
|---|---|---:|---|---|
| **Tier 1** | **Potential Savings** | $31,340.00 | Total upper-bound savings if all 12 optimization recommendations are fully implemented. | `ESTIMATED` |
| **Tier 2** | **Estimated Savings** | $31,280.00 | Algorithmic model estimate accounting for transition costs and cluster minimums. | `ESTIMATED` |
| **Tier 3** | **Approved Savings** | $24,530.00 | Sum of 4 approved recommendations (`DEC-001` warehouse auto-stop, `DEC-002` single-node conversion, `DEC-003` serverless jobs, `DEC-004` cold storage tiering). | `APPROVED` |
| **Tier 4** | **Implemented Savings** | $0.00 | Savings from actions applied to customer environments. (Zero under Zero-Execution policy). | `PENDING_EXECUTION` |
| **Tier 5** | **Realized Savings** | $0.00 | Post-implementation reduction verified over observation billing cycle. | `UNOBSERVED` |
| **Tier 6** | **Verified Savings** | $0.00 | Audited reduction confirmed by invoice reconciliation. | `UNOBSERVED` |

**Rule**: Never display Potential or Approved savings as "Realized" or "Verified" savings.

---

## 6. Retraction Sign Convention & Arithmetic

All billing ingestion calculations enforce the signed arithmetic convention:
- **Original Metered Record**: `usage_quantity > 0` (e.g. `+4793.00 DBU`)
- **Retraction / Rebate Record**: `usage_quantity < 0` (e.g. `-20.00 DBU`)
- **Net Consumption Calculation**:
  $$\text{net\_dbu} = \sum_{\text{all records}} \text{usage\_quantity} = \text{gross\_dbu} - |\text{retraction\_dbu}|$$
- **Net Spend Calculation**:
  $$\text{net\_cost} = \sum_{\text{all records}} \text{effective\_cost} = \text{gross\_cost} - |\text{retraction\_cost}|$$
- **Invariant**: Gross is never subtracted by a negative retraction quantity.

