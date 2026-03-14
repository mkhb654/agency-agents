"""LangGraph agent state definition with merge-dict reducer.

The :class:`AgentState` TypedDict is the single state object that flows
through every node in the hedge fund analysis graph.  The ``data`` and
``metadata`` channels use :func:`merge_dicts` as their reducer so that
each agent node can emit a *partial* update that is deep-merged into the
accumulator without clobbering sibling keys.

Helper functions (:func:`get_analyst_signals`, :func:`get_risk_assessment`,
:func:`get_portfolio`) provide type-safe access to commonly-read sub-trees
of the state.
"""

from __future__ import annotations

import copy
import operator
from typing import Annotated, Any, Optional, Sequence, TypedDict

from hedge_fund.data.models import (
    AnalystSignal,
    PortfolioState,
    RiskAssessment,
)


# ---------------------------------------------------------------------------
# Reducer: deep-merge two dicts
# ---------------------------------------------------------------------------


def merge_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *right* into a copy of *left*.

    - For keys present in both:
      - If both values are dicts, merge recursively.
      - If both values are lists, concatenate them.
      - Otherwise the value from *right* wins.
    - Keys only in *left* or only in *right* are preserved.

    This is used as the LangGraph *reducer* for the ``data`` and ``metadata``
    channels so that multiple agent nodes can independently contribute
    partial state updates.

    Args:
        left: Existing accumulated state.
        right: New partial update from an agent node.

    Returns:
        A new merged dictionary (neither input is mutated).
    """
    merged = copy.deepcopy(left)
    for key, right_val in right.items():
        if key in merged:
            left_val = merged[key]
            if isinstance(left_val, dict) and isinstance(right_val, dict):
                merged[key] = merge_dicts(left_val, right_val)
            elif isinstance(left_val, list) and isinstance(right_val, list):
                merged[key] = left_val + right_val
            else:
                merged[key] = copy.deepcopy(right_val)
        else:
            merged[key] = copy.deepcopy(right_val)
    return merged


# ---------------------------------------------------------------------------
# State definition
# ---------------------------------------------------------------------------


class AgentState(TypedDict, total=False):
    """Shared state flowing through the LangGraph agent pipeline.

    Channels
    --------
    data : dict
        The main data payload.  Expected top-level keys include:

        - ``tickers`` (``list[str]``): ticker symbols under analysis.
        - ``analyst_signals`` (``dict[str, dict[str, AnalystSignal]]``):
          mapping of ``agent_name -> {ticker: signal}``.
        - ``risk_assessment`` (``dict[str, RiskAssessment]``):
          mapping of ``ticker -> assessment``.
        - ``portfolio`` (``PortfolioState``): current portfolio snapshot.
        - ``start_date`` / ``end_date`` (``str``): analysis date range.

        Uses :func:`merge_dicts` as its reducer so that each node can
        return only the keys it cares about.

    messages : list
        LangGraph message list (used by chat-style nodes).  Uses the
        default ``operator.add`` (append) reducer.

    metadata : dict
        Run-level metadata (run_id, user config overrides, etc.).
        Also uses :func:`merge_dicts`.
    """

    data: Annotated[dict[str, Any], merge_dicts]
    messages: Annotated[Sequence[Any], operator.add]
    metadata: Annotated[dict[str, Any], merge_dicts]


# ---------------------------------------------------------------------------
# Convenience accessors
# ---------------------------------------------------------------------------


def get_analyst_signals(
    state: AgentState,
) -> dict[str, dict[str, AnalystSignal]]:
    """Extract the full analyst signals map from state.

    Returns a dict of ``{agent_name: {ticker: AnalystSignal}}``.
    If the key is missing an empty dict is returned.

    Args:
        state: The current agent state.

    Returns:
        Nested mapping of analyst signals.
    """
    data: dict[str, Any] = state.get("data", {})
    raw_signals: dict[str, Any] = data.get("analyst_signals", {})

    result: dict[str, dict[str, AnalystSignal]] = {}
    for agent_name, ticker_signals in raw_signals.items():
        if not isinstance(ticker_signals, dict):
            continue
        agent_entry: dict[str, AnalystSignal] = {}
        for ticker, signal in ticker_signals.items():
            if isinstance(signal, AnalystSignal):
                agent_entry[ticker] = signal
            elif isinstance(signal, dict):
                try:
                    agent_entry[ticker] = AnalystSignal.model_validate(signal)
                except Exception:
                    continue
        result[agent_name] = agent_entry
    return result


def get_risk_assessment(
    state: AgentState,
    ticker: Optional[str] = None,
) -> Optional[RiskAssessment]:
    """Extract a :class:`RiskAssessment` from state.

    When *ticker* is provided, looks up ``data.risk_assessment[ticker]``.
    When ``None``, returns the first available assessment.

    Args:
        state: The current agent state.
        ticker: Optional ticker to look up.

    Returns:
        A :class:`RiskAssessment` instance, or ``None``.
    """
    data: dict[str, Any] = state.get("data", {})
    assessments: Any = data.get("risk_assessment", {})

    if isinstance(assessments, RiskAssessment):
        return assessments
    if isinstance(assessments, dict):
        if ticker and ticker in assessments:
            val = assessments[ticker]
        else:
            # Return the first entry.
            val = next(iter(assessments.values()), None)

        if val is None:
            return None
        if isinstance(val, RiskAssessment):
            return val
        if isinstance(val, dict):
            try:
                return RiskAssessment.model_validate(val)
            except Exception:
                return None
    return None


def get_portfolio(state: AgentState) -> PortfolioState:
    """Extract the :class:`PortfolioState` from state, creating a default if absent.

    Args:
        state: The current agent state.

    Returns:
        The portfolio state object.
    """
    data: dict[str, Any] = state.get("data", {})
    portfolio: Any = data.get("portfolio")

    if isinstance(portfolio, PortfolioState):
        return portfolio
    if isinstance(portfolio, dict):
        try:
            return PortfolioState.model_validate(portfolio)
        except Exception:
            pass
    # Return a fresh default portfolio.
    return PortfolioState()
