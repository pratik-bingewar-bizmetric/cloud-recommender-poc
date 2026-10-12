"""Common domain enums and shared types for Cloud Recommender POC."""

from enum import StrEnum


class CloudProvider(StrEnum):
    """Supported cloud infrastructure providers."""

    AZURE = "azure"
    AWS = "aws"
    GCP = "gcp"


class ServiceCategory(StrEnum):
    """Normalized cloud service architectural categories."""

    COMPUTE = "compute"
    DATABASE = "database"
    STORAGE = "storage"
    NETWORKING = "networking"
    SECURITY = "security"
    MONITORING = "monitoring"
    AI_ML = "ai_ml"
    INTEGRATION = "integration"


class WorkloadCategory(StrEnum):
    """Categorization of application workload architectural archetypes."""

    WEB_APP = "web_app"
    MICROSERVICES = "microservices"
    BATCH_PROCESSING = "batch_processing"
    DATA_PIPELINE = "data_pipeline"
    AI_INFERENCE = "ai_inference"
    EVENT_DRIVEN = "event_driven"
    API_SERVICE = "api_service"
    E_COMMERCE = "e_commerce"


class ComplianceStandard(StrEnum):
    """Regulatory and security compliance certification frameworks."""

    HIPAA = "hipaa"
    GDPR = "gdpr"
    PCI_DSS = "pci_dss"
    SOC2 = "soc2"
    FEDRAMP = "fedramp"
    ISO27001 = "iso27001"


class CatalogRecordStatus(StrEnum):
    """Operational status and verification tier of a catalog service entry."""

    VERIFIED = "verified"
    FIXTURE = "fixture"
    DEPRECATED = "deprecated"


class RecommendationStatus(StrEnum):
    """Lifecycle status of a generated architecture recommendation."""

    DRAFT = "draft"
    PROPOSED = "proposed"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class AuditApprovalStatus(StrEnum):
    """Human review status for cloud optimization and waste assessments."""

    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
