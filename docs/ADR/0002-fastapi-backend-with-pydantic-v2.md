# ADR 0002: Backend Framework Selection (FastAPI & Pydantic v2)

| Status | Accepted |
| :--- | :--- |
| **Date** | 2026-10-12 |
| **Authors** | Architecture Working Group |
| **Deciders** | Lead Cloud Architect, Backend Engineering Lead |

---

## Context & Problem Statement

The backend of the Cloud Recommender POC must:
1. Ingest complex, nested workload profile data from both REST clients and natural-language parsers.
2. Interface with modern AI/LLM SDKs (Google GenAI, OpenAI, Anthropic) which heavily rely on Python type hints and structured JSON schemas.
3. Serve interactive API responses and diagram code with minimal latency.
4. Auto-generate OpenAPI / Swagger specifications for easy frontend consumption.

We considered alternatives including Node.js (Express/NestJS), Go (Gin/Fiber), and Python (Django, Flask, FastAPI).

---

## Decision

We select **Python 3.11+ with FastAPI and Pydantic v2** as the core backend stack.

### Key Factors:
1. **Pydantic v2 Performance & Validation:** Written in Rust, Pydantic v2 provides 5x–15x faster schema serialization and deserialization, making high-volume validation of cloud catalogs and LLM outputs fast and type-safe.
2. **First-Class AI/ML Ecosystem:** The latest generative AI SDKs and structured output libraries (such as Pydantic-based Instructor, LangChain, and LiteLLM) have native Python support.
3. **Async IO Concurrency:** FastAPI's asynchronous architecture handles concurrent LLM calls and streaming responses efficiently.
4. **Automated Documentation:** Native OpenAPI (Swagger UI) at `/docs` simplifies frontend and agent testing.

---

## Consequences

### Positive
- Strict compile-time and runtime type checking using `mypy` and Pydantic v2.
- Direct alignment with Python AI toolchains.
- Rapid prototyping without boilerplate.

### Negative / Trade-offs
- Python CPU-bound tasks require careful design (though rule evaluation and catalog lookups over hundreds of services are fast enough to run in sub-millisecond time).
