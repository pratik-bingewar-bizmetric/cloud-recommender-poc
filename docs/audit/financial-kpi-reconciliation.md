# FinOps Platform — Financial KPI Reconciliation & Audit Report

**Repository:** `cloud-recommender-poc`  
**Date:** October 2026  
**Auditor:** Senior Cloud Architect & FinOps Specialist  
**Operating Boundary:** 100% Read-Only / Zero-Execution Architecture

---

## Executive Summary

This audit examines and reconciles all financial Key Performance Indicators (KPIs), cost rollups, category distributions, and optimization findings across the platform's primary views:
1. **Home / Product Landing (`LandingView.tsx`)**
2. **Executive FinOps Dashboard (`DashboardView.tsx`)**
3. **Centralized Cloud Infrastructure Monitoring (`SectionCentralizedMonitoring.tsx`)**
4. **Cost & FinOps Waste Intelligence (`SectionCostWaste.tsx`)**
5. **Architectural Savings & Trade-Off Review (`SectionSavingsReview.tsx`)**
6. **Token Economics & AI Rate Telemetry (`SectionTokenEconomics.tsx`)**

Prior to this reconciliation, disparate components exhibited numerical and conceptual discrepancies due to:
- Disconnected mock defaults (`$14,820.50` spend / `$3,419.09` savings in Dashboard vs `$225.11` spend / `$118.27` savings in connected Azure monitoring).
- Hardcoded finding lists whose itemized savings (`$1,516.50`) did not match the header KPI card (`$3,419.09`).
- Artificial percentage scaling (`monthlyTotal * 0.2307`) in Savings Review that conflicted with the sum of itemized recommendations (`$3,463.69`).
- Duplicate local "Switch Account" buttons competing with the authoritative global header switch control.

This document establishes the **Canonical Financial Contract**, documents the exact provenance of every financial KPI, and outlines the reconciliation rules applied.

---

## 1. Master Financial KPI Provenance Matrix

