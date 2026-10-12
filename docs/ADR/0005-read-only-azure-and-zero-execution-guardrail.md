# ADR 0005: Read-Only Azure Integration & Human-in-the-Loop Zero-Execution Security Boundary

| Status | Accepted |
| :--- | :--- |
| **Date** | 2026-10-12 |
| **Authors** | Architecture Working Group |
| **Deciders** | Lead Cloud Architect, Chief Information Security Officer (CISO) |

---

## Context & Problem Statement

Phase B connects to customer Azure environments to inspect resource inventories, performance metrics, and cost management records. 

Automated tools that possess write permissions (`Contributor` or `Owner`) represent an existential risk:
- Erroneous or unintended API calls could delete production resources, modify network routing, or cause costly outages.
- Enterprise security and compliance boards will categorically refuse to authorize an external POC that requests write or administrative rights.
- Customers must retain total sovereign control over any changes to their infrastructure.

---

## Decision

We establish an immutable **Zero-Execution and Read-Only Security Boundary**:

1. **Strictly Read-Only Azure Role Scope:**
   - Supported roles: `Reader` (inventory and resource topology), `Cost Management Reader` (billing and consumption data), and `Monitoring Reader` (performance telemetry).
   - Explicitly prohibited roles: `Owner`, `Contributor`, `User Access Administrator`, and any custom role containing `*.write` or `*.delete` actions.
   - The Azure client initialization code validates the Service Principal role assignments on startup and immediately aborts if write privileges are detected.

2. **Zero-Execution Policy (Strictly Advisory):**
   - The Cloud Recommender platform **MUST NEVER** execute infrastructure creation, modification, or teardown against customer clouds.
   - All optimization recommendations are output as advisory blueprints, cost models, and downloadable Terraform/Bicep HCL templates.
   - Any actual deployment or reconfiguration requires **explicit human review, authorization, and manual execution** by customer DevOps staff outside the POC.

---

## Consequences

### Positive
- Zero risk of unintended downtime, security misconfiguration, or data loss in customer environments.
- Greatly accelerated security approval process with enterprise enterprise infosec teams.
- Clear, auditable legal and operational boundaries.

### Negative / Trade-offs
- The platform cannot offer one-click automated remediation (e.g. automatically shutting down an idle VM), requiring manual customer execution.
