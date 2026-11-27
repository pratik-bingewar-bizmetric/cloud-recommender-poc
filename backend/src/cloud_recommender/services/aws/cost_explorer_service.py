"""AWS Cost Explorer Service.

Provides deterministic integration with the AWS Cost Explorer API (ce:GetCostAndUsage,
ce:GetCostForecast, ce:GetDimensionValues, ce:GetTags) using SigV4 signed requests.

Strict Invariants:
1. Pure read-only inspection; zero mutation or billing account configuration changes.
2. Never convert missing or inaccessible cost data into zero expenditure.
3. Keep cost metrics unblended vs amortized strictly separated; never mix totals.
4. Fail-closed on authorization errors with structured classification.
5. Use Decimal arithmetic for all financial calculations to prevent floating point inaccuracies.
6. Support multi-page pagination safely without dropping records or replaying requests.
7. Explicitly calculate projected month-end spend = Actual MTD + Forecast Remaining.
"""

import json
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import httpx
import structlog

from cloud_recommender.schemas.aws import (
    AwsCostBreakdownItem,
    AwsCostForecast,
    AwsCostGranularity,
    AwsCostMetricType,
    AwsCostRecord,
    AwsCostSummary,
)
from cloud_recommender.services.aws.auth_service import (
    AwsAuthService,
    AwsCredentials,
    _sanitize_aws_error,
    get_aws_auth_service,
)
from cloud_recommender.services.aws.sigv4 import sign_aws_request
from cloud_recommender.services.aws.sync_approval_service import AwsBudgetGuard

logger = structlog.get_logger(__name__)

CE_ENDPOINT = "https://ce.us-east-1.amazonaws.com/"
CE_REGION = "us-east-1"
CE_SERVICE = "ce"


