# Product Requirements Document (PRD)

| Document Metadata | Value |
| :--- | :--- |
| **Product Name** | Cloud Recommender POC |
| **Target Stage** | Proof of Concept (POC) / MVP |
| **Primary Audience** | Cloud Architects, Solutions Architects, Tech Leads, FinOps Practitioners |
| **Status** | Approved for Implementation |
| **Last Updated** | October 2026 |

---

## 1. Executive Summary & Vision

Choosing the optimal cloud architecture across hyperscalers (**Amazon Web Services (AWS)**, **Microsoft Azure**, and **Google Cloud Platform (GCP)**) is currently a manual, time-consuming, and error-prone process. Organizations face complex trade-offs between pricing models, regional latency, compliance mandates, proprietary lock-in, and operational ergonomics.

The **Cloud Recommender POC** is an intelligent decision-support tool that ingests workload profiles—via structured parameters or natural-language prompts—and generates:
1. **Ranked Multi-Cloud Architectural Blueprints** (AWS, Azure, GCP, or Best-of-Breed).
2. **Granular Service Mapping Tables** with technical justification for each choice.
3. **Estimated Monthly Bill of Materials (BOM)** and operational cost comparison.
4. **Interactive Architecture Diagrams** (Mermaid.js format) and starter **Terraform (IaC)** scaffolding.

---

## 2. Problem Statement & Market Pain Points

1. **Information Asymmetry:** Hyperscalers have thousands of discrete SKUs with differing pricing curves, network egress tariffs, and SLAs.
2. **Analysis Paralysis:** Engineering teams often default to whichever provider they used last, ignoring significant cost savings or architectural advantages offered by competitors.
3. **Compliance & Constraint Pitfalls:** Manually verifying whether every recommended service in a specific cloud region complies with HIPAA, FedRAMP, or GDPR leads to costly architectural re-spins.
4. **Lack of Instant Visuals & IaC:** Architects need to manually draw diagrams and write initial Terraform boilerplate before a spike can even be prototyped.

---

## 3. Target User Personas

| Persona | Role | Primary Goal | Pain Point |
| :--- | :--- | :--- | :--- |
| **Architect Alex** | Principal Solutions Architect | Design resilient, compliant multi-cloud or single-cloud systems. | Needs fast, objective comparison matrices between AWS, Azure, and GCP. |
| **DevOps Dana** | Lead Platform / DevOps Engineer | Rapidly scaffold infrastructure with Infrastructure as Code. | Wants instant Terraform skeletons matching recommended services. |
| **FinOps Frank** | Cloud Financial Analyst | Forecast cloud spend and identify cost-optimized service tiers. | Cloud pricing calculators are disconnected from architecture design. |
| **Startup Sam** | Technical Founder / CTO | Pick the right cloud for an MVP with low initial cost and room to scale. | Overwhelmed by cloud marketing and complex pricing schemes. |

---

## 4. Scope Boundaries

### In Scope (POC / MVP)
- Structured Workload Input Form (web UI) & Natural Language Workload Prompt.
- Hyperscaler coverage: **AWS**, **Azure**, and **GCP**.
- Core infrastructure domains:
  - **Compute:** Serverless, Containers/Kubernetes, Virtual Machines.
  - **Database:** Relational (SQL/ACID), Document/NoSQL, In-Memory Caches, Time-Series.
  - **Storage:** Object storage, Block storage, File systems.
  - **Networking:** Load Balancers, API Gateways, CDN.
  - **Observability & Security:** Cloud native monitoring, IAM, Secret management.
- Deterministic constraint filtering (Compliance, Region, SLA, Budget).
- Hybrid AI synthesis (LLM justification, trade-off matrices, fit score 0–100).
- Baseline heuristic monthly cost estimation.
- Renderable Mermaid.js architecture diagrams.
- Starter Terraform HCL export for top-ranked recommendation.
- Offline/mock mode for zero-cost local execution and CI testing.

### Out of Scope (Future Releases)
- Automated deployment into live cloud accounts via OAuth / cloud credentials.
- Real-time billing account sync via Cloud Billing APIs.
- Continuous runtime cost anomaly detection.
- Legacy on-premise hardware discovery agents.

---

## 5. Functional Requirements (FR)

### FR-1: Workload Specification Ingestion
- **FR-1.1:** The system shall accept workload requirements through a structured web form capturing:
  - Workload Type (Web App, Batch Processing, Data Pipeline, AI/ML Training/Inference, Event-Driven).
  - Traffic / Concurrency (Requests/sec, Monthly Active Users, Peak vs Average multiplier).
  - Compute Needs (CPU/vCPU requirements, Memory requirements, GPU acceleration need).
  - Data & Storage Needs (Dataset volume, Read/Write throughput IOPS, Relational vs Document vs Graph).
  - High Availability & SLA (99.9%, 99.99%, Multi-AZ, Multi-Region active-active).
  - Compliance Requirements (HIPAA, GDPR, PCI-DSS, SOC2, FedRAMP).
  - Maximum Monthly Budget (USD).
  - Cloud Preferences (Open to any, AWS only, Azure only, GCP only).
- **FR-1.2:** The system shall support free-form natural language query input (e.g., *"We need to host a HIPAA-compliant medical imaging platform processing 50,000 scans daily with high availability and a \$3,000 monthly budget"*), which is automatically parsed into a structured `WorkloadProfile`.

