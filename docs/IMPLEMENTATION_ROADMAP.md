# Implementation Roadmap & Milestone Validation Guide

| Document Metadata | Value |
| :--- | :--- |
| **Project** | Cloud Recommender POC |
| **Execution Model** | Phased, Test-Driven Milestone Delivery |
| **Status** | Active Execution Plan |
| **Last Updated** | October 2026 |

---

## 1. Roadmap Overview & Execution Philosophy

This roadmap defines the sequential, verifiable steps to build the **Cloud Recommender POC**. 

### Rules of Engagement for Coding Agents:
1. **Linear Progression:** Agents must complete milestones in order (M0 $\to$ M1 $\to$ M2 ...). Do not jump ahead to build frontend components before the backend schemas and rule engine pass validation.
2. **Mandatory Validation:** Every milestone includes an explicit **Validation Protocol**. The agent must run the specified commands and confirm they exit with code 0 before concluding the milestone.
3. **No Breaking Regression:** Subsequent milestones must not break existing test suites.

---

## 2. Milestone Breakdown

```mermaid
flowchart LR
    M0["M0: Foundation & Config"] --> M1["M1: Catalog & Models"]
    M1 --> M2["M2: Rule Engine"]
    M2 --> M3["M3: LLM & Synthesizer"]
    M3 --> M4["M4: Cost Estimator"]
    M4 --> M5["M5: Diagram & IaC"]
    M5 --> M6["M6: FastAPI API"]
    M6 --> M7["M7: React Frontend"]
    M7 --> M8["M8: E2E Verification"]
```

---

### Milestone 0: Foundation, Project Configuration & Tooling Setup
- **Objective:** Establish the project workspace, dependency definitions, linter/typecheck configurations, and CI baseline.
- **Deliverables:**
  - `backend/pyproject.toml` (FastAPI, Pydantic v2, Uvicorn, Pytest, Ruff, Mypy).
  - Directory skeleton matching `docs/ARCHITECTURE.md`.
  - Smoke test suite validating the test runner.
- **Validation Protocol:**
  ```bash
  ruff check backend/
  ruff format --check backend/
  mypy backend/
  pytest backend/tests/ -v
  ```
- **Exit Criteria:** Linter, formatter, type checker, and base test runner pass with zero errors.

---

### Milestone 1: Domain Schemas & Multi-Cloud Service Catalog
- **Objective:** Implement core domain models (`WorkloadProfile`, `CloudCatalogItem`, etc.) and the seed datasets for AWS, Azure, and GCP.
- **Deliverables:**
  - `backend/app/schemas/domain.py`: Typed Pydantic v2 models.
  - `backend/app/catalog/data/aws_services.json`: AWS catalog seed (ECS, Lambda, Aurora, S3, DynamoDB, CloudFront, etc.).
  - `backend/app/catalog/data/azure_services.json`: Azure catalog seed (ACA, Azure Functions, Azure SQL, Blob, Cosmos DB, Front Door, etc.).
  - `backend/app/catalog/data/gcp_services.json`: GCP catalog seed (Cloud Run, Cloud Functions, Cloud SQL, GCS, Bigtable, Cloud CDN, etc.).
  - `backend/app/catalog/registry.py`: In-memory catalog querying, category indexing, and lookup methods.
  - `backend/tests/test_catalog.py`: Unit tests validating catalog loading, category filtering, and schema parsing.
- **Validation Protocol:**
  ```bash
  pytest backend/tests/test_catalog.py -v
  mypy backend/app/catalog/
  ```
- **Exit Criteria:** Catalog queries correctly return services across all 3 providers without missing required fields or failing Pydantic validation.

---

### Milestone 2: Deterministic Constraint & Validation Engine
- **Objective:** Build the rule engine to filter catalog candidates based on hard technical constraints (compliance, memory/CPU thresholds, region, budget caps).
- **Deliverables:**
  - `backend/app/engine/rule_engine.py`: Hard constraint evaluation logic.
  - Compliance filtering (e.g. HIPAA filters out non-compliant services).
  - High availability / multi-region compatibility checks.
  - Diagnostic warning generator when constraints create partial or zero matches.
  - `backend/tests/test_rule_engine.py`: Unit tests covering all Scenario A-D edge cases and boundary conditions.
- **Validation Protocol:**
  ```bash
  pytest backend/tests/test_rule_engine.py -v
  ```
- **Exit Criteria:** 100% test pass rate for all constraint checks; no non-compliant services ever leak through the filter.

---

### Milestone 3: LLM Provider Abstraction & Architectural Synthesizer
- **Objective:** Implement pluggable LLM adapters and the synthesis engine that takes qualified catalog services and produces reasoned architecture rankings and fit scores.
- **Deliverables:**
  - `backend/app/providers/base.py`: `LLMProvider` abstract interface.
  - `backend/app/providers/mock_provider.py`: Deterministic mock provider producing structured outputs without external network calls.
  - `backend/app/providers/gemini_provider.py`: Google Gemini adapter with structured Pydantic output support.
  - `backend/app/providers/openai_provider.py`: OpenAI GPT-4o adapter.
  - `backend/app/providers/claude_provider.py`: Anthropic Claude adapter.
  - `backend/app/engine/synthesizer.py`: Orchestrates prompt construction, invokes provider, and parses structured output into `RecommendationResponse`.
  - `backend/tests/test_providers.py` & `backend/tests/test_synthesizer.py`.
