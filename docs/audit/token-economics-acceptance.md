# Token Economics Phase 2 — Final Acceptance & Cost Reconciliation Report

> **Status:** Fully Reconciled & Accepted  
> **Repository:** `cloud-recommender-poc`  
> **Evaluation Date:** October 2026  
> **Target Scope:** Azure Subscription `f718c261-ab85-49fd-907e-99c022cc2aeb`  
> **Safety Mode:** Strictly Read-Only (Zero Cloud Mutations, Zero Infrastructure Modifications)  

---

## 1. Executive Summary & Root-Cause Resolution

During initial Phase 2 telemetry probing against live Azure subscription `f718c261-ab85-49fd-907e-99c022cc2aeb`, an apparent discrepancy was observed between raw metric queries and the aggregated figures reported in early session summaries.

A rigorous, evidence-based code and raw HTTP telemetry audit revealed two key findings:
1. **Metric Aliasing & Double Counting:** Azure Resource Manager's Metrics API (`microsoft.insights/metrics`, API version `2023-10-01`) returns both legacy inference metric names (`ProcessedPromptTokens`, `GeneratedTokens`, `TokenTransaction`) and modern usage metric names (`InputTokens`, `OutputTokens`, `TotalTokens`) as mirrored timeseries. Summing across both sets resulted in exactly $2\times$ duplication of prompt, completion, and transaction counts.
2. **Resource Scope & Sub-Resource Isolation:** Azure AI Foundry project sub-resources (`Microsoft.CognitiveServices/accounts/{account}/projects/{proj}`) and non-generative services (`FormRecognizer`, `SpeechServices`) do not expose platform token metrics, returning HTTP 400 when queried.