### FR-2: Cloud Service Catalog & Knowledge Base
- **FR-2.1:** The system shall maintain an offline-accessible service registry covering core services across AWS, Azure, and GCP.
- **FR-2.2:** Each catalog entry shall record: Service ID, Cloud Provider, Category, Pricing Unit / Baseline Cost Model, SLA rating, Supported Compliance Frameworks, Strengths, and Known Limitations.
- **FR-2.3:** The catalog schema must allow updates via JSON files without code modifications.

### FR-3: Deterministic Constraint & Validation Engine
- **FR-3.1:** The engine must enforce hard rules before invoking any generative LLM:
  - If a workload requires `HIPAA`, any candidate service lacking verified HIPAA compliance must be eliminated or flagged with an explicit warning.
  - If budget is specified, total estimated baseline cost must not exceed the budget without an overt budget overrun warning.
  - If low latency / specific region is requested, only services available in that geographic region are considered.
- **FR-3.2:** If no single cloud satisfies all hard constraints, the system must output a clear diagnostic stating which constraints conflicted.

### FR-4: AI Architectural Synthesis & Scoring Engine
- **FR-4.1:** The system shall produce a weighted **Fit Score (0–100)** for each provider, calculated across five key dimensions:
  - Cost Efficiency (weight: 25%)
  - Performance & Scalability (weight: 25%)
  - Reliability & Fault Tolerance (weight: 20%)
  - Security & Compliance (weight: 15%)
  - Operational Simplicity / Dev Experience (weight: 15%)
- **FR-4.2:** The system shall generate explicit architectural trade-off rationales:
  - *Why this primary provider was chosen.*
  - *What compromises are made (e.g., proprietary lock-in vs development velocity).*
  - *Alternatives considered and reasons for rejection.*

### FR-5: Multi-Cloud Comparison Matrix
- **FR-5.1:** The output must present a side-by-side service mapping table:
  - e.g. Compute: AWS ECS Fargate vs Azure Container Apps vs GCP Cloud Run.
  - Database: AWS Aurora PostgreSQL vs Azure Database for PostgreSQL vs GCP Cloud SQL / AlloyDB.
- **FR-5.2:** Highlight key differentiators (e.g. cold start times, scaling speed, pricing granularity).

### FR-6: Cost Estimation & Bill of Materials (BOM)
- **FR-6.1:** Output an itemized monthly cost estimate per component (Compute, Database, Storage, Data Egress).
- **FR-6.2:** Apply a configurable safety buffer (default: +15%) to account for unpredicted traffic spikes and network overhead.
- **FR-6.3:** Provide a 3-way cost comparison summary (AWS vs Azure vs GCP).

### FR-7: Visual Architecture Diagram & Terraform Export
- **FR-7.1:** The engine shall generate a valid, renderable Mermaid.js flowchart representing the proposed topology (Client -> CDN/WAF -> API Gateway / Load Balancer -> Compute Tier -> Database / Cache Tier -> Storage Tier).
- **FR-7.2:** The system shall generate a valid starter Terraform (`main.tf`, `variables.tf`) HCL template configuring the recommended services.

### FR-8: Reporting & Export
- **FR-8.1:** Users can export the complete recommendation as a structured Markdown document or JSON payload.

---

## 6. Non-Functional Requirements (NFR)

| ID | Category | Requirement | Metric / Target |
| :--- | :--- | :--- | :--- |
| **NFR-1** | Response Time | Deterministic catalog lookup and scoring completes under 500ms; full LLM synthesis completes under 10 seconds. | P95 < 10s |
| **NFR-2** | Offline Resilience | The system must be fully operational without internet or external LLM API keys via the `mock` engine and local catalog. | 100% test pass offline |
| **NFR-3** | Security & Privacy | No user cloud credentials or API secrets required. Workload prompts are scrubbed of sensitive identifiers before LLM ingestion. | Zero credential storage |
| **NFR-4** | Accuracy & Hallucination Prevention | Recommended cloud service names and SKUs must strictly match verified catalog entries. | 0% invalid service names |
| **NFR-5** | Code Maintainability | Backend test coverage > 85% for business logic and rule engine modules. Strict typing enforced. | Mypy 0 errors, Pytest >85% |
| **NFR-6** | Accessibility & UX | Web UI responds cleanly to standard desktop screen resolutions, providing clear loading states during synthesis. | Lighthouse Accessibility > 90 |

---

## 7. Standard Validation Scenarios (Acceptance Tests)

The POC must be validated against four standardized workload benchmarks:

1. **Scenario A (Serverless E-Commerce):**
   - 2,000 req/sec peak, event-driven order processing, PCI-DSS compliance, \$1,500/mo budget.
   - *Expected Winner:* AWS (Lambda, EventBridge, DynamoDB) or GCP (Cloud Run, Pub/Sub, Cloud Firestore).
2. **Scenario B (Regulated Healthcare Analytics):**
   - HIPAA compliance required, 10 TB DICOM image storage, relational metadata, multi-AZ high availability, \$5,000/mo budget.
   - *Expected Winner:* Azure (Azure Container Apps, Azure Database for PostgreSQL, Azure Blob with HIPAA encryption) or AWS.
3. **Scenario C (High-Throughput Streaming / AI Inference):**
   - GPU-assisted inference, low latency (<50ms), global distribution, 50 TB monthly egress.
   - *Expected Winner:* GCP (Vertex AI / GKE, BigQuery, Cloud CDN) or AWS.
4. **Scenario D (Budget-Constrained Microservices MVP):**
   - Low traffic (<50 req/sec), single-region, relational DB, strict <\$150/mo budget limit.
   - *Expected Outcome:* Lightweight container solution (Cloud Run / ECS Fargate / ACA) + Serverless PostgreSQL tier with cost warning.
