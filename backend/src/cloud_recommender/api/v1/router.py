"""Version 1 API router consolidating v1 endpoints."""

from fastapi import APIRouter

from cloud_recommender.api.routes.health import router as health_router

api_v1_router = APIRouter()

# Mount health routes under /api/v1 as well for API consumers
api_v1_router.include_router(health_router, prefix="", tags=["Health"])

# Placeholders for future milestone routers (e.g. Phase A and Phase B)
# api_v1_router.include_router(phase_a_router, prefix="/architectures", tags=["Phase A"])
# api_v1_router.include_router(phase_b_router, prefix="/optimizations", tags=["Phase B"])
