# Security & Permissions Checklist: Databricks FinOps Command Center

- **Repository:** `cloud-recommender-poc`
- **Active Branch:** `feature/databricks-apps-integration`
- **Target Workspace:** Azure Databricks Dev (`642006393507276`)
- **Status:** Security Hardened & Audit Verified

---

## 1. Identity & Least-Privilege Role Matrix

To guarantee adherence to the read-only operational boundary, all identities and service principals must strictly conform to this matrix:

### 1.1 Azure Cloud Tenant Scoping
| Azure Role | Purpose | Status | Permitted? |
|---|---|---|:---:|
| `Reader` | Read subscription metadata and resource groups | **Required** | **YES** |
| `Cost Management Reader` | Ingest aggregated Azure invoice billing telemetry | **Required** | **YES** |
| `Monitoring Reader` | Read infrastructure health and Azure Monitor metrics | **Required** | **YES** |
| `Contributor` | Deploy, resize, or delete cloud infrastructure | **PROHIBITED** | **NO** |
| `Owner` | Manage tenant permissions and assignments | **PROHIBITED** | **NO** |

---

### 1.2 Databricks Unity Catalog Privileges
| Catalog / Schema / Table | Privilege | Justification | Permitted? |
|---|---|---|:---:|
| `system.billing.usage` | `SELECT` | Granular compute and DBU metering events | **YES** |
| `system.billing.list_prices` | `SELECT` | Official published rate card matching | **YES** |
| `system.access.audit` | `SELECT` | Security audit trail validation | **YES** |
| `system.compute.clusters` | `SELECT` | Cluster inventory metadata | **YES** |
| `system.compute.warehouses` | `SELECT` | Warehouse status and configuration inspection | **YES** |
| All other catalogs/schemas | `ALL PRIVILEGES` | Any write, drop, alter, or create statement | **NO** |

---

## 2. Server-Side SQL Security & Guardrail Controls

### 2.1 Multi-Statement & Keyword Blocklist
In `DatabricksSqlService.validate_read_only_statement()`:
- **Single Statement Enforcement**: Any statement containing semicolons `;` (outside string literals) is immediately rejected with `MutationProhibitedError`.
- **Prefix Requirement**: Statements must strictly begin with `SELECT` or `WITH`.
- **Mutation Blocklist**: Case-insensitive AST search rejects `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `MERGE`, `GRANT`, `REVOKE`.
- **System Table Allowlist**: Only explicit tables in `ALLOWED_SYSTEM_TABLES` can be targeted.

### 2.2 Server-Enforced Cryptographic Approval Gate
In `DatabricksSqlService.execute_read_only_statement()`:
- Client flags (`approved=true`, `approval_confirmed=true`) submitted without a verified server token are **rejected**.
- Tokens are generated using HMAC-SHA256:
  $$\text{Payload} = \text{warehouse\_id} : \text{sha256(query)} : \text{expiration\_epoch}$$
- Tokens expire after 300 seconds (5 minutes) and are non-replayable across queries or warehouses.

---

## 3. Credential Redaction & Secret Hygiene

- **Logging**: All log formatters scrub Azure tokens, Databricks personal access tokens (PAT), and client secrets using regex patterns (`dapi[a-f0-9]{32}`, `Bearer [a-zA-Z0-9_\-\.]+`).
- **Object Serialization**: `DatabricksSqlService.__repr__` and `DatabricksAuthService.__repr__` automatically replace `client_secret` and authorization headers with `<REDACTED>`.
- **Zero Frontend Secrets**: No cloud credentials, client secrets, or private keys exist in Next.js code or client-side bundles.

