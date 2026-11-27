"""AWS CloudWatch Historical Telemetry & Resource Utilization Service.

Queries standard AWS CloudWatch metrics (ListMetrics, GetMetricData) for discovered
Compute, Storage, Database, and Networking resources using SigV4 signed requests.

Strict Invariants:
1. Zero mutation: never creates alarms, metric filters, or agent installations.
2. Memory utilization for EC2 is strictly marked INSTRUMENTATION_REQUIRED unless a CloudWatch agent exists.
3. S3 metrics respect daily granularity; never enables paid request metrics.
4. Container Insights and agent monitoring are never enabled automatically.
"""

import re
import urllib.parse
from datetime import UTC, datetime, timedelta

import httpx
import structlog

from cloud_recommender.schemas.aws import (
    AwsMetricDataPoint,
    AwsResourceItem,
    AwsResourceMetricSeries,
)
from cloud_recommender.services.aws.auth_service import (
    AwsAuthService,
    AwsCredentials,
    _sanitize_aws_error,
    get_aws_auth_service,
)
from cloud_recommender.services.aws.sigv4 import sign_aws_request

logger = structlog.get_logger(__name__)


class AwsCloudWatchMetricsService:
    """Retrieves and normalizes CloudWatch time-series metrics across AWS resources."""

    def __init__(
        self,
        auth_service: AwsAuthService | None = None,
        timeout_seconds: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.auth_service = auth_service or get_aws_auth_service()
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def _query_cloudwatch(
        self,
        client: httpx.AsyncClient,
        creds: AwsCredentials,
        region: str,
        params: dict[str, str],
    ) -> str:
        """Execute a signed form-urlencoded POST request to CloudWatch."""
        endpoint = f"https://monitoring.{region}.amazonaws.com/"
        body = urllib.parse.urlencode(params)
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        }

        signed_headers = sign_aws_request(
            method="POST",
            url=endpoint,
            headers=headers,
            body=body,
            access_key_id=creds.access_key_id,
            secret_access_key=creds.secret_access_key,
            region=region,
            service="monitoring",
            session_token=creds.session_token,
        )

        resp = await client.post(
            endpoint,
            headers=signed_headers,
            content=body,
            timeout=self.timeout_seconds,
        )

        if resp.status_code == 200:
            return resp.text

        error_text = resp.text
        logger.warning(
            "cloudwatch_query_failed",
            status_code=resp.status_code,
            error=_sanitize_aws_error(error_text[:300]),
        )
        raise RuntimeError(
            f"CloudWatch request failed with HTTP {resp.status_code}: {_sanitize_aws_error(error_text[:200])}"
        )

    # -------------------------------------------------------------------------
    # Metric Queries by Resource Type
    # -------------------------------------------------------------------------

    async def get_resource_metrics(
        self,
        client: httpx.AsyncClient,
        creds: AwsCredentials,
        resource: AwsResourceItem,
        lookback_hours: int = 24,
    ) -> list[AwsResourceMetricSeries]:
        """Fetch all relevant historical metrics for a single discovered resource."""
        now = datetime.now(UTC)
        start_time = now - timedelta(hours=lookback_hours)

        # Select period based on lookback
        if lookback_hours <= 24:
            period = 300  # 5 minutes
        elif lookback_hours <= 168:  # 7 days
            period = 3600  # 1 hour
        else:
            period = 86400  # 1 day

        res_type = resource.resource_type
        series_list: list[AwsResourceMetricSeries] = []

        if res_type == "AWS::Lambda::Function":
            series_list = await self._get_lambda_metrics(
                client, creds, resource, start_time, now, period
            )
        elif res_type == "AWS::EC2::Instance":
            series_list = await self._get_ec2_metrics(
                client, creds, resource, start_time, now, period
            )
        elif res_type == "AWS::RDS::DBInstance":
            series_list = await self._get_rds_metrics(
                client, creds, resource, start_time, now, period
            )
        elif res_type == "AWS::EC2::Volume":
            series_list = await self._get_ebs_metrics(
                client, creds, resource, start_time, now, period
            )
        elif res_type == "AWS::EC2::NatGateway":
            series_list = await self._get_nat_gateway_metrics(
                client, creds, resource, start_time, now, period
            )
        elif res_type == "AWS::S3::Bucket":
            series_list = await self._get_s3_metrics(client, creds, resource, start_time, now)
        elif "ECS" in res_type or "EKS" in res_type:
            series_list = self._get_container_placeholder_metrics(resource)

        return series_list

    # -------------------------------------------------------------------------
    # Resource-Specific Handlers
    # -------------------------------------------------------------------------

    async def _get_lambda_metrics(
        self,
        client: httpx.AsyncClient,
        creds: AwsCredentials,
        res: AwsResourceItem,
        start_time: datetime,
        end_time: datetime,
        period: int,
    ) -> list[AwsResourceMetricSeries]:
        """Retrieve Lambda Invocations, Duration, Errors, and Throttles."""
        func_name = res.resource_name
        metrics_to_query = [
            ("Invocations", "Count", "Sum"),
            ("Duration", "Milliseconds", "Average"),
            ("Errors", "Count", "Sum"),
            ("Throttles", "Count", "Sum"),
            ("ConcurrentExecutions", "Count", "Maximum"),
        ]

        series_results: list[AwsResourceMetricSeries] = []

        for metric_name, unit, stat in metrics_to_query:
            try:
                data_points = await self._fetch_single_metric_data(
                    client=client,
                    creds=creds,
                    region=res.region,
                    namespace="AWS/Lambda",
                    metric_name=metric_name,
                    dimensions={"FunctionName": func_name},
                    start_time=start_time,
                    end_time=end_time,
                    period=period,
                    stat=stat,
                    unit=unit,
                )

                vals = [dp.value for dp in data_points]
                latest = vals[-1] if vals else None
                avg = round(sum(vals) / len(vals), 2) if vals else None
                peak = round(max(vals), 2) if vals else None

                series_results.append(
                    AwsResourceMetricSeries(
                        resource_id=res.resource_id,
                        resource_type=res.resource_type,
                        metric_name=metric_name,
                        namespace="AWS/Lambda",
                        unit=unit,
                        data_points=data_points,
                        latest_value=latest,
                        average_value=avg,
                        peak_value=peak,
                        period_seconds=period,
                        status="AVAILABLE" if data_points else "NO_DATA",
                    )
                )
            except Exception as exc:
                series_results.append(
                    AwsResourceMetricSeries(
                        resource_id=res.resource_id,
                        resource_type=res.resource_type,
                        metric_name=metric_name,
                        namespace="AWS/Lambda",
                        unit=unit,
                        status="PERMISSION_REQUIRED",
                        notes=str(exc),
                    )
                )

        return series_results

    async def _get_ec2_metrics(
        self,
        client: httpx.AsyncClient,
        creds: AwsCredentials,
        res: AwsResourceItem,
        start_time: datetime,
        end_time: datetime,
        period: int,
    ) -> list[AwsResourceMetricSeries]:
        """Retrieve EC2 CPUUtilization, Network, Disk Ops, and Status."""
        inst_id = res.resource_id
        metrics_to_query = [
            ("CPUUtilization", "Percent", "Average"),
            ("NetworkIn", "Bytes", "Average"),
            ("NetworkOut", "Bytes", "Average"),
            ("DiskReadOps", "Count", "Sum"),
            ("DiskWriteOps", "Count", "Sum"),
            ("StatusCheckFailed", "Count", "Maximum"),
        ]

        series_results: list[AwsResourceMetricSeries] = []

        for metric_name, unit, stat in metrics_to_query:
            try:
                data_points = await self._fetch_single_metric_data(
                    client=client,
                    creds=creds,
                    region=res.region,
                    namespace="AWS/EC2",
                    metric_name=metric_name,
                    dimensions={"InstanceId": inst_id},
                    start_time=start_time,
                    end_time=end_time,
                    period=period,
                    stat=stat,
                    unit=unit,
                )

                vals = [dp.value for dp in data_points]
                series_results.append(
                    AwsResourceMetricSeries(
                        resource_id=res.resource_id,
                        resource_type=res.resource_type,
                        metric_name=metric_name,
                        namespace="AWS/EC2",
                        unit=unit,
                        data_points=data_points,
                        latest_value=vals[-1] if vals else None,
                        average_value=round(sum(vals) / len(vals), 2) if vals else None,
                        peak_value=round(max(vals), 2) if vals else None,
                        period_seconds=period,
                        status="AVAILABLE" if data_points else "NO_DATA",
                    )
                )
            except Exception as exc:
                series_results.append(
                    AwsResourceMetricSeries(
                        resource_id=res.resource_id,
                        resource_type=res.resource_type,
                        metric_name=metric_name,
                        namespace="AWS/EC2",
                        unit=unit,
                        status="PERMISSION_REQUIRED",
                        notes=str(exc),
                    )
                )

        # Mandatory Rule: Memory utilization requires CloudWatch Agent
        series_results.append(
            AwsResourceMetricSeries(
                resource_id=res.resource_id,
                resource_type=res.resource_type,
                metric_name="MemoryUtilization",
                namespace="CWAgent",
                unit="Percent",
                status="INSTRUMENTATION_REQUIRED",
                notes="Memory utilization requires the Amazon CloudWatch Agent to be installed and configured on the OS.",
            )
        )

        return series_results

    async def _get_rds_metrics(
        self,
        client: httpx.AsyncClient,
        creds: AwsCredentials,
        res: AwsResourceItem,
        start_time: datetime,
        end_time: datetime,
        period: int,
    ) -> list[AwsResourceMetricSeries]:
        """Retrieve RDS CPU, DatabaseConnections, FreeableMemory, FreeStorageSpace, Read/Write IOPS."""
        db_id = res.resource_name
        metrics_to_query = [
            ("CPUUtilization", "Percent", "Average"),
            ("DatabaseConnections", "Count", "Average"),
            ("FreeableMemory", "Bytes", "Average"),
            ("FreeStorageSpace", "Bytes", "Average"),
            ("ReadIOPS", "Count/Second", "Average"),
            ("WriteIOPS", "Count/Second", "Average"),
        ]

        series_results: list[AwsResourceMetricSeries] = []
        for metric_name, unit, stat in metrics_to_query:
            try:
                data_points = await self._fetch_single_metric_data(
                    client=client,
                    creds=creds,
                    region=res.region,
                    namespace="AWS/RDS",
                    metric_name=metric_name,
                    dimensions={"DBInstanceIdentifier": db_id},
                    start_time=start_time,
                    end_time=end_time,
                    period=period,
                    stat=stat,
                    unit=unit,
                )
                vals = [dp.value for dp in data_points]
                series_results.append(
                    AwsResourceMetricSeries(
                        resource_id=res.resource_id,
                        resource_type=res.resource_type,
                        metric_name=metric_name,
                        namespace="AWS/RDS",
                        unit=unit,
                        data_points=data_points,
                        latest_value=vals[-1] if vals else None,
                        average_value=round(sum(vals) / len(vals), 2) if vals else None,
                        peak_value=round(max(vals), 2) if vals else None,
                        period_seconds=period,
                        status="AVAILABLE" if data_points else "NO_DATA",
                    )
                )
            except Exception as exc:
                series_results.append(
                    AwsResourceMetricSeries(
                        resource_id=res.resource_id,
                        resource_type=res.resource_type,
                        metric_name=metric_name,
                        namespace="AWS/RDS",
                        unit=unit,
                        status="PERMISSION_REQUIRED",
                        notes=str(exc),
                    )
                )

        return series_results

    async def _get_ebs_metrics(
        self,
        client: httpx.AsyncClient,
        creds: AwsCredentials,
        res: AwsResourceItem,
        start_time: datetime,
        end_time: datetime,
        period: int,
    ) -> list[AwsResourceMetricSeries]:
        """Retrieve EBS Read/Write Ops, Bytes, and Queue Length."""
        vol_id = res.resource_id
        metrics_to_query = [
            ("VolumeReadOps", "Count", "Sum"),
            ("VolumeWriteOps", "Count", "Sum"),
            ("VolumeReadBytes", "Bytes", "Sum"),
            ("VolumeWriteBytes", "Bytes", "Sum"),
            ("VolumeQueueLength", "Count", "Average"),
        ]

        series_results: list[AwsResourceMetricSeries] = []
        for metric_name, unit, stat in metrics_to_query:
            try:
                data_points = await self._fetch_single_metric_data(
                    client=client,
                    creds=creds,
                    region=res.region,
                    namespace="AWS/EBS",
                    metric_name=metric_name,
                    dimensions={"VolumeId": vol_id},
                    start_time=start_time,
                    end_time=end_time,
                    period=period,
                    stat=stat,
                    unit=unit,
                )
                vals = [dp.value for dp in data_points]
                series_results.append(
                    AwsResourceMetricSeries(
                        resource_id=res.resource_id,
                        resource_type=res.resource_type,
                        metric_name=metric_name,
                        namespace="AWS/EBS",
                        unit=unit,
                        data_points=data_points,
                        latest_value=vals[-1] if vals else None,
                        average_value=round(sum(vals) / len(vals), 2) if vals else None,
                        peak_value=round(max(vals), 2) if vals else None,
                        period_seconds=period,
                        status="AVAILABLE" if data_points else "NO_DATA",
                    )
                )
            except Exception as exc:
                series_results.append(
                    AwsResourceMetricSeries(
                        resource_id=res.resource_id,
                        resource_type=res.resource_type,
                        metric_name=metric_name,
                        namespace="AWS/EBS",
                        unit=unit,
                        status="PERMISSION_REQUIRED",
                        notes=str(exc),
                    )
                )

        return series_results

    async def _get_nat_gateway_metrics(
        self,
        client: httpx.AsyncClient,
        creds: AwsCredentials,
        res: AwsResourceItem,
        start_time: datetime,
        end_time: datetime,
        period: int,
    ) -> list[AwsResourceMetricSeries]:
        """Retrieve NAT Gateway byte flows, active connections, and error port allocations."""
        nat_id = res.resource_id
        metrics_to_query = [
            ("BytesInFromSource", "Bytes", "Sum"),
            ("BytesOutToDestination", "Bytes", "Sum"),
            ("BytesInFromDestination", "Bytes", "Sum"),
            ("BytesOutToSource", "Bytes", "Sum"),
            ("ActiveConnectionCount", "Count", "Maximum"),
            ("ErrorPortAllocation", "Count", "Sum"),
        ]

        series_results: list[AwsResourceMetricSeries] = []
        for metric_name, unit, stat in metrics_to_query:
            try:
                data_points = await self._fetch_single_metric_data(
                    client=client,
                    creds=creds,
                    region=res.region,
                    namespace="AWS/NATGateway",
                    metric_name=metric_name,
                    dimensions={"NatGatewayId": nat_id},
                    start_time=start_time,
                    end_time=end_time,
                    period=period,
                    stat=stat,
                    unit=unit,
                )
                vals = [dp.value for dp in data_points]
                series_results.append(
                    AwsResourceMetricSeries(
                        resource_id=res.resource_id,
                        resource_type=res.resource_type,
                        metric_name=metric_name,
                        namespace="AWS/NATGateway",
                        unit=unit,
                        data_points=data_points,
                        latest_value=vals[-1] if vals else None,
                        average_value=round(sum(vals) / len(vals), 2) if vals else None,
                        peak_value=round(max(vals), 2) if vals else None,
                        period_seconds=period,
                        status="AVAILABLE" if data_points else "NO_DATA",
                    )
                )
            except Exception as exc:
                series_results.append(
                    AwsResourceMetricSeries(
                        resource_id=res.resource_id,
                        resource_type=res.resource_type,
                        metric_name=metric_name,
                        namespace="AWS/NATGateway",
                        unit=unit,
                        status="PERMISSION_REQUIRED",
                        notes=str(exc),
                    )
                )

        return series_results

    async def _get_s3_metrics(
        self,
        client: httpx.AsyncClient,
        creds: AwsCredentials,
        res: AwsResourceItem,
        start_time: datetime,
        end_time: datetime,
    ) -> list[AwsResourceMetricSeries]:
        """Retrieve S3 storage metrics respecting daily granularity."""
        b_name = res.resource_name
        daily_period = 86400  # 1 day period
        metrics_to_query = [
            (
                "BucketSizeBytes",
                "Bytes",
                "Average",
                {"BucketName": b_name, "StorageType": "StandardStorage"},
            ),
            (
                "NumberOfObjects",
                "Count",
                "Average",
                {"BucketName": b_name, "StorageType": "AllStorageTypes"},
            ),
        ]

        series_results: list[AwsResourceMetricSeries] = []
        for metric_name, unit, stat, dims in metrics_to_query:
            try:
                data_points = await self._fetch_single_metric_data(
                    client=client,
                    creds=creds,
                    region=res.region,
                    namespace="AWS/S3",
                    metric_name=metric_name,
                    dimensions=dims,
                    start_time=start_time,
                    end_time=end_time,
                    period=daily_period,
                    stat=stat,
                    unit=unit,
                )
                vals = [dp.value for dp in data_points]
                series_results.append(
                    AwsResourceMetricSeries(
                        resource_id=res.resource_id,
                        resource_type=res.resource_type,
                        metric_name=metric_name,
                        namespace="AWS/S3",
                        unit=unit,
                        data_points=data_points,
                        latest_value=vals[-1] if vals else None,
                        average_value=round(sum(vals) / len(vals), 2) if vals else None,
                        peak_value=round(max(vals), 2) if vals else None,
                        period_seconds=daily_period,
                        status="AVAILABLE" if data_points else "NO_DATA",
                        notes="S3 storage metrics are reported once daily by AWS CloudWatch free of charge.",
                    )
                )
            except Exception as exc:
                series_results.append(
                    AwsResourceMetricSeries(
                        resource_id=res.resource_id,
                        resource_type=res.resource_type,
                        metric_name=metric_name,
                        namespace="AWS/S3",
                        unit=unit,
                        status="PERMISSION_REQUIRED",
                        notes=str(exc),
                    )
                )

        return series_results

    def _get_container_placeholder_metrics(
        self, res: AwsResourceItem
    ) -> list[AwsResourceMetricSeries]:
        """Mark ECS/EKS container metrics as instrumentation required."""
        return [
            AwsResourceMetricSeries(
                resource_id=res.resource_id,
                resource_type=res.resource_type,
                metric_name="ContainerCPUUtilization",
                namespace="ECS/ContainerInsights",
                unit="Percent",
                status="INSTRUMENTATION_REQUIRED",
                notes="Amazon ECS/EKS container metrics require AWS Container Insights to be enabled.",
            ),
            AwsResourceMetricSeries(
                resource_id=res.resource_id,
                resource_type=res.resource_type,
                metric_name="ContainerMemoryUtilization",
                namespace="ECS/ContainerInsights",
                unit="Percent",
                status="INSTRUMENTATION_REQUIRED",
                notes="Container memory tracking requires Container Insights or Prometheus monitoring.",
            ),
        ]

    # -------------------------------------------------------------------------
    # Core GetMetricData Engine
    # -------------------------------------------------------------------------

    async def _fetch_single_metric_data(
        self,
        client: httpx.AsyncClient,
        creds: AwsCredentials,
        region: str,
        namespace: str,
        metric_name: str,
        dimensions: dict[str, str],
        start_time: datetime,
        end_time: datetime,
        period: int,
        stat: str,
        unit: str,
    ) -> list[AwsMetricDataPoint]:
        """Construct and execute GetMetricData Query API call for a single metric."""
        query_id = "m1"
        params: dict[str, str] = {
            "Action": "GetMetricData",
            "Version": "2010-08-01",
            "StartTime": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "EndTime": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "MetricDataQueries.member.1.Id": query_id,
            "MetricDataQueries.member.1.MetricStat.Metric.Namespace": namespace,
            "MetricDataQueries.member.1.MetricStat.Metric.MetricName": metric_name,
            "MetricDataQueries.member.1.MetricStat.Period": str(period),
            "MetricDataQueries.member.1.MetricStat.Stat": stat,
            "MetricDataQueries.member.1.ReturnData": "true",
        }

        # Dimensions
        dim_idx = 1
        for d_name, d_val in dimensions.items():
            params[
                f"MetricDataQueries.member.1.MetricStat.Metric.Dimensions.member.{dim_idx}.Name"
            ] = d_name
            params[
                f"MetricDataQueries.member.1.MetricStat.Metric.Dimensions.member.{dim_idx}.Value"
            ] = d_val
            dim_idx += 1

        xml_resp = await self._query_cloudwatch(client, creds, region, params)
        return self._parse_metric_data_xml(xml_resp, unit, stat)

    def _parse_metric_data_xml(
        self,
        xml_text: str,
        unit: str,
        stat: str,
    ) -> list[AwsMetricDataPoint]:
        """Parse Timestamps and Values from CloudWatch GetMetricData XML response."""
        data_points: list[AwsMetricDataPoint] = []

        # Find timestamps block
        ts_matches = re.findall(r"<Timestamps>(.*?)</Timestamps>", xml_text, re.DOTALL)
        val_matches = re.findall(r"<Values>(.*?)</Values>", xml_text, re.DOTALL)

        if not ts_matches or not val_matches:
            return data_points

        timestamps = re.findall(r"<member>([^<]+)</member>", ts_matches[0])
        values = re.findall(r"<member>([^<]+)</member>", val_matches[0])

        count = min(len(timestamps), len(values))
        for i in range(count):
            try:
                val = float(values[i])
                data_points.append(
                    AwsMetricDataPoint(
                        timestamp=timestamps[i],
                        value=round(val, 2),
                        unit=unit,
                        statistic=stat,
                    )
                )
            except ValueError:
                continue

        # Sort ascending by timestamp
        data_points.sort(key=lambda dp: dp.timestamp)
        return data_points


# Singleton helper
_cloudwatch_service_instance: AwsCloudWatchMetricsService | None = None


def get_aws_cloudwatch_service() -> AwsCloudWatchMetricsService:
    global _cloudwatch_service_instance
    if _cloudwatch_service_instance is None:
        _cloudwatch_service_instance = AwsCloudWatchMetricsService()
    return _cloudwatch_service_instance