| KPI Name | Component | Data Source & Endpoint | Scope / Context | Currency & Basis | Pricing Source & Rate Effective Date | Formula / Derivation | Prior Discrepancy / Root Cause | Reconciled Value & Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Estimated Monthly Spend** | `DashboardView.tsx` | `/api/v1/inventory/azure/analyze` or `/monitoring/overview` | Active Cloud Scope (`sub-prod-enterprise-01` or `smart-expense-gcp-prod`) | USD ($) / INR (₹ @ 83.15) | Azure Retail Prices API (Public Tier) / GCP Billing Catalog (Oct 2026) | $\sum_{r \in \text{Resources}} \text{estimated\_monthly\_cost}_r$ | Displayed hardcoded `$14,820.50` regardless of active connected scope | Dynamically derived from canonical scope summary: **$225.11/mo** (Azure) or **$280.87/mo** (GCP). In Greenfield Simulator: reflects active BOM. |
| **Monthly Optimization Opportunity** | `DashboardView.tsx` | `/api/v1/inventory/azure/analyze` (`waste_findings`) | Active Cloud Scope | USD ($) / INR (₹ @ 83.15) | Azure Retail Prices / GCP Billing Catalog | $\sum_{f \in \text{WasteFindings}} \text{potential\_monthly\_savings}_f$ | Displayed `$3,419.09` (`spend * 0.2307`), conflicting with the 3 listed findings (`$1,516.50`) | Reconciled to exact sum of active deduplicated findings: **$118.27/mo** (52.5% of Azure spend) or **$84.27/mo** (30.0% of GCP spend). |
| **High-Impact Optimization Findings** | `DashboardView.tsx` | `waste_debt_engine.py` via `analyze_subscription` | Active Cloud Scope | USD ($) / Avoidable Spend | Azure Retail Prices API / GCP Billing Catalog | Itemized non-double-counted waste detections | Contained 3 hardcoded sample findings totaling `$1,516.50` | Now bound to actual discovered scope findings (Azure: 5 findings totaling **$118.27**; GCP: 3 findings totaling **$84.27**). |
| **Spend Breakdown by Category** | `DashboardView.tsx` | `cost_breakdown` in `SubscriptionOrProjectAnalysis` | Active Cloud Scope | USD ($) / Category Sum | Azure Retail Prices API / GCP Billing Catalog | $\text{Compute} + \text{DB} + \text{Storage} + \text{AI} + \text{Network}$ | Displayed fixed synthetic percentages (42%, 28%, 16%, 9%, 5%) on $14,820.50 | Bound to canonical category breakdown (Azure: Compute $91.25, DB $73.00, Storage $32.21, AI $25.00, Network $3.65 = **$225.11**, exact 100%). |
| **Monthly Cloud Spend Trajectory** | `DashboardView.tsx` | In-memory 6-month historical billing model | Active Cloud Scope | USD ($) | Official Public Tier Meters | 6-month trend ending at active month spend; budget threshold at $15,000 (or scope equivalent) | Last bar hovered at $14,820.50 while connected scope was $225.11 | Trajectory anchored to current scope monthly spend with budget threshold dynamically scaled. |
| **Estimated Monthly Spend** | `SectionCostWaste.tsx` | `overview.kpis.estimated_monthly_cost` | Active Cloud Scope | USD ($) / Catalog List | Azure Retail Prices API / GCP Billing Catalog | $\sum \text{Resource Cost}$ | Previously lacked click-to-drilldown definition drawer | **$225.11/mo** (Azure) / **$280.87/mo** (GCP). Interactive drilldown enabled. |
| **Potential Monthly Savings** | `SectionCostWaste.tsx` | `analysisData.total_potential_monthly_savings` | Active Cloud Scope | USD ($) / Avoidable Waste | Deterministic FinOps rules engine | $\sum \text{Deduplicated Waste Savings}$ | Consistent, but lacked modal audit breakdown and formula explanation | **$118.27/mo** (Azure) / **$84.27/mo** (GCP). Matches finding table to the exact penny. |
| **Projected Annual Savings** | `SectionCostWaste.tsx` | `potential_monthly_savings * 12` | Active Cloud Scope | USD ($) / Non-Double-Counted | 12-month projection of current monthly avoidable waste | $\text{monthly\_savings} \times 12$ | None (calculated as 118.27 * 12 = $1,419.24) | Reconciled: **$1,419.24/yr** (Azure) / **$1,011.24/yr** (GCP). Explicitly marked as non-realized projection. |
| **Waste Savings Category Distribution** | `SectionCostWaste.tsx` | `rawFindings.reduce(acc, f)` | Active Cloud Scope | USD ($) / Category Pool | FinOps Rules Engine | $\sum_{f \in \text{category}} \text{savings}_f$ | Worked locally but lacked alignment with Dashboard categories | Aligned to category totals: Overprovisioned DB ($36.50), Stopped Compute ($31.03), Oversized Compute ($27.38), Unattached Storage ($19.71), Unattached IP ($3.65) = **$118.27**. |
| **Showcase Monthly Spend** | `LandingView.tsx` | Props `monthlyTotal` with benchmark fallback | Product Landing Mockup | USD ($) | Azure Retail Prices API | Benchmark reference ($14,820.50) or live connected scope | Unclear whether showcase was live telemetry or synthetic benchmark | Explicitly badged as `"Reference Enterprise Production Benchmark"` or `"Active Connected Scope Telemetry"`. |
| **Showcase Identified Savings** | `LandingView.tsx` | Props or benchmark default | Product Landing Mockup | USD ($) | Reference Benchmark | Benchmark reference ($3,420.00 / 23.1%) or live connected scope | Unclear provenance | Badged truthfully with benchmark attribution. |
| **Architectural Savings Review** | `SectionSavingsReview.tsx` | `costBreakdown.total_monthly` & `recommendations` | Greenfield AI Architect Workspace | USD ($) / Proposed Optimization | Azure Retail Prices API | $\sum_{r \in \text{Recommendations}} \text{savings}_r$ | KPI card showed $3,419.09 (`* 0.2307`), but recommendation sum was $3,463.69 (+$44.60 discrepancy) | Reconciled: KPI card dynamically equals $\sum \text{monthlySavings}$ of all recommendations with zero residual delta. |

---

## 2. Itemized Waste Findings Reconciliation (Azure: `sub-prod-enterprise-01`)

The deterministic waste engine (`waste_debt_engine.py`) detects 5 non-double-counted waste findings in the reference Azure production scope. The sum of these 5 findings exactly equals the scope's total potential savings:

