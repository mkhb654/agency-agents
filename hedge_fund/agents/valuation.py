"""Valuation Analyst Agent (RULE-BASED, no LLM).

Computes intrinsic value using four independent models, then compares the
weighted-average fair value to current market capitalisation:

  1. **DCF** (35%) -- project FCF 5 years using historical CAGR, discount at WACC
  2. **Owner Earnings** (35%) -- Buffett formula capitalised at required return
  3. **EV/EBITDA Relative** (20%) -- compare to sector median (default 12x)
  4. **Residual Income** (10%) -- book value + PV of future residual income

Margin of safety = (intrinsic - market) / intrinsic
  - margin > 20%  -> bullish
  - margin < -20% -> bearish
  - else          -> neutral
"""

from __future__ import annotations

import logging
from typing import Any

from rich.console import Console
from rich.table import Table

from hedge_fund.data.api import FinancialDataClient
from hedge_fund.data.models import FinancialMetrics, LineItem
from hedge_fund.graph.state import AgentState

logger = logging.getLogger(__name__)
console = Console()

# ---------------------------------------------------------------------------
# Constants / defaults
# ---------------------------------------------------------------------------

RISK_FREE_RATE = 0.043
EQUITY_RISK_PREMIUM = 0.055
DEFAULT_BETA = 1.0
DEFAULT_SECTOR_EV_EBITDA = 12.0
PROJECTION_YEARS = 5
TERMINAL_GROWTH = 0.025

MODEL_WEIGHTS = {
    "dcf": 0.35,
    "owner_earnings": 0.35,
    "ev_ebitda": 0.20,
    "residual_income": 0.10,
}

BULLISH_MARGIN = 0.20
BEARISH_MARGIN = -0.20

