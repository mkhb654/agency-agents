"""Portfolio Manager Agent — LLM-powered trade decision maker.

This is the ONLY agent that produces final trade decisions.  It works in two
phases:

1. **Deterministic constraint computation** — for each ticker, compute which
   actions are allowed (buy, sell, short, cover, hold) and the maximum
   quantity for each, based on cash, risk limits, and current positions.

2. **LLM decision** — feed the compressed analyst signals, allowed actions,
   and portfolio context to the LLM and request a structured trade decision
   per ticker.  The output is then validated against the deterministic
   constraints to guarantee safety.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import date
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from hedge_fund.config import get_settings
from hedge_fund.data.api import FinancialDataClient
from hedge_fund.data.models import PortfolioState, Price, TradeDecision
from hedge_fund.graph.state import AgentState
from hedge_fund.llm.models import call_llm

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Structured output schema for the LLM response
# ---------------------------------------------------------------------------


class _TickerDecision(BaseModel):
    """Schema for a single ticker decision returned by the LLM."""

    action: Literal["buy", "sell", "short", "cover", "hold"]
    quantity: int = Field(ge=0, description="Number of shares. 0 for hold.")
    confidence: float = Field(ge=0, le=100, description="Decision confidence 0-100.")
    reasoning: str = Field(description="Concise rationale for the decision.")


class _PortfolioDecisions(BaseModel):
    """Top-level schema wrapping decisions for all tickers."""

    decisions: dict[str, _TickerDecision]


# ---------------------------------------------------------------------------
# Phase 1: Deterministic constraint computation
# ---------------------------------------------------------------------------


def _get_current_price(
    ticker: str,
    end_date: str,
    client: Optional[FinancialDataClient] = None,
) -> float:
    """Fetch the most recent closing price for *ticker*.

    Falls back to 0.0 if no data is available.
    """
    close_client = client is None
    if client is None:
        client = FinancialDataClient()
    try:
        end_dt = date.fromisoformat(end_date)
        prices = client.get_prices(ticker, start_date=end_dt, end_date=end_dt)
        if not prices:
            # Try a small lookback
            from datetime import timedelta

            lookback = end_dt - timedelta(days=7)
            prices = client.get_prices(ticker, start_date=lookback, end_date=end_dt)
        if prices:
            prices = sorted(prices, key=lambda p: p.date)
            return prices[-1].close
        return 0.0
    except Exception:
        logger.warning("Could not fetch price for %s", ticker)
        return 0.0
    finally:
        if close_client and client is not None:
            client.close()


def compute_allowed_actions(
    ticker: str,
    current_price: float,
    portfolio: PortfolioState,
    risk_limit: float,
) -> dict[str, dict[str, Any]]:
    """Compute which actions are allowed and their maximum quantities.

    Parameters
    ----------
    ticker:
        The stock ticker symbol.
    current_price:
        The current market price per share.
    portfolio:
        The current portfolio state.
    risk_limit:
        Remaining position limit from the risk manager (in USD).

    Returns
    -------
    dict[str, dict]
        Mapping of action name -> {"max_quantity": int, "max_value": float}.
        Actions with max_quantity == 0 are excluded (except "hold").
    """
    settings = get_settings()
    actions: dict[str, dict[str, Any]] = {}

    if current_price <= 0:
        # Cannot trade without a valid price
        actions["hold"] = {"max_quantity": 0, "max_value": 0.0}
        return actions

    # --- BUY ---
    cash_available = max(portfolio.cash, 0.0)
    buy_from_cash = math.floor(cash_available / current_price)
    buy_from_risk = math.floor(risk_limit / current_price) if risk_limit > 0 else 0
    buy_max = max(min(buy_from_cash, buy_from_risk), 0)
    if buy_max > 0:
        actions["buy"] = {
            "max_quantity": buy_max,
            "max_value": round(buy_max * current_price, 2),
        }

    # --- SELL (close long position) ---
    long_position = portfolio.positions.get(ticker)
    if long_position and long_position.shares > 0:
        sell_max = int(long_position.shares)
        if sell_max > 0:
            actions["sell"] = {
                "max_quantity": sell_max,
                "max_value": round(sell_max * current_price, 2),
            }

    # --- SHORT ---
    margin_requirement = settings.margin_requirement
    total_equity = portfolio.total_equity
    # Available margin = equity * (1 - margin_requirement) - margin_used
    # But simplified: margin_available = cash * (1 / margin_requirement) - current short exposure
    margin_capacity = max(
        total_equity / margin_requirement - portfolio.margin_used - portfolio.short_market_value,
        0.0,
    )
    short_from_margin = math.floor(margin_capacity / current_price) if margin_capacity > 0 else 0
    short_from_risk = math.floor(risk_limit / current_price) if risk_limit > 0 else 0
    short_max = max(min(short_from_margin, short_from_risk), 0)
    if short_max > 0:
        actions["short"] = {
            "max_quantity": short_max,
            "max_value": round(short_max * current_price, 2),
        }

    # --- COVER (close short position) ---
    short_position = portfolio.short_positions.get(ticker)
    if short_position and short_position.shares != 0:
        cover_max = int(abs(short_position.shares))
        # Need cash to cover
        cover_from_cash = math.floor(cash_available / current_price)
        cover_max = min(cover_max, cover_from_cash)
        if cover_max > 0:
            actions["cover"] = {
                "max_quantity": cover_max,
                "max_value": round(cover_max * current_price, 2),
            }

    # --- HOLD (always available) ---
    actions["hold"] = {"max_quantity": 0, "max_value": 0.0}

    return actions


# ---------------------------------------------------------------------------
# Phase 2: LLM decision
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are the Portfolio Manager of an elite AI-driven hedge fund.

ROLE:
You are the SOLE decision-maker for all trades. You receive signals from a team
of specialist analyst agents and risk limits from the risk manager.  Your job
is to synthesize these inputs into concrete trade decisions that maximize
risk-adjusted returns.

DECISION FRAMEWORK:
1. Weigh analyst signals by their confidence levels — higher confidence signals
   carry more weight.
2. Look for consensus: when multiple analysts agree, the signal is stronger.
3. Resolve conflicting signals by considering the reasoning quality and the
   current market context.
4. Respect risk limits absolutely: NEVER exceed the maximum allowed quantities.
5. Size positions proportionally to conviction — low confidence = smaller size.
6. Prefer to hold when signals are weak or conflicting.

OUTPUT RULES:
- Return a JSON object with a "decisions" key mapping ticker to decision.
- Each decision must include: action, quantity, confidence, reasoning.
- Quantity must be a whole number and MUST NOT exceed the max_quantity shown.
- For "hold" actions, set quantity to 0.
- Be concise but specific in your reasoning (2-3 sentences max).
"""


