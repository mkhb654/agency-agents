"""API route handlers for the Agency Hedge Fund.

Defines Pydantic request/response models and route handler functions
for analysis, backtesting, portfolio inspection, and WebSocket streaming.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from hedge_fund.config import DEFAULT_MODELS, LLMProvider, get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["hedge-fund"])

# ---------------------------------------------------------------------------
# In-memory task tracking for background jobs
# ---------------------------------------------------------------------------

_background_tasks: dict[str, dict[str, Any]] = {}
_ws_connections: dict[str, list[WebSocket]] = {}


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class AnalyzeRequest(BaseModel):
    """Request body for the /api/analyze endpoint."""

    tickers: list[str] = Field(
        ...,
        min_length=1,
        description="List of stock ticker symbols to analyse.",
        examples=[["AAPL", "GOOGL", "MSFT"]],
    )
    start_date: Optional[str] = Field(
        default=None,
        description="Analysis start date in YYYY-MM-DD format. Defaults to 3 months ago.",
        examples=["2024-01-01"],
    )
    end_date: Optional[str] = Field(
        default=None,
        description="Analysis end date in YYYY-MM-DD format. Defaults to today.",
        examples=["2024-12-31"],
    )
    analysts: Optional[list[str]] = Field(
        default=None,
        description="Analyst agent names to use. None = all available.",
    )
    model_name: str = Field(
        default="gpt-4.1",
        description="LLM model identifier.",
    )
    model_provider: str = Field(
        default="openai",
        description="LLM provider name.",
    )
    show_reasoning: bool = Field(
        default=False,
        description="Whether to include detailed analyst reasoning in the response.",
    )


class BacktestRequest(BaseModel):
    """Request body for the /api/backtest endpoint."""

    tickers: list[str] = Field(
        ...,
        min_length=1,
        description="List of stock ticker symbols.",
        examples=[["AAPL", "GOOGL", "MSFT"]],
    )
    start_date: str = Field(
        ...,
        description="Backtest start date in YYYY-MM-DD format.",
        examples=["2023-01-01"],
    )
    end_date: str = Field(
        ...,
        description="Backtest end date in YYYY-MM-DD format.",
        examples=["2024-01-01"],
    )
    step_months: int = Field(
        default=1,
        ge=1,
        le=12,
        description="Number of months per analysis window.",
    )
    initial_cash: float = Field(
        default=100_000.0,
        gt=0,
        description="Starting cash balance in USD.",
    )
    margin_requirement: float = Field(
        default=0.5,
        gt=0.0,
        le=1.0,
        description="Margin requirement fraction.",
    )
    analysts: Optional[list[str]] = Field(
        default=None,
        description="Analyst agent names to use.",
    )
    model_name: str = Field(
        default="gpt-4.1",
        description="LLM model identifier.",
    )
    model_provider: str = Field(
        default="openai",
        description="LLM provider name.",
    )


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Response for the /api/health endpoint."""

    status: str = "healthy"
    version: str = "1.0.0"
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class AnalystInfo(BaseModel):
    """Information about an available analyst agent."""

    name: str
    display_name: str
    description: str


class AnalystsResponse(BaseModel):
    """Response listing available analyst agents."""

    analysts: list[AnalystInfo]
    total: int


class ModelInfo(BaseModel):
    """Information about an available LLM model."""

    provider: str
    model_id: str
    is_default: bool


class ModelsResponse(BaseModel):
    """Response listing available LLM models."""

    models: list[ModelInfo]
    total: int


class AnalysisSignal(BaseModel):
    """A single analyst's signal for one ticker."""

    analyst: str
    ticker: str
    signal: str  # bullish, bearish, neutral
    confidence: float
    reasoning: Optional[dict[str, Any]] = None


class AnalyzeResponse(BaseModel):
    """Response for the /api/analyze endpoint."""

    task_id: str
    status: str  # pending, running, completed, failed
    tickers: list[str]
    signals: list[AnalysisSignal] = Field(default_factory=list)
    decisions: list[dict[str, Any]] = Field(default_factory=list)
    message: str = ""


class BacktestResponse(BaseModel):
    """Response for the /api/backtest endpoint."""

    task_id: str
    status: str
    result: Optional[dict[str, Any]] = None
    message: str = ""


class PortfolioResponse(BaseModel):
    """Response for the /api/portfolio endpoint."""

    cash: float
    total_value: float
    return_pct: float
    positions: dict[str, Any]
    short_positions: dict[str, Any]
    margin_used: float
    realized_pnl: float


