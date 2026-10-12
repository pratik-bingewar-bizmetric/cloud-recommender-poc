"""Pydantic v2 domain schemas package for Cloud Recommender POC."""

from cloud_recommender.schemas.catalog import (
    CatalogService,
    CatalogServiceBase,
    CatalogServiceFilter,
    CatalogServiceListResponse,
)
from cloud_recommender.schemas.common import (
    AuditApprovalStatus,
    CatalogRecordStatus,
    CloudProvider,
    ComplianceStandard,
    RecommendationStatus,
    ServiceCategory,
    WorkloadCategory,
)
from cloud_recommender.schemas.optimization import (
    AuditEvidence,
    AuditScope,
    ModernizationOpportunity,
    OptimizationAudit,
    WasteFinding,
)
from cloud_recommender.schemas.recommendation import (
    ArchitectureComponent,
    CostBreakdown,
    PricingReference,
    RecommendationReport,
    TradeOffAssessment,
    TradeOffDimension,
)
from cloud_recommender.schemas.workload import (
    WorkloadProfile,
    WorkloadProfileBase,
    WorkloadProfileCreate,
    WorkloadProfileUpdate,
)

__all__ = [
    "CloudProvider",
    "ServiceCategory",
    "WorkloadCategory",
    "ComplianceStandard",
    "CatalogRecordStatus",
    "RecommendationStatus",
    "AuditApprovalStatus",
    "WorkloadProfileBase",
    "WorkloadProfileCreate",
    "WorkloadProfileUpdate",
    "WorkloadProfile",
    "ArchitectureComponent",
    "CostBreakdown",
    "TradeOffDimension",
    "TradeOffAssessment",
    "PricingReference",
    "RecommendationReport",
    "AuditScope",
    "AuditEvidence",
    "WasteFinding",
    "ModernizationOpportunity",
    "OptimizationAudit",
    "CatalogServiceBase",
    "CatalogService",
    "CatalogServiceFilter",
    "CatalogServiceListResponse",
]