- **Validation Protocol:**
  ```bash
  pytest backend/tests/test_providers.py backend/tests/test_synthesizer.py -v
  ```
- **Exit Criteria:** Mock provider generates complete, valid recommendations deterministically; graceful fallback executes seamlessly when API calls fail.

---

### Milestone 4: Cost Estimator & Bill of Materials (BOM) Calculator
- **Objective:** Implement deterministic FinOps cost estimation logic calculating itemized monthly bills for compute, database, storage, and egress.
- **Deliverables:**
  - `backend/app/engine/cost_estimator.py`: Heuristic cost estimation algorithms.
  - Egress calculation heuristics based on requests and user volume.
  - Configurable safety buffer calculation (+15%).
  - 3-way comparative cost summary (AWS vs Azure vs GCP).
  - `backend/tests/test_cost_estimator.py`.
- **Validation Protocol:**
  ```bash
  pytest backend/tests/test_cost_estimator.py -v
  ```
- **Exit Criteria:** Math verified across low, medium, and high load scenarios; no negative costs or NaN values.

---

### Milestone 5: Architecture Diagram & Terraform IaC Generator
- **Objective:** Generate visual Mermaid.js flowcharts and clean starter Terraform HCL configuration files for the top-ranked recommendation.
- **Deliverables:**
  - `backend/app/engine/diagram_generator.py`: Generates valid Mermaid flowchart syntax mapping client $\to$ ingress $\to$ compute $\to$ data $\to$ storage.
  - `backend/app/engine/iac_scaffolder.py`: Generates parameterized Terraform HCL templates (`main.tf`, `variables.tf`) for AWS, Azure, and GCP.
  - `backend/tests/test_diagram_generator.py` & `backend/tests/test_iac_scaffolder.py`.
- **Validation Protocol:**
  ```bash
  pytest backend/tests/test_diagram_generator.py backend/tests/test_iac_scaffolder.py -v
  ```
- **Exit Criteria:** Mermaid syntax passes regex/syntax validation; generated Terraform HCL is syntactically well-formed.

---

### Milestone 6: FastAPI REST API Endpoints & Integration Suite
- **Objective:** Expose the complete recommendation engine via clean, documented REST endpoints.
- **Deliverables:**
  - `backend/app/main.py`: Application factory, CORS middleware, error handlers.
  - `backend/app/api/v1/endpoints/recommendations.py`: `POST /api/v1/recommendations/analyze`, `POST /api/v1/recommendations/parse-prompt`.
  - `backend/app/api/v1/endpoints/catalog.py`: `GET /api/v1/catalog/services`.
  - `backend/app/api/v1/endpoints/health.py`: `GET /health` with system status.
  - `backend/tests/test_api_integration.py`: End-to-end API tests using FastAPI TestClient.
- **Validation Protocol:**
  ```bash
  pytest backend/tests/test_api_integration.py -v
  mypy backend/
  ```
- **Exit Criteria:** All API endpoints return appropriate HTTP status codes, handle invalid payloads with 422 Unprocessable Entity, and OpenAPI docs are available at `/docs`.

---

### Milestone 7: Frontend Web Application (React + Vite + Tailwind)
- **Objective:** Build an intuitive, responsive user interface to input workload specs, view side-by-side cloud recommendations, render Mermaid diagrams, and export reports.
- **Deliverables:**
  - `frontend/src/components/WorkloadForm.tsx`: Multi-step parameter wizard.
  - `frontend/src/components/PromptInput.tsx`: Natural language query interface.
  - `frontend/src/components/ComparisonMatrix.tsx`: Side-by-side cloud comparison grid.
  - `frontend/src/components/DiagramViewer.tsx`: Mermaid diagram renderer.
  - `frontend/src/components/CostBreakdown.tsx`: Bill of Materials chart/table.
  - `frontend/src/components/IaCExportModal.tsx`: Terraform HCL viewer with one-click copy.
- **Validation Protocol:**
  ```bash
  npm --prefix frontend run lint
  npm --prefix frontend run typecheck
  npm --prefix frontend run build
  ```
- **Exit Criteria:** Frontend compiles with 0 TypeScript errors, bundle builds successfully, and UI renders correctly.

---

### Milestone 8: End-to-End System Verification & Acceptance Scenarios
- **Objective:** Validate the complete end-to-end system against the 4 standard benchmark scenarios defined in `PRODUCT_REQUIREMENTS.md`.
- **Deliverables:**
  - Execution of Scenario A (E-Commerce), Scenario B (Healthcare), Scenario C (AI Inference), and Scenario D (Budget MVP).
  - Verified report outputs and diagnostic logs.
  - Final documentation updates in `README.md`.
- **Validation Protocol:**
  ```bash
  # Complete repository verification suite
  ruff check backend/
  mypy backend/
  pytest backend/tests/ -v --cov=backend/app --cov-report=term-missing
  npm --prefix frontend run build
  ```
- **Exit Criteria:** Overall test coverage > 85%, 0 lint or type errors, all 4 scenarios produce valid recommendations and diagrams.
