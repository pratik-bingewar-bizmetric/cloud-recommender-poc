# ADR 0002: Backend API (FastAPI) and Relational Persistence (PostgreSQL)

| Status | Accepted |
| :--- | :--- |
| **Date** | 2026-10-12 |
| **Authors** | Architecture Working Group |
| **Deciders** | Lead Cloud Architect, Backend Engineering Lead |

---

## Context & Problem Statement

The backend of the Cloud Recommender platform must:
1. Ingest complex, nested workload profiles from both REST clients, uploaded documents, and natural-language parsers.
2. Interface seamlessly with LangGraph, Python AI SDKs, Azure management SDKs, and document parsers (`pypdf`, `python-docx`).
3. Maintain robust, transactional state persistence for user projects, workload profiles, clarification chat sessions, and generated reports.
4. Provide high-performance async concurrency for handling long-running agent workflows and streaming responses.

---

## Decision

We select **Python 3.11+ with FastAPI** for the API layer and **PostgreSQL 15+** with **SQLAlchemy 2.0 (asyncpg)** for relational persistence.

### Key Justifications:
1. **Python AI & Azure Ecosystem:** The Python ecosystem has first-class native support for LangGraph, Azure Python SDK (`azure-mgmt-*`), document parsing, and static code analysis tools.
2. **Pydantic v2 Performance:** Written in Rust, Pydantic v2 offers ultra-fast data serialization and strict type validation for complex cloud catalog and workload schemas.
3. **PostgreSQL Relational Rigor & LangGraph Checkpointing:** PostgreSQL provides reliable ACID persistence for projects, audit trails, and conversational checkpoints (`PostgresSaver` in LangGraph).
4. **Native OpenAPI & Async IO:** FastAPI automatically exposes interactive OpenAPI (Swagger) documentation and handles high-throughput asynchronous workloads.

---

## Consequences

### Positive
- Unified Python runtime across API endpoints, LangGraph agents, document processing, and Azure telemetry clients.
- Clean separation between relational operational data (PostgreSQL) and analytics telemetry (Microsoft Fabric).
- Strict static type checking via `mypy --strict`.

### Negative / Trade-offs
- Async SQLAlchemy 2.0 requires careful session and connection pool management.
