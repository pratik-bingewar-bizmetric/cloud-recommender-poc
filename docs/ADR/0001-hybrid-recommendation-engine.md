# ADR 0001: Hybrid Architecture with LangGraph Stateful Agent Orchestration

| Status | Accepted |
| :--- | :--- |
| **Date** | 2026-10-12 |
| **Authors** | Architecture Working Group |
| **Deciders** | Lead Cloud Architect, Engineering Lead |

---

## Context & Problem Statement

Cloud architecture recommendation and optimization across hyperscalers (Azure, AWS, GCP) involves two opposing challenges:
1. **Unstructured Reasoning & Conversational Clarification:** Understanding requirements from free-form text, PDF/Word documents, and source-code repositories requires conversational intelligence. When critical requirements (such as throughput, SLA, or compliance) are missing, the system must not guess; it must pause and ask clarifying questions.
2. **Deterministic Pricing & Zero-Hallucination Constraints:** LLMs frequently hallucinate cloud SKU pricing, region availability, and compliance ratings. Recommending a non-compliant service or an inaccurate price can result in catastrophic architectural failures.

Simple single-shot LLM prompts or rigid linear pipelines cannot manage interactive clarification dialogs, cyclic state transitions, or deterministic pricing integration.

---

## Decision

We will implement a **Two-Stage Hybrid Architecture** orchestrated by **LangGraph**:

1. **Stateful Graph Orchestration (LangGraph):**
   - **Phase A Graph:** Coordinates document parsing, requirements extraction, validation, conditional branching to a human-in-the-loop clarification node when specs are incomplete, and architectural synthesis.
   - **Phase B Graph:** Coordinates static source-code analysis, read-only Azure telemetry ingestion, Microsoft Fabric Lakehouse writes, and waste detection.
   - Graph state is persisted using a PostgreSQL checkpointer, ensuring session continuity across asynchronous user clarification responses.

2. **Deterministic Constraint & Pricing Isolation:**
   - LLMs are strictly forbidden from generating or guessing pricing numbers.
   - Pricing is retrieved deterministically from official provider APIs (Azure Retail Prices API, AWS Price List API, GCP Catalog API) and local cached datasets.
   - Hard constraint filters (e.g. HIPAA compliance, geographic region limits) filter candidate services before final blueprint synthesis.

---

## Consequences

### Positive
- **Guaranteed Pricing & Compliance Accuracy:** Official provider pricing and verified compliance records eliminate hallucinated costs and illegal architectures.
- **Stateful Human-in-the-Loop Clarification:** LangGraph state machine naturally pauses execution to solicit missing requirements from users and seamlessly resumes.
- **Auditability:** Every node transition in the LangGraph graph is logged and traceable.

### Negative / Trade-offs
- Increased architectural complexity compared to simple stateless REST endpoints.
- Requires PostgreSQL state persistence to manage graph checkpoints.
