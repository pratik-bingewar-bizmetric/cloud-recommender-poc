# Hidden & Preserved Platform Capabilities

> **Status:** Enforced Feature Flag Configuration  
> **Last Updated:** October 2026  
> **Repository:** `cloud-recommender-poc`

---

## 1. Overview & Architectural Rationale

To align the platform with the current POC focus—**Connection-First Cloud Onboarding, Live Infrastructure Monitoring, Token Economics, and Evidence-Backed FinOps Waste Analysis**—certain advanced capabilities have been decoupled from the primary navigation while preserving 100% of their underlying code, domain models, deterministic pricing calculations, and test suites.

Per the **Preserve Documentation Integrity & Avoid Blind Refactors** principle in `AGENTS.md`, no functional code has been deleted or degraded. Instead, visibility is managed via centralized feature flags in `frontend/src/config/features.ts`.

---

## 2. Inventory of Hidden & Deferred Features

### 2.1 AI Cloud Architect (Phase A: Requirements-to-Architecture Workspace)

- **Flag:** `ENABLE_AI_ARCHITECT = false` in `frontend/src/config/features.ts`
- **Purpose:** Ingests raw application concepts or uploaded specification documents, extracts workload profiles, conducts clarifying question loops, synthesizes multi-tier cloud topologies (Mermaid diagrams), simulates line-item bills of materials against the official Azure Retail Prices API, and evaluates 5-pillar architectural trade-offs.
- **Preserved Frontend Files:**
  - `frontend/src/config/features.ts` (Feature flag configuration)
  - `frontend/src/components/ArchitectStepper.tsx` (5-step progressive workflow navigation)
  - `frontend/src/components/SectionRequirements.tsx` (Natural language ingestion & clarifying questions)
  - `frontend/src/components/SectionAssumptions.tsx` (Workload sizing & safety buffers)
  - `frontend/src/components/SectionArchitecture.tsx` (Mermaid topology rendering & component catalog)
  - `frontend/src/components/SectionCostSimulator.tsx` (Deterministic BOM & line-item meter calculations)
  - `frontend/src/components/SectionSavingsReview.tsx` (5-pillar architectural trade-offs & reservations)
- **Preserved Backend Services & Endpoints:**
  - `backend/src/cloud_recommender/api/routes/architecture.py` (`POST /api/v1/architecture/generate`, `POST /api/v1/architecture/analyze-requirements`)
  - `backend/src/cloud_recommender/services/architecture/generator.py` (LangGraph synthesis graph)
  - `backend/src/cloud_recommender/services/pricing/pricing_engine.py` (Deterministic retail prices calculation engine)
  - `backend/tests/test_architecture_synthesis.py` (Integration test suite)
- **Why Hidden in this Phase:** Keeps user attention centered on live telemetry onboarding, ARM resource graph exploration, and FinOps waste detection for connected Azure subscriptions and GCP projects.

---

### 2.2 Microsoft Fabric Lakehouse Integration (Phase B Analytics)

- **Flag:** `ENABLE_MICROSOFT_FABRIC = false` in `frontend/src/config/features.ts`
- **Purpose:** Planned enterprise telemetry ingestion and Medallion Lakehouse (Bronze / Silver / Gold) architecture in Microsoft Fabric for historical cost analytics and cross-tenant FinOps reporting.
- **Current Status:** In accordance with the offline/mock requirement and zero-execution boundary, Microsoft Fabric telemetry pipelines are planned for Phase B. No active Fabric tenant or license is required for this POC.

---

### 2.3 Amazon Web Services (AWS) Integration

- **Flag:** `ENABLE_AWS = false` in `frontend/src/config/features.ts`
- **Purpose:** Multi-cloud AWS Pricing List API and AWS Cost Explorer integration.
- **Current Status:** Deferred per the Azure-first design mandate specified in `AGENTS.md` and ADR-0001. Live Azure and benchmark GCP integrations take operational precedence.

---

## 3. How to Re-Enable AI Architect

To restore AI Cloud Architect to the application navigation:

1. Open `frontend/src/config/features.ts`.
2. Change the feature flag:
   ```typescript
   export const ENABLE_AI_ARCHITECT = true;
   ```
3. Save the file.
4. Next.js Fast Refresh will immediately restore:
   - "AI Architect" item in the Sidebar navigation (`frontend/src/components/Sidebar.tsx`)
   - Azure AI Foundry Inference Status Pill in Top Navigation (`frontend/src/components/TopNav.tsx`)
   - Primary Hero CTAs and Feature Cards in the Landing View (`frontend/src/components/LandingView.tsx`)
   - Launchpad actions and plan review links in the Executive Dashboard (`frontend/src/components/DashboardView.tsx`)

