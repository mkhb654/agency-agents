"""LangGraph workflow orchestration for the AI hedge fund.

Builds and runs the multi-agent analysis pipeline:

    START -> start_node
          -> [analyst_1, analyst_2, ...] (fan-out, parallel)
          -> risk_manager                 (fan-in)
          -> portfolio_manager
          -> END

Usage::

    decisions = run_hedge_fund(
        tickers=["AAPL", "GOOGL", "MSFT"],
        start_date="2024-01-01",
        end_date="2024-12-31",
    )
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Callable, Optional

from langgraph.graph import END, START, StateGraph

from hedge_fund.agents.portfolio_manager import portfolio_manager_agent
from hedge_fund.agents.risk_manager import risk_manager_agent
from hedge_fund.data.models import PortfolioState
from hedge_fund.graph.state import AgentState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Analyst registry — lazy import to avoid circular dependency issues and
# to allow selective inclusion.
# ---------------------------------------------------------------------------

# Maps human-friendly analyst name -> (module_path, function_name)
_ANALYST_REGISTRY: dict[str, tuple[str, str]] = {
    # Analytical agents (rule-based / hybrid)
    "fundamentals": ("hedge_fund.agents.fundamentals", "fundamentals_agent"),
    "technicals": ("hedge_fund.agents.technicals", "technicals_agent"),
    "sentiment": ("hedge_fund.agents.sentiment", "sentiment_agent"),
    "valuation": ("hedge_fund.agents.valuation", "valuation_agent"),
    "macro": ("hedge_fund.agents.macro", "macro_agent"),
    # Investor persona agents (LLM-powered)
    "warren_buffett": ("hedge_fund.agents.warren_buffett", "warren_buffett_agent"),
    "ben_graham": ("hedge_fund.agents.ben_graham", "ben_graham_agent"),
    "cathie_wood": ("hedge_fund.agents.cathie_wood", "cathie_wood_agent"),
    "michael_burry": ("hedge_fund.agents.michael_burry", "michael_burry_agent"),
    "peter_lynch": ("hedge_fund.agents.peter_lynch", "peter_lynch_agent"),
    "stanley_druckenmiller": (
        "hedge_fund.agents.stanley_druckenmiller",
        "stanley_druckenmiller_agent",
    ),
}


def _resolve_analyst(name: str) -> Callable[[AgentState], dict[str, Any]]:
    """Dynamically import and return an analyst agent function by registry name.

    Parameters
    ----------
    name:
        Key in :data:`_ANALYST_REGISTRY`.

    Returns
    -------
    Callable
        The agent function with signature ``(AgentState) -> dict``.

    Raises
    ------
    ValueError
        If *name* is not found in the registry.
    ImportError
        If the analyst module cannot be imported.
    """
    entry = _ANALYST_REGISTRY.get(name)
    if entry is None:
        raise ValueError(
            f"Unknown analyst '{name}'. Available: {sorted(_ANALYST_REGISTRY.keys())}"
        )

    module_path, func_name = entry
    import importlib

    module = importlib.import_module(module_path)
    func = getattr(module, func_name)
    return func  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Start node
# ---------------------------------------------------------------------------


def _start_node(state: AgentState) -> dict[str, Any]:
    """Initialize / validate the shared state at the beginning of the pipeline.

    Ensures required keys exist and sets sensible defaults.
    """
    data = dict(state.get("data", {}))
    metadata = dict(state.get("metadata", {}))

    # Ensure essential data keys
    data.setdefault("tickers", [])
    data.setdefault("start_date", "")
    data.setdefault("end_date", str(date.today()))
    data.setdefault("analyst_signals", {})
    data.setdefault("risk_assessment", {})
    data.setdefault("decisions", {})

    # Ensure portfolio
    if "portfolio" not in data or data["portfolio"] is None:
        from hedge_fund.config import get_settings

        settings = get_settings()
        data["portfolio"] = PortfolioState(cash=settings.initial_cash).model_dump()
    elif isinstance(data["portfolio"], PortfolioState):
        data["portfolio"] = data["portfolio"].model_dump()

    logger.info(
        "Pipeline started: tickers=%s, window=%s to %s",
        data["tickers"],
        data.get("start_date", "?"),
        data.get("end_date", "?"),
    )

    return {
        "data": data,
        "metadata": metadata,
        "messages": state.get("messages", []),
    }


# ---------------------------------------------------------------------------
# Analyst wrapper factory
# ---------------------------------------------------------------------------


def _make_analyst_node(
    analyst_fn: Callable[[AgentState], dict[str, Any]],
    analyst_name: str,
) -> Callable[[AgentState], dict[str, Any]]:
    """Wrap an analyst function to merge its signals into ``analyst_signals``.

    Each analyst produces signals keyed by ticker.  This wrapper ensures the
    result is stored under ``data.analyst_signals[analyst_name]``.
    """

    def _wrapper(state: AgentState) -> dict[str, Any]:
        try:
            result = analyst_fn(state)
        except Exception:
            logger.exception("Analyst '%s' raised an exception; returning empty signals.", analyst_name)
            result = {"data": {}}

        result_data = result.get("data", {})
        current_data = dict(state.get("data", {}))

        # Merge analyst signals
        analyst_signals = dict(current_data.get("analyst_signals", {}))

        # The analyst may return signals under various keys
        # Convention: the analyst's signals are in result_data keyed by ticker
        # or under a "signals" sub-key
        signals = result_data.get("signals", {})
        if not signals:
            # Try to extract per-ticker signals directly
            for key, value in result_data.items():
                if isinstance(value, dict) and "signal" in value:
                    signals[key] = value

        analyst_signals[analyst_name] = signals

        updated_data = {**current_data, **result_data, "analyst_signals": analyst_signals}
        return {"data": updated_data}

    _wrapper.__name__ = f"analyst_{analyst_name}"
    _wrapper.__qualname__ = f"analyst_{analyst_name}"
    return _wrapper


# ---------------------------------------------------------------------------
# Fan-out / fan-in routing
# ---------------------------------------------------------------------------


def _fan_out_to_analysts(state: AgentState) -> list[str]:
    """Return the list of analyst node names to run in parallel.

    Used as a conditional-edge mapper from the start node.
    """
    metadata = state.get("metadata", {})
    analyst_names = metadata.get("selected_analysts", list(_ANALYST_REGISTRY.keys()))
    return [f"analyst_{name}" for name in analyst_names]


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def create_workflow(
    selected_analysts: Optional[list[str]] = None,
    model_name: Optional[str] = None,
    model_provider: Optional[str] = None,
) -> StateGraph:
    """Build the LangGraph :class:`StateGraph` for the hedge fund pipeline.

    Parameters
    ----------
    selected_analysts:
        List of analyst names to include.  Defaults to all registered analysts.
    model_name:
        LLM model identifier override (e.g. ``"gpt-4.1"``).
    model_provider:
        LLM provider override (e.g. ``"openai"``).

    Returns
    -------
    StateGraph
        A **compiled** LangGraph graph ready to ``.invoke()``.
    """
    if selected_analysts is None:
        selected_analysts = list(_ANALYST_REGISTRY.keys())

    # Validate analyst names
    valid_analysts: list[str] = []
    for name in selected_analysts:
        if name in _ANALYST_REGISTRY:
            valid_analysts.append(name)
        else:
            logger.warning(
                "Unknown analyst '%s'; skipping. Available: %s",
                name,
                sorted(_ANALYST_REGISTRY.keys()),
            )

    if not valid_analysts:
        logger.warning("No valid analysts selected; using all available analysts.")
        valid_analysts = list(_ANALYST_REGISTRY.keys())

    logger.info("Building workflow with analysts: %s", valid_analysts)

    # 1. Create the state graph
    workflow = StateGraph(AgentState)

    # 2. Add the start node
    workflow.add_node("start", _start_node)

    # 3. Add analyst nodes
    analyst_node_names: list[str] = []
    for analyst_name in valid_analysts:
        try:
            analyst_fn = _resolve_analyst(analyst_name)
            node_name = f"analyst_{analyst_name}"
            wrapped = _make_analyst_node(analyst_fn, analyst_name)
            workflow.add_node(node_name, wrapped)
            analyst_node_names.append(node_name)
        except (ValueError, ImportError):
            logger.exception("Could not load analyst '%s'; skipping.", analyst_name)

    if not analyst_node_names:
        raise RuntimeError(
            "No analyst agents could be loaded. Cannot build workflow."
        )

    # 4. Add risk_manager and portfolio_manager nodes
    workflow.add_node("risk_manager", risk_manager_agent)
    workflow.add_node("portfolio_manager", portfolio_manager_agent)

    # 5. Wire edges
    # START -> start
    workflow.add_edge(START, "start")

    # start -> fan-out to all analysts in parallel
    for node_name in analyst_node_names:
        workflow.add_edge("start", node_name)

    # all analysts -> risk_manager (fan-in)
    for node_name in analyst_node_names:
        workflow.add_edge(node_name, "risk_manager")

    # risk_manager -> portfolio_manager
    workflow.add_edge("risk_manager", "portfolio_manager")

    # portfolio_manager -> END
    workflow.add_edge("portfolio_manager", END)

    # 6. Compile and return
    compiled = workflow.compile()
    logger.info("Workflow compiled successfully with %d analyst nodes.", len(analyst_node_names))
    return compiled


# ---------------------------------------------------------------------------
# High-level entry point
# ---------------------------------------------------------------------------


def run_hedge_fund(
    tickers: list[str],
    start_date: str,
    end_date: str,
    portfolio: Optional[dict[str, Any] | PortfolioState] = None,
    selected_analysts: Optional[list[str]] = None,
    model_name: str = "gpt-4.1",
    model_provider: str = "openai",
    show_reasoning: bool = False,
) -> dict[str, Any]:
    """Execute the hedge fund analysis pipeline end-to-end.

    Parameters
    ----------
    tickers:
        List of stock ticker symbols to analyse.
    start_date:
        Start of the analysis window (ISO date string).
    end_date:
        End of the analysis window (ISO date string).
    portfolio:
        Optional initial portfolio state.  If ``None`` a default portfolio
        with $100k cash is created.
    selected_analysts:
        Subset of analyst names to run.  ``None`` means all.
    model_name:
        LLM model identifier for the portfolio manager.
    model_provider:
        LLM provider name.
    show_reasoning:
        If ``True``, log detailed decision reasoning.

    Returns
    -------
    dict[str, Any]
        The ``decisions`` dict mapping ticker -> :class:`TradeDecision` dict.
    """
    # Serialise portfolio
    if isinstance(portfolio, PortfolioState):
        portfolio_data = portfolio.model_dump()
    elif isinstance(portfolio, dict):
        portfolio_data = portfolio
    else:
        portfolio_data = None  # will be initialised by start node

    # Build initial state
    initial_state: AgentState = {
        "data": {
            "tickers": tickers,
            "start_date": start_date,
            "end_date": end_date,
            "portfolio": portfolio_data,
            "analyst_signals": {},
            "risk_assessment": {},
            "decisions": {},
        },
        "messages": [],
        "metadata": {
            "model_name": model_name,
            "model_provider": model_provider,
            "show_reasoning": show_reasoning,
            "selected_analysts": selected_analysts or list(_ANALYST_REGISTRY.keys()),
        },
    }

    logger.info(
        "Running hedge fund: tickers=%s, window=%s to %s, model=%s/%s",
        tickers,
        start_date,
        end_date,
        model_provider,
        model_name,
    )

    # Create and compile the workflow
    compiled = create_workflow(
        selected_analysts=selected_analysts,
        model_name=model_name,
        model_provider=model_provider,
    )

    # Invoke the graph
    final_state = compiled.invoke(initial_state)

    # Extract decisions
    final_data = final_state.get("data", {})
    decisions = final_data.get("decisions", {})

    logger.info("Pipeline complete. %d decisions produced.", len(decisions))

    return decisions
