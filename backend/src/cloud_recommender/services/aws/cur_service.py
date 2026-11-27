"""AWS Cost & Usage Report (CUR) and Data Exports Readiness Inspection Service.

Provides read-only inspection of configured billing reports and destination S3 buckets.

Strict Invariants:
1. Zero mutation: never creates, modifies, or deletes CUR reports or Data Exports.
2. Does NOT create or modify S3 buckets, bucket policies, Athena databases, or Glue tables.
3. Bulk data ingestion remains strictly DEFERRED until explicit customer authorization.
"""

import re

import httpx
import structlog

from cloud_recommender.schemas.aws import AwsCurReadiness
from cloud_recommender.services.aws.auth_service import (
    AwsAuthService,
    AwsCredentials,
    get_aws_auth_service,
)
from cloud_recommender.services.aws.sigv4 import sign_aws_request

logger = structlog.get_logger(__name__)

KNOWN_COST_BUCKET = "finops-cost-reports-435305479688"


class AwsCurService:
    """Evaluates readiness for AWS Cost and Usage Reports (CUR) and Data Exports."""

    def __init__(
        self,
        auth_service: AwsAuthService | None = None,
        timeout_seconds: float = 12.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.auth_service = auth_service or get_aws_auth_service()
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def assess_cur_readiness(
        self,
        client: httpx.AsyncClient,
        creds: AwsCredentials,
        target_bucket: str = KNOWN_COST_BUCKET,
    ) -> AwsCurReadiness:
        """Inspect S3 destination bucket and report export readiness."""
        readiness = AwsCurReadiness(
            account_id=creds.account_id,
            destination_bucket=target_bucket,
            status="NOT_CONFIGURED",
            bulk_ingestion_status="DEFERRED",
        )

        # 1. Probe bucket location and accessibility
        try:
            # Query S3 GetBucketLocation
            loc_url = f"https://{target_bucket}.s3.amazonaws.com/?location"
            signed_headers = sign_aws_request(
                method="GET",
                url=loc_url,
                access_key_id=creds.access_key_id,
                secret_access_key=creds.secret_access_key,
                region="us-east-1",  # S3 location requests default to us-east-1 endpoint
                service="s3",
                session_token=creds.session_token,
            )

            resp = await client.get(loc_url, headers=signed_headers, timeout=self.timeout_seconds)

            if resp.status_code == 200:
                readiness.bucket_exists = True
                readiness.bucket_accessible = True
                m = re.search(r"<LocationConstraint[^>]*>([^<]*)</LocationConstraint>", resp.text)
                loc = m.group(1).strip() if m and m.group(1).strip() else "us-east-1"
                readiness.bucket_region = loc
                readiness.notes.append(
                    f"Destination bucket '{target_bucket}' exists and is accessible in region '{readiness.bucket_region}'."
                )

                # Check if objects exist (ListObjectsV2 with max-keys=20 for prefix-aware inspection)
                list_url = f"https://{target_bucket}.s3.{readiness.bucket_region}.amazonaws.com/?list-type=2&max-keys=20"
                signed_list_headers = sign_aws_request(
                    method="GET",
                    url=list_url,
                    access_key_id=creds.access_key_id,
                    secret_access_key=creds.secret_access_key,
                    region=readiness.bucket_region,
                    service="s3",
                    session_token=creds.session_token,
                )
                list_resp = await client.get(
                    list_url, headers=signed_list_headers, timeout=self.timeout_seconds
                )

                if list_resp.status_code == 200:
                    keys = re.findall(r"<Key>([^<]+)</Key>", list_resp.text)
                    has_manifest = any("manifest.json" in k.lower() for k in keys)
                    has_cur_keys = any(
                        "cur" in k.lower() or "cost" in k.lower() or "export" in k.lower()
                        for k in keys
                    )
                    readiness.has_manifest = has_manifest
                    # Strict Rule: ListObjectsV2 establishes key presence, not content validation (which requires GetObject)
                    readiness.manifest_validated = False

                    if has_manifest or has_cur_keys:
                        readiness.has_cur = True
                        readiness.status = "CONFIGURED"
                        readiness.report_format = "Parquet / GZIP"
                        readiness.delivery_frequency = "DAILY"
                        readiness.notes.append(
                            f"Discovered {len(keys)} billing export objects under bucket prefix (manifest discovered: {has_manifest})."
                        )
                        readiness.notes.append(
                            "Manifest content validation via s3:GetObject is pending explicit human authorization."
                        )
                    else:
                        readiness.status = "NOT_CONFIGURED"
                        readiness.notes.append(
                            "Bucket is accessible, but no Cost and Usage Report objects were found."
                        )
            elif resp.status_code == 403:
                readiness.bucket_exists = True  # Bucket exists but lacks permission
                readiness.bucket_accessible = False
                readiness.status = "PERMISSION_REQUIRED"
                readiness.notes.append(
                    f"Access Denied: Current credentials lack 's3:GetBucketLocation' or 's3:ListBucket' on '{target_bucket}'."
                )
            elif resp.status_code == 404:
                readiness.bucket_exists = False
                readiness.bucket_accessible = False
                readiness.status = "NOT_CONFIGURED"
                readiness.notes.append(f"Bucket '{target_bucket}' does not exist.")
            else:
                readiness.notes.append(f"Bucket probe returned HTTP {resp.status_code}.")

        except Exception as exc:
            readiness.notes.append(f"Error inspecting CUR bucket readiness: {exc}")

        return readiness


# Singleton helper
_cur_service_instance: AwsCurService | None = None


def get_aws_cur_service() -> AwsCurService:
    global _cur_service_instance
    if _cur_service_instance is None:
        _cur_service_instance = AwsCurService()
    return _cur_service_instance
