"""Domain schemas for application requirements analysis, clarifying questions, and simulation."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from cloud_recommender.schemas.recommendation import (
    ArchitectureComponent,
    CostBreakdown,
    PricingReference,
)
from cloud_recommender.schemas.workload import WorkloadProfile, WorkloadProfileCreate


class ClarifyingQuestion(BaseModel):
    """An interactive question for missing requirements that materially affect architecture/cost."""

    id: str = Field(..., description="Unique question identifier (e.g. 'q-availability-tier').")
    category: str = Field(
        ..., description="Architecture category (e.g. 'availability', 'scaling')."
    )
    question: str = Field(..., description="Natural language clarifying inquiry.")
    rationale: str = Field(
        ..., description="Why this missing information materially impacts choices."
    )
    options: list[str] = Field(..., min_length=2, description="Targeted response choices.")
    default_answer: str | None = Field(default=None, description="Recommended default answer.")
    impact_on_architecture: str = Field(
        ..., description="Explanation of how the choice alters Azure services or SKU sizing."
    )


class WorkloadAssumptions(BaseModel):
    """Explicit workload sizing parameters and volume metrics used for cost modeling."""

    customer_count: int = Field(
        default=10000, ge=1, description="Registered tenant or customer count."
    )
    monthly_active_users: int = Field(default=2500, ge=1, description="Monthly active human users.")
    requests_per_user_per_day: int = Field(
        default=20, ge=1, description="Average API interactions per user daily."
    )
    peak_rps: float = Field(default=50.0, ge=0.1, description="Peak requests per second handled.")
    db_storage_gb: float = Field(
        default=100.0, ge=1.0, description="Relational database size in GB."
    )
    blob_storage_gb: float = Field(
        default=250.0, ge=0.0, description="Unstructured file storage in GB."
    )
    monthly_egress_gb: float = Field(
        default=150.0, ge=0.0, description="Internet outbound data transfer in GB."
    )
    ai_support_monthly_tokens: int = Field(
        default=5000000,
        ge=0,
        description="Estimated monthly LLM tokens for customer support / automated intelligence.",
    )
    target_sla_percentage: float = Field(
        default=99.95, ge=90.0, le=99.999, description="Target availability SLA percentage."
    )
    ha_required: bool = Field(
        default=True, description="Zone-redundant multi-zone high availability flag."
    )
    backup_retention_days: int = Field(
        default=30, ge=1, le=365, description="Automated backup retention days."
    )
    target_region: str = Field(default="eastus", description="Target Azure deployment region.")


class ClarifyingAnswer(BaseModel):
    """User response to a specific clarifying inquiry."""

    question_id: str = Field(..., description="ID matching the clarifying question.")
    selected_option: str = Field(
        ..., description="User-selected option string or custom clarification."
    )


class RequirementsAnalysisRequest(BaseModel):
    """Request payload to analyze natural language application idea."""

    idea: str = Field(
        ...,
        min_length=10,
        description="Unstructured application description or architectural requirements.",
        examples=[
            "I want a customer management platform for 10,000 customers with user authentication, "
            "a web frontend, REST APIs, PostgreSQL, document storage, monitoring, "
            "high availability, and AI-powered customer support."
        ],
    )
    target_region: str = Field(default="eastus", description="Target Azure cloud region.")
    customer_preset: int | None = Field(
        default=None,
        description="Optional customer scale preset: 21, 51, or 10000.",
    )


class RequirementsAnalysisResponse(BaseModel):
    """Structured result of application idea analysis."""

    workload_profile: WorkloadProfile = Field(..., description="Extracted workload profile.")
    clarifying_questions: list[ClarifyingQuestion] = Field(
        default_factory=list, description="Targeted inquiries for missing critical requirements."
    )
    workload_assumptions: WorkloadAssumptions = Field(
        ..., description="Derived workload assumptions and sizing parameters."
    )
    missing_critical_requirements: list[str] = Field(
        default_factory=list, description="List of identified missing requirement categories."
    )
    ai_provider_used: str = Field(
        default="azure_ai_foundry", description="AI provider that performed the analysis."
    )
    status: str = Field(default="ready_for_architecture", description="Workflow state.")


class ArchitectureGenerationRequest(BaseModel):
    """Request payload to generate a production-oriented Azure architecture."""

    workload_profile: WorkloadProfileCreate = Field(..., description="Validated workload profile.")
    workload_assumptions: WorkloadAssumptions = Field(
        ..., description="Workload sizing assumptions."
    )
    clarifications: list[ClarifyingAnswer] = Field(
        default_factory=list, description="User answers to clarifying questions."
    )
    target_region: str = Field(default="eastus", description="Target Azure deployment region.")


class CostSimulationRequest(BaseModel):
    """Request payload to immediately recalculate costs without re-running AI."""

    components: list[ArchitectureComponent] = Field(
        ..., min_length=1, description="Current list of architecture components to price."
    )
    workload_assumptions: WorkloadAssumptions = Field(
        ..., description="Current workload parameters (customer count, storage, RPS, AI volume)."
    )
    target_region: str = Field(default="eastus", description="Target Azure region for pricing.")
    safety_buffer_percentage: Annotated[Decimal, Field(max_digits=5, decimal_places=2)] = Field(
        default=Decimal("15.00"),
        ge=Decimal("0.0"),
        le=Decimal("100.0"),
        description="Percentage added to baseline BOM as contingency.",
    )


class CostSimulationResponse(BaseModel):
    """Deterministic cost simulation results."""

    cost_breakdown: CostBreakdown = Field(
        ..., description="Itemized and aggregated cost breakdown."
    )
    components: list[ArchitectureComponent] = Field(
        ..., description="Components with verified pricing calculations applied."
    )
    pricing_provenance: list[PricingReference] = Field(
        default_factory=list, description="Official pricing references backing each calculation."
    )
    missing_price_warnings: list[str] = Field(
        default_factory=list,
        description="Warnings for services where live prices were unavailable.",
    )
    assumptions: list[str] = Field(
        default_factory=list, description="Explicit billing assumptions utilized in calculation."
    )
    calculation_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp of deterministic calculation.",
    )

    model_config = ConfigDict(from_attributes=True)