| Finding ID | Resource Name & Native Type | Category | Severity | Current Monthly Spend | Potential Monthly Savings | Derivation Formula & Pricing Basis | Evidence | Confidence |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `waste-dev-db-ha-psql-smart-expense-dev` | `psql-smart-expense-dev` (`Microsoft.DBforPostgreSQL/flexibleServers`) | `overprovisioned_database` | Medium | $73.00 | **$36.50** | 50% cost elimination by disabling redundant multi-zone standby on non-production workload (B2s compute $36.50/mo active + $36.50/mo standby). | Environment tagged `dev`; multi-zone standby active with 0 read replicas and 2.1% average CPU. | High |
| `waste-stopped-vm-vm-staging-processor` | `vm-staging-processor` (`Microsoft.Compute/virtualMachines`) | `stopped_compute` | Medium | $36.50 | **$31.03** | Avoidable compute and license cost for deallocated VM; retains attached OS disk ($5.47/mo) while eliminating compute meter ($31.03/mo). | VM state is `Deallocated` for >30 days; 0 vCPU hours billed in current period. | High |
| `waste-oversized-asp-asp-smart-expense` | `asp-smart-expense` (`Microsoft.Web/serverfarms`) | `oversized_compute` | Medium | $54.75 | **$27.38** | Rightsizing B2 Basic (2 vCPU, 3.5 GB @ $54.75/mo) to B1 Basic (1 vCPU, 1.75 GB @ $27.38/mo). | P95 CPU is 8.4% and P95 RAM is 28.2% over 30-day monitoring window. Headroom > 100% on B1. | High |
| `waste-unattached-disk-disk-analytics-legacy-temp` | `disk-analytics-legacy-temp` (`Microsoft.Compute/disks`) | `unattached_storage` | High | $19.71 | **$19.71** | 100% elimination of orphan Standard SSD managed disk (E20 512 GiB @ $19.71/mo). | Disk state is `Unattached`; last attach timestamp > 45 days ago; 0 cumulative IOPS. | High |
| `waste-unattached-ip-pip-smart-expense-legacy` | `pip-smart-expense-legacy` (`Microsoft.Network/publicIPAddresses`) | `unattached_ip` | Low | $3.65 | **$3.65** | 100% elimination of unassociated Standard Public IPv4 address ($0.005/hr = $3.65/mo). | IP association is `null`; 0 inbound/outbound packets routed in 30 days. | High |
| **TOTAL** | **5 Discovered Waste Findings** | — | — | **$187.61** | **$118.27** | **$\sum \text{Savings} = \$118.27$** (Exactly matches `kpis.potential_monthly_savings`) | **Zero Residual Delta ($0.0000)** | **100% Verified** |

---

## 3. Itemized Waste Findings Reconciliation (GCP: `smart-expense-gcp-prod`)

For Google Cloud Platform project `smart-expense-gcp-prod`:

| Finding ID | Resource Name & Native Type | Category | Severity | Current Monthly Spend | Potential Monthly Savings | Derivation Formula & Pricing Basis | Evidence | Confidence |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `waste-gcp-dev-sql-ha-psql-smart-expense-gcp` | `psql-smart-expense-gcp` (`sqladmin.googleapis.com/Instance`) | `overprovisioned_database` | High | $158.04 | **$79.02** | 50% reduction by converting Regional High Availability to Zonal deployment on development tier. | Environment label `dev`; Regional HA active on Cloud SQL PostgreSQL with 1.8% CPU. | High |
| `waste-unattached-gcp-disk-smart-expense-disk-temp-orphaned` | `smart-expense-disk-temp-orphaned` (`compute.googleapis.com/Disk`) | `unattached_storage` | Medium | $5.25 | **$5.25** | 100% elimination of orphaned 100 GB `pd-standard` disk ($0.04/GB/mo + tax). | Attached users: `0`; last attach timestamp: None. | High |
| `waste-unused-gcp-ip-smart-expense-static-ip-unattached` | `smart-expense-static-ip-unattached` (`compute.googleapis.com/Address`) | `unattached_ip` | Low | $7.30 | **$0.00** | In-use reservation fee; capped to prevent duplicate accounting since already marked for deletion. | Status `RESERVED`, unattached to forwarding rule or compute instance. | High |
| **TOTAL** | **3 Discovered Waste Findings** | — | — | **$170.59** | **$84.27** | **$\sum \text{Savings} = \$84.27$** (Exactly matches `kpis.potential_monthly_savings`) | **Zero Residual Delta ($0.0000)** | **100% Verified** |

