"""Tests for WorkloadProfile schema validation, optionality, and financial precision."""

import json
from decimal import Decimal

import pytest
from pydantic import ValidationError

from cloud_recommender.schemas.common import ComplianceStandard, WorkloadCategory
from cloud_recommender.schemas.workload import (
    WorkloadProfile,
    WorkloadProfileCreate,
    WorkloadProfileUpdate,
)


def test_workload_profile_minimal_valid() -> None:
    """Verify minimal workload profile requires only name and category defaults."""
    profile = WorkloadProfile(name="Minimal Web Service")
    assert profile.name == "Minimal Web Service"
    assert profile.category == WorkloadCategory.WEB_APP
    assert profile.currency == "USD"
    assert profile.cost_buffer_percentage == Decimal("15.00")
    # Verify optional fields remain None without fabricated defaults
    assert profile.target_traffic_rps is None
    assert profile.monthly_active_users is None
    assert profile.storage_volume_gb is None
    assert profile.max_monthly_budget is None
    assert profile.rpo_minutes is None
    assert profile.rto_minutes is None
    assert profile.primary_region is None


def test_workload_profile_full_valid() -> None:
    """Verify fully populated workload profile parses Decimal types cleanly."""
    profile = WorkloadProfile(
        name="Enterprise Healthcare Imaging",
        description="Processes DICOM medical images with HIPAA compliance requirements.",
        category=WorkloadCategory.MICROSERVICES,
        target_traffic_rps=2500,
        monthly_active_users=150000,
        peak_multiplier=Decimal("3.50"),
        target_sla_percentage=Decimal("99.950"),
        high_availability=True,
        multi_region=True,
        rpo_minutes=15,
        rto_minutes=60,
        compliance_frameworks=[ComplianceStandard.HIPAA, ComplianceStandard.SOC2],
        data_classification="Restricted/PHI",
        storage_volume_gb=Decimal("5000.00"),
        monthly_data_egress_gb=Decimal("1200.50"),
        database_type="relational",
        primary_region="eastus",
        target_regions=["westeurope"],
        currency="usd",  # Tests lowercase normalization
        max_monthly_budget=Decimal("7500.00"),
        cost_buffer_percentage=Decimal("20.00"),
        estimation_assumptions={"retention_years": "7"},
    )
    assert profile.currency == "USD"  # Normalized
    assert profile.storage_volume_gb == Decimal("5000.00")
    assert profile.max_monthly_budget == Decimal("7500.00")
    assert len(profile.compliance_frameworks) == 2


def test_workload_profile_validation_errors() -> None:
    """Verify validation fails on negative traffic, SLAs, and currencies."""
    # Negative traffic RPS
    with pytest.raises(ValidationError):
        WorkloadProfile(name="Test", target_traffic_rps=0)

    # SLA over 99.999%
    with pytest.raises(ValidationError):
        WorkloadProfile(name="Test", target_sla_percentage=Decimal("100.0"))

    # SLA below 90%
    with pytest.raises(ValidationError):
        WorkloadProfile(name="Test", target_sla_percentage=Decimal("89.9"))

    # Negative storage
    with pytest.raises(ValidationError):
        WorkloadProfile(name="Test", storage_volume_gb=Decimal("-10.0"))

    # Empty name
    with pytest.raises(ValidationError):
        WorkloadProfile(name="")


def test_workload_profile_create_and_update_dtos() -> None:
    """Verify DTO schemas for creation and partial updates."""
    create_dto = WorkloadProfileCreate(
        name="New App",
        category=WorkloadCategory.DATA_PIPELINE,
        max_monthly_budget=Decimal("500.00"),
    )
    assert create_dto.name == "New App"

    update_dto = WorkloadProfileUpdate(
        target_traffic_rps=500,
        max_monthly_budget=Decimal("800.00"),
    )
    assert update_dto.target_traffic_rps == 500
    assert update_dto.name is None


def test_workload_profile_json_serialization_preserves_decimals() -> None:
    """Verify JSON dumping does not degrade Decimal precision to binary float."""
    profile = WorkloadProfile(
        name="FinOps Test",
        storage_volume_gb=Decimal("1024.75"),
        max_monthly_budget=Decimal("1999.99"),
    )
    dumped = profile.model_dump_json()
    data = json.loads(dumped)
    assert data["storage_volume_gb"] == "1024.75"
    assert isinstance(data["storage_volume_gb"], str)
    assert data["max_monthly_budget"] == "1999.99"
    assert isinstance(data["max_monthly_budget"], str)
