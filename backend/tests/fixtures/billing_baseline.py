"""Offline TEST-ONLY billing usage fixture.

These rows are synthetic. They must never be loaded by the application at runtime;
tests opt in explicitly via ``load_baseline_usage(service)``.
"""

from typing import Any

from cloud_recommender.schemas.billing_ingestion import (
    BillingIngestionRunResponse,
    BillingUsageRecord,
)

BASELINE_USAGE: list[dict[str, Any]] = [
    # 1. SQL Warehouse 05ed10a52697a344 (19,172 DBU, $42,180.00)
    {
        "record_id": "rec-usage-sql-01",
        "workspace_id": "642006393507276",
        "account_id": "acc-dbx-az-01",
        "sku_name": "SERVERLESS_SQL_COMPUTE",
        "cloud": "azure",
        "usage_start_time": "2026-11-01T00:00:00Z",
        "usage_end_time": "2026-11-01T23:59:59Z",
        "usage_date": "2026-11-01",
        "usage_unit": "DBU",
        "usage_quantity": 4793.0,
        "record_type": "original",
        "ingestion_date": "2026-11-02",
        "billing_origin_product": "SQL",
        "product_features": {"warehouse_type": "Serverless Starter", "size": "2X-Small"},
        "usage_metadata": {"warehouse_id": "05ed10a52697a344"},
        "custom_tags": {"Owner": "Analytics", "CostCenter": "BI-101"},
    },
    {
        "record_id": "rec-usage-sql-02",
        "workspace_id": "642006393507276",
        "account_id": "acc-dbx-az-01",
        "sku_name": "SERVERLESS_SQL_COMPUTE",
        "cloud": "azure",
        "usage_start_time": "2026-11-02T00:00:00Z",
        "usage_end_time": "2026-11-02T23:59:59Z",
        "usage_date": "2026-11-02",
        "usage_unit": "DBU",
        "usage_quantity": 4793.0,
        "record_type": "original",
        "ingestion_date": "2026-11-03",
        "billing_origin_product": "SQL",
        "product_features": {"warehouse_type": "Serverless Starter", "size": "2X-Small"},
        "usage_metadata": {"warehouse_id": "05ed10a52697a344"},
        "custom_tags": {"Owner": "Analytics", "CostCenter": "BI-101"},
    },
    {
        "record_id": "rec-usage-sql-03",
        "workspace_id": "642006393507276",
        "account_id": "acc-dbx-az-01",
        "sku_name": "SERVERLESS_SQL_COMPUTE",
        "cloud": "azure",
        "usage_start_time": "2026-11-03T00:00:00Z",
        "usage_end_time": "2026-11-03T23:59:59Z",
        "usage_date": "2026-11-03",
        "usage_unit": "DBU",
        "usage_quantity": 4793.0,
        "record_type": "original",
        "ingestion_date": "2026-11-04",
        "billing_origin_product": "SQL",
        "product_features": {"warehouse_type": "Serverless Starter", "size": "2X-Small"},
        "usage_metadata": {"warehouse_id": "05ed10a52697a344"},
        "custom_tags": {"Owner": "Analytics", "CostCenter": "BI-101"},
    },
    {
        "record_id": "rec-usage-sql-04",
        "workspace_id": "642006393507276",
        "account_id": "acc-dbx-az-01",
        "sku_name": "SERVERLESS_SQL_COMPUTE",
        "cloud": "azure",
        "usage_start_time": "2026-11-04T00:00:00Z",
        "usage_end_time": "2026-11-04T23:59:59Z",
        "usage_date": "2026-11-04",
        "usage_unit": "DBU",
        "usage_quantity": 4793.0,
        "record_type": "original",
        "ingestion_date": "2026-11-05",
        "billing_origin_product": "SQL",
        "product_features": {"warehouse_type": "Serverless Starter", "size": "2X-Small"},
        "usage_metadata": {"warehouse_id": "05ed10a52697a344"},
        "custom_tags": {"Owner": "Analytics", "CostCenter": "BI-101"},
    },
    # 2. Interactive Cluster 1102-081455-7t3bqp3v (11,180 DBU, $24,600.00)
    {
        "record_id": "rec-usage-cl-01",
        "workspace_id": "642006393507276",
        "account_id": "acc-dbx-az-01",
        "sku_name": "STANDARD_ALL_PURPOSE_COMPUTE",
        "cloud": "azure",
        "usage_start_time": "2026-11-01T00:00:00Z",
        "usage_end_time": "2026-11-04T23:59:59Z",
        "usage_date": "2026-11-04",
        "usage_unit": "DBU",
        "usage_quantity": 11180.0,
        "record_type": "original",
        "ingestion_date": "2026-11-05",
        "billing_origin_product": "ALL_PURPOSE",
        "product_features": {"cluster_name": "adf-deaccelator-compute"},
        "usage_metadata": {"cluster_id": "1102-081455-7t3bqp3v"},
        "custom_tags": {"Owner": "DataPlatform", "Workload": "ETL"},
    },
    # 3. Model Serving Endpoints (6,685 DBU, $26,740.00 across 4 windows)
    {
        "record_id": "rec-usage-srv-01",
        "workspace_id": "642006393507276",
        "account_id": "acc-dbx-az-01",
        "sku_name": "MODEL_SERVING_COMPUTE",
        "cloud": "azure",
        "usage_start_time": "2026-11-01T00:00:00Z",
        "usage_end_time": "2026-11-01T23:59:59Z",
        "usage_date": "2026-11-01",
        "usage_unit": "DBU",
        "usage_quantity": 1671.25,
        "record_type": "original",
        "ingestion_date": "2026-11-02",
        "billing_origin_product": "MODEL_SERVING",
        "product_features": {"endpoint_type": "Foundation Model"},
        "usage_metadata": {"endpoint_id": "databricks-claude-fable-5"},
        "custom_tags": {"Model": "Claude 3.5 Sonnet", "Team": "AI-Eng"},
    },
    {
        "record_id": "rec-usage-srv-02",
        "workspace_id": "642006393507276",
        "account_id": "acc-dbx-az-01",
        "sku_name": "MODEL_SERVING_COMPUTE",
        "cloud": "azure",
        "usage_start_time": "2026-11-02T00:00:00Z",
        "usage_end_time": "2026-11-02T23:59:59Z",
        "usage_date": "2026-11-02",
        "usage_unit": "DBU",
        "usage_quantity": 1671.25,
        "record_type": "original",
        "ingestion_date": "2026-11-03",
        "billing_origin_product": "MODEL_SERVING",
        "product_features": {"endpoint_type": "Foundation Model"},
        "usage_metadata": {"endpoint_id": "databricks-meta-llama-3-1-405b-instruct"},
        "custom_tags": {"Model": "Llama 3.1 405B", "Team": "Research"},
    },
    {
        "record_id": "rec-usage-srv-03",
        "workspace_id": "642006393507276",
        "account_id": "acc-dbx-az-01",
        "sku_name": "MODEL_SERVING_COMPUTE",
        "cloud": "azure",
        "usage_start_time": "2026-11-03T00:00:00Z",
        "usage_end_time": "2026-11-03T23:59:59Z",
        "usage_date": "2026-11-03",
        "usage_unit": "DBU",
        "usage_quantity": 1671.25,
        "record_type": "original",
        "ingestion_date": "2026-11-04",
        "billing_origin_product": "MODEL_SERVING",
        "product_features": {"endpoint_type": "Embeddings"},
        "usage_metadata": {"endpoint_id": "databricks-bge-large-en"},
        "custom_tags": {"Model": "BGE Large", "Team": "Search"},
    },
    {
        "record_id": "rec-usage-srv-04",
        "workspace_id": "642006393507276",
        "account_id": "acc-dbx-az-01",
        "sku_name": "MODEL_SERVING_COMPUTE",
        "cloud": "azure",
        "usage_start_time": "2026-11-04T00:00:00Z",
        "usage_end_time": "2026-11-04T23:59:59Z",
        "usage_date": "2026-11-04",
        "usage_unit": "DBU",
        "usage_quantity": 1671.25,
        "record_type": "original",
        "ingestion_date": "2026-11-05",
        "billing_origin_product": "MODEL_SERVING",
        "product_features": {"endpoint_type": "General"},
        "usage_metadata": {"endpoint_id": "databricks-dbrx-instruct"},
        "custom_tags": {"Model": "DBRX", "Team": "AI-Eng"},
    },
    # 4. Automated Jobs (51,073 DBU, $74,080.00)
    {
        "record_id": "rec-usage-job-01",
        "workspace_id": "642006393507276",
        "account_id": "acc-dbx-az-01",
        "sku_name": "STANDARD_JOBS_COMPUTE",
        "cloud": "azure",
        "usage_start_time": "2026-11-01T00:00:00Z",
        "usage_end_time": "2026-11-04T23:59:59Z",
        "usage_date": "2026-11-04",
        "usage_unit": "DBU",
        "usage_quantity": 51073.0,
        "record_type": "original",
        "ingestion_date": "2026-11-05",
        "billing_origin_product": "JOBS",
        "product_features": {"job_type": "Automated ETL"},
        "usage_metadata": {"job_id": "job-etl-pipeline-nightly"},
        "custom_tags": {"Environment": "Production", "Owner": "DataPlatform"},
    },
    # 5. Databricks Apps (310 DBU, $1,240.00 unattributed compute pool)
    {
        "record_id": "rec-usage-app-01",
        "workspace_id": "642006393507276",
        "account_id": "acc-dbx-az-01",
        "sku_name": "SERVERLESS_REAL_TIME_INFERENCE",
        "cloud": "azure",
        "usage_start_time": "2026-11-01T00:00:00Z",
        "usage_end_time": "2026-11-04T23:59:59Z",
        "usage_date": "2026-11-04",
        "usage_unit": "DBU",
        "usage_quantity": 310.0,
        "record_type": "original",
        "ingestion_date": "2026-11-05",
        "billing_origin_product": "APPS",
        "product_features": {"app_runtime": "Serverless App Container"},
        "usage_metadata": {"app_id": "cement-demand-forecasting"},
        "custom_tags": {"Owner": "SupplyChain"},
    },
]