# Line items we need for valuation
_VALUATION_LINE_ITEMS = [
    "revenue",
    "net_income",
    "depreciation_and_amortization",
    "capital_expenditure",
    "free_cash_flow",
    "operating_cash_flow",
    "total_equity",
    "total_debt",
    "total_assets",
    "total_liabilities",
    "cash_and_equivalents",
    "interest_expense",
    "ebitda",
    "working_capital",
    "current_assets",
    "current_liabilities",
    "shares_outstanding",
    "market_cap",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_get(items: list[LineItem], attr: str) -> float | None:
    """Return the first non-None value of *attr* from line items."""
    for item in items:
        val = getattr(item, attr, None)
        if val is not None:
            return float(val)
    return None


def _safe_metric(items: list[FinancialMetrics], attr: str) -> float | None:
    """Return the first non-None value of *attr* from metrics."""
    for item in items:
        val = getattr(item, attr, None)
        if val is not None:
            return float(val)
    return None


def _cagr(first: float, last: float, periods: int) -> float:
    """Compound annual growth rate.  Returns 0 if inputs are invalid."""
    if first <= 0 or last <= 0 or periods <= 0:
        return 0.0
    return (last / first) ** (1.0 / periods) - 1.0


def _estimate_wacc(
    market_cap: float,
    total_debt: float,
    interest_expense: float | None,
    beta: float = DEFAULT_BETA,
) -> float:
    """Estimate WACC using CAPM for equity cost."""
    cost_of_equity = RISK_FREE_RATE + beta * EQUITY_RISK_PREMIUM

    if total_debt > 0 and interest_expense is not None and interest_expense > 0:
        cost_of_debt = (interest_expense / total_debt) * (1 - 0.25)
    else:
        cost_of_debt = RISK_FREE_RATE + 0.02

    total_capital = market_cap + total_debt
    if total_capital <= 0:
        return cost_of_equity

    equity_weight = market_cap / total_capital
    debt_weight = total_debt / total_capital
    wacc = equity_weight * cost_of_equity + debt_weight * cost_of_debt
    return max(0.05, min(0.20, wacc))


# ---------------------------------------------------------------------------
# Valuation models
# ---------------------------------------------------------------------------


def _dcf_model(
    line_items: list[LineItem],
    market_cap: float,
    wacc: float,
) -> tuple[float | None, str]:
    """Discounted Cash Flow model."""
    fcf_values = [
        li.free_cash_flow
        for li in reversed(line_items)
        if li.free_cash_flow is not None
    ]

    if not fcf_values or len(fcf_values) < 2:
        return None, "DCF: Insufficient FCF history."

    latest_fcf = fcf_values[-1]
    if latest_fcf <= 0:
        return None, f"DCF: Latest FCF is negative (${latest_fcf:,.0f}); model not applicable."

    annual_periods = max(1, (len(fcf_values) - 1) / 4.0)
    growth_rate = _cagr(fcf_values[0], fcf_values[-1], annual_periods) if fcf_values[0] > 0 else 0.05
    growth_rate = max(-0.05, min(0.25, growth_rate))

    projected_fcfs: list[float] = []
    fcf = latest_fcf
    for year in range(1, PROJECTION_YEARS + 1):
        fcf = fcf * (1 + growth_rate)
        projected_fcfs.append(fcf)

    terminal_value = projected_fcfs[-1] * (1 + TERMINAL_GROWTH) / max(wacc - TERMINAL_GROWTH, 0.01)
    pv_fcfs = sum(cf / (1 + wacc) ** yr for yr, cf in enumerate(projected_fcfs, 1))
    pv_terminal = terminal_value / (1 + wacc) ** PROJECTION_YEARS
    intrinsic_value = pv_fcfs + pv_terminal

    reason = (
        f"DCF: latest FCF=${latest_fcf:,.0f}, growth={growth_rate:.1%}, WACC={wacc:.1%}, "
        f"PV(FCFs)=${pv_fcfs:,.0f}, PV(terminal)=${pv_terminal:,.0f}, "
        f"intrinsic=${intrinsic_value:,.0f} vs market=${market_cap:,.0f}."
    )
    return intrinsic_value, reason


def _owner_earnings_model(
    line_items: list[LineItem],
    market_cap: float,
    cost_of_equity: float,
) -> tuple[float | None, str]:
    """Buffett's Owner Earnings model."""
    net_income = _safe_get(line_items, "net_income")
    depreciation = _safe_get(line_items, "depreciation_and_amortization")
    capex = _safe_get(line_items, "capital_expenditure")

    if net_income is None:
        return None, "Owner Earnings: Net income not available."

    dep = depreciation or 0
    cx = abs(capex) if capex else 0

    wc_values = [li.working_capital for li in line_items if li.working_capital is not None]
    wc_change = (wc_values[0] - wc_values[1]) if len(wc_values) >= 2 else 0

    owner_earnings_quarterly = net_income + dep - cx - wc_change
    owner_earnings_annual = owner_earnings_quarterly * 4

    if owner_earnings_annual <= 0:
        return None, (
            f"Owner Earnings: negative annual OE (${owner_earnings_annual:,.0f}); "
            f"NI=${net_income:,.0f}, D&A=${dep:,.0f}, CapEx=${cx:,.0f}, dWC=${wc_change:,.0f}."
        )

    effective_rate = max(cost_of_equity, 0.06)
    intrinsic_value = owner_earnings_annual / effective_rate

    reason = (
        f"Owner Earnings: NI=${net_income:,.0f}, D&A=${dep:,.0f}, CapEx=${cx:,.0f}, "
        f"dWC=${wc_change:,.0f}, quarterly OE=${owner_earnings_quarterly:,.0f}, "
        f"annual OE=${owner_earnings_annual:,.0f}, cap rate={effective_rate:.1%}, "
        f"intrinsic=${intrinsic_value:,.0f} vs market=${market_cap:,.0f}."
    )
    return intrinsic_value, reason


def _ev_ebitda_relative_model(
    line_items: list[LineItem],
    metrics: list[FinancialMetrics],
    market_cap: float,
) -> tuple[float | None, str]:
    """EV/EBITDA relative valuation."""
    ebitda = _safe_get(line_items, "ebitda")
    total_debt = _safe_get(line_items, "total_debt") or 0
    cash = _safe_get(line_items, "cash_and_equivalents") or 0

    if ebitda is None or ebitda <= 0:
        return None, "EV/EBITDA: EBITDA not available or non-positive."

    annual_ebitda = ebitda * 4
    current_ev = market_cap + total_debt - cash
    fair_ev = annual_ebitda * DEFAULT_SECTOR_EV_EBITDA
    intrinsic_value = fair_ev - total_debt + cash
    actual_multiple = current_ev / annual_ebitda if annual_ebitda > 0 else 0
    premium_discount = (actual_multiple / DEFAULT_SECTOR_EV_EBITDA - 1) if DEFAULT_SECTOR_EV_EBITDA > 0 else 0

    reason = (
        f"EV/EBITDA: annual EBITDA=${annual_ebitda:,.0f}, current={actual_multiple:.1f}x "
        f"vs sector={DEFAULT_SECTOR_EV_EBITDA:.1f}x ({premium_discount:+.1%}), "
        f"fair EV=${fair_ev:,.0f}, intrinsic=${intrinsic_value:,.0f} vs market=${market_cap:,.0f}."
    )
    return intrinsic_value, reason


def _residual_income_model(
    line_items: list[LineItem],
    metrics: list[FinancialMetrics],
    market_cap: float,
    cost_of_equity: float,
) -> tuple[float | None, str]:
    """Residual Income model: book_value + PV(future residual income)."""
    total_equity = _safe_get(line_items, "total_equity")
    roe = _safe_metric(metrics, "return_on_equity")

    if total_equity is None or total_equity <= 0:
        return None, "Residual Income: Book value (total equity) not available."

    if roe is None:
        net_income = _safe_get(line_items, "net_income")
        if net_income is not None and total_equity > 0:
            roe = (net_income * 4) / total_equity
        else:
            return None, "Residual Income: Cannot determine ROE."

    residual_income_annual = (roe - cost_of_equity) * total_equity

    pv_residual = 0.0
    decay_rate = 0.90
    ri = residual_income_annual
    for year in range(1, 11):
        ri *= decay_rate
        pv_residual += ri / (1 + cost_of_equity) ** year

    intrinsic_value = total_equity + pv_residual

    reason = (
        f"Residual Income: book_value=${total_equity:,.0f}, ROE={roe:.1%}, "
        f"Ke={cost_of_equity:.1%}, annual RI=${residual_income_annual:,.0f}, "
        f"PV(RI)=${pv_residual:,.0f}, intrinsic=${intrinsic_value:,.0f} "
        f"vs market=${market_cap:,.0f}."
    )
    return intrinsic_value, reason


# ---------------------------------------------------------------------------
# Per-ticker analysis
# ---------------------------------------------------------------------------


def _analyse_ticker(ticker: str, api: FinancialDataClient) -> dict[str, Any]:
    """Run all four valuation models and produce a combined signal."""
    line_items: list[LineItem] = api.search_line_items_sync(
        ticker, line_items=_VALUATION_LINE_ITEMS, period_type="quarterly", limit=8,
    )
    metrics: list[FinancialMetrics] = api.get_financial_metrics_sync(
        ticker, period_type="quarterly", limit=4,
    )

    market_cap = _safe_metric(metrics, "market_cap") or _safe_get(line_items, "market_cap")

    if not line_items or market_cap is None or market_cap <= 0:
        logger.warning("Insufficient data for valuation of %s", ticker)
        return {
            "signal": "neutral",
            "confidence": 0.15,
            "reasoning": f"Insufficient financial data for valuation of {ticker}.",
            "agent_scores": {},
        }

    total_debt = _safe_get(line_items, "total_debt") or 0
    interest_expense = _safe_get(line_items, "interest_expense")
    wacc = _estimate_wacc(market_cap, total_debt, interest_expense)
    cost_of_equity = RISK_FREE_RATE + DEFAULT_BETA * EQUITY_RISK_PREMIUM

    # Run models
    dcf_value, dcf_reason = _dcf_model(line_items, market_cap, wacc)
    oe_value, oe_reason = _owner_earnings_model(line_items, market_cap, cost_of_equity)
    ev_value, ev_reason = _ev_ebitda_relative_model(line_items, metrics, market_cap)
    ri_value, ri_reason = _residual_income_model(line_items, metrics, market_cap, cost_of_equity)

    model_results: dict[str, tuple[float | None, float, str]] = {
        "dcf": (dcf_value, MODEL_WEIGHTS["dcf"], dcf_reason),
        "owner_earnings": (oe_value, MODEL_WEIGHTS["owner_earnings"], oe_reason),
        "ev_ebitda": (ev_value, MODEL_WEIGHTS["ev_ebitda"], ev_reason),
        "residual_income": (ri_value, MODEL_WEIGHTS["residual_income"], ri_reason),
    }

    weighted_value = 0.0
    total_weight = 0.0
    model_values: dict[str, float | None] = {}

    for model_name, (value, weight, _reason) in model_results.items():
        model_values[model_name] = value
        if value is not None and value > 0:
            weighted_value += value * weight
            total_weight += weight

    if total_weight > 0:
        intrinsic_value = weighted_value / total_weight
    else:
        return {
            "signal": "neutral",
            "confidence": 0.15,
            "reasoning": (
                f"All valuation models failed for {ticker}.\n"
                + "\n".join(r for _, _, r in model_results.values())
            ),
            "agent_scores": {"models_failed": True},
        }

    margin_of_safety = (intrinsic_value - market_cap) / intrinsic_value if intrinsic_value != 0 else 0

    if margin_of_safety > BULLISH_MARGIN:
        signal = "bullish"
    elif margin_of_safety < BEARISH_MARGIN:
        signal = "bearish"
    else:
        signal = "neutral"

    # Confidence
    models_available = sum(1 for v in model_values.values() if v is not None and v > 0)
    valid_values = [v for v in model_values.values() if v is not None and v > 0]
    if len(valid_values) >= 2:
        value_std = (sum((v - intrinsic_value) ** 2 for v in valid_values) / len(valid_values)) ** 0.5
        dispersion = value_std / market_cap if market_cap > 0 else 1
        agreement_score = max(0, 1.0 - dispersion)
    else:
        agreement_score = 0.3

    confidence = min(
        1.0,
        0.2 + 0.2 * (models_available / 4) + 0.3 * agreement_score + 0.2 * min(1.0, abs(margin_of_safety)),
    )
    confidence = round(max(0.1, confidence), 2)

    # Build reasoning
    reasoning_lines = [
        f"Valuation analysis for {ticker} (market cap: ${market_cap:,.0f}):",
        f"WACC estimate: {wacc:.1%}, Cost of equity: {cost_of_equity:.1%}",
        "",
    ]
    for model_name, (value, weight, reason) in model_results.items():
        status = f"${value:,.0f}" if value is not None and value > 0 else "N/A"
        reasoning_lines.append(f"[{model_name.upper()} - weight {weight:.0%}] Fair value: {status}")
        reasoning_lines.append(f"  {reason}")
        reasoning_lines.append("")
    reasoning_lines.extend([
        f"Weighted intrinsic value: ${intrinsic_value:,.0f}",
        f"Market cap: ${market_cap:,.0f}",
        f"Margin of safety: {margin_of_safety:+.1%}",
        f"Signal: {signal.upper()}",
    ])

    # Rich table display
    table = Table(title=f"Valuation: {ticker}", show_header=True)
    table.add_column("Model", style="cyan")
    table.add_column("Fair Value", justify="right")
    table.add_column("Weight", justify="right")
    table.add_column("vs Market", justify="right")

    for model_name, (value, weight, _) in model_results.items():
        if value is not None and value > 0:
            pct = (value - market_cap) / market_cap
            table.add_row(
                model_name.replace("_", " ").title(),
                f"${value:,.0f}",
                f"{weight:.0%}",
                f"{pct:+.1%}",
            )
        else:
            table.add_row(model_name.replace("_", " ").title(), "N/A", f"{weight:.0%}", "-")

    table.add_row(
        "[bold]Weighted Avg[/bold]",
        f"[bold]${intrinsic_value:,.0f}[/bold]",
        "100%",
        f"[bold]{margin_of_safety:+.1%}[/bold]",
    )
    console.print(table)
    console.print(f"  Market cap: ${market_cap:,.0f} | Margin of safety: {margin_of_safety:+.1%}")

    return {
        "signal": signal,
        "confidence": confidence,
        "reasoning": "\n".join(reasoning_lines),
        "agent_scores": {
            "intrinsic_value": round(intrinsic_value, 2),
            "market_cap": market_cap,
            "margin_of_safety": round(margin_of_safety, 4),
            "wacc": round(wacc, 4),
            "model_values": {k: round(v, 2) if v else None for k, v in model_values.items()},
            "models_available": models_available,
        },
    }


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------


def valuation_agent(state: AgentState) -> dict[str, Any]:
    """Valuation Analyst -- multi-model intrinsic value estimation.

    Runs DCF, Owner Earnings, EV/EBITDA Relative, and Residual Income
    models.  Compares weighted-average intrinsic value to market cap and
    produces a signal based on margin of safety.

    Parameters
    ----------
    state : AgentState
        Must contain ``state["data"]["tickers"]``.

    Returns
    -------
    dict
        Partial state update: ``{"data": {"analyst_signals": {"valuation": ...}}}``.
    """
    data: dict[str, Any] = state["data"]
    tickers: list[str] = data["tickers"]

    console.rule("[bold magenta]Valuation Analyst[/bold magenta]")
    logger.info("Valuation agent running for tickers: %s", tickers)

    api = FinancialDataClient()
    signals: dict[str, Any] = {}

    for ticker in tickers:
        console.print(f"\n[bold]Analysing {ticker}...[/bold]")
        try:
            signals[ticker] = _analyse_ticker(ticker, api)
        except Exception:
            logger.exception("Error in valuation agent for %s", ticker)
            signals[ticker] = {
                "signal": "neutral",
                "confidence": 0.0,
                "reasoning": f"Analysis failed for {ticker}; defaulting to neutral.",
                "agent_scores": {},
            }

    return {"data": {"analyst_signals": {"valuation": signals}}}
