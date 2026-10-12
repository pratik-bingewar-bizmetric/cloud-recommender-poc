"""Version 1 API router consolidating v1 endpoints."""

from fastapi import APIRouter

from cloud_recommender.api.routes.catalog import router as catalog_router
from cloud_recommender.api.routes.health import router as health_router

api_v1_router = APIRouter()

# Health endpoints mounted under /api/v1
api_v1_router.include_router(health_router, prefix="", tags=["Health"])

# Catalog endpoints mounted under /api/v1/catalog
api_v1_router.include_router(catalog_router)
