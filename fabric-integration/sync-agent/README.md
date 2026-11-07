# Microsoft Fabric FinOps Sync Agent

Production-grade local Python synchronization agent for extracting authentic Azure cloud infrastructure inventory, Cost Management consumption data, and Azure Monitor telemetry, and persisting them into **Microsoft Fabric OneLake Delta tables**.

---

## 1. Overview & Architecture

The FinOps Sync Agent bridges live Microsoft Azure subscriptions and Microsoft Fabric Lakehouse storage:

```
+-----------------------------------------------------------------------------------+
|                              Azure Cloud Environment                              |
|                                                                                   |
|  +------------------------+  +------------------------+  +---------------------+  |
|  |  Azure Resource Graph  |  |    Cost Management     |  |    Azure Monitor    |  |
|  |     Inventory API      |  |       Query API        |  |     Metrics API     |  |
|  +-----------+------------+  +-----------+------------+  +----------+----------+  |
+--------------|---------------------------|--------------------------|-------------+
               |                           |                          |
               v                           v                          v
+-----------------------------------------------------------------------------------+
|                         FinOps Sync Agent (Local Windows)                         |
|                                                                                   |
|  * AzureCliAuthManager (Audience-Routed Bearer Tokens)                            |
|  * TokenRedactionFilter (Secret & Token Redaction)                                |
|  * Adaptive Backoff & 429 Rate-Limit Recovery                                     |
|  * Deterministic SHA-256 Hashing & Table Deduplication                            |
+-----------------------------------------------------------------------------------+
                                           |
                                           v
+-----------------------------------------------------------------------------------+
|                      Microsoft Fabric OneLake (Delta Lake)                        |
|                                                                                   |
|  * finops_lakehouse: 4bba3647-0112-4adc-8b18-f7a422461404                         |
|  * Workspace:        672a6995-4190-4000-befd-5cc6479c3f74                         |
|                                                                                   |
|  +------------------------+  +------------------------+  +---------------------+  |
|  |   resource_inventory   |  |      cost_details      |  |  resource_metrics   |  |
|  |      Delta Table       |  |      Delta Table       |  |     Delta Table     |  |
|  +------------------------+  +------------------------+  +---------------------+  |
|  +----------------------------------------------------+                           |
|  |                    sync_history                    |                           |
|  |                 Audit Ledger Delta                 |                           |
|  +----------------------------------------------------+                           |
+-----------------------------------------------------------------------------------+
```

---

## 2. Core Operational Guarantees

1. **Zero Resource Mutations:** Strictly executes read-only queries against customer Azure subscriptions.
2. **Deterministic Record Hashing:**
   - `cost_record_id`: SHA-256 hash of `(subscription_id, usage_date, resource_id, service_name, meter_category, meter_name, charge_type)`.
   - `metric_record_id`: SHA-256 hash of `(resource_id, metric_name, timestamp)`.
3. **Idempotent Appends & Deduplication:**
   - Pre-reads existing Delta table IDs on OneLake before appending new batches.
   - Prevents duplicate cost and metric records upon re-execution.
4. **429 Rate-Limit Resilience:**
   - Automatically inspects `x-ms-ratelimit-microsoft.costmanagement-clienttype-retry-after` response headers from Azure Cost Management and pauses execution accordingly.
5. **Secret Redaction:**
   - Intercepts all logger records to prevent OAuth bearer tokens and secrets from leaking into logs.

---

## 3. Directory Layout

```
fabric-integration/sync-agent/
|-- __init__.py
|-- config.py                 # Configuration loader and Lakehouse URI resolver
|-- auth.py                   # Audience-routed Azure CLI authentication manager
|-- models.py                 # Typed DTOs and domain records
|-- sync_logger.py            # Logger configuration with TokenRedactionFilter
|-- azure_client.py           # Azure Resource Graph inventory extractor
|-- cost_client.py            # Azure Cost Management extractor with 429 backoff
|-- monitor_client.py         # Azure Monitor metrics extractor
|-- delta_writer.py           # OneLake Delta Lake reader/writer & deduplication engine
|-- azure_sync_agent.py       # Main CLI entry point and pipeline orchestrator
|-- verify_sync_tables.py     # Delta table validation and inspection utility
`-- tests/                    # Pytest unit and integration test suite
    |-- conftest.py
    |-- test_models.py
    |-- test_config.py
    |-- test_auth.py
    |-- test_sync_logger.py
    |-- test_azure_client.py
    |-- test_cost_client.py
    |-- test_monitor_client.py
    |-- test_delta_writer.py
    |-- test_azure_sync_agent_cli.py
```

---

## 4. CLI Usage

Execute the agent using the virtual environment:

### Pre-flight Verification
Checks active Azure CLI session, tenant, subscription, and verifies that the OneLake Delta tables exist:
```bash
python fabric-integration/sync-agent/azure_sync_agent.py --check
```

### Full Synchronization
Runs inventory extraction, Cost Management ingestion, Monitor metrics, and writes an audit record to `sync_history`:
```bash
python fabric-integration/sync-agent/azure_sync_agent.py --full
```

### Dry-Run Mode
Extracts and validates all Azure telemetry without writing to OneLake:
```bash
python fabric-integration/sync-agent/azure_sync_agent.py --full --dry-run
```

### Granular Execution Modes
```bash
# Sync inventory only
python fabric-integration/sync-agent/azure_sync_agent.py --inventory

# Sync Cost Management data only
python fabric-integration/sync-agent/azure_sync_agent.py --cost

# Sync Azure Monitor metrics only
python fabric-integration/sync-agent/azure_sync_agent.py --metrics
```

### Inspect OneLake Delta Tables
```bash
python fabric-integration/sync-agent/verify_sync_tables.py
```

---

## 5. Running the Automated Test Suite

```bash
pytest fabric-integration/sync-agent/tests/ -v
```
All 30 unit tests pass with zero warnings, validating credential caching, schema mapping, deterministic hashing, deduplication logic, and CLI pipelines without external network dependencies.