class TaskStatusResponse(BaseModel):
    """Response for task status polling."""

    task_id: str
    status: str
    progress: float = 0.0
    message: str = ""
    result: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Analyst registry
# ---------------------------------------------------------------------------

AVAILABLE_ANALYSTS: list[AnalystInfo] = [
    AnalystInfo(
        name="ben_graham",
        display_name="Ben Graham",
        description="Value investing: seeks stocks trading below intrinsic value with margin of safety.",
    ),
    AnalystInfo(
        name="warren_buffett",
        display_name="Warren Buffett",
        description="Quality-focused: looks for durable competitive advantages and strong management.",
    ),
    AnalystInfo(
        name="peter_lynch",
        display_name="Peter Lynch",
        description="Growth at a reasonable price (GARP): classifies stocks by growth category.",
    ),
    AnalystInfo(
        name="cathie_wood",
        display_name="Cathie Wood",
        description="Disruptive innovation: focuses on transformative technologies and high growth.",
    ),
    AnalystInfo(
        name="michael_burry",
        display_name="Michael Burry",
        description="Contrarian deep-value: hunts for asymmetric risk/reward opportunities.",
    ),
    AnalystInfo(
        name="stanley_druckenmiller",
        display_name="Stanley Druckenmiller",
        description="Macro-driven: combines top-down macro analysis with bottom-up stock selection.",
    ),
]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return API health status."""
    return HealthResponse()


@router.get("/analysts", response_model=AnalystsResponse)
async def list_analysts() -> AnalystsResponse:
    """List all available analyst agents."""
    return AnalystsResponse(analysts=AVAILABLE_ANALYSTS, total=len(AVAILABLE_ANALYSTS))


@router.get("/models", response_model=ModelsResponse)
async def list_models() -> ModelsResponse:
    """List all available LLM models and providers."""
    models = [
        ModelInfo(
            provider=provider.value,
            model_id=model_id,
            is_default=(provider == LLMProvider.OPENAI),
        )
        for provider, model_id in DEFAULT_MODELS.items()
    ]
    return ModelsResponse(models=models, total=len(models))


@router.post("/analyze", response_model=AnalyzeResponse)
async def run_analysis(
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
) -> AnalyzeResponse:
    """Run AI analysis on the specified tickers.

    For long-running analysis, the task runs in the background.
    Poll ``/api/tasks/{task_id}`` or connect to ``/ws/analysis``
    for progress updates.
    """
    task_id = str(uuid.uuid4())

    # Set default dates if not provided
    today = date.today()
    end_date = request.end_date or today.isoformat()
    if request.start_date:
        start_date = request.start_date
    else:
        # Default to 3 months ago
        month = today.month - 3
        year = today.year
        if month <= 0:
            month += 12
            year -= 1
        start_date = date(year, month, today.day).isoformat()

    _background_tasks[task_id] = {
        "status": "pending",
        "progress": 0.0,
        "message": "Task queued",
        "result": None,
    }

    background_tasks.add_task(
        _run_analysis_task,
        task_id=task_id,
        tickers=request.tickers,
        start_date=start_date,
        end_date=end_date,
        analysts=request.analysts,
        model_name=request.model_name,
        model_provider=request.model_provider,
        show_reasoning=request.show_reasoning,
    )

    return AnalyzeResponse(
        task_id=task_id,
        status="pending",
        tickers=request.tickers,
        message=f"Analysis queued for {len(request.tickers)} tickers. "
                f"Poll /api/tasks/{task_id} for status.",
    )


@router.post("/backtest", response_model=BacktestResponse)
async def run_backtest(
    request: BacktestRequest,
    background_tasks: BackgroundTasks,
) -> BacktestResponse:
    """Run a historical backtest.

    Runs in the background due to potentially long execution time.
    Poll ``/api/tasks/{task_id}`` for results.
    """
    task_id = str(uuid.uuid4())

    _background_tasks[task_id] = {
        "status": "pending",
        "progress": 0.0,
        "message": "Backtest queued",
        "result": None,
    }

    background_tasks.add_task(
        _run_backtest_task,
        task_id=task_id,
        tickers=request.tickers,
        start_date=request.start_date,
        end_date=request.end_date,
        step_months=request.step_months,
        initial_cash=request.initial_cash,
        margin_requirement=request.margin_requirement,
        analysts=request.analysts,
        model_name=request.model_name,
        model_provider=request.model_provider,
    )

    return BacktestResponse(
        task_id=task_id,
        status="pending",
        message=f"Backtest queued for {len(request.tickers)} tickers "
                f"({request.start_date} -> {request.end_date}). "
                f"Poll /api/tasks/{task_id} for results.",
    )


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str) -> TaskStatusResponse:
    """Get the status of a background task."""
    task = _background_tasks.get(task_id)
    if task is None:
        return TaskStatusResponse(
            task_id=task_id,
            status="not_found",
            message="Task not found. It may have expired.",
        )

    return TaskStatusResponse(
        task_id=task_id,
        status=task["status"],
        progress=task["progress"],
        message=task["message"],
        result=task.get("result"),
    )


@router.get("/portfolio", response_model=PortfolioResponse)
async def get_portfolio() -> PortfolioResponse:
    """Get the current portfolio state.

    Returns the default initial portfolio if no analysis has been run.
    """
    settings = get_settings()
    return PortfolioResponse(
        cash=settings.initial_cash,
        total_value=settings.initial_cash,
        return_pct=0.0,
        positions={},
        short_positions={},
        margin_used=0.0,
        realized_pnl=0.0,
    )


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


ws_router = APIRouter()


@ws_router.websocket("/ws/analysis")
async def websocket_analysis(websocket: WebSocket) -> None:
    """WebSocket endpoint for streaming analysis progress updates.

    Clients connect and send a JSON message with ``task_id`` to subscribe
    to updates for that task.  The server pushes progress events as JSON
    messages.
    """
    await websocket.accept()
    task_id: Optional[str] = None

    try:
        # Wait for subscription message
        data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
        msg = json.loads(data)
        task_id = msg.get("task_id")

        if not task_id:
            await websocket.send_json({"error": "task_id is required"})
            await websocket.close()
            return

        # Register WebSocket connection
        if task_id not in _ws_connections:
            _ws_connections[task_id] = []
        _ws_connections[task_id].append(websocket)

        await websocket.send_json({
            "type": "subscribed",
            "task_id": task_id,
            "message": "Subscribed to task updates.",
        })

        # Keep connection alive and relay task state changes
        while True:
            task = _background_tasks.get(task_id)
            if task and task["status"] in ("completed", "failed"):
                await websocket.send_json({
                    "type": "complete",
                    "task_id": task_id,
                    "status": task["status"],
                    "result": task.get("result"),
                    "message": task.get("message", ""),
                })
                break

            # Wait for client pings or just sleep
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=2.0)
            except asyncio.TimeoutError:
                pass  # Normal: no client message, just keep looping

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected (task_id=%s)", task_id)
    except asyncio.TimeoutError:
        await websocket.send_json({"error": "Connection timeout: no subscription received"})
        await websocket.close()
    except Exception as exc:
        logger.error("WebSocket error: %s", exc, exc_info=True)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        # Clean up connection
        if task_id and task_id in _ws_connections:
            conns = _ws_connections[task_id]
            if websocket in conns:
                conns.remove(websocket)
            if not conns:
                del _ws_connections[task_id]


# ---------------------------------------------------------------------------
# Background task runners
# ---------------------------------------------------------------------------


async def _broadcast_progress(task_id: str, step: int, total: int, message: str) -> None:
    """Broadcast progress to all WebSocket subscribers for a task."""
    if task_id in _ws_connections:
        payload = {
            "type": "progress",
            "task_id": task_id,
            "step": step,
            "total": total,
            "progress": step / total if total > 0 else 0.0,
            "message": message,
        }
        dead: list[WebSocket] = []
        for ws in _ws_connections[task_id]:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            _ws_connections[task_id].remove(ws)


async def _run_analysis_task(
    task_id: str,
    tickers: list[str],
    start_date: str,
    end_date: str,
    analysts: Optional[list[str]],
    model_name: str,
    model_provider: str,
    show_reasoning: bool,
) -> None:
    """Background task: run the hedge fund analysis pipeline."""
    _background_tasks[task_id]["status"] = "running"
    _background_tasks[task_id]["message"] = "Analysis in progress"

    try:
        # Attempt to import and run the graph
        try:
            from hedge_fund.graph.workflow import run_hedge_fund  # type: ignore[import-not-found]

            result = run_hedge_fund(
                tickers=tickers,
                start_date=start_date,
                end_date=end_date,
                selected_analysts=analysts,
                model_name=model_name,
                model_provider=model_provider,
            )

            # Parse result
            signals = []
            decisions = []

            if isinstance(result, dict):
                raw_signals = result.get("analyst_signals", {})
                for analyst_name, ticker_signals in raw_signals.items():
                    if isinstance(ticker_signals, dict):
                        for ticker, signal_data in ticker_signals.items():
                            signal_entry = {
                                "analyst": analyst_name,
                                "ticker": ticker,
                                "signal": getattr(signal_data, "signal", signal_data.get("signal", "neutral")),
                                "confidence": getattr(signal_data, "confidence", signal_data.get("confidence", 0)),
                            }
                            if show_reasoning:
                                signal_entry["reasoning"] = getattr(
                                    signal_data, "reasoning", signal_data.get("reasoning", {})
                                )
                            signals.append(signal_entry)

                raw_decisions = result.get("decisions", [])
                for d in raw_decisions:
                    decisions.append({
                        "action": getattr(d, "action", d.get("action", "hold") if isinstance(d, dict) else "hold"),
                        "ticker": getattr(d, "ticker", d.get("ticker", "") if isinstance(d, dict) else ""),
                        "quantity": getattr(d, "quantity", d.get("quantity", 0) if isinstance(d, dict) else 0),
                        "confidence": getattr(d, "confidence", d.get("confidence", 0) if isinstance(d, dict) else 0),
                        "reasoning": getattr(d, "reasoning", d.get("reasoning", "") if isinstance(d, dict) else ""),
                    })

            _background_tasks[task_id].update({
                "status": "completed",
                "progress": 1.0,
                "message": "Analysis complete",
                "result": {
                    "tickers": tickers,
                    "signals": signals,
                    "decisions": decisions,
                },
            })

        except ImportError:
            _background_tasks[task_id].update({
                "status": "completed",
                "progress": 1.0,
                "message": "Analysis complete (graph module not yet implemented - returning stub)",
                "result": {
                    "tickers": tickers,
                    "signals": [],
                    "decisions": [
                        {"action": "hold", "ticker": t, "quantity": 0, "confidence": 0, "reasoning": "Stub response"}
                        for t in tickers
                    ],
                },
            })

    except Exception as exc:
        logger.error("Analysis task failed: %s", exc, exc_info=True)
        _background_tasks[task_id].update({
            "status": "failed",
            "progress": 0.0,
            "message": f"Analysis failed: {exc}",
        })

    # Notify WebSocket subscribers
    await _broadcast_progress(
        task_id,
        step=1,
        total=1,
        message=_background_tasks[task_id]["message"],
    )


async def _run_backtest_task(
    task_id: str,
    tickers: list[str],
    start_date: str,
    end_date: str,
    step_months: int,
    initial_cash: float,
    margin_requirement: float,
    analysts: Optional[list[str]],
    model_name: str,
    model_provider: str,
) -> None:
    """Background task: run a backtest."""
    _background_tasks[task_id]["status"] = "running"
    _background_tasks[task_id]["message"] = "Backtest in progress"

    try:
        from hedge_fund.backtesting.engine import BacktestEngine

        engine = BacktestEngine(
            initial_cash=initial_cash,
            margin_requirement=margin_requirement,
        )

        # Wire up progress callback to update task state
        def on_progress(step: int, total: int, message: str) -> None:
            progress = step / total if total > 0 else 0.0
            _background_tasks[task_id].update({
                "progress": progress,
                "message": message,
            })
            # Schedule WebSocket broadcast (fire-and-forget)
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(_broadcast_progress(task_id, step, total, message))
            except RuntimeError:
                pass

        engine.set_progress_callback(on_progress)

        # Run backtest (this is synchronous / CPU-bound)
        result = await asyncio.to_thread(
            engine.run,
            tickers=tickers,
            start_date=start_date,
            end_date=end_date,
            step_months=step_months,
            selected_analysts=analysts,
            model_name=model_name,
            model_provider=model_provider,
        )

        _background_tasks[task_id].update({
            "status": "completed",
            "progress": 1.0,
            "message": "Backtest complete",
            "result": result.to_dict(),
        })

    except Exception as exc:
        logger.error("Backtest task failed: %s", exc, exc_info=True)
        _background_tasks[task_id].update({
            "status": "failed",
            "progress": 0.0,
            "message": f"Backtest failed: {exc}",
        })

    # Final WebSocket notification
    await _broadcast_progress(
        task_id,
        step=1,
        total=1,
        message=_background_tasks[task_id]["message"],
    )
