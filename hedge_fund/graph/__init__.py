"""LangGraph-based agent orchestration.

Public API:
    - :class:`AgentState` -- the shared state TypedDict flowing through the graph.
    - :func:`merge_dicts` -- reducer that deep-merges two dictionaries.
    - :func:`get_analyst_signals` -- extract analyst signals from state.
    - :func:`get_risk_assessment` -- extract the risk assessment from state.
    - :func:`get_portfolio` -- extract the portfolio snapshot from state.
"""

from hedge_fund.graph.state import (
    AgentState,
    get_analyst_signals,
    get_portfolio,
    get_risk_assessment,
    merge_dicts,
)

__all__ = [
    "AgentState",
    "get_analyst_signals",
    "get_portfolio",
    "get_risk_assessment",
    "merge_dicts",
]
