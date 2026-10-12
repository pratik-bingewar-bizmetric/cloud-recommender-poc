"""FastAPI application factory, lifecycle handling, and global middlewares."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from cloud_recommender import __version__
from cloud_recommender.api.routes.health import router as health_router
from cloud_recommender.api.v1.router import api_v1_router
from cloud_recommender.core.config import Settings, get_settings, setup_logging
from cloud_recommender.db.session import close_db_engine

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager handling startup and shutdown hooks."""
    settings = get_settings()
    setup_logging(settings)

    logger.info(
        "application_starting",
        service=settings.app_name,
        env=settings.app_env,
        version=__version__,
        debug=settings.debug,
    )

    yield

    logger.info("application_shutting_down")
    await close_db_engine()
    logger.info("application_shutdown_complete")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure a FastAPI application instance."""
    if settings is None:
        settings = get_settings()

    app = FastAPI(
        title="Cloud Recommender API",
        description=(
            "AI-powered multi-cloud architecture and optimization platform. "
            "Advisory only; zero automated cloud modifications."
        ),
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Configure CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --------------------------------------------------------------------------
    # Global Exception Handlers
    # --------------------------------------------------------------------------
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        logger.warning(
            "http_exception",
            path=request.url.path,
            status_code=exc.status_code,
            detail=exc.detail,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.status_code,
                    "message": exc.detail,
                    "type": "http_error",
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.warning(
            "validation_error",
            path=request.url.path,
            errors=exc.errors(),
        )
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": 422,
                    "message": "Request validation failed",
                    "type": "validation_error",
                    "details": exc.errors(),
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled_server_error",
            path=request.url.path,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": (
                        str(exc)
                        if settings.debug
                        else "An unexpected internal server error occurred."
                    ),
                    "type": "internal_error",
                }
            },
        )

    # --------------------------------------------------------------------------
    # Mount Routers
    # --------------------------------------------------------------------------
    # Root level health probes (standard for Kubernetes / load balancers)
    app.include_router(health_router)

    # Versioned API routes under /api/v1
    app.include_router(api_v1_router, prefix=settings.api_v1_str)

    @app.get("/", tags=["Root"])
    async def root() -> dict[str, str]:
        """Root informational landing endpoint."""
        return {
            "service": settings.app_name,
            "version": __version__,
            "status": "online",
            "docs": "/docs",
        }

    return app


# Application singleton for ASGI servers (Uvicorn)
app = create_app()
