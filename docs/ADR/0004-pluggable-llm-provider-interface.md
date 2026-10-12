# ADR 0004: Pluggable LLM Provider Interface with Mandatory Mock Engine

| Status | Accepted |
| :--- | :--- |
| **Date** | 2026-10-12 |
| **Authors** | Architecture Working Group |
| **Deciders** | Lead Cloud Architect, AI Engineering Lead |

---

## Context & Problem Statement

The platform requires foundation LLM capabilities for unstructured requirements extraction, code quality analysis, and conversational clarifying questions. However:
- Cloud environments and customer deployments vary in LLM availability (e.g. enterprise Azure OpenAI vs direct OpenAI API vs Google Gemini).
- CI/CD pipelines, local development environments, and air-gapped test runners lack active commercial API keys and should not incur external API costs.
- Foundation model SDKs frequently change method signatures and deprecate models.

Directly coupling LangGraph agent nodes to a single proprietary SDK introduces severe vendor lock-in and prevents offline testing.

---

## Decision

We implement a **Pluggable LLM Provider Abstraction**:

1. **`LLMProvider` Abstract Base Interface (`backend/app/providers/base.py`):**
   - Standardizes methods for chat completion, structured output extraction via Pydantic, and token tracking.
2. **First-Class `MockProvider`:**
   - Bundles a deterministic, zero-cost mock provider in `backend/app/providers/mock_provider.py`.
   - Returns realistic, schema-valid Pydantic outputs for requirements extraction, clarifying questions, and code review without network calls.
   - Default configuration: `LLM_PROVIDER=mock`.
3. **Pluggable Hyperscaler Adapters:**
   - `AzureOpenAIProvider`: Recommended for enterprise Azure deployments.
   - `OpenAIProvider`: Direct OpenAI API.
   - `GeminiProvider`: Google GenAI adapter.
   - `ClaudeProvider`: Anthropic Claude adapter.
4. **LangGraph Integration:**
   - LangGraph nodes interact exclusively through the provider interface, making the orchestration graphs completely model-agnostic.

---

## Consequences

### Positive
- Zero external API costs during automated testing and CI runs.
- Flexible deployment matching customer enterprise LLM agreements.
- Resilience against vendor deprecations and rate limits.

### Negative / Trade-offs
- Adapters must normalize differing provider output formats into common Pydantic schemas.