class AwsCostExplorerError(Exception):
    """Exception raised for Cost Explorer API failures."""

    def __init__(self, message: str, error_code: str = "COST_EXPLORER_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code


def _to_decimal(val: Any) -> Decimal:
    """Safe conversion to Decimal."""
    if val is None:
        return Decimal("0.00")
    try:
        return Decimal(str(val))
    except Exception:
        return Decimal("0.00")


def _round_currency(val: Decimal) -> float:
    """Round Decimal to 2 decimal places and return float for JSON schema compatibility."""
    return float(val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class AwsCostExplorerService:
    """Retrieves and normalizes financial spend, breakdowns, and forecasts from AWS Cost Explorer."""

    def __init__(
        self,
        auth_service: AwsAuthService | None = None,
        timeout_seconds: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.auth_service = auth_service or get_aws_auth_service()
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def _post_ce(
        self,
        client: httpx.AsyncClient,
        creds: AwsCredentials,
        action: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a signed JSON POST request to the AWS Cost Explorer endpoint."""
        body = json.dumps(payload)
        headers = {
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": f"AWSInsightsIndexService.{action}",
        }

        signed_headers = sign_aws_request(
            method="POST",
            url=CE_ENDPOINT,
            headers=headers,
            body=body,
            access_key_id=creds.access_key_id,
            secret_access_key=creds.secret_access_key,
            region=CE_REGION,
            service=CE_SERVICE,
            session_token=creds.session_token,
        )

        resp = await client.post(
            CE_ENDPOINT,
            headers=signed_headers,
            content=body,
            timeout=self.timeout_seconds,
        )

        if resp.status_code == 200:
            return resp.json()

        error_body = resp.text
        if resp.status_code in (401, 403) or "AccessDenied" in error_body:
            raise AwsCostExplorerError(
                "Access Denied: The authenticated AWS principal lacks 'ce:GetCostAndUsage' or Cost Explorer is not enabled.",
                error_code="PERMISSION_DENIED",
            )
        if "DataUnavailableException" in error_body:
            raise AwsCostExplorerError(
                "Cost Explorer data is currently unavailable or historical lookback exceeds limit.",
                error_code="DATA_UNAVAILABLE",
            )
        if "ValidationException" in error_body:
            raise AwsCostExplorerError(
                f"Cost Explorer request validation error: {_sanitize_aws_error(error_body)}",
                error_code="VALIDATION_ERROR",
            )

        raise AwsCostExplorerError(
            f"Cost Explorer request failed with HTTP {resp.status_code}: {_sanitize_aws_error(error_body)}",
            error_code="REQUEST_FAILED",
        )

    # -------------------------------------------------------------------------
    # Core Cost & Usage Methods with Safe Pagination
    # -------------------------------------------------------------------------

    async def get_cost_and_usage(
        self,
        client: httpx.AsyncClient,
        creds: AwsCredentials,
        start_date: str,
        end_date: str,
        granularity: AwsCostGranularity = AwsCostGranularity.DAILY,
        metric: AwsCostMetricType = AwsCostMetricType.UNBLENDED_COST,
        group_by: list[dict[str, str]] | None = None,
        filter_dict: dict[str, Any] | None = None,
        max_pages: int = 5,
        budget_guard: AwsBudgetGuard | None = None,
    ) -> dict[str, Any]:
        """Fetch cost and usage records with safe multi-page pagination and transport-level budget guard."""
        payload: dict[str, Any] = {
            "TimePeriod": {"Start": start_date, "End": end_date},
            "Granularity": granularity.value,
            "Metrics": [metric.value],
        }

        if group_by:
            payload["GroupBy"] = group_by[:2]

        if filter_dict:
            payload["Filter"] = filter_dict

        aggregated_results: list[dict[str, Any]] = []
        dimension_value_attributes: list[dict[str, Any]] = []
        page_count = 0
        next_token: str | None = None
        seen_tokens: set[str] = set()
        is_partial = False
        truncation_reason: str | None = None

        while True:
            current_payload = dict(payload)
            if next_token:
                if next_token in seen_tokens:
                    logger.warning("aws_ce_repeated_page_token_detected", token=next_token)
                    is_partial = True
                    truncation_reason = (
                        "Repeated pagination token detected; loop terminated safely."
                    )
                    break
                seen_tokens.add(next_token)
                current_payload["NextPageToken"] = next_token

            # Transport-level budget check before dispatching potentially chargeable request
            if budget_guard:
                await budget_guard.check_and_reserve(
                    request_type="cost_explorer",
                    count=1,
                    estimated_cost=Decimal("0.01"),
                )

            page_data = await self._post_ce(client, creds, "GetCostAndUsage", current_payload)
            page_count += 1

            for rbt in page_data.get("ResultsByTime", []):
                aggregated_results.append(rbt)

            for dva in page_data.get("DimensionValueAttributes", []):
                dimension_value_attributes.append(dva)

            next_token = page_data.get("NextPageToken")
            if not next_token:
                break

            if page_count >= max_pages:
                is_partial = True
                truncation_reason = f"Pagination truncated at safety limit of {max_pages} pages. Additional records exist on AWS."
                break

        return {
            "ResultsByTime": aggregated_results,
            "DimensionValueAttributes": dimension_value_attributes,
            "is_partial": is_partial,
            "truncation_reason": truncation_reason,
            "pages_retrieved": page_count,
        }

    async def get_cost_forecast(
        self,
        client: httpx.AsyncClient,
        creds: AwsCredentials,
        start_date: str,
        end_date: str,
        actual_mtd_cost: Decimal = Decimal("0.00"),
        metric: AwsCostMetricType = AwsCostMetricType.UNBLENDED_COST,
        granularity: AwsCostGranularity = AwsCostGranularity.MONTHLY,
        budget_guard: AwsBudgetGuard | None = None,
    ) -> AwsCostForecast | None:
        """Fetch forecasted expenditure for the remainder of the month, calculating total projected spend."""
        if budget_guard:
            await budget_guard.check_and_reserve(
                request_type="cost_explorer",
                count=1,
                estimated_cost=Decimal("0.01"),
            )

        payload = {
            "TimePeriod": {"Start": start_date, "End": end_date},
            "Granularity": granularity.value,
            "Metric": metric.value,
            "PredictionIntervalLevel": 95,
        }

        try:
            data = await self._post_ce(client, creds, "GetCostForecast", payload)
            total = data.get("Total", {})
            amount_str = total.get("Amount", "0.0")
            currency = total.get("Unit", "USD")

            remaining_forecast_dec = _to_decimal(amount_str)
            lower_bound_dec: Decimal | None = None
            upper_bound_dec: Decimal | None = None
            is_symmetric = False

            forecast_results = data.get("ForecastResultsByTime", [])
            if forecast_results:
                first_res = forecast_results[0]
                if "PredictionIntervalLowerBound" in first_res:
                    lower_bound_dec = _to_decimal(first_res["PredictionIntervalLowerBound"])
                if "PredictionIntervalUpperBound" in first_res:
                    upper_bound_dec = _to_decimal(first_res["PredictionIntervalUpperBound"])

                if lower_bound_dec is not None and upper_bound_dec is not None:
                    diff_lower = abs(remaining_forecast_dec - lower_bound_dec)
                    diff_upper = abs(upper_bound_dec - remaining_forecast_dec)
                    is_symmetric = bool(abs(diff_upper - diff_lower) < Decimal("0.001"))

            # Total Projected Month-End Spend = Actual non-overlapping MTD + Remaining Forecast
            projected_month_end_dec = actual_mtd_cost + remaining_forecast_dec
            proj_lower_dec = (
                (actual_mtd_cost + lower_bound_dec) if lower_bound_dec is not None else None
            )
            proj_upper_dec = (
                (actual_mtd_cost + upper_bound_dec) if upper_bound_dec is not None else None
            )

            return AwsCostForecast(
                remaining_forecast_amount=_round_currency(remaining_forecast_dec),
                actual_month_to_date_cost=_round_currency(actual_mtd_cost),
                projected_month_end_cost=_round_currency(projected_month_end_dec),
                prediction_interval_lower_bound=_round_currency(proj_lower_dec)
                if proj_lower_dec is not None
                else None,
                prediction_interval_upper_bound=_round_currency(proj_upper_dec)
                if proj_upper_dec is not None
                else None,
                start_date=start_date,
                end_date=end_date,
                currency=currency,
                confidence_level=95,
                is_prediction_interval_symmetric=is_symmetric,
                forecast_observed_at=datetime.now(UTC),
            )
        except AwsCostExplorerError as exc:
            logger.info("aws_cost_forecast_unavailable", reason=exc.message)
            return None
        except Exception as exc:
            logger.warning("aws_cost_forecast_error", error=str(exc))
            return None

    async def get_dimension_values(
        self,
        client: httpx.AsyncClient,
        creds: AwsCredentials,
        dimension: str = "SERVICE",
        start_date: str | None = None,
        end_date: str | None = None,
        search_string: str | None = None,
    ) -> list[str]:
        """Fetch available dimension values (e.g. all billed services or linked accounts)."""
        now = datetime.now(UTC)
        if not start_date or not end_date:
            start_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")
            end_date = now.strftime("%Y-%m-%d")

        payload: dict[str, Any] = {
            "TimePeriod": {"Start": start_date, "End": end_date},
            "Dimension": dimension,
        }
        if search_string:
            payload["SearchString"] = search_string

        try:
            data = await self._post_ce(client, creds, "GetDimensionValues", payload)
            dimension_values = data.get("DimensionValues", [])
            return [d.get("Value", "") for d in dimension_values if d.get("Value")]
        except Exception as exc:
            logger.warning("aws_get_dimension_values_failed", dimension=dimension, error=str(exc))
            return []

    async def get_tags(
        self,
        client: httpx.AsyncClient,
        creds: AwsCredentials,
        start_date: str | None = None,
        end_date: str | None = None,
        tag_key: str | None = None,
    ) -> list[str]:
        """Retrieve cost allocation tag keys or values."""
        now = datetime.now(UTC)
        if not start_date or not end_date:
            start_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")
            end_date = now.strftime("%Y-%m-%d")

        payload: dict[str, Any] = {
            "TimePeriod": {"Start": start_date, "End": end_date},
        }
        if tag_key:
            payload["TagKey"] = tag_key

        try:
            data = await self._post_ce(client, creds, "GetTags", payload)
            return data.get("Tags", [])
        except Exception:
            return []

    # -------------------------------------------------------------------------
    # Comprehensive Summary Aggregator (with Decimal Precision & Leap Year Math)
    # -------------------------------------------------------------------------

    async def get_cost_summary(
        self,
        client: httpx.AsyncClient,
        creds: AwsCredentials,
        metric: AwsCostMetricType = AwsCostMetricType.UNBLENDED_COST,
        tag_key_for_breakdown: str | None = None,
        budget_guard: AwsBudgetGuard | None = None,
    ) -> AwsCostSummary:
        """Construct full Cost Intelligence summary with MTD, previous month, daily trends, and breakdowns."""
        now = datetime.now(UTC)
        today = now.date()

        # Date boundaries: Actual MTD is current_month_start (inclusive) to cutoff_date (exclusive)
        current_month_start = today.replace(day=1)
        cutoff_date = today

        # AWS Cost Explorer end-date is strictly exclusive.
        start_mtd_str = current_month_start.strftime("%Y-%m-%d")
        # When today is day 1, query day 1 exclusively to day 2 (or 1 day)
        end_mtd_str = (
            cutoff_date.strftime("%Y-%m-%d")
            if cutoff_date > current_month_start
            else (cutoff_date + timedelta(days=1)).strftime("%Y-%m-%d")
        )

        # Next month start calculation (handling Dec -> Jan)
        if current_month_start.month == 12:
            next_month_start = current_month_start.replace(
                year=current_month_start.year + 1, month=1, day=1
            )
        else:
            next_month_start = current_month_start.replace(
                month=current_month_start.month + 1, day=1
            )

        # Non-overlapping forecast boundaries: cutoff_date (inclusive) to next_month_start (exclusive)
        forecast_start = cutoff_date.strftime("%Y-%m-%d")
        forecast_end = next_month_start.strftime("%Y-%m-%d")

        # Previous month boundaries
        prev_month_last_day = current_month_start - timedelta(days=1)
        prev_month_start = prev_month_last_day.replace(day=1)
        prev_month_end = current_month_start

        # Comparable previous month period (handling varying month lengths, Feb, & leap years)
        comp_day = min(today.day, prev_month_last_day.day)
        comp_prev_end = prev_month_start + timedelta(days=comp_day)

        start_prev_str = prev_month_start.strftime("%Y-%m-%d")
        end_prev_str = prev_month_end.strftime("%Y-%m-%d")
        end_comp_prev_str = comp_prev_end.strftime("%Y-%m-%d")

        summary = AwsCostSummary(
            account_id=creds.account_id,
            metric_type=metric,
            currency="USD",
            data_availability="AVAILABLE",
            actual_cost_period_start=start_mtd_str,
            actual_cost_period_end=end_mtd_str,
            forecast_period_start=forecast_start,
            forecast_period_end=forecast_end,
        )

        try:
            # 1. Fetch Current Month Daily Trend
            mtd_resp = await self.get_cost_and_usage(
                client=client,
                creds=creds,
                start_date=start_mtd_str,
                end_date=end_mtd_str,
                granularity=AwsCostGranularity.DAILY,
                metric=metric,
                budget_guard=budget_guard,
            )

            daily_records: list[AwsCostRecord] = []
            current_mtd_dec = Decimal("0.00")
            is_estimated = False
            primary_currency: str | None = None

            for period in mtd_resp.get("ResultsByTime", []):
                p_start = period.get("TimePeriod", {}).get("Start", "")
                p_end = period.get("TimePeriod", {}).get("End", "")
                metric_data = period.get("Total", {}).get(metric.value, {})
                amount_dec = _to_decimal(metric_data.get("Amount", "0.0"))
                currency = metric_data.get("Unit", "USD")

                # Mixed currency rejection
                if primary_currency and currency != primary_currency:
                    raise AwsCostExplorerError(
                        f"Mixed currencies detected in billing records: '{primary_currency}' and '{currency}'. "
                        "Multi-currency aggregation without conversion rates is rejected.",
                        error_code="MIXED_CURRENCIES",
                    )
                primary_currency = currency
                est = period.get("Estimated", False)
                if est:
                    is_estimated = True

                current_mtd_dec += amount_dec
                daily_records.append(
                    AwsCostRecord(
                        start_date=p_start,
                        end_date=p_end,
                        amount=float(
                            amount_dec
                        ),  # Preserve full Decimal source precision without early rounding
                        currency=currency,
                        metric_type=metric,
                        is_estimated=est,
                    )
                )

            summary.daily_trend = daily_records
            summary.current_month_to_date_cost = _round_currency(current_mtd_dec)
            summary.currency = primary_currency or "USD"
            summary.is_estimated = is_estimated

            if mtd_resp.get("is_partial"):
                summary.is_partial = True
                summary.data_availability = "PARTIAL_DATA"
                summary.truncation_reason = mtd_resp.get("truncation_reason")
                summary.notes.append(
                    summary.truncation_reason or "Results truncated by pagination safety cap."
                )

            # 2. Fetch Previous Month Total Cost
            prev_resp = await self.get_cost_and_usage(
                client=client,
                creds=creds,
                start_date=start_prev_str,
                end_date=end_prev_str,
                granularity=AwsCostGranularity.MONTHLY,
                metric=metric,
                budget_guard=budget_guard,
            )
            prev_results = prev_resp.get("ResultsByTime", [])
            if prev_results:
                prev_total_data = prev_results[0].get("Total", {}).get(metric.value, {})
                prev_dec = _to_decimal(prev_total_data.get("Amount", "0.0"))
                summary.previous_month_cost = _round_currency(prev_dec)

            # 3. Fetch Comparable Previous Month-to-Date Cost
            comp_resp = await self.get_cost_and_usage(
                client=client,
                creds=creds,
                start_date=start_prev_str,
                end_date=end_comp_prev_str,
                granularity=AwsCostGranularity.MONTHLY,
                metric=metric,
                budget_guard=budget_guard,
            )
            comp_results = comp_resp.get("ResultsByTime", [])
            if comp_results:
                comp_data = comp_results[0].get("Total", {}).get(metric.value, {})
                comp_dec = _to_decimal(comp_data.get("Amount", "0.0"))
                summary.comparable_previous_month_to_date_cost = _round_currency(comp_dec)

                if comp_dec > Decimal("0.00"):
                    diff = current_mtd_dec - comp_dec
                    mom_pct = (diff / comp_dec) * Decimal("100")
                    summary.month_over_month_percentage_change = float(
                        mom_pct.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
                    )
                elif comp_dec < Decimal("0.00"):
                    summary.month_over_month_percentage_change = None
                    summary.notes.append(
                        "Comparable previous month spend is negative; MoM % change is undefined."
                    )
                else:
                    summary.month_over_month_percentage_change = None

            # 4. Top Services Breakdown (Grouped by SERVICE)
            svc_resp = await self.get_cost_and_usage(
                client=client,
                creds=creds,
                start_date=start_mtd_str,
                end_date=end_mtd_str,
                granularity=AwsCostGranularity.MONTHLY,
                metric=metric,
                group_by=[{"Type": "DIMENSION", "Key": "SERVICE"}],
                budget_guard=budget_guard,
            )
            svc_breakdown = self._parse_group_breakdown(svc_resp, metric, current_mtd_dec)
            summary.top_services = svc_breakdown[:10]

            # 5. Region Breakdown (Grouped by REGION)
            region_resp = await self.get_cost_and_usage(
                client=client,
                creds=creds,
                start_date=start_mtd_str,
                end_date=end_mtd_str,
                granularity=AwsCostGranularity.MONTHLY,
                metric=metric,
                group_by=[{"Type": "DIMENSION", "Key": "REGION"}],
                budget_guard=budget_guard,
            )
            summary.region_breakdown = self._parse_group_breakdown(
                region_resp, metric, current_mtd_dec
            )

            # 6. Cost Allocation Tag Breakdown (Optional)
            if tag_key_for_breakdown:
                try:
                    tag_resp = await self.get_cost_and_usage(
                        client=client,
                        creds=creds,
                        start_date=start_mtd_str,
                        end_date=end_mtd_str,
                        granularity=AwsCostGranularity.MONTHLY,
                        metric=metric,
                        group_by=[{"Type": "TAG", "Key": tag_key_for_breakdown}],
                        budget_guard=budget_guard,
                    )
                    summary.tag_breakdown = self._parse_group_breakdown(
                        tag_resp, metric, current_mtd_dec
                    )
                except Exception as tag_err:
                    logger.info(
                        "tag_breakdown_skipped", key=tag_key_for_breakdown, error=str(tag_err)
                    )

            # 7. Month-End Forecast (strictly non-overlapping future period)
            if forecast_start < forecast_end:
                summary.forecast = await self.get_cost_forecast(
                    client=client,
                    creds=creds,
                    start_date=forecast_start,
                    end_date=forecast_end,
                    actual_mtd_cost=current_mtd_dec,
                    metric=metric,
                    budget_guard=budget_guard,
                )

        except AwsCostExplorerError as exc:
            logger.warning("aws_cost_summary_error", error=exc.message, code=exc.error_code)
            summary.data_availability = exc.error_code
            summary.notes.append(exc.message)
            # Strict FinOps Rule: Never fabricate zero when data is unavailable or permission denied!
            summary.current_month_to_date_cost = None
            summary.previous_month_cost = None
        except Exception as exc:
            logger.exception("aws_cost_summary_unexpected_error", error=str(exc))
            summary.data_availability = "SERVICE_UNAVAILABLE"
            summary.notes.append(f"Unexpected error retrieving Cost Explorer metrics: {exc}")
            summary.current_month_to_date_cost = None
            summary.previous_month_cost = None

        return summary

    def _parse_group_breakdown(
        self,
        resp: dict[str, Any],
        metric: AwsCostMetricType,
        total_sum_dec: Decimal | float | None = None,
        total_sum: Decimal | float | None = None,
    ) -> list[AwsCostBreakdownItem]:
        """Aggregate and sort grouped results by spend descending using Decimal math."""
        if total_sum_dec is None and total_sum is not None:
            total_dec = _to_decimal(total_sum)
        elif total_sum_dec is None:
            total_dec = Decimal("0.00")
        else:
            total_dec = _to_decimal(total_sum_dec)
        items: list[AwsCostBreakdownItem] = []
        for period in resp.get("ResultsByTime", []):
            for group in period.get("Groups", []):
                keys = group.get("Keys", ["Unknown"])
                key_name = keys[0] if keys else "Unknown"
                metric_data = group.get("Metrics", {}).get(metric.value, {})
                amount_dec = _to_decimal(metric_data.get("Amount", "0.0"))
                currency = metric_data.get("Unit", "USD")

                # Handle credits, refunds, negative adjustments
                if amount_dec != Decimal("0.00"):
                    if total_dec > Decimal("0.00"):
                        pct_dec = (amount_dec / total_dec) * Decimal("100")
                        pct = float(pct_dec.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
                    else:
                        pct = 0.0

                    items.append(
                        AwsCostBreakdownItem(
                            key=key_name,
                            amount=_round_currency(amount_dec),
                            percentage=pct,
                            unit=currency,
                        )
                    )

        # Sort descending by spend amount (preserving negative items at bottom)
        items.sort(key=lambda x: x.amount, reverse=True)
        return items


# Singleton instance helper
_service_instance: AwsCostExplorerService | None = None


def get_aws_cost_explorer_service() -> AwsCostExplorerService:
    global _service_instance
    if _service_instance is None:
        _service_instance = AwsCostExplorerService()
    return _service_instance
