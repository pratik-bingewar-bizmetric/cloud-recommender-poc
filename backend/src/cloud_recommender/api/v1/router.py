from fastapi import APIRouter

from cloud_recommender.api.routes.analysis import router as analysis_router
from cloud_recommender.api.routes.architecture import router as architecture_router
from cloud_recommender.api.routes.catalog import router as catalog_router
from cloud_recommender.api.routes.health import router as health_router
from cloud_recommender.api.routes.inventory import router as inventory_router
from cloud_recommender.api.routes.monitoring import router as monitoring_router
from cloud_recommender.api.routes.pricing import router as pricing_router

api_v1_router = APIRouter()

# Health endpoints mounted under /api/v1
api_v1_router.include_router(health_router, prefix="", tags=["Health"])

# Catalog endpoints mounted under /api/v1/catalog
api_v1_router.include_router(catalog_router)

# Phase A & B Analysis, Architecture, Pricing, Inventory, and Monitoring routes
api_v1_router.include_router(analysis_router)
api_v1_router.include_router(architecture_router)
api_v1_router.include_router(pricing_router)
api_v1_router.include_router(inventory_router)
api_v1_router.include_router(monitoring_router)
