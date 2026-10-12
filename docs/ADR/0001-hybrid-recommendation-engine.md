# ADR 0001: Hybrid Deterministic-Generative Architecture

| Status | Accepted |
| :--- | :--- |
| **Date** | 2026-10-12 |
| **Authors** | Architecture Working Group |
| **Deciders** | Lead Cloud Architect, Engineering Lead |

---

## Context & Problem Statement

Cloud architecture recommendation requires balancing two distinct needs:
1. **Absolute correctness on hard constraints:** Regulatory compliance (e.g., HIPAA, FedRAMP), geographic region availability, and minimum hardware limits cannot tolerate hallucinations or probabilistic guesswork. If a cloud service is not HIPAA-certified, recommending it for a healthcare workload represents a catastrophic failure.
2. **Contextual reasoning and narrative synthesis:** Evaluating subtle architectural trade-offs (e.g., developer ergonomics of Google Cloud Run vs flexibility of AWS ECS Fargate, or vendor lock-in risks) requires qualitative synthesis and explanation that static rule engines cannot generate.

A purely generative (LLM-only) solution suffers from hallucinated SKUs, out-of-date pricing, and probabilistic constraint violation. A purely deterministic rule engine produces rigid, uninspiring recommendations with no contextual narrative.

---

## Decision

We will implement a **Two-Stage Hybrid Architecture**:

1. **Stage 1 (Deterministic Filter):**
   - The workload profile is evaluated against an in-memory catalog via pure Python rule engines.
   - Any service that fails hard constraints (compliance, memory/CPU thresholds, region limits) is pruned.
   - Incompatible architectures are rejected deterministically before any LLM prompt is constructed.

2. **Stage 2 (Generative Synthesis):**
   - Only pre-validated, compliant candidate services are passed into the LLM context.
   - The LLM is constrained via structured prompt engineering and Pydantic schemas to reason about trade-offs, fit scores (0–100), and narrative justification between the validated candidates.

---

## Consequences

### Positive
- **Zero Hallucination of Critical Constraints:** The LLM cannot recommend a non-compliant service because non-compliant services are never provided in its prompt context.
- **Predictable Cost & Latency:** In scenarios where hard constraints result in a single obvious fit or where external LLMs are unavailable, the deterministic stage can complete without waiting for an LLM response.
- **High-Quality Explanation:** Users receive rich, human-readable trade-off rationales tailored to their exact workload description.

### Negative / Trade-offs
- Requires maintaining a curated catalog of services and their compliance/capability attributes.
- Slightly higher pipeline complexity than a single monolithic LLM prompt.
