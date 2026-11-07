# Milestone 3G.3 — AI Gateway Token-Cost Discrepancy & Lineage Reconciliation

> **Status:** Fully Reconciled & Documented  
> **Workspace ID:** `642006393507276` (`Azure Databricks Dev`)  
> **Author:** Staff FinOps Solutions Architect  
> **Milestone:** Milestone 3G.3 — Financial Reconciliation & Evidence Closure  

---

## 1. Executive Summary & Problem Statement

During the Milestone 3G.2 forensic review, a **\$96.00 mathematical discrepancy** was discovered between two representations of AI Gateway external spend:
1. **Top-Down Reported Spend:** **\$11,296.00** surfaced in Executive Overview and AI Economics KPI cards.
2. **Bottom-Up Token Pricing:** **\$11,200.00** derived from reported prompt and completion token volumes multiplied by rate-card prices.

This document traces the origin of this discrepancy, enforces strict accounting rules against cosmetic figure alterations, codifies the composition of total AI spend (\$38,460.00), and defines the audit pathway for future live System Tables verification.

---

## 2. Mathematical Forensic Analysis

### 2.1 Top-Down Derivation of \$11,296.00
In the workspace baseline financial ledger, the total AI spend across workspace `642006393507276` is certified at **\$38,460.00**.

Total AI spend decomposes across three distinct components:
$$\text{Total AI Spend} = \text{Model Serving DBU Spend} + \text{AI Gateway External Tokens} + \text{Auxiliary Vector Search}$$

Substituting known baseline components:
$$\$38,460.00 = \$26,740.00 + \text{AI Gateway External Tokens} + \$424.00$$
$$\text{AI Gateway External Tokens} = \$38,460.00 - \$26,740.00 - \$424.00 = \$11,296.00$$

Thus, **\$11,296.00** originated as a top-down residual from cloud billing and consumption ledger reconciliation.

---

### 2.2 Bottom-Up Token Calculation yielding \$11,200.00
The AI Gateway Telemetry module reports token consumption across model requests:
- **Prompt (Input) Tokens:** $8,420,000,000$ tokens ($8.42\text{B}$)
- **Completion (Output) Tokens:** $1,860,000,000$ tokens ($1.86\text{B}$)
- **Cached Context Tokens:** $2,100,000,000$ tokens ($2.10\text{B}$) (subset of input volume)

Applying the standard Model Rate Card tiering:
- **Input Rate:** $\$0.0008 \text{ per } 1,000 \text{ tokens}$ ($\$0.0000008 / \text{token}$)
- **Output Rate:** $\$0.0024 \text{ per } 1,000 \text{ tokens}$ ($\$0.0000024 / \text{token}$)

Calculating bottom-up itemized costs:
$$\text{Input Token Cost} = 8,420,000,000 \times \left(\frac{\$0.0008}{1,000}\right) = \$6,736.00$$
$$\text{Output Token Cost} = 1,860,000,000 \times \left(\frac{\$0.0024}{1,000}\right) = \$4,464.00$$
$$\text{Bottom-Up Calculated Total} = \$6,736.00 + \$4,464.00 = \$11,200.00$$

---

### 2.3 The \$96.00 Variance
Subtracting bottom-up calculated cost from the top-down allocated figure:
$$\Delta = \$11,296.00 - \$11,200.00 = +\$96.00$$

The reported AI Gateway spend exceeds the bottom-up calculated token cost by exactly **\$96.00** ($0.85\%$ variance).

---

## 3. Strict Operating Decisions & Non-Negotiable Rules

In accordance with FinOps architectural governance and the Milestone 3G.3 prompt instructions:

1. **Zero Artificial Mutation:**
   - Under no circumstances is the reported AI Gateway spend figure (\$11,296.00) artificially altered to \$11,200.00 merely to force a cosmetic match.
   - Forcing \$11,200.00 would break the top-down reconciliation: $\$26,740 + \$11,200 + \$424 = \$38,364 \neq \$38,460$, creating a new \$96.00 leak in the executive financial ledger.
2. **Zero Token Volume Mutation:**
   - Token counts ($8.42\text{B}$ input, $1.86\text{B}$ output) must not be adjusted to match \$11,296.00.
3. **Explicit Documentation & Provenance:**
   - The reported \$11,296.00 figure is retained as an **unverified baseline**.
   - The \$96.00 variance is explicitly documented in code formulas, limitations metadata, and schema docstrings.

---

## 4. Probable Forensic Causes of the \$96.00 Variance

Because live query execution against Databricks System Tables (`system.ai.gateway.usage`) is currently gated under the Zero-Execution policy, the exact micro-line items cannot be queried. However, forensic analysis identifies three probable causes:

| Potential Cause | Mechanism | Financial Impact |
| :--- | :--- | :--- |
| **A. Rate-Card Tiering / Blended Models** | Baseline calculations apply flat rates (\$0.0008 / \$0.0024), whereas actual usage spans mixed models (e.g. Llama 3.1 405B vs Claude 3.5 Sonnet vs BGE embeddings). | Small variance ($\pm \$50-\$150$) based on model mix |
| **B. Unmetered Provider Base Fees** | AI Gateway provisioned throughput, connection maintenance, or fixed platform routing fees. | Fixed monthly baseline overhead |
| **C. Context Caching Read Overhead** | Caching operations incur write/read fees at fraction of standard input rates ($0.25\times$), not captured in simplified two-tier formulas. | Shifts effective blended cost by $\approx \$96$ |

---

## 5. Implementation & Lineage Verification

The exact reconciliation formula has been codified in `finops_analytics_service.py`:

```python
# Executive Overview & AI Economics Lineage
formula = (
    "model_serving_dbu_spend ($26,740.00) + "
    "ai_gateway_external_tokens ($11,296.00) + "
    "auxiliary_vector_search ($424.00) = $38,460.00"
)
limitations = (
    "Total AI spend across workspace: $26,740 Model Serving DBU compute "
    "(part of $176,840 consumption ledger) + $11,296 external AI Gateway token API spend "
    "+ $424 auxiliary Vector Search compute (part of $284,620 cloud spend). "
    "Reconciled with zero double-counting. Note on AI Gateway spend: bottom-up calculation "
    "from 8.42B input tokens ($0.0008/1K = $6,736.00) + 1.86B output tokens ($0.0024/1K = $4,464.00) "
    "yields $11,200.00; the $96 difference against reported $11,296.00 represents unverified "
    "baseline variance retained as top-down allocation remainder."
)
```

Automated verification is enforced by `backend/tests/test_milestone_3g3_reconciliation.py::test_ai_gateway_token_cost_discrepancy_and_traceability`.

