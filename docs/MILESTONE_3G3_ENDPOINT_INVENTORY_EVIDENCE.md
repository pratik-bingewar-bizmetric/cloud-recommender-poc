# Milestone 3G.3 — Serving Endpoint Inventory Forensic Evidence & Classification Report

> **Status:** Audited & Codified  
> **Workspace ID:** `642006393507276` (`Azure Databricks Dev`)  
> **Author:** Staff FinOps Solutions Architect  
> **Milestone:** Milestone 3G.3 — Financial Reconciliation & Evidence Closure  

---

## 1. Objective & Investigation Scope

Earlier milestone reports (Milestone 3B, 3C, 3D, and 3E) reported that **27 Model Serving Endpoints** were discovered in Azure Databricks workspace `642006393507276`.
However, during the Milestone 3G.2 audit, `KNOWN_SERVING_ENDPOINTS` in `finops_analytics_service.py` was found to explicitly register **11 endpoints**.

The objective of this forensic investigation is to:
1. Examine historical discovery artifacts and saved logs to trace the full list of 27 endpoints.
2. Verify the exact boundary between verified canonical endpoints and unverified baseline records.
3. Enforce the Zero-Execution / Zero-Mutation policy prohibiting live network queries during audit.
4. Establish definitive documentation and classification for the entire endpoint inventory.

---

## 2. Investigation Findings & Artifact Lineage

### 2.1 The Discovery of 27 Endpoints in Milestone 3C
In `docs/MILESTONE_3C_AZURE_LIVE_TEST_REPORT.md` (Test #20), read-only discovery was executed via the Databricks Python SDK:
```python
endpoints = list(w.serving_endpoints.list())
# Result: len(endpoints) == 27
```
The SDK call returned a count of 27 endpoints present in the live workspace at that time.

In `docs/MILESTONE_6_PHASE_3A_DATABRICKS_CONNECTIVITY_REPORT.md` (line 183), the report summarized:
- 6 named high-profile foundation model endpoints (`databricks-claude-fable-5`, `databricks-claude-fable-5-1`, `databricks-meta-llama-3-1-405b-instruct`, `databricks-bge-large-en`, `databricks-dbrx-instruct`, `databricks-mixtral-8x7b-instruct`).
- Followed by: `*(21 additional active/ready endpoints)*`.

### 2.2 The 11 Verified Canonical Endpoints in Baseline Registry
When constructing `finops_analytics_service.py`, 11 verified endpoints were codified into `KNOWN_SERVING_ENDPOINTS`:

| # | Endpoint Identifier | Model Family / Workload | Verification Status |
| :-: | :--- | :--- | :--- |
| **1** | `databricks-claude-fable-5` | Anthropic Claude 3.5 Pay-per-token | **VERIFIED CANONICAL** |
| **2** | `databricks-claude-fable-5-1` | Anthropic Claude 3.5 Revision | **VERIFIED CANONICAL** |
| **3** | `databricks-meta-llama-3-1-405b-instruct` | Meta Llama 3.1 405B Heavy Inference | **VERIFIED CANONICAL** |
| **4** | `databricks-bge-large-en` | BAAI BGE Large Vector Embedding | **VERIFIED CANONICAL** |
| **5** | `databricks-dbrx-instruct` | Databricks DBRX MoE General | **VERIFIED CANONICAL** |
| **6** | `databricks-mixtral-8x7b-instruct` | Mistral Mixtral 8x7B MoE | **VERIFIED CANONICAL** |
| **7** | `dbrx-instruct-endpoint` | DBRX Secondary Provisioned | **VERIFIED CANONICAL** |
| **8** | `mpt-30b-instruct` | MPT 30B Fine-Tuned LLM | **VERIFIED CANONICAL** |
| **9** | `bge-large-en-v1.5` | BGE Embedding v1.5 Production | **VERIFIED CANONICAL** |
| **10** | `llama-3-70b-instruct` | Meta Llama 3 70B Fast Serving | **VERIFIED CANONICAL** |
| **11** | `mistral-large` | Mistral Large Production Endpoint | **VERIFIED CANONICAL** |

---

### 2.3 Quarantine of Historical Fixtures
In Milestone 3G.2, two historical endpoints used in prototype mock fixtures were identified and quarantined from live inventory:
- `deepseek-r1-endpoint` (Quarantined in `HISTORICAL_FIXTURE_ENDPOINTS`)
- `mistral-large-endpoint` (Quarantined in `HISTORICAL_FIXTURE_ENDPOINTS`)

Both identifiers are strictly rejected if queried in live workspace scope.

---

### 2.4 Status of the Remaining 16 Endpoints
The full list of the remaining 16 endpoint names was not codified in saved offline JSON fixtures. Under the repository's **Strict Human Approval & Zero-Execution Policy**:
> Coding agents and automated runners must NEVER initiate live cloud network calls or execute queries against customer environments during acceptance.

Because a live SDK call (`w.serving_endpoints.list()`) is prohibited, the remaining 16 endpoints cannot be reconstructed without making external network calls.

---

## 3. Official Classification & Audit Verdict

| Category | Count | Definition | Architectural Treatment |
| :--- | :-: | :--- | :--- |
| **Verified Canonical Endpoints** | **11** | Explicitly registered in `KNOWN_SERVING_ENDPOINTS`, accepted by exact-matching filter, and attributed in FinOps modules. | **Production Accepted** |
| **Unverified Baseline Endpoints** | **16** | Discovered in earlier live scan count (27 total), but names not frozen in offline fixtures. | **Unverified Baseline** (requires future live read query upon customer authorization) |
| **Quarantined Historical Fixtures** | **2** | Preserved in `HISTORICAL_FIXTURE_ENDPOINTS` for offline unit testing; blocked from production attribution. | **Quarantined** |

---

## 4. Test Verification

Automated test `backend/tests/test_milestone_3g3_reconciliation.py::test_serving_endpoint_inventory_canonical_closure` verifies:
- `KNOWN_SERVING_ENDPOINTS` contains exactly 11 canonical endpoints.
- All 11 endpoints resolve to category `serving` with `is_unknown=False`.
- Any unverified or synthetic endpoint ID returns `is_unknown=True` and falls into the typed `NO_DATA` state.

