from contextlib import asynccontextmanager
from typing import AsyncGenerator
import logging
from fastapi import FastAPI
from fastapi.responses import JSONResponse

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

    @app.get("/health", tags=["System"], summary="Health check endpoint")
    async def health_check() -> JSONResponse:
        return JSONResponse(content={"status": "ok"})

    return app


app = create_app()