def _build_llm_prompt(
    ticker_data: dict[str, dict[str, Any]],
    portfolio_summary: dict[str, Any],
) -> str:
    """Build the user prompt for the LLM with all context.

    Parameters
    ----------
    ticker_data:
        Per-ticker dict with keys: signals, allowed_actions, risk, current_price.
    portfolio_summary:
        Condensed portfolio snapshot.

    Returns
    -------
    str
        Formatted prompt string.
    """
    sections: list[str] = []

    # Portfolio overview
    sections.append("=== PORTFOLIO STATE ===")
    sections.append(json.dumps(portfolio_summary, indent=2, default=str))

    # Per-ticker analysis
    for ticker, info in ticker_data.items():
        sections.append(f"\n=== {ticker} (Price: ${info.get('current_price', 'N/A')}) ===")

        # Analyst signals
        signals = info.get("signals", {})
        if signals:
            sections.append("Analyst Signals:")
            for agent_name, sig in signals.items():
                sections.append(
                    f"  - {agent_name}: {sig.get('signal', 'N/A')} "
                    f"(confidence: {sig.get('confidence', 0):.0f}%)"
                )
        else:
            sections.append("Analyst Signals: None available")

        # Allowed actions
        allowed = info.get("allowed_actions", {})
        sections.append("Allowed Actions:")
        for action, limits in allowed.items():
            if action == "hold":
                sections.append(f"  - HOLD: always allowed")
            else:
                sections.append(
                    f"  - {action.upper()}: max {limits['max_quantity']} shares "
                    f"(${limits['max_value']:,.2f})"
                )

        # Risk summary
        risk = info.get("risk", {})
        if risk:
            sections.append(
                f"Risk: regime={risk.get('volatility_regime', 'N/A')}, "
                f"score={risk.get('risk_score', 'N/A')}, "
                f"limit=${risk.get('remaining_position_limit', 0):,.0f}"
            )
            warnings = risk.get("warnings", [])
            if warnings:
                for w in warnings:
                    sections.append(f"  WARNING: {w}")

    sections.append(
        "\nMake your trading decisions now. Return ONLY a JSON object "
        "matching the required schema."
    )

    return "\n".join(sections)