# TEST-ONLY rate card. The application ships NO prices (M7.1 D1); rates enter at runtime only via
# an approved system.billing.list_prices ingestion. These rows use the real nested shape.
BASELINE_PRICES: list[dict[str, Any]] = [
    {"sku": "SERVERLESS_SQL_COMPUTE", "default": "2.20"},
    {"sku": "STANDARD_ALL_PURPOSE_COMPUTE", "default": "2.20"},
    {"sku": "MODEL_SERVING_COMPUTE", "default": "4.00"},
    {"sku": "STANDARD_JOBS_COMPUTE", "default": "1.45047"},
    {"sku": "SERVERLESS_REAL_TIME_INFERENCE", "default": "4.00"},
]


def baseline_price_rows() -> list[dict[str, Any]]:
    """Rows shaped like SELECT results from system.billing.list_prices (nested pricing struct)."""
    return [
        {
            "account_id": "acc-test",
            "sku_name": p["sku"],
            "cloud": "AZURE",
            "currency_code": "USD",
            "usage_unit": "DBU",
            "price_start_time": "2026-01-01T00:00:00.000+00:00",
            "price_end_time": None,
            "pricing": {"default": p["default"], "promotional": {"default": None}},
        }
        for p in BASELINE_PRICES
    ]


def load_baseline_prices(service: Any) -> None:
    """Ingest the TEST-ONLY rate card through the real row mapper."""
    prices = [service._row_to_price_record(r) for r in baseline_price_rows()]
    service.ingest_price_records([p for p in prices if p is not None])


