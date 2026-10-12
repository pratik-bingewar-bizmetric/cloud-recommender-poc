# ADR 0004: Pluggable LLM Provider Interface with Mandatory Mock Engine

| Status | Accepted |
| :--- | :--- |
| **Date** | 2026-10-12 |
| **Authors** | Architecture Working Group |
| **Deciders** | Lead Cloud Architect, AI Engineering Lead |

---

## Context & Problem Statement

LLM APIs are dynamic: models are continuously deprecated, rate limits can throttle requests, pricing structures change, and developer environments may lack active commercial API keys (e.g., in CI/CD pipelines, offline local development, or restricted enterprise networks).

Directly coupling the application to a single vendor SDK (e.g. only OpenAI or only Google Gemini) creates architectural fragility and prevents offline testing.

---

## Decision

We will implement an **Abstract Adapter Pattern** for all LLM interactions:

1. **`LLMProvider` Abstract Base Class (`backend/app/providers/base.py`):**
   - Defines standard methods:
     - `synthesize_recommendation(profile: WorkloadProfile, candidates: dict) -> RecommendationResponse`
     - `parse_natural_language_prompt(prompt: str) -> WorkloadProfile`
2. **Mandatory `MockProvider`:**
   - A fully functional, deterministic mock provider bundled in `backend/app/providers/mock_provider.py`.
   - Uses pre-programmed heuristic matrices and deterministic fit scoring to generate valid, realistic recommendations and trade-offs.
   - Requires zero network calls and zero API keys.
   - Configured via `LLM_PROVIDER=mock`.
3. **Hyperscaler Adapters:**
   - `GeminiProvider` (Google Gemini 2.5 / Flash via `google-genai` / REST)
   - `OpenAIProvider` (GPT-4o via `openai` SDK)
   - `ClaudeProvider` (Claude 3.7 Sonnet via `anthropic` SDK)
4. **Automatic Fallback:**
   - If an external provider encounters an unrecoverable failure (e.g., quota exceeded, network timeout), the engine falls back gracefully to deterministic heuristics and logs a warning.

---

## Consequences

### Positive
- Zero friction for new developers and CI pipelines: running `pytest` never requires API keys or costs money.
- Freedom to switch between foundation model providers based on price/performance without refactoring business logic.
- Robust fault tolerance in production environments.

### Negative / Trade-offs
- Adapters must normalize different LLM output structures and error types into common Pydantic response models.
