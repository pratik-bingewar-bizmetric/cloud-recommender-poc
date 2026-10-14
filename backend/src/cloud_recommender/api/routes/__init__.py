from cloud_recommender.api.routes.analysis import router as analysis_router
from cloud_recommender.api.routes.architecture import router as architecture_router
from cloud_recommender.api.routes.catalog import router as catalog_router
from cloud_recommender.api.routes.health import router as health_router
from cloud_recommender.api.routes.pricing import router as pricing_router

__all__ = [
    "health_router",
    "catalog_router",
    "analysis_router",
    "architecture_router",
    "pricing_router",
]
