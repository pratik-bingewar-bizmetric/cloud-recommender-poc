# AWS Phase 2 — Implementation & Architecture Report

> **Target Cloud Environment:** AWS Account `435305479688`  
> **Primary Inspected Region:** `eu-north-1` (Stockholm) | **Secondary Region:** `us-east-1` (N. Virginia)  
> **Security & Governance Invariant:** 100% Read-Only, Pure-Python SigV4, Zero Infrastructure Mutations  
> **Status:** Implementation Complete & Validated  

---

## 1. Executive Summary

AWS Phase 2 expands the foundational connectivity and discovery established in Phase 1 and verified in Phase 1.1 by implementing a production-grade Cost Intelligence, CloudWatch Telemetry, and Resource Utilization platform.

All services have been engineered following strict FinOps principles:
- **Deterministic Pricing Engine:** Avoids generative hallucinations by querying official AWS Price List APIs with an in-memory TTL cache and an offline static fallback catalog.
- **Fail-Closed Cost Explorer Normalization:** Preserves exact financial truth—never fabricating zeros or assuming zero-cost when permissions are withheld or data is missing.
- **Strict Metric Taxonomy:** Enforces that EC2 memory utilization and container performance cannot be measured without explicitly deployed agents, labeling them unambiguously as `INSTRUMENTATION_REQUIRED`.
- **Zero Mutation Guardrails:** CUR bulk ingestion and S3/Athena modifications remain strictly deferred, and background polling is disabled by default to guard against accidental API charges.

---

## 2. Core Architecture & Implemented Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          AWS FinOps Control Plane                           │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
     ┌─────────────────────────────────┼─────────────────────────────────┐
     │                                 │                                 │
     ▼                                 ▼                                 ▼
┌─────────────────────────┐ ┌─────────────────────────┐ ┌─────────────────────────┐
│ AwsCostExplorerService  │ │ AwsCloudWatchMetricsSvc │ │    AwsPricingService    │
│  - ce:GetCostAndUsage   │ │  - GetMetricData (XML)  │ │  - Price List Catalog   │
│  - ce:GetCostForecast   │ │  - 24h / 7d / 30d stats │ │  - Location Mapping     │
│  - MTD & MoM Delta      │ │  - Lambda & S3 metrics  │ │  - In-Memory TTL Cache  │
│  - Dimension Breakdown  │ │  - EC2 Memory Gating    │ │  - Static Fallback Rate │
└─────────────────────────┘ └─────────────────────────┘ └─────────────────────────┘
     │                                 │                                 │
     └─────────────────────────────────┼─────────────────────────────────┘
                                       │
                                       ▼
                         ┌───────────────────────────┐
                         │       AwsCurService       │
                         │  - S3 Location Inspection │
                         │  - Manifest Validation    │
                         │  - Bulk Ingestion DEFERRED│
                         └───────────────────────────┘
```

### 2.1 Backend Micro-Services
1. **`AwsCostExplorerService` (`backend/src/cloud_recommender/services/aws/cost_explorer_service.py`):**
   - Interacts with `https://ce.us-east-1.amazonaws.com/` signed with AWS SigV4 (`service="ce"`).
   - Supports `UnblendedCost`, `AmortizedCost`, `NetUnblendedCost`, and `NetAmortizedCost`.
   - Aggregates Month-to-Date (MTD) spend, previous complete month, and comparable previous month-to-date with MoM percentage change.
   - Categorizes group dimensions (`SERVICE`, `REGION`, `USAGE_TYPE`, `LINKED_ACCOUNT`).
   - Retrieves confidence interval forecasts for month-end expenditure.

2. **`AwsCloudWatchMetricsService` (`backend/src/cloud_recommender/services/aws/cloudwatch_service.py`):**
   - Pure-Python SigV4 querying `https://monitoring.{region}.amazonaws.com/` via XML POST.
   - Resource-specific metric mapping for Lambda (`Invocations`, `Duration`, `Errors`, `Throttles`), EC2 (`CPUUtilization`, `NetworkIn`, `NetworkOut`, `DiskReadOps`, `DiskWriteOps`), RDS, EBS, NAT Gateways, and S3.
   - Strictly flags EC2 Memory utilization as `INSTRUMENTATION_REQUIRED`.
   - Respects S3 storage metrics daily aggregation boundary without triggering chargeable request metrics.

