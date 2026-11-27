from fastapi import APIRouter, Depends

from cloud_recommender.api.routes.analysis import router as analysis_router
from cloud_recommender.api.routes.architecture import router as architecture_router
from cloud_recommender.api.routes.auth import router as auth_router
from cloud_recommender.api.routes.aws import router as aws_router
from cloud_recommender.api.routes.azure_live import router as azure_live_router
from cloud_recommender.api.routes.catalog import router as catalog_router
from cloud_recommender.api.routes.configuration import router as configuration_router
from cloud_recommender.api.routes.connections import router as connections_router
from cloud_recommender.api.routes.databricks import router as databricks_router
from cloud_recommender.api.routes.finops import router as finops_router
from cloud_recommender.api.routes.gcp import router as gcp_router
from cloud_recommender.api.routes.health import router as health_router
from cloud_recommender.api.routes.ingestion import router as ingestion_router
from cloud_recommender.api.routes.inventory import router as inventory_router
from cloud_recommender.api.routes.monitoring import router as monitoring_router
from cloud_recommender.api.routes.pricing import router as pricing_router
from cloud_recommender.core.auth import enforce_route_policy

api_v1_router = APIRouter()

# Health endpoints mounted under /api/v1 (Public - no auth required for liveness/readiness probes)
api_v1_router.include_router(health_router, prefix="", tags=["Health"])

# Catalog endpoints mounted under /api/v1/catalog (Public service catalog)
api_v1_router.include_router(catalog_router)

# Service Principal-only authentication and application sessions mounted under /api/v1/auth
api_v1_router.include_router(auth_router)

# Protected routes: Entra authentication + client/scope/role policy (core.auth.enforce_route_policy)
auth_deps = [Depends(enforce_route_policy)]

# Connection and authentication lifecycle endpoints mounted under /api/v1/connections
api_v1_router.include_router(connections_router, dependencies=auth_deps)

# Multi-cloud resource selection & Databricks configuration mounted under /api/v1/configuration
api_v1_router.include_router(configuration_router, dependencies=auth_deps)

# Scope-aware ingestion & configuration enforcement mounted under /api/v1/ingestion
api_v1_router.include_router(ingestion_router, dependencies=auth_deps)

# Databricks multi-workspace connectivity & discovery mounted under /api/v1/databricks
api_v1_router.include_router(databricks_router, dependencies=auth_deps)

# Azure Databricks FinOps Command Center (15 modules) mounted under /api/v1/finops
api_v1_router.include_router(finops_router, dependencies=auth_deps)

# Phase A & B Analysis, Architecture, Pricing, Inventory, and Monitoring routes
api_v1_router.include_router(analysis_router, dependencies=auth_deps)
api_v1_router.include_router(architecture_router, dependencies=auth_deps)
api_v1_router.include_router(pricing_router, dependencies=auth_deps)
api_v1_router.include_router(inventory_router, dependencies=auth_deps)
api_v1_router.include_router(monitoring_router, dependencies=auth_deps)

# Live Azure connection demo: user-supplied service principal, owner-bound sessions
api_v1_router.include_router(azure_live_router, dependencies=auth_deps)

# Google Cloud Platform (GCP) Service Account authentication, connectivity, and discovery
api_v1_router.include_router(gcp_router, dependencies=auth_deps)

# Amazon Web Services (AWS) authentication, connectivity, resource discovery, and findings
api_v1_router.include_router(aws_router, dependencies=auth_deps)
