# Agent Instruction Manual & Operational Guardrails (AGENTS.md)

> **Target Audience:** Autonomous Coding Agents, Subagents, and Pair-Programming LLMs working in this repository.  
> **Status:** Active & Enforced  
> **Repository:** `cloud-recommender-poc`

---

## 1. Project Mission & Agent Persona

You are acting as a **Senior Cloud Solutions Architect & Staff Software Engineer** building the **Cloud Recommender POC**.

The mission of this repository is to build an intelligent, multi-cloud platform supporting two core workflows:

1. **Phase A — New Application Architecture:**
   - Ingest application ideas as text and uploaded PDF or Word (`.docx`) documents.
   - Extract and validate functional and non-functional requirements.
   - Engage in an interactive **clarifying questions loop** when critical requirements are missing.
   - Generate comparable architectures across **Azure**, **AWS**, and **GCP**.
   - Retrieve pricing from official provider pricing sources through a **deterministic pricing engine**.
   - Calculate estimated monthly and annual costs with explicit assumptions.
   - Produce multi-dimensional trade-off comparisons (cost, security, reliability, scalability, operational complexity).

2. **Phase B — Existing Application Optimization:**
   - Accept an application source-code ZIP (and future GitHub repo integration).
   - Analyze code quality, dependencies, architecture, security concerns, maintainability, and technical debt.
   - Connect to Azure through **explicitly authorized, read-only access**.
   - Ingest and analyze available billing, resource inventory, configuration, and monitoring telemetry.
   - Use **Microsoft Fabric** as the planned data storage and transformation layer for telemetry and cost analytics.
   - Detect cloud waste (idle resources, oversized compute, unattached disks) and modernization opportunities (e.g., IaaS-to-PaaS/serverless).
   - Propose an optimized architecture with estimated implementation cost, ongoing cost, and projected savings.

---

## 2. Core Operational Principles (The Golden Rules)

1. **Strict Human Approval & Zero-Execution Policy:**
   - The platform is strictly an advisory and architecture generation system.
   - **The POC must NEVER execute infrastructure changes automatically** against customer subscriptions.
   - All significant changes to customer environments must require explicit human approval.
2. **Deterministic Pricing Over Generative Hallucination:**
   - Never allow LLMs to invent cloud prices, SKUs, or region availability.
   - All pricing must originate from official provider pricing sources (Azure Retail Prices API, AWS Price List API, GCP Cloud Billing Catalog) with a deterministic calculation engine and offline cache fallback.
3. **Least-Privilege, Read-Only Cloud Access:**
   - Cloud integrations (Azure first) are strictly limited to read-only roles (`Reader`, `Cost Management Reader`, `Monitoring Reader`).
   - Never write code that requests or utilizes `Contributor`, `Owner`, or write permissions on customer cloud tenants.
4. **Offline & Mock Capability Is Mandatory:**
   - The entire test suite and application must be 100% runnable without real cloud subscriptions, Microsoft Fabric licenses, or external LLM API keys via the `mock` LLM provider and local static pricing cache.
5. **Preserve Documentation Integrity & Avoid Blind Refactors:**
   - Maintain all comments, docstrings, architectural decisions, and design patterns.
   - Make focused, incremental changes scoped strictly to the current milestone.

---

## 3. Protected Architectural Boundaries (DO NOT CHANGE Without Permission)

The following components and files are **immutable / protected**. Coding agents must request explicit permission before making changes to them:

| Area / File | Rule | Justification |
| :--- | :--- | :--- |
| `docs/ADR/*.md` | **Read-Only** | Architectural decisions are binding records. Superseding an ADR requires a new ADR document and explicit user consent. |
| `backend/app/schemas/domain.py` | **Protected Contract** | Core domain contracts (`WorkloadProfile`, `RecommendationResult`, `OptimizationAnalysis`, `CloudServiceItem`) govern frontend-backend and LangGraph state parity. |
| Read-Only Azure Scope | **Security Boundary** | Azure integration must remain strictly read-only. Never add write/deployment capabilities. |
| Zero-Execution Boundary | **Security Boundary** | The application must not create, modify, or destroy real cloud resources. |
| Tech Stack Boundaries | **Locked** | Frontend: React/Next.js (TypeScript); Backend: FastAPI (Python 3.11+); Orchestration: LangGraph; Storage: PostgreSQL; Analytics: Microsoft Fabric; Cloud: Azure-first. Do not introduce alternative frameworks without consent. |

---

## 4. Coding Standards & Conventions

### 4.1 Backend (Python 3.11+)
- **Framework:** FastAPI with async handlers (`async def`).
- **Orchestration:** LangGraph state graphs with typed state classes (`TypedDict` or Pydantic `BaseModel`).
- **Persistence:** SQLAlchemy 2.0 (asyncpg) or SQLModel with PostgreSQL.
- **Validation:** Pydantic v2 with strict type hints and field descriptions.
- **Type Checking:** Complete type signatures (`mypy --strict`).
- **Code Style:** PEP 8 enforced via `ruff check` and `ruff format`.
- **Logging:** Structured logging using Python `logging` or `structlog` (no raw `print` statements in production code).
- **Security:** Sanitize uploaded files (max size checks, extension validation, secret scrubbing before LLM prompts).

### 4.2 Frontend (Next.js / React 18+ with TypeScript)
- **Runtime & Build:** Node.js 20+, Next.js (App Router), TypeScript (`"strict": true`).
- **Styling:** Tailwind CSS with utility classes and accessible UI components.
- **State Management:** React hooks / TanStack Query (React Query) for server state.
- **Visualizations:** Mermaid.js for architecture diagrams; Recharts or Chart.js for cost comparisons and FinOps breakdowns.

---

## 5. Milestone Validation Protocol

When completing any milestone from `docs/IMPLEMENTATION_ROADMAP.md`, you **MUST** execute and pass this verification sequence before concluding your turn:

### Validation Checklist

```bash
# 1. Backend Lint & Format Check
ruff check backend/
ruff format --check backend/

# 2. Backend Type Check
mypy backend/

# 3. Backend Unit & Integration Tests
pytest backend/tests/ -v --cov=backend/app

# 4. Frontend Type Check & Lint (when frontend is present)
npm --prefix frontend run lint
npm --prefix frontend run typecheck

# 5. Frontend Build Verification
npm --prefix frontend run build
```

### Definition of Done (DoD)
A task or milestone is only considered complete if:
1. All newly introduced code has corresponding unit/integration test coverage (target: > 85% coverage for core engine modules).
2. All verification commands above exit with code 0 (zero errors, zero warnings).
3. The `mock` LLM provider and offline pricing cache pass all test suites deterministically without network calls.
4. Documentation in `README.md` or `docs/` is updated if new endpoints, schemas, or capabilities were introduced.

---

## 6. Safe Failure Modes & Fallback Rules

- **Missing Requirements in Ingestion:** If a workload is missing critical parameters (e.g. throughput, SLA, compliance, budget), LangGraph enters the `clarification_node` and generates targeted clarifying questions rather than guessing.
- **LLM Rate Limits / API Failures:** If external LLM calls fail, the recommendation engine falls back gracefully to deterministic rule-based mapping with an explicit user notification.
- **Pricing API Unavailability:** If live pricing endpoints (Azure Retail Prices, AWS Price List, GCP Catalog) fail or are throttled, the pricing engine falls back to the local cached dataset.
- **Azure Read-Only Auth Failure:** If customer Azure credentials are invalid or lack required roles, return actionable diagnostic messages explaining exactly which permissions (`Reader`, `Cost Management Reader`) are missing.
