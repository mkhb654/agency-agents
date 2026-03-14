"""API server for the hedge fund application.

Exposes a FastAPI application with REST endpoints for running
analysis, backtesting, and inspecting portfolio state.  Also
provides a WebSocket endpoint for streaming progress updates.
"""

from hedge_fund.api.server import app, create_app

__all__ = ["app", "create_app"]
