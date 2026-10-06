import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.files import router as files_router
from app.core.errors import AppError
from app.database import Base, engine

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("geo-measurement-api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager for startup and shutdown events."""
    logger.info("Initializing database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Application startup complete.")
    yield
    logger.info("Application shutdown.")


def create_app() -> FastAPI:
    """Create and configure FastAPI application instance."""
    app = FastAPI(
        title="Geospatial File Measurement API",
        description="Production-grade API for geospatial file ingestion, validation, and projected CRS measurement calculation.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Register error handlers
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        error_payload = {"code": exc.code, "message": exc.message}
        if exc.details:
            error_payload.update(exc.details)
        return JSONResponse(status_code=exc.status_code, content={"error": error_payload})

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Standardized error structure for validation failures
        message = "; ".join(f"{err['loc'][-1]}: {err['msg']}" for err in exc.errors())
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "VALIDATION_ERROR", "message": message}},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            f"Unhandled server error on {request.method} {request.url.path}: {exc}", exc_info=True
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {"code": "INTERNAL_ERROR", "message": "An internal server error occurred."}
            },
        )

    # Register health endpoint
    @app.get("/health", tags=["System"], summary="Health check endpoint")
    async def health_check() -> JSONResponse:
        return JSONResponse(content={"status": "ok"})

    # Register API routers
    app.include_router(files_router)

    return app


app = create_app()