def _validate_decision(
    ticker: str,
    decision: _TickerDecision,
    allowed_actions: dict[str, dict[str, Any]],
) -> TradeDecision:
    """Validate and clamp an LLM decision against deterministic constraints.

    If the LLM returns an action that is not allowed or a quantity that
    exceeds the maximum, the decision is clamped or downgraded to hold.

    Returns
    -------
    TradeDecision
        A safe, validated trade decision.
    """
    action = decision.action
    quantity = decision.quantity

    # Check if action is allowed
    if action not in allowed_actions:
        logger.warning(
            "LLM returned disallowed action '%s' for %s; forcing hold.",
            action,
            ticker,
        )
        return TradeDecision(
            action="hold",
            ticker=ticker,
            quantity=0,
            confidence=decision.confidence,
            reasoning=f"Original action '{action}' not allowed. {decision.reasoning}",
        )

    # Clamp quantity
    if action != "hold":
        max_qty = allowed_actions[action]["max_quantity"]
        if quantity > max_qty:
            logger.warning(
                "LLM quantity %d exceeds max %d for %s/%s; clamping.",
                quantity,
                max_qty,
                ticker,
                action,
            )
            quantity = max_qty
        if quantity <= 0:
            # Downgrade to hold
            return TradeDecision(
                action="hold",
                ticker=ticker,
                quantity=0,
                confidence=decision.confidence,
                reasoning=f"Quantity resolved to 0 for '{action}'. {decision.reasoning}",
            )

    return TradeDecision(
        action=action,
        ticker=ticker,
        quantity=quantity if action != "hold" else 0,
        confidence=decision.confidence,
        reasoning=decision.reasoning,
    )


# ---------------------------------------------------------------------------
# LangGraph node function
# ---------------------------------------------------------------------------


