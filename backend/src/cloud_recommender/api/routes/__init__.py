"""API route modules."""

from cloud_recommender.api.routes.catalog import router as catalog_router
from cloud_recommender.api.routes.health import router as health_router

__all__ = ["health_router", "catalog_router"]