def load_baseline_usage(service: Any) -> None:
    """Load the synthetic baseline into a BillingIngestionService under test."""
    load_baseline_prices(service)
    for u_dict in BASELINE_USAGE:
        rec = BillingUsageRecord(**u_dict)
        service._annotate(rec)
        service._apply_price_matching(rec)
        service._usage_store[rec.record_id] = rec
    service._runs_store.append(
        BillingIngestionRunResponse(
            run_id="run-baseline-001",
            workspace_id="642006393507276",
            source_table="system.billing.usage",
            requested_period_start="2026-10-01",
            requested_period_end="2026-11-04",
            started_at="2026-11-05T08:00:00Z",
            completed_at="2026-11-05T08:00:02Z",
            status="completed",
            extracted_count=len(BASELINE_USAGE),
            inserted_count=len(BASELINE_USAGE),
            duplicate_count=0,
            retraction_count=0,
            error_count=0,
        )
    )


def baseline_expectations() -> dict[str, Any]:
    """Independently recompute expected totals from BASELINE_USAGE x rate card (list prices).

    Mirrors the pricing rule (DBU x list price, full precision, rounded once at the end)
    without using the service under test.
    """
    from decimal import ROUND_HALF_UP, Decimal

    prices = {p["sku"]: Decimal(p["default"]) for p in BASELINE_PRICES}
    total = Decimal("0")
    dbu = Decimal("0")
    by_product: dict[str, Decimal] = {}
    by_product_dbu: dict[str, Decimal] = {}
    by_resource: dict[str, Decimal] = {}
    for row in BASELINE_USAGE:
        qty = Decimal(str(row["usage_quantity"]))
        cost = qty * prices[row["sku_name"]]
        product = str(row["billing_origin_product"])
        total += cost
        dbu += qty
        by_product[product] = by_product.get(product, Decimal("0")) + cost
        by_product_dbu[product] = by_product_dbu.get(product, Decimal("0")) + qty
        for value in row["usage_metadata"].values():
            by_resource[str(value)] = by_resource.get(str(value), Decimal("0")) + cost
    cents = Decimal("0.01")
    return {
        "total_cost": float(total.quantize(cents, rounding=ROUND_HALF_UP)),
        "total_dbu": float(dbu),
        "by_product": {
            k: float(v.quantize(cents, rounding=ROUND_HALF_UP)) for k, v in by_product.items()
        },
        "by_product_dbu": {k: float(v) for k, v in by_product_dbu.items()},
        "by_resource": {
            k: float(v.quantize(cents, rounding=ROUND_HALF_UP)) for k, v in by_resource.items()
        },
        "row_count": len(BASELINE_USAGE),
    }


def add_synthetic_history(
    service: Any,
    days: int = 20,
    dbu_per_day: float = 50.0,
    spike_day: int | None = None,
    spike_dbu: float = 600.0,
) -> None:
    """Ingest `days` of constant daily SQL usage in Nov 2026 (+ optional spike) for the dev workspace.

    At the rate card ($2.20/DBU) 50 DBU/day is exactly $110.00/day.
    """
    load_baseline_prices(service)
    records = []
    for d in range(1, days + 1):
        qty = spike_dbu if d == spike_day else dbu_per_day
        records.append(
            BillingUsageRecord(
                record_id=f"synthetic-{d:02d}",
                workspace_id="642006393507276",
                sku_name="SERVERLESS_SQL_COMPUTE",
                usage_start_time=f"2026-11-{d:02d}T00:00:00Z",
                usage_end_time=f"2026-11-{d:02d}T23:59:59Z",
                usage_date=f"2026-11-{d:02d}",
                usage_unit="DBU",
                usage_quantity=qty,
                billing_origin_product="SQL",
                usage_metadata={"warehouse_id": "05ed10a52697a344"},
                custom_tags={"Owner": "Analytics"},
            )
        )
    service.ingest_records(records)
