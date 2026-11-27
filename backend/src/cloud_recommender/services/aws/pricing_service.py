"""AWS Price List Intelligence Service.

Queries the AWS Price List API (us-east-1) for on-demand retail rates across EC2, Lambda,
RDS, S3, and EBS, with in-memory caching and region location normalization.

Strict Invariants:
1. Pure read-only queries against public pricing catalogs.
2. Caching is mandatory to avoid repeated identical network round-trips.
3. Explicitly labels rates as public on-demand list price; never represents as customer's negotiated discount.
"""

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from cloud_recommender.schemas.aws import AwsPricingEstimate, AwsResourceItem
from cloud_recommender.services.aws.auth_service import (
    AwsAuthService,
    AwsCredentials,
    get_aws_auth_service,
)
from cloud_recommender.services.aws.sigv4 import sign_aws_request

logger = structlog.get_logger(__name__)

PRICING_ENDPOINT = "https://api.pricing.us-east-1.amazonaws.com/"
PRICING_REGION = "us-east-1"
PRICING_SERVICE = "pricing"

# AWS Region Code -> AWS Price List Location Attribute Mapping
REGION_TO_LOCATION_MAP: dict[str, str] = {
    "eu-north-1": "EU (Stockholm)",
    "us-east-1": "US East (N. Virginia)",
    "us-east-2": "US East (Ohio)",
    "us-west-1": "US West (N. California)",
    "us-west-2": "US West (Oregon)",
    "eu-west-1": "EU (Ireland)",
    "eu-west-2": "EU (London)",
    "eu-west-3": "EU (Paris)",
    "eu-central-1": "EU (Frankfurt)",
    "ap-south-1": "Asia Pacific (Mumbai)",
    "ap-southeast-1": "Asia Pacific (Singapore)",
    "ap-southeast-2": "Asia Pacific (Sydney)",
    "ap-northeast-1": "Asia Pacific (Tokyo)",
    "ca-central-1": "Canada (Central)",
    "sa-east-1": "South America (Sao Paulo)",
}

# Static Fallback Price Catalog for Offline Verification
STATIC_FALLBACK_RATES: dict[str, dict[str, Any]] = {
    "AWS::Lambda::Function": {
        "service": "AWSLambda",
        "hourly_rate": 0.0000166667,  # per GB-second / memory equivalent
        "monthly_rate": 2.45,
        "pricing_unit": "Requests/Duration",
    },
    "AWS::EC2::Instance": {
        "service": "AmazonEC2",
        "hourly_rate": 0.0416,  # t3.medium in eu-north-1
        "monthly_rate": 30.37,
        "pricing_unit": "Hrs",
    },
    "AWS::RDS::DBInstance": {
        "service": "AmazonRDS",
        "hourly_rate": 0.068,  # db.t3.medium postgresql
        "monthly_rate": 49.64,
        "pricing_unit": "Hrs",
    },
    "AWS::EC2::Volume": {
        "service": "AmazonEC2",
        "hourly_rate": 0.0001095,  # $0.08 per GB-month gp3
        "monthly_rate": 8.00,  # 100GB gp3
        "pricing_unit": "GB-Mo",
    },
    "AWS::EC2::NatGateway": {
        "service": "AmazonEC2",
        "hourly_rate": 0.045,  # per NAT Gateway hour
        "monthly_rate": 32.85,
        "pricing_unit": "Hrs",
    },
    "AWS::S3::Bucket": {
        "service": "AmazonS3",
        "hourly_rate": 0.0000315,  # $0.023 per GB-month Standard
        "monthly_rate": 2.30,  # 100GB Standard
        "pricing_unit": "GB-Mo",
    },
}


