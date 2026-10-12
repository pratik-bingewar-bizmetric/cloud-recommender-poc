"""Tests for OptimizationAudit schema, evidence traceability, and approval gates."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from cloud_recommender.schemas.common import AuditApprovalStatus
from cloud_recommender.schemas.optimization import (
    AuditEvidence,
    AuditScope,
    ModernizationOpportunity,
    OptimizationAudit,
    WasteFinding,
)


def test_optimization_audit_valid_creation() -> None:
    """Verify OptimizationAudit instantiates with findings, evidence, and savings."""
    scope = AuditScope(
        azure_subscription_id="00000000-0000-0000-0000-000000000001",
        resource_groups=["rg-production-workloads"],
        metric_window_days=30,
        source_archive_name="app-source-v2.zip",
    )

    evidence1 = AuditEvidence(
        evidence_id="ev-vm-cpu-p95",
        source_system="Azure Monitor",
        metric_name="Percentage CPU P95",
        observed_value="3.2% avg over 30d",
    )

    waste1 = WasteFinding(
        finding_id="waste-oversized-vm-01",
        resource_id="/subscriptions/00000000/resourceGroups/rg-prod/providers/Microsoft.Compute/virtualMachines/vm-legacy",
        resource_type="Microsoft.Compute/virtualMachines",
        waste_category="idle_vm",
        description="Standard_D8s_v5 running at <5% average CPU for 30 consecutive days.",
        current_monthly_spend=Decimal("292.00"),
        potential_monthly_savings=Decimal("219.00"),
        remediation_recommendation="Downsize to D2s_v5 or modernize to Azure Container Apps.",
        evidence_ids=["ev-vm-cpu-p95"],
    )

    modern1 = ModernizationOpportunity(
        opportunity_id="mod-aca-migration",
        title="Migrate Web API from IaaS to Azure Container Apps",
        source_architecture="IaaS VM hosting Python FastAPI service with manual Nginx proxy",
        target_architecture="Azure Container Apps with built-in ingress and auto-scaling",
        migration_complexity="low",
        estimated_implementation_days=3,
        benefits=[
            "Automated patching",
            "Scale-to-zero during quiet hours",
            "Integrated TLS certificate",
        ],
    )

    audit = OptimizationAudit(
        scope=scope,
        waste_findings=[waste1],
        modernization_opportunities=[modern1],
        evidence=[evidence1],
        current_monthly_spend=Decimal("1450.00"),
        projected_monthly_spend=Decimal("1231.00"),
        estimated_monthly_savings=Decimal("219.00"),
        estimated_annual_savings=Decimal("2628.00"),
        total_implementation_effort_days=3,
        confidence_score=Decimal("0.92"),
        assumptions=["Workload peak demands remain consistent with previous 30-day baseline."],
        limitations=["Database write IOPS telemetry was unavailable due to diagnostic settings."],
        approval_status=AuditApprovalStatus.PENDING_REVIEW,
    )

    assert audit.scope.metric_window_days == 30
    assert audit.estimated_monthly_savings == Decimal("219.00")
    assert audit.estimated_annual_savings == Decimal("2628.00")
    assert audit.confidence_score == Decimal("0.92")
    assert audit.approval_status == AuditApprovalStatus.PENDING_REVIEW
    assert len(audit.waste_findings) == 1
    assert len(audit.modernization_opportunities) == 1


def test_optimization_audit_confidence_score_bounds() -> None:
    """Verify confidence score must be between 0.0 and 1.0."""
    scope = AuditScope()

    # Exceeding 1.0
    with pytest.raises(ValidationError):
        OptimizationAudit(scope=scope, confidence_score=Decimal("1.5"))

    # Below 0.0
    with pytest.raises(ValidationError):
        OptimizationAudit(scope=scope, confidence_score=Decimal("-0.1"))