---

## 4. Account-Switch Control Deduplication

### Audit of Existing Switch Controls
1. **Global Header Switch Control (`TopNav.tsx`, lines 96–105)**:
   - Located in the persistent sticky top navigation bar.
   - Shows active connected scope badge: Provider (`AZURE` / `GCP`), display name, and resource scope ID.
   - Includes `<button onClick={onSwitchConnection}>Switch</button>` which triggers `setActiveConnection(null)`, returning the user safely to `ConnectCloudView`.
   - **Status**: Kept as the single, authoritative global account-switching action.

2. **Redundant Local Switch Button (`SectionCentralizedMonitoring.tsx`, lines 795–804)**:
   - Located in the sub-header of Monitoring next to the Scope Selector dropdown and Refresh button.
   - Redundantly duplicated the action of the top header bar, introducing visual clutter and competing actions.
   - **Status**: Removed. The provider selector tabs ("Microsoft Azure" and "Google Cloud") and the scope selector `<select>` dropdown remain intact for seamless scope browsing.

---

## 5. Non-Execution / Read-Only Policy Guarantees

All financial optimization metrics and remediation scripts surfaced in this platform conform strictly to the repository's Zero-Execution Policy:
1. **No Auto-Remediation**: The platform never executes Azure CLI (`az`) or Google Cloud SDK (`gcloud`) delete/modify commands automatically against customer subscriptions.
2. **Explicit Human Approval**: Remediation commands are presented solely as copyable advisory text in code blocks with pre-remediation considerations (e.g. taking disk snapshots before deletion).
3. **Savings Categorization**:
   - **Potential Monthly Savings**: Theoretical avoidable spend identified by FinOps rules.
   - **Recommended Monthly Savings**: High-confidence subset vetted for non-production environments.
   - **Realized Savings**: Explicitly displayed as **$0.00** across all cards because no automated destructive infrastructure actions have been performed.

---

## 6. Verification Suite Execution Results

All verification commands executed cleanly with zero errors:

```bash
# 1. Frontend Typecheck
npm --prefix frontend run typecheck
# Output: Exit Code 0 (tsc --noEmit clean)

# 2. Frontend Lint
npm --prefix frontend run lint
# Output: Exit Code 0 ("✔ No ESLint warnings or errors")

# 3. Frontend Production Build
npm --prefix frontend run build
# Output: Exit Code 0 ("✓ Compiled successfully", static optimization complete)

# 4. Backend Unit & Integration Tests
uv run --directory backend pytest tests/test_connections_and_tokens.py -v
# Output: Exit Code 0 (13 passed in 33.48s)

# 5. Backend Lint & Format
uv run --directory backend ruff check .
# Output: Exit Code 0 ("All checks passed!")
uv run --directory backend ruff format --check .
# Output: Exit Code 0 ("82 files already formatted")

# 6. Runtime Probing
curl -I http://localhost:3000 -> HTTP 200 OK
curl http://127.0.0.1:8001/api/v1/health -> HTTP 200 {"status":"ok"}
```

---

## 7. Sign-Off & Invariant Certification

- [x] **Spend Invariant**: Reconciles across all views to exact cent ($225.11 for Azure reference, $280.87 for GCP reference).
- [x] **Savings Invariant**: Sum of deduplicated findings equals header potential savings with $0.0000 residual delta ($118.27 for Azure, $84.27 for GCP).
- [x] **Annual Savings Invariant**: Exactly equals Monthly Savings &times; 12 ($1,419.24 for Azure, $1,011.24 for GCP).
- [x] **Realized Savings Invariant**: Strictly $0.00 under zero-execution read-only policy.
- [x] **Control Deduplication**: Redundant local "Switch Account" removed from Monitoring; global TopNav switch remains authoritative.
- [x] **Drill-Down Access**: Clickable KPI cards open rich `FinancialKpiDrawer` with mathematical definitions, inclusions/exclusions, itemized findings, CSV export, and telemetry links.
