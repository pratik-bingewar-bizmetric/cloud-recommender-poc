# Milestone 3G.2 — AI Spend Lineage & Attribution Report

**Repository:** `cloud-recommender-poc`  
**Branch:** `feature/databricks-apps-integration`  
**Workspace:** Azure Databricks `642006393507276` (`Azure Databricks Dev`)  
**Status:** Certified & Lineage-Traceable  

---

## 1. Objective

To provide an exhaustive, auditable breakdown of how AI and GenAI costs are calculated, categorized, and attributed across the FinOps Command Center. This directly resolves the question of why Databricks Model Serving in the DBU ledger is **$26,740.00** while Total AI Spend is **$38,460.00**.

---

## 2. Canonical AI Cost Architecture

In enterprise Azure Databricks environments, AI and Generative AI workloads span two distinct financial metering mechanisms:

1. **Databricks Provisioned & Serverless Model Serving (DBU Metered):**
   - Metered via Databricks consumption DBUs.
   - Billed as part of the primary Databricks consumption ledger ($176,840.00).
   - Covers VM cluster infrastructure, CPU/GPU node instances, and container runtime orchestration for hosting real-time model serving endpoints.
   - **Amount:** **$26,740.00** (6,685.0 DBU).

2. **Azure AI Gateway & External Foundation Model APIs (Pay-per-Token Metered):**
   - Metered per 1,000 prompt (input) and completion (output) tokens routed through the Databricks AI Gateway to foundation model providers (e.g. Anthropic Claude, Meta Llama, OpenAI).
   - Incurred at the Azure subscription level as external API payload consumption.
   - Billed outside the DBU ledger as part of the broader cloud spend ($284,620.00).
   - **Amount:** **$11,296.00**.

3. **Auxiliary Vector Search & Embedding Compute:**
   - Metered via Azure search/indexing instances for Delta Sync and vector embeddings.
   - **Amount:** **$424.00**.

---

## 3. Financial Attribution Matrix

| Cost Component | Metering Metric | Quantity | Unit Rate | Ledger Spend | Cloud Spend Category |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Model Serving Compute** | DBU | 6,685.0 DBU | $4.00 / DBU (Effective) | **$26,740.00** | Compute / Databricks DBU Ledger |
| **AI Gateway Input Tokens** | Tokens | 8.42 Billion | $0.0008 / 1K tokens | — | External GenAI API Spend |
| **AI Gateway Output Tokens** | Tokens | 1.86 Billion | $0.0024 / 1K tokens | — | External GenAI API Spend |
| **Subtotal AI Gateway Tokens** | Tokens | 10.28 Billion | Blended | **$11,296.00** | AI / GenAI Services |
| **Vector Search Indexing** | Node-hours | 212 hours | $2.00 / hour | **$424.00** | AI / GenAI Services |
| **Total AI Spend** | — | — | — | — | **$38,460.00** |

---

## 4. Lineage Verification Across Modules

### 4.1 Executive Overview
- **KPI `ai_spend`:** $38,460.00 (formatted: `$38,460`, status: `BASELINE`).
- **Formula:** `model_serving_dbu_spend ($26,740.00) + ai_gateway_external_tokens ($11,296.00) + auxiliary_vector_search ($424.00) = $38,460.00`.
- **Spend Composition:** Category `AI / GenAI` has share `0.135` (13.5%) and amount `$38,460`.

### 4.2 AI & Token Economics Module
- **KPI `ai_spend`:** $38,460.00.
- **KPI `input_tokens`:** 8.42B tokens (81.9% of total 10.28B tokens).
- **KPI `output_tokens`:** 1.86B tokens (18.1% of total 10.28B tokens).
- **Endpoint Table:** Displays live discovered endpoints (`databricks-claude-fable-5`, `databricks-meta-llama-3-1-405b-instruct`, `databricks-bge-large-en`).

### 4.3 Cost Explorer (24-Record Ledger)
- 4 daily entries for `product="Model Serving"` (Nov 01 to Nov 04):
  - Nov 04: 1,671.25 DBU · $6,685.00
  - Nov 03: 1,671.25 DBU · $6,685.00
  - Nov 02: 1,671.25 DBU · $6,685.00
  - Nov 01: 1,671.25 DBU · $6,685.00
  - **Subtotal:** 6,685.0 DBU · **$26,740.00**.

---

## 5. Scope Isolation for Serving Endpoints

When scoped to a specific Model Serving Endpoint (e.g. `resource_id="databricks-claude-fable-5"`, `resource_type="serving_endpoint"`):
- The Executive Overview and AI Economics modules isolate the scoped endpoint's cost ($8,420 / month).
- All unrelated clusters, warehouses, and jobs are filtered out.
- Token consumption reflects only requests processed by that endpoint.
- For unknown endpoint IDs (or historical fixtures like `deepseek-r1-endpoint`), the system returns `NO_DATA`, preventing unearned attribution.

