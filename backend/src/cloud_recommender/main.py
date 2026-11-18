"""FastAPI application factory, lifecycle handling, and global middlewares."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from cloud_recommender import __version__
from cloud_recommender.api.routes.health import router as health_router
from cloud_recommender.api.v1.router import api_v1_router
from cloud_recommender.core.auth import describe_auth_mode
from cloud_recommender.core.config import Settings, get_settings, setup_logging
from cloud_recommender.db.session import close_db_engine
from cloud_recommender.services.inventory.azure_inventory import AzureAuthenticationRequired

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager handling startup and shutdown hooks."""
    settings = get_settings()
    settings.validate_for_serving()
    setup_logging(settings)

    logger.info(
        "application_starting",
        service=settings.app_name,
        env=settings.app_env,
        version=__version__,
        debug=settings.debug,
    )
    auth_mode, auth_hint = describe_auth_mode(settings)
    if auth_mode == "none":
        logger.warning("authentication_not_configured", auth_mode=auth_mode, hint=auth_hint)
    else:
        logger.info("authentication_mode", auth_mode=auth_mode, hint=auth_hint)

    refresher = None
    if settings.app_env != "testing" and settings.databricks_inventory_refresh_seconds > 0:
        from cloud_recommender.services.databricks.refresher import get_refresher

        refresher = get_refresher()
        refresher.start()
        logger.info(
            "databricks_refresher_started",
            inventory_seconds=settings.databricks_inventory_refresh_seconds,
            metadata_seconds=settings.databricks_metadata_refresh_seconds,
        )

    yield

    if refresher is not None:
        await refresher.stop()
    logger.info("application_shutting_down")
    await close_db_engine()
    logger.info("application_shutdown_complete")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure a FastAPI application instance."""
    if settings is None:
        settings = get_settings()
    # Web-server security requirements (not applied to operational scripts); never skippable.
    settings.validate_for_serving()

    # Interactive API documentation is a development aid: disabled entirely in production.
    docs_enabled = settings.app_env != "production"

    app = FastAPI(
        title="Cloud Recommender API",
        description=(
            "AI-powered multi-cloud architecture and optimization platform. "
            "Advisory only; zero automated cloud modifications."
        ),
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    # Configure CORS Middleware
    # Production: only the verbs/headers the API actually uses (routes are GET/POST/PATCH/DELETE; the SPA sends
    # a Bearer token and JSON). Development keeps permissive behaviour for local tooling.
    is_production = settings.app_env == "production"
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"] if is_production else ["*"],
        allow_headers=["Authorization", "Content-Type", "Accept"] if is_production else ["*"],
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
            headers=exc.headers,
        )

    @app.exception_handler(AzureAuthenticationRequired)
    async def azure_auth_required_handler(
        request: Request, exc: AzureAuthenticationRequired
    ) -> JSONResponse:
        """Expired/missing Azure identity: fail closed with 401, never fixture data."""
        logger.warning("azure_authentication_required", path=request.url.path)
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "code": 401,
                    "message": str(exc),
                    "type": "azure_authentication_required",
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Submitted values (``input``) and ``ctx`` are dropped: they can contain secrets such as
        # a service principal client secret, and must never be logged or echoed back.
        safe_errors = [
            {k: v for k, v in error.items() if k not in ("input", "ctx", "url")}
            for error in exc.errors()
        ]
        logger.warning(
            "validation_error",
            path=request.url.path,
            errors=safe_errors,
        )
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": 422,
                    "message": "Request validation failed",
                    "type": "validation_error",
                    "details": safe_errors,
                }
            },
        )

    @app.exception_handler(SQLAlchemyError)
    @app.exception_handler(ConnectionError)
    async def database_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
        """Database problems are an explicit 503 with guidance, never a generic 500."""
        logger.error("database_unavailable", path=request.url.path, error_type=type(exc).__name__)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": {
                    "code": 503,
                    "message": {
                        "error_code": "DATABASE_UNAVAILABLE",
                        "message": (
                            "The application database is unavailable or not initialised "
                            "(an administrator must apply the pending database migrations). "
                            "Nothing was saved."
                        ),
                    },
                    "type": "database_unavailable",
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
            "docs": "/docs" if docs_enabled else "disabled",
        }

    return app


# Application singleton for ASGI servers (Uvicorn)
app = create_app()