def portfolio_manager_agent(state: AgentState) -> dict[str, Any]:
    """LangGraph node: make final trade decisions for all tickers.

    This is the **only agent that makes trade decisions**.  It combines analyst
    signals, risk limits, and portfolio state to produce a :class:`TradeDecision`
    per ticker.

    Reads from state
    ----------------
    - ``data.tickers``           : list[str]
    - ``data.end_date``          : str
    - ``data.portfolio``         : dict (serialised PortfolioState)
    - ``data.analyst_signals``   : dict[analyst -> {ticker -> signal}]
    - ``data.risk_assessment``   : dict[ticker -> assessment_dict]

    Writes to state
    ---------------
    - ``data.decisions`` : dict[ticker -> decision_dict]
    """
    data: dict[str, Any] = state.get("data", {})
    metadata: dict[str, Any] = state.get("metadata", {})
    tickers: list[str] = data.get("tickers", [])
    end_date_str: str = data.get("end_date", str(date.today()))

    # Reconstruct portfolio
    portfolio_raw = data.get("portfolio", {})
    if isinstance(portfolio_raw, dict):
        try:
            portfolio = PortfolioState(**portfolio_raw)
        except Exception:
            logger.warning("Could not parse portfolio state; using default.")
            portfolio = PortfolioState()
    elif isinstance(portfolio_raw, PortfolioState):
        portfolio = portfolio_raw
    else:
        portfolio = PortfolioState()

    # Gather analyst signals — reshape from per-analyst to per-ticker
    raw_signals: dict[str, Any] = data.get("analyst_signals", {})
    per_ticker_signals: dict[str, dict[str, dict[str, Any]]] = {}
    for agent_name, ticker_signals in raw_signals.items():
        if not isinstance(ticker_signals, dict):
            continue
        for ticker, signal in ticker_signals.items():
            if ticker not in per_ticker_signals:
                per_ticker_signals[ticker] = {}
            per_ticker_signals[ticker][agent_name] = (
                signal if isinstance(signal, dict) else {"signal": str(signal), "confidence": 50}
            )

    # Gather risk assessments
    risk_assessment: dict[str, dict[str, Any]] = data.get("risk_assessment", {})

    # Fetch current prices
    client = FinancialDataClient()
    ticker_prices: dict[str, float] = {}
    for ticker in tickers:
        ticker_prices[ticker] = _get_current_price(ticker, end_date_str, client)
    client.close()

    logger.info(
        "Portfolio manager evaluating %d tickers | cash=$%.2f | equity=$%.2f",
        len(tickers),
        portfolio.cash,
        portfolio.total_equity,
    )

    # Phase 1: Compute allowed actions per ticker
    ticker_data: dict[str, dict[str, Any]] = {}
    all_hold_only = True

    for ticker in tickers:
        price = ticker_prices.get(ticker, 0.0)
        risk = risk_assessment.get(ticker, {})
        risk_limit = risk.get("remaining_position_limit", 0.0)

        allowed = compute_allowed_actions(
            ticker=ticker,
            current_price=price,
            portfolio=portfolio,
            risk_limit=risk_limit,
        )

        # Check if there are any non-hold actions
        non_hold = {k: v for k, v in allowed.items() if k != "hold"}
        if non_hold:
            all_hold_only = False

        ticker_data[ticker] = {
            "current_price": price,
            "signals": per_ticker_signals.get(ticker, {}),
            "allowed_actions": allowed,
            "risk": risk,
        }

    # If only "hold" is possible for every ticker, skip the LLM call
    if all_hold_only:
        logger.info("Only hold actions available for all tickers; skipping LLM call.")
        decisions: dict[str, dict[str, Any]] = {}
        for ticker in tickers:
            td = TradeDecision(
                action="hold",
                ticker=ticker,
                quantity=0,
                confidence=0.0,
                reasoning="No actionable trades available within risk limits.",
            )
            decisions[ticker] = td.model_dump()
        updated_data = {**data, "decisions": decisions}
        return {"data": updated_data}

    # Phase 2: LLM decision
    portfolio_summary = {
        "cash": round(portfolio.cash, 2),
        "total_equity": round(portfolio.total_equity, 2),
        "long_positions": {
            t: {"shares": p.shares, "avg_entry": p.avg_entry_price, "current": p.current_price}
            for t, p in portfolio.positions.items()
        },
        "short_positions": {
            t: {"shares": abs(p.shares), "avg_entry": p.avg_entry_price, "current": p.current_price}
            for t, p in portfolio.short_positions.items()
        },
        "margin_used": round(portfolio.margin_used, 2),
        "realized_gains": round(portfolio.realized_gains, 2),
    }

    prompt = _build_llm_prompt(ticker_data, portfolio_summary)

    # Get model config from metadata
    model_name = metadata.get("model_name")
    model_provider = metadata.get("model_provider")

    try:
        llm_result = call_llm(
            prompt=prompt,
            system_message=_SYSTEM_PROMPT,
            response_format=_PortfolioDecisions,
            model=model_name,
        )
    except Exception:
        logger.exception("LLM call failed in portfolio manager; defaulting to hold for all.")
        decisions = {}
        for ticker in tickers:
            td = TradeDecision(
                action="hold",
                ticker=ticker,
                quantity=0,
                confidence=0.0,
                reasoning="LLM call failed; holding as safety measure.",
            )
            decisions[ticker] = td.model_dump()
        updated_data = {**data, "decisions": decisions}
        return {"data": updated_data}

    # Parse and validate LLM decisions
    decisions = {}

    if isinstance(llm_result, dict):
        raw_decisions = llm_result.get("decisions", {})
    else:
        # Attempt to parse string as JSON
        try:
            parsed = json.loads(str(llm_result))
            raw_decisions = parsed.get("decisions", parsed)
        except (json.JSONDecodeError, TypeError):
            logger.error("Could not parse LLM response; defaulting to hold.")
            raw_decisions = {}

    for ticker in tickers:
        allowed = ticker_data[ticker]["allowed_actions"]
        raw = raw_decisions.get(ticker)

        if raw is None:
            # LLM didn't produce a decision for this ticker
            logger.warning("No LLM decision for %s; defaulting to hold.", ticker)
            td = TradeDecision(
                action="hold",
                ticker=ticker,
                quantity=0,
                confidence=0.0,
                reasoning="No decision produced by LLM.",
            )
            decisions[ticker] = td.model_dump()
            continue

        try:
            if isinstance(raw, dict):
                ticker_decision = _TickerDecision(**raw)
            else:
                ticker_decision = _TickerDecision.model_validate(raw)
        except Exception:
            logger.exception("Failed to parse LLM decision for %s; defaulting to hold.", ticker)
            td = TradeDecision(
                action="hold",
                ticker=ticker,
                quantity=0,
                confidence=0.0,
                reasoning="Failed to parse LLM decision.",
            )
            decisions[ticker] = td.model_dump()
            continue

        # Validate against constraints
        validated = _validate_decision(ticker, ticker_decision, allowed)
        decisions[ticker] = validated.model_dump()

        logger.info(
            "Decision [%s]: %s %d shares @ $%.2f (confidence: %.0f%%) — %s",
            ticker,
            validated.action.upper(),
            validated.quantity,
            ticker_prices.get(ticker, 0.0),
            validated.confidence,
            validated.reasoning[:80],
        )

    # Show reasoning if requested
    show_reasoning = metadata.get("show_reasoning", False)
    if show_reasoning:
        for ticker, dec in decisions.items():
            logger.info(
                "REASONING [%s] %s: %s",
                ticker,
                dec.get("action", "hold").upper(),
                dec.get("reasoning", ""),
            )

    updated_data = {**data, "decisions": decisions}
    return {"data": updated_data}
