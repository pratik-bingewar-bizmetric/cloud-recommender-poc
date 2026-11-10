# Production Secrets Management & Security Architecture

> **Application:** Bizmetric FinOps & Infrastructure Intelligence Platform  
> **Target Environment:** Azure Databricks Apps (`bizmetric-finops`)  
> **Security Standard:** Zero-Trust Secret Isolation & Least Privilege  
> **Status:** Production Reference  

---

## 1. Zero-Trust Security Policies & Invariants

The Bizmetric FinOps Platform enforces strict operational security rules:

1. **Zero Plaintext Secrets in Repositories:** No production credentials, API keys, or database passwords may ever be committed to Git. `.env` and `.env.local` files are strictly gitignored.
2. **Zero Credentials in Frontend Bundles:** Client-side JavaScript bundles never contain Azure secrets, Databricks tokens, or database passwords. All external communications originate from the backend.
3. **Zero Secrets in Application Logs:** Structured logging (`structlog`) sanitizes log events, redacting authorization headers, passwords, and tokens.
4. **Zero Plaintext Tokens in Database:** Approval tokens for change control are cryptographically signed using HMAC-SHA256 with key rotation (`finops_signing_kid`).
5. **Zero Mutation Cloud Boundary:** The platform operates strictly in read-only mode with no write or delete permissions on customer clouds.

---

## 2. Secrets Management via Databricks Secret Scopes

In Azure Databricks, credentials are stored in secure, encrypted Databricks Secret Scopes backed by Databricks internal storage or Azure Key Vault:

### 2.1 Approved Production Secret Keys

| Secret Scope | Secret Key | Description | Consumed By |
|:---|:---|:---|:---|
| `finops-secrets` | `azure-client-secret` | Microsoft Entra ID Service Principal client secret. | Azure Cost Management & ARM Ingestion |
| `finops-secrets` | `postgres-password` | Runtime password for PostgreSQL `finops_app_user`. | SQLAlchemy asyncpg connection pool |
| `finops-secrets` | `postgres-admin-password` | Standalone migration password for `finops_migrator`. | Standalone migration runner |
| `finops-secrets` | `finops-signing-secret` | HMAC-SHA256 secret for signing approval tokens. | Token signing and verification engine |

### 2.2 CLI Commands for Secret Provisioning
```bash
# 1. Create dedicated secret scope
databricks secrets create-scope finops-secrets --profile azure-dev

# 2. Store secrets interactively or via string value
databricks secrets put-secret finops-secrets azure-client-secret --profile azure-dev
databricks secrets put-secret finops-secrets postgres-password --profile azure-dev
databricks secrets put-secret finops-secrets finops-signing-secret --profile azure-dev

# 3. Verify registered keys (secret values are never echoed)
databricks secrets list-secrets finops-secrets --profile azure-dev
```

---

## 3. Environment Variable Injection into Databricks Apps

In the production `app.yaml` manifest, secrets are referenced using the supported Databricks Secret syntax:

```yaml
env:
  - name: "APP_ENV"
    value: "production"
  - name: "AZURE_CLIENT_ID"
    value: "4b8e21a0-7f3c-4d89-912b-3e5f7a9c1d02"
  - name: "AZURE_TENANT_ID"
    value: "fe82a67c-faa7-4d9a-bbfa-7d25b7047b41"
  # Secure Secret Scope Reference
  - name: "AZURE_CLIENT_SECRET"
    valueFrom:
      secret:
        scope: "finops-secrets"
        key: "azure-client-secret"
  - name: "DATABASE_URL"
    value: "postgresql+asyncpg://finops_app_user:{{secrets/finops-secrets/postgres-password}}@psql-finops-prod.postgres.database.azure.com:5432/cloud_recommender?ssl=require"
```

---

## 4. Credential Rotation Procedures (Zero Downtime)

### 4.1 Azure Service Principal Secret Rotation
1. In Microsoft Entra ID, generate a new client secret (Secret B) on the Service Principal without deleting Secret A.
2. Update the Databricks Secret Scope:
   ```bash
   databricks secrets put-secret finops-secrets azure-client-secret --string-value "<Secret-B-Value>" --profile azure-dev
   ```
3. Restart or redeploy the Databricks App to load the updated secret:
   ```bash
   databricks apps restart bizmetric-finops --profile azure-dev
   ```
4. Verify API connectivity via the health probe.
5. In Microsoft Entra ID, delete the retired Secret A.

### 4.2 Database Password Rotation
1. In PostgreSQL, update `finops_app_user` password.
2. Update `finops-secrets/postgres-password` in the Databricks Secret Scope.
3. Restart the Databricks App.

### 4.3 HMAC Token Signing Key Ring Rotation
The platform supports zero-downtime key rotation via the `FINOPS_VERIFICATION_KEYS` dictionary:
- Set `FINOPS_SIGNING_KID="k2-2026"` for signing newly issued tokens.
- Maintain `{"k1-2026": "<old-key>", "k2-2026": "<new-key>"}` in `FINOPS_VERIFICATION_KEYS` to validate legacy in-flight tokens until their TTL expires.

---

## 5. Security Audit Verification

An automated security audit script scans for credential leakage:
- Verification that no `.env` files with production values exist in source trees.
- Verification that `frontend/src/` contains zero private keys, connection strings, or cloud secrets.
- Verification that all backend log formatters redact Authorization headers and passwords.