3. **`AwsPricingService` (`backend/src/cloud_recommender/services/aws/pricing_service.py`):**
   - Queries `https://api.pricing.us-east-1.amazonaws.com/` with SigV4 (`service="pricing"`).
   - Maps standard AWS region codes (`eu-north-1`) to Price List location strings (`EU (Stockholm)`).
   - In-memory TTL caching prevents redundant API roundtrips.
   - Deterministic offline static catalog fallback ensures offline test suites and network-isolated environments function seamlessly.

4. **`AwsCurService` (`backend/src/cloud_recommender/services/aws/cur_service.py`):**
   - Non-invasive inspection of destination bucket `finops-cost-reports-435305479688`.
   - Inspects `?location` constraint and validates manifest presence via `ListObjectsV2`.
   - Strictly marks bulk data ingestion status as `DEFERRED` per FinOps guardrails.

### 2.2 API Layer (`/api/v1/aws/*`)
- `GET /cost/summary`: Monthly overview, MTD spend, MoM delta, daily trend, top services, and forecast.
- `GET /cost/trend`: Daily or monthly spend time-series for custom date ranges.
- `GET /cost/breakdown`: Spend breakdown grouped by service, region, or usage type.
- `GET /cost/forecast`: Month-end expenditure forecast with upper and lower prediction bounds.
- `GET /metrics/summary`: Account-wide utilization overview across top discovered resources.
- `GET /metrics/{resource_id}`: Dedicated CloudWatch time-series for an individual resource.
- `GET /pricing/estimate`: Retail catalog on-demand pricing estimate for a resource.
- `GET /cur/readiness`: Status of Cost & Usage Reports and destination S3 bucket.
- `GET /sync/health`: Data freshness, synchronization status, and chargeable API call counters.

---

## 3. Frontend Dashboard Architecture

The frontend component `AwsResourceDiscoveryView.tsx` has been upgraded to a 7-tab FinOps command console:

1. **Tab 1: AWS Overview:** Executive KPIs, connection state, verified inventory counts, active security findings, and direct links to downstream modules.
2. **Tab 2: Cost Intelligence:** Interactive MTD spend indicator, MoM trend cards, daily spend chart, top-10 services breakdown, and month-end forecast banner.
3. **Tab 3: Resource Telemetry:** Historical utilization graphs, CloudWatch telemetry series, and instrumentation requirement indicators.
4. **Tab 4: Resource Inventory:** Filterable resource grid with category filters, region filters, evidence badges (`VERIFIED_LIVE`, `VERIFIED_MOCK`), and detail drawer modal.
5. **Tab 5: Findings & Security:** Route table blackhole alerts, IAM permission gaps, and unattached resource alerts with explicit remediation commands.
6. **Tab 6: Service Probes & IAM:** 11-service probe matrix detailing live probe results, required IAM permissions, and endpoints.
7. **Tab 7: Configuration & Scope:** Regional inspection scope toggles, telemetry lookback selectors (24h / 7d / 30d), and API query budget safety controls.

---

## 4. Verification & Validation Summary

- **Unit & Integration Suite:** 10 dedicated automated tests in `backend/tests/test_aws_phase2.py` passing 100%.
- **Regression Suite:** AWS Phase 1 (`test_aws_phase1.py`) and GCP Phase 1 (`test_gcp_phase1_service_account.py`) passing with zero regressions.
- **Code Quality:** PEP 8 enforced via `ruff check` and `ruff format` with zero warnings or errors.
- **Frontend Verification:** ESLint clean (`No ESLint warnings or errors`) and TypeScript compilation (`tsc --noEmit`) passing cleanly.

