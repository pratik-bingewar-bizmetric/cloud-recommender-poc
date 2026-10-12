# ADR 0003: Cloud Catalog Schema and Offline-First Dataset

| Status | Accepted |
| :--- | :--- |
| **Date** | 2026-10-12 |
| **Authors** | Architecture Working Group |
| **Deciders** | Lead Cloud Architect, FinOps Lead |

---

## Context & Problem Statement

Real-time cloud pricing APIs (such as AWS Price List API, Azure Retail Prices API, and GCP Cloud Billing Catalog) are notoriously complex:
- AWS Price List API involves multi-gigabyte JSON/CSV indexes.
- Rate limits and transient network failures make live API queries slow and fragile during user interaction.
- Calling external pricing APIs requires live network connections and in some cases authenticated cloud credentials.
- Test suites in CI environments cannot depend on external cloud billing availability.

---

## Decision

We will implement an **Offline-First, Versioned JSON Catalog** bundled directly within the repository under `backend/app/catalog/data/`:
- `aws_services.json`
- `azure_services.json`
- `gcp_services.json`

### Key Architectural Guidelines:
1. **Curated Heuristic Baseline:** Each catalog entry contains baseline hourly rates, storage rates per GB/month, network egress costs per GB, and standard SLA percentages based on official hyperscaler documentation.
2. **In-Memory Query Engine:** On application startup, the JSON files are validated against the `CloudServiceItem` Pydantic model and indexed in memory for sub-millisecond filtering.
3. **Pluggable Updates:** Updating service capabilities or adding new cloud regions is done by modifying or appending JSON data files without touching Python business logic.
4. **Estimated Cost Labeling:** All cost figures are explicitly presented with the `ESTIMATED_BASELINE` label, applying a default +15% safety buffer for operational realism.

---

## Consequences

### Positive
- The application runs 100% offline with zero dependencies on external cloud provider networks.
- Deterministic, repeatable test runs in CI.
- Millisecond query latency.

### Negative / Trade-offs
- Pricing does not automatically reflect intraday changes or complex volume discount tiers (e.g. Enterprise Agreements, AWS Savings Plans) without periodic manual or automated catalog sync scripts.
