"""FastAPI application factory and server configuration.

Usage:
    # Run directly
    python -m hedge_fund.api.server

    # Or import
    from hedge_fund.api.server import app
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from hedge_fund.api.routes import router, ws_router
from hedge_fund.config import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown events."""
    settings = get_settings()
    logger.info(
        "Agency Hedge Fund API starting on %s:%d (provider=%s, model=%s)",
        settings.api_host,
        settings.api_port,
        settings.llm_provider.value,
        settings.resolved_model,
    )
    yield
    logger.info("Agency Hedge Fund API shutting down")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns
    -------
    FastAPI
        Fully configured application instance with all middleware
        and routes registered.
    """
    settings = get_settings()

    application = FastAPI(
        title="Agency Hedge Fund API",
        description=(
            "AI-powered hedge fund API with multi-agent analysis, "
            "backtesting, and portfolio management."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------
    # CORS middleware
    # ------------------------------------------------------------------
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://localhost:3001",
            "http://localhost:5173",
            "http://localhost:8080",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    # ------------------------------------------------------------------
    # Exception handlers
    # ------------------------------------------------------------------
    @application.exception_handler(Exception)
    async def global_exception_handler(request, exc):  # noqa: ANN001
        """Catch-all exception handler for unhandled errors."""
        logger.error("Unhandled exception: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
            },
        )

    @application.exception_handler(ValueError)
    async def value_error_handler(request, exc):  # noqa: ANN001
        """Handle validation-type errors with a 400 status."""
        return JSONResponse(
            status_code=400,
            content={
                "error": "Bad request",
                "detail": "Invalid input parameters",
            },
        )

    # ------------------------------------------------------------------
    # Register routers
    # ------------------------------------------------------------------
    application.include_router(router)
    application.include_router(ws_router)

    # ------------------------------------------------------------------
    # Root redirect
    # ------------------------------------------------------------------
    @application.get("/", include_in_schema=False)
    async def root():
        """Redirect root to API docs."""
        return {
            "name": "Agency Hedge Fund API",
            "version": "1.0.0",
            "docs": "/docs",
            "health": "/api/health",
        }

    return application


# Module-level app instance for uvicorn and imports
app = create_app()


def serve(host: str | None = None, port: int | None = None, reload: bool = False) -> None:
    """Start the Uvicorn server.

    Parameters
    ----------
    host : str, optional
        Bind address.  Defaults to ``settings.api_host``.
    port : int, optional
        Bind port.  Defaults to ``settings.api_port``.
    reload : bool
        Enable auto-reload for development.
    """
    settings = get_settings()
    uvicorn.run(
        "hedge_fund.api.server:app",
        host=host or settings.api_host,
        port=port or settings.api_port,
        reload=reload,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    serve()
