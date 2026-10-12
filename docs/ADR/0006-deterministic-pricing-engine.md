# ADR 0006: Deterministic Multi-Cloud Pricing Engine with Official API Integration and Local Cache

| Status | Accepted |
| :--- | :--- |
| **Date** | 2026-10-12 |
| **Authors** | Architecture Working Group |
| **Deciders** | Lead Cloud Architect, FinOps Practice Lead |

---

## Context & Problem Statement

Accurate cost estimation is central to both Phase A (multi-cloud comparison) and Phase B (savings forecasting).

Generative AI models are notoriously inaccurate at mathematical calculation and frequently hallucinate cloud SKU pricing, disk throughput tariffs, and data egress rates. Furthermore, cloud pricing models are complex: hourly rates, reserved instance discounts, storage tiering, and region-dependent variables must be calculated with mathematical determinism.

Relying purely on real-time external pricing APIs during user interactions also introduces risk:
- Rate limits on public endpoints (e.g. Azure Retail Prices API throttles excessive queries).
- Network latency causes slow UI rendering.
- Offline environments (e.g. local developer laptops, CI runners) fail when external APIs are unreachable.

---

## Decision

We implement a **Deterministic Pricing Engine with Official Provider Sources and Local Caching**:

1. **Official Provider Integration:**
   - **Azure:** Azure Retail Prices API (`https://prices.azure.com/api/retail/prices`) querying official SKUs and retail rates.
   - **AWS:** AWS Price List API / Price List Query API.
   - **GCP:** Google Cloud Billing Catalog API (`cloudbilling.googleapis.com`).
2. **Deterministic Calculation Core:**
   - Pure Python mathematical models calculate monthly and annual compute, database, storage, and networking bills based on explicit workload parameters.
   - Assumptions (e.g., 730 hours/month, on-demand vs 1-year reserved, +15% safety buffer) are recorded explicitly in every calculation result.
3. **Local Cache & Offline Fallback:**
   - Pricing responses are cached locally in JSON / SQLite under `backend/app/pricing/cache/` with a 24-hour TTL.
   - If live API calls fail or `OFFLINE_PRICING_MODE=true`, the engine automatically serves verified benchmark pricing from bundled static datasets.

---

## Consequences

### Positive
- 100% mathematical accuracy and complete traceability to official cloud pricing records.
- Zero price hallucination.
- Fast sub-second pricing evaluations via local caching.
- Full offline testability in CI and air-gapped environments.

### Negative / Trade-offs
- Local cache must be refreshed periodically to capture changes in cloud provider pricing catalogs.