Both defects have been resolved in [`monitoring_service.py`](file:///c:/Users/Admin/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/src/cloud_recommender/services/monitoring/monitoring_service.py) via canonical metric selection, child-project exclusion, and exact mathematical cost reconciliation. All numbers are reproducible from live Azure provider data.

---

## 2. Raw Provider Datapoints & Aggregate Token Reproduction

A read-only inspection script (`scratch/inspect_raw_points.py`) probed all Cognitive Services accounts in subscription `f718c261-ab85-49fd-907e-99c022cc2aeb` over a 7-day window (`7d`, `PT1H` interval, `Total` aggregation).

### 2.1 Raw Timeseries Datapoints

#### Resource A: `rg-cloud-recomender`
*Resource ID:* `/subscriptions/f718c261-ab85-49fd-907e-99c022cc2aeb/resourceGroups/rg-cloud-recomender/providers/Microsoft.CognitiveServices/accounts/rg-cloud-recomender`

| Timestamp (UTC) | Metric Name | Raw Value | Metric Category | Canonical Selected |
| :--- | :--- | :--- | :--- | :--- |
| `2026-10-16T06:26:00Z` | `ProcessedPromptTokens` | **1,120** | Prompt | Yes |
| `2026-10-16T06:26:00Z` | `InputTokens` | 1,120 | Prompt (Alias) | Suppressed (Duplicate) |
| `2026-10-16T06:26:00Z` | `GeneratedTokens` | **4,633** | Completion | Yes |
| `2026-10-16T06:26:00Z` | `OutputTokens` | 4,633 | Completion (Alias) | Suppressed (Duplicate) |
| `2026-10-16T06:26:00Z` | `TokenTransaction` | **5,753** | Total Transaction | Yes ($1,120 + 4,633 = 5,753$) |
| `2026-10-16T06:26:00Z` | `TotalTokens` | 5,753 | Total (Alias) | Suppressed (Duplicate) |
| `2026-10-16T09:26:00Z` | `ProcessedPromptTokens` | **1,073** | Prompt | Yes |
| `2026-10-16T09:26:00Z` | `InputTokens` | 1,073 | Prompt (Alias) | Suppressed (Duplicate) |
| `2026-10-16T09:26:00Z` | `GeneratedTokens` | **3,990** | Completion | Yes |
| `2026-10-16T09:26:00Z` | `OutputTokens` | 3,990 | Completion (Alias) | Suppressed (Duplicate) |
| `2026-10-16T09:26:00Z` | `TokenTransaction` | **5,063** | Total Transaction | Yes ($1,073 + 3,990 = 5,063$) |
| `2026-10-16T09:26:00Z` | `TotalTokens` | 5,063 | Total (Alias) | Suppressed (Duplicate) |

- **Subtotal Prompt Tokens:** $1,120 + 1,073 = \mathbf{2,193}$
- **Subtotal Completion Tokens:** $4,633 + 3,990 = \mathbf{8,623}$
- **Subtotal Total Tokens:** $5,753 + 5,063 = \mathbf{10,816}$  
  *(Check: $2,193 + 8,623 = 10,816 \checkmark$)*

---

#### Resource B: `rg-telecom-rag-poc`
*Resource ID:* `/subscriptions/f718c261-ab85-49fd-907e-99c022cc2aeb/resourceGroups/rg-telecom-rag-poc/providers/Microsoft.CognitiveServices/accounts/rg-telecom-rag-poc`

| Timestamp (UTC) | Metric Name | Raw Value | Metric Category | Canonical Selected |
| :--- | :--- | :--- | :--- | :--- |
| `2026-10-21T09:26:00Z` | `ProcessedPromptTokens` | **1,630** | Prompt | Yes |
| `2026-10-21T09:26:00Z` | `InputTokens` | 1,630 | Prompt (Alias) | Suppressed (Duplicate) |
| `2026-10-21T09:26:00Z` | `GeneratedTokens` | **691** | Completion | Yes |
| `2026-10-21T09:26:00Z` | `OutputTokens` | 691 | Completion (Alias) | Suppressed (Duplicate) |
| `2026-10-21T09:26:00Z` | `TokenTransaction` | **2,321** | Total Transaction | Yes ($1,630 + 691 = 2,321$) |
| `2026-10-21T09:26:00Z` | `TotalTokens` | 2,321 | Total (Alias) | Suppressed (Duplicate) |
| `2026-10-21T11:26:00Z` | `ProcessedPromptTokens` | **315** | Prompt | Yes |
| `2026-10-21T11:26:00Z` | `InputTokens` | 315 | Prompt (Alias) | Suppressed (Duplicate) |
| `2026-10-21T11:26:00Z` | `GeneratedTokens` | **61** | Completion | Yes |
| `2026-10-21T11:26:00Z` | `OutputTokens` | 61 | Completion (Alias) | Suppressed (Duplicate) |
| `2026-10-21T11:26:00Z` | `TokenTransaction` | **376** | Total Transaction | Yes ($315 + 61 = 376$) |
| `2026-10-21T11:26:00Z` | `TotalTokens` | 376 | Total (Alias) | Suppressed (Duplicate) |

- **Subtotal Prompt Tokens:** $1,630 + 315 = \mathbf{1,945}$
- **Subtotal Completion Tokens:** $691 + 61 = \mathbf{752}$
- **Subtotal Total Tokens:** $2,321 + 376 = \mathbf{2,697}$  
  *(Check: $1,945 + 752 = 2,697 \checkmark$)*

---

#### Other Discovered Subscription Accounts
- `smart-expense-ai-bizmetric` (`rg-smart-expense`): HTTP 200, **0 tokens** across 168 intervals (measured zero).
- `pratikbingewar-5556-resource` (`rg-smart-expense`): HTTP 200, **0 tokens** across 168 intervals (measured zero).
- `panasonic-voice-ai` (`rg-panasonic-voice`): HTTP 200, **0 tokens** across 168 intervals (measured zero).
- `smart-expense-docintel` (`FormRecognizer`): HTTP 400 (unsupported metric names; safely omitted).
- `smart-expense-speech` (`SpeechServices`): HTTP 400 (unsupported metric names; safely omitted).
- `*/projects/*` sub-resources: Excluded from query scope as Azure Monitor metrics operate at the parent account level.

---

### 2.2 Reconciled Aggregate Totals

$$\text{Total Prompt Tokens} = 2,193 + 1,945 = \mathbf{4,138}$$
$$\text{Total Completion Tokens} = 8,623 + 752 = \mathbf{9,375}$$
$$\text{Total Ingested Tokens} = 10,816 + 2,697 = \mathbf{13,513}$$

---

## 3. Exact Pricing Assumptions & Mathematical Formula

### 3.1 Model Unit Rates & Source
Azure Monitor account-level platform metrics provide aggregated prompt and completion volume per account without per-request model SKU attribution (which requires Log Analytics workspace diagnostic settings).

The FinOps engine applies the **GPT-4o standard public tier rate** as a uniform baseline across all live observed tokens:
- **Prompt Rate ($R_{\text{prompt}}$):** $\$2.5000$ per 1,000,000 tokens ($\$0.00000250$ per token)
- **Completion Rate ($R_{\text{completion}}$):** $\$10.0000$ per 1,000,000 tokens ($\$0.00001000$ per token)
- **Rate Source:** Explicitly labeled as `"Azure OpenAI Public Tier (GPT-4o Baseline Rate)"`

### 3.2 Exact Calculation Formula

$$\text{Cost}_{\text{USD}} = \frac{(P \times R_{\text{prompt}}) + (C \times R_{\text{completion}})}{1,000,000}$$

$$\text{Final Cost} = \text{quantize}\left(\text{Cost}_{\text{USD}}, 0.0001, \text{ROUND\_HALF\_UP}\right)$$

---

## 4. Per-Resource Cost Reconciliation

### 4.1 Resource: `rg-cloud-recomender`

$$\text{Prompt Cost} = \frac{2,193 \times 2.5000}{1,000,000} = \frac{5,482.5}{1,000,000} = \$0.0054825$$

$$\text{Completion Cost} = \frac{8,623 \times 10.0000}{1,000,000} = \frac{86,230.0}{1,000,000} = \$0.0862300$$

$$\text{Subtotal Cost} = \$0.0054825 + \$0.0862300 = \$0.0917125$$

$$\text{Quantized Cost} = \mathbf{\$0.0917}$$

---

### 4.2 Resource: `rg-telecom-rag-poc`

$$\text{Prompt Cost} = \frac{1,945 \times 2.5000}{1,000,000} = \frac{4,862.5}{1,000,000} = \$0.0048625$$

$$\text{Completion Cost} = \frac{752 \times 10.0000}{1,000,000} = \frac{7,520.0}{1,000,000} = \$0.0075200$$

$$\text{Subtotal Cost} = \$0.0048625 + \$0.0075200 = \$0.0123825$$

$$\text{Quantized Cost} = \mathbf{\$0.0124}$$

---

### 4.3 Aggregate Subscription Cost

$$\text{Total Cost} = \$0.0917125 + \$0.0123825 = \$0.1040950$$

$$\text{Quantized Aggregate Cost} = \mathbf{\$0.1041}$$

*(Check: $\$0.0917 + \$0.0124 = \$0.1041 \checkmark$)*

---

## 5. Telemetry Provenance: Live Provider Data vs Estimates

| Telemetry Element | Provenance Category | Live Provider Data | Sourced or Estimated Baseline |
| :--- | :--- | :--- | :--- |
| **Token Counts** | Live Provider Telemetry | **100% Real** (Azure Monitor Metrics API `2023-10-01`) | No estimation. Directly queried from ARM timeseries. |
| **Hourly Trend Timeseries** | Live Provider Telemetry | **100% Real** (Hourly timeseries timestamps & buckets) | No interpolation or simulation. |
| **Workload Attribution** | Live Provider Telemetry | **100% Real** (Mapped to ARM Resource Group IDs) | Exactly matches Azure resource hierarchy. |
| **Unit Rates** | Reference Price Baseline | Sourced from official Azure OpenAI pricing schedule | Fixed at \$2.50 / \$10.00 (GPT-4o reference baseline). |
| **Estimated Cost** | Deterministic Calculation | Derived directly from real token counts $\times$ baseline rates | Exact formula without generative guessing. |
| **Benchmark Preview** | Isolated Fixture | Strictly segregated behind UI preview toggle | Zero leakage into live dashboard KPIs or API responses. |

---

## 6. Regression Testing & Acceptance Test Results

Two new regression tests were added in [`test_connections_and_tokens.py`](file:///c:/Users/Admin/OneDrive%20-%20bizmetric.com/Desktop/Workspace/cloud-recommender-poc/backend/tests/test_connections_and_tokens.py):
1. `test_token_economics_live_telemetry_with_positive_volume_and_no_double_counting`: Returns all 6 metric aliases concurrently; asserts prompt is NOT doubled ($1,630$), completion is NOT doubled ($691$), total is NOT doubled ($2,321$), and cost equals $\$0.0110$.
2. `test_token_economics_multi_resource_reconciliation_and_child_exclusion`: Simulates multiple active accounts alongside child project sub-resources; asserts child project endpoints are never queried, token counts aggregate to $13,513$, and cost reconciles to $\$0.1041$.

### Validation Suite Pass Evidence

```text
# 1. Targeted Connection & Token Economics Suite
uv run --directory backend pytest tests/test_connections_and_tokens.py -v
============================= 9 passed in 36.64s ==============================

# 2. Complete Backend Test Suite
uv run --directory backend pytest tests/
================= 160 passed, 2 skipped in 214.65s (0:03:34) ==================

# 3. Static Type Analysis
uv run --directory backend mypy src/ tests/
Success: no issues found in 78 source files

# 4. Code Style & Formatting
uv run --directory backend ruff check src/ tests/
All checks passed!

uv run --directory backend ruff format --check src/ tests/
78 files already formatted

# 5. Frontend Quality Checks
npm --prefix frontend run typecheck
✔ tsc --noEmit: Clean (0 errors)

npm --prefix frontend run lint -- --max-warnings=0
✔ No ESLint warnings or errors
```

---

## 7. Remaining Limitations & Recommendations

1. **Per-Model SKU Attribution via Diagnostic Settings:**
   - *Current Limitation:* ARM Platform Metrics (`microsoft.insights/metrics`) do not break down token consumption by individual model deployment (e.g. distinguishing `gpt-4o` from `gpt-4o-mini` on the same resource) without Log Analytics export.
   - *Recommendation:* When deeper model-level granularity is needed by customers, instruct them via the in-app Diagnostic Setup Guide to route `RequestResponse` logs to an Azure Log Analytics Workspace.
2. **Read-Only & Zero-Execution Assurance:**
   - The platform strictly adheres to read-only compliance (`GET` requests only). No customer resources, diagnostic settings, IAM roles, or Azure OpenAI configurations were modified during probing or acceptance verification. All changes remain uncommitted and unpushed.

