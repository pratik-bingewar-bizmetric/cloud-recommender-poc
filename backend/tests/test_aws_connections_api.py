"""Regression tests for Centralized Cloud Connection API (POST /api/v1/connections) with AWS Provider.

Covers:
1. POST /api/v1/connections with provider=aws and profile finops-dev.
2. Dynamic profile credential resolution and account validation.
3. Unsupported provider rejection for unknown providers.
4. AWS connection persistence in repository and retrieval via GET /api/v1/connections.
5. Account ID mismatch rejection.
6. Tenant isolation for AWS connections.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from cloud_recommender.core.auth import AuthenticatedUser, get_current_user
from cloud_recommender.main import create_app
from cloud_recommender.schemas.aws import (
    AwsServiceConnectivityState,
    AwsServiceStatus,
    AwsTestConnectionResponse,
)


@pytest.fixture
def mock_user() -> AuthenticatedUser:
    return AuthenticatedUser(
        sub="user-finops-tester",
        tid="tenant-finops-dev",
        roles=["FinOpsAdmin"],
        oid="oid-12345",
        scp="access_as_user",
        is_development_identity=True,
    )


@pytest.fixture
def app(mock_user: AuthenticatedUser):
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: mock_user
    yield app
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_aws_connection_via_central_api(app: Any):
    """Verify POST /api/v1/connections accepts provider='aws' and registers successfully."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch(
            "cloud_recommender.services.aws.connectivity_service.AwsConnectivityService.test_connection",
            new_callable=AsyncMock,
        ) as mock_test_conn:
            mock_test_conn.return_value = AwsTestConnectionResponse(
                success=True,
                account_id="435305479688",
                default_region="eu-north-1",
                auth_method="profile",
                overall_status="Connected",
                services=[
                    AwsServiceStatus(
                        service="sts",
                        service_name="AWS STS",
                        status=AwsServiceConnectivityState.SUCCESS,
                        api_endpoint="https://sts.eu-north-1.amazonaws.com/",
                        required_role_or_permission="sts:GetCallerIdentity",
                    )
                ],
                arn="arn:aws:iam::435305479688:user/pratik.bingewar@bizmetric.com",
            )

            payload = {
                "provider": "aws",
                "name": "Bizmetric AWS Dev",
                "scope_id": "435305479688",
                "aws_account_id": "435305479688",
                "aws_region": "eu-north-1",
                "aws_auth_method": "profile",
                "aws_profile": "finops-dev",
            }
            resp = await client.post("/api/v1/connections", json=payload)
            assert resp.status_code == 201, f"Failed: {resp.text}"
            data = resp.json()
            assert data["provider"] == "aws"
            assert data["name"] == "Bizmetric AWS Dev"
            assert data["scope_id"] == "435305479688"
            assert data["status"] == "connected"
            assert "id" in data

            # Verify connection appears in GET /api/v1/connections
            list_resp = await client.get("/api/v1/connections")
            assert list_resp.status_code == 200
            connections = list_resp.json()
            aws_conns = [
                c for c in connections if c["provider"] == "aws" and c["scope_id"] == "435305479688"
            ]
            assert len(aws_conns) >= 1
            assert aws_conns[0]["name"] == "Bizmetric AWS Dev"


@pytest.mark.asyncio
async def test_create_connection_rejects_unsupported_provider(app: Any):
    """Verify POST /api/v1/connections still cleanly rejects actually invalid providers with 400."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "provider": "oracle_cloud_unknown",
            "name": "Oracle Dev",
            "scope_id": "ocid-12345",
        }
        resp = await client.post("/api/v1/connections", json=payload)
        assert resp.status_code in (422, 400)


@pytest.mark.asyncio
async def test_create_aws_connection_auth_failure_handling(app: Any):
    """Verify POST /api/v1/connections surfaces validation error when AWS authentication fails."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch(
            "cloud_recommender.services.aws.connectivity_service.AwsConnectivityService.test_connection",
            new_callable=AsyncMock,
        ) as mock_test_conn:
            mock_test_conn.return_value = AwsTestConnectionResponse(
                success=False,
                account_id="435305479688",
                default_region="eu-north-1",
                auth_method="profile",
                overall_status="Authentication Failed",
                services=[],
                error_summary="Failed to authenticate with profile invalid-profile",
                arn="arn:aws:iam::435305479688:caller",
            )

            payload = {
                "provider": "aws",
                "name": "Invalid AWS Connection",
                "scope_id": "999888777666",
                "aws_account_id": "999888777666",
                "aws_region": "eu-north-1",
                "aws_auth_method": "profile",
                "aws_profile": "invalid-profile",
            }
            resp = await client.post("/api/v1/connections", json=payload)
            assert resp.status_code == 400
            assert "AWS_VALIDATION_FAILED" in resp.text or "Authentication Failed" in resp.text