class AwsPricingService:
    """Manages AWS retail pricing retrieval, caching, and resource estimation."""

    def __init__(
        self,
        auth_service: AwsAuthService | None = None,
        timeout_seconds: float = 12.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.auth_service = auth_service or get_aws_auth_service()
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self._cache: dict[str, AwsPricingEstimate] = {}

    def get_pricing_location(self, region_code: str) -> str:
        """Translate region code (e.g. eu-north-1) to Price List location string."""
        return REGION_TO_LOCATION_MAP.get(region_code, "EU (Stockholm)")

    def _build_canonical_cache_key(
        self,
        service_code: str,
        region: str,
        resource_type: str,
        instance_type_or_tier: str | None = None,
        storage_type: str | None = None,
        operating_system: str = "Linux",
        tenancy: str = "Shared",
        database_engine: str = "none",
        deployment_option: str = "Single-AZ",
        usage_type: str = "general",
        operation: str = "RunInstances",
        currency: str = "USD",
        pricing_unit: str = "Hrs",
        purchase_option: str = "OnDemand",
    ) -> str:
        """Construct deterministic canonical SKU cache key using standard cloud attributes."""
        tier = instance_type_or_tier or "standard"
        st = storage_type or "general"
        return (
            f"{service_code}:{region}:{resource_type}:{tier}:{operating_system}:{tenancy}:"
            f"{database_engine}:{deployment_option}:{st}:{usage_type}:{operation}:{currency}:"
            f"{pricing_unit}:{purchase_option}"
        )

    async def get_resource_pricing_estimate(
        self,
        client: httpx.AsyncClient,
        creds: AwsCredentials,
        resource: AwsResourceItem,
    ) -> AwsPricingEstimate:
        """Retrieve estimated on-demand retail price for a discovered cloud resource."""
        service_code = "AmazonEC2"
        if "Lambda" in resource.resource_type:
            service_code = "AWSLambda"
        elif "RDS" in resource.resource_type:
            service_code = "AmazonRDS"
        elif "S3" in resource.resource_type:
            service_code = "AmazonS3"

        tier = (
            resource.details.get("instance_type")
            or resource.metadata.get("instance_type")
            or resource.details.get("runtime")
        )
        storage_type = (
            resource.details.get("volume_type")
            or resource.metadata.get("volume_type")
            or "standard"
        )

        canonical_key = self._build_canonical_cache_key(
            service_code=service_code,
            region=resource.region,
            resource_type=resource.resource_type,
            instance_type_or_tier=str(tier) if tier else None,
            storage_type=str(storage_type) if storage_type else None,
        )

        short_key = f"{service_code}:{resource.region}:{resource.resource_type}:{str(tier) if tier else 'standard'}:{str(storage_type) if storage_type else 'general'}"
        legacy_key = f"{resource.resource_type}:{resource.region}:{resource.resource_name}"

        matched_key = (
            canonical_key
            if canonical_key in self._cache
            else (
                short_key
                if short_key in self._cache
                else (legacy_key if legacy_key in self._cache else None)
            )
        )

        if matched_key:
            cached = self._cache[matched_key]
            # Return cached copy with updated source classification
            return cached.model_copy(
                update={
                    "pricing_source": (
                        "CACHED_AWS_PRICE_LIST"
                        if cached.pricing_source == "LIVE_AWS_PRICE_LIST"
                        else cached.pricing_source
                    )
                }
            )

        pricing_location = self.get_pricing_location(resource.region)
        res_type = resource.resource_type

        # Attempt Price List API lookup
        try:
            estimate = await self._fetch_live_pricing(
                client=client,
                creds=creds,
                resource=resource,
                pricing_location=pricing_location,
            )
            if estimate:
                estimate.pricing_source = "LIVE_AWS_PRICE_LIST"
                self._cache[canonical_key] = estimate
                return estimate
        except Exception as exc:
            logger.info("aws_live_pricing_query_skipped", reason=str(exc))

        # Fallback to deterministic offline catalog
        fallback_data = STATIC_FALLBACK_RATES.get(
            res_type,
            {
                "service": "AmazonAWS",
                "hourly_rate": 0.01,
                "monthly_rate": 7.30,
                "pricing_unit": "Hrs",
            },
        )

        estimate = AwsPricingEstimate(
            service=fallback_data["service"],
            resource_type=res_type,
            region=resource.region,
            pricing_location=pricing_location,
            instance_type_or_tier=str(tier) if tier else None,
            hourly_rate=fallback_data["hourly_rate"],
            monthly_estimated_rate=fallback_data["monthly_rate"],
            pricing_unit=fallback_data["pricing_unit"],
            currency="USD",
            observation_timestamp=datetime.now(UTC),
            is_list_price=True,
            pricing_source="OFFLINE_REFERENCE_CATALOG",
            operating_hours_assumption=730,
            is_partial_estimate="Volume" in res_type or "NatGateway" in res_type,
        )

        self._cache[canonical_key] = estimate
        return estimate

    async def _fetch_live_pricing(
        self,
        client: httpx.AsyncClient,
        creds: AwsCredentials,
        resource: AwsResourceItem,
        pricing_location: str,
    ) -> AwsPricingEstimate | None:
        """Query AWS Price List GetProducts endpoint."""
        service_code = "AmazonEC2"
        if "Lambda" in resource.resource_type:
            service_code = "AWSLambda"
        elif "RDS" in resource.resource_type:
            service_code = "AmazonRDS"
        elif "S3" in resource.resource_type:
            service_code = "AmazonS3"

        filters = [
            {"Type": "TERM_MATCH", "Field": "location", "Value": pricing_location},
        ]

        payload = {
            "ServiceCode": service_code,
            "Filters": filters,
            "FormatVersion": "aws_v1",
            "MaxResults": 1,
        }

        body = json.dumps(payload)
        headers = {
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": "AWSPriceListService.GetProducts",
        }

        signed_headers = sign_aws_request(
            method="POST",
            url=PRICING_ENDPOINT,
            headers=headers,
            body=body,
            access_key_id=creds.access_key_id,
            secret_access_key=creds.secret_access_key,
            region=PRICING_REGION,
            service=PRICING_SERVICE,
            session_token=creds.session_token,
        )

        resp = await client.post(
            PRICING_ENDPOINT,
            headers=signed_headers,
            content=body,
            timeout=self.timeout_seconds,
        )

        if resp.status_code != 200:
            return None

        data = resp.json()
        price_list = data.get("PriceList", [])
        if not price_list:
            return None

        # Parse PriceList item JSON
        first_item = json.loads(price_list[0]) if isinstance(price_list[0], str) else price_list[0]
        sku = first_item.get("product", {}).get("sku")

        # Extract OnDemand rate from terms
        terms = first_item.get("terms", {}).get("OnDemand", {})
        hourly_rate = 0.05  # baseline fallback
        for _, term_data in terms.items():
            price_dimensions = term_data.get("priceDimensions", {})
            for _, dim in price_dimensions.items():
                price_per_unit = dim.get("pricePerUnit", {})
                if "USD" in price_per_unit:
                    try:
                        hourly_rate = float(price_per_unit["USD"])
                        break
                    except ValueError:
                        pass

        monthly_rate = round(hourly_rate * 730, 2)
        return AwsPricingEstimate(
            service=service_code,
            resource_type=resource.resource_type,
            sku=sku,
            region=resource.region,
            pricing_location=pricing_location,
            hourly_rate=hourly_rate,
            monthly_estimated_rate=monthly_rate,
            pricing_unit="Hrs",
            currency="USD",
            observation_timestamp=datetime.now(UTC),
            is_list_price=True,
            pricing_source="AWS Price List API (us-east-1 Live)",
        )


# Singleton instance helper
_pricing_service_instance: AwsPricingService | None = None


def get_aws_pricing_service() -> AwsPricingService:
    global _pricing_service_instance
    if _pricing_service_instance is None:
        _pricing_service_instance = AwsPricingService()
    return _pricing_service_instance
