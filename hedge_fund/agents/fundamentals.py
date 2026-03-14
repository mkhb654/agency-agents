"""Fundamentals Analyst Agent (RULE-BASED, no LLM).

Fetches the last 4 quarters of financial metrics and computes a composite
score across four categories:

  1. **Profitability** (0-10 pts)
  2. **Growth** (0-10 pts)
  3. **Financial Health** (0-10 pts)
  4. **Valuation** (0-10 pts)

Total score range is 0-40.  Signal thresholds:
  - > 28  -> bullish
  - < 16  -> bearish
  - else  -> neutral

Confidence is derived from data coverage and score extremity.
"""

from __future__ import annotations

import logging
from typing import Any

from rich.console import Console
from rich.table import Table

from hedge_fund.data.api import FinancialDataClient
from hedge_fund.data.models import AnalystSignal, FinancialMetrics, SignalDirection
from hedge_fund.graph.state import AgentState

logger = logging.getLogger(__name__)
console = Console()

# ---------------------------------------------------------------------------
# Scoring thresholds
# ---------------------------------------------------------------------------

BULLISH_THRESHOLD = 28
BEARISH_THRESHOLD = 16
MAX_TOTAL_SCORE = 40


# ---------------------------------------------------------------------------
# Category scorers
# ---------------------------------------------------------------------------


def _score_profitability(metrics: list[FinancialMetrics]) -> tuple[float, int, list[str]]:
    """Score profitability metrics.

    Returns (normalised_score_out_of_10, raw_max_possible, reasoning_lines).
    """
    scores: list[float] = []
    max_points = 0
    reasons: list[str] = []

    roe_vals = [m.return_on_equity for m in metrics if m.return_on_equity is not None]
    net_margin_vals = [m.net_profit_margin for m in metrics if m.net_profit_margin is not None]
    gross_margin_vals = [m.gross_margin for m in metrics if m.gross_margin is not None]
    op_margin_vals = [m.operating_margin for m in metrics if m.operating_margin is not None]
    fcf_vals = [m.free_cash_flow for m in metrics if m.free_cash_flow is not None]

    # ROE > 15% -> 3 pts
    if roe_vals:
        avg_roe = sum(roe_vals) / len(roe_vals)
        max_points += 3
        if avg_roe > 0.15:
            scores.append(3.0)
            reasons.append(f"ROE {avg_roe:.1%} > 15% (+3)")
        elif avg_roe > 0.10:
            scores.append(1.5)
            reasons.append(f"ROE {avg_roe:.1%} moderate (+1.5)")
        else:
            scores.append(0.0)
            reasons.append(f"ROE {avg_roe:.1%} < 10% (+0)")

    # Net margin > 10% -> 2 pts
    if net_margin_vals:
        avg_nm = sum(net_margin_vals) / len(net_margin_vals)
        max_points += 2
        if avg_nm > 0.10:
            scores.append(2.0)
            reasons.append(f"Net margin {avg_nm:.1%} > 10% (+2)")
        elif avg_nm > 0.05:
            scores.append(1.0)
            reasons.append(f"Net margin {avg_nm:.1%} moderate (+1)")
        else:
            scores.append(0.0)
            reasons.append(f"Net margin {avg_nm:.1%} low (+0)")

    # Gross margin > 40% -> 2 pts
    if gross_margin_vals:
        avg_gm = sum(gross_margin_vals) / len(gross_margin_vals)
        max_points += 2
        if avg_gm > 0.40:
            scores.append(2.0)
            reasons.append(f"Gross margin {avg_gm:.1%} > 40% (+2)")
        elif avg_gm > 0.25:
            scores.append(1.0)
            reasons.append(f"Gross margin {avg_gm:.1%} moderate (+1)")
        else:
            scores.append(0.0)
            reasons.append(f"Gross margin {avg_gm:.1%} low (+0)")

    # Operating margin > 15% -> 2 pts
    if op_margin_vals:
        avg_om = sum(op_margin_vals) / len(op_margin_vals)
        max_points += 2
        if avg_om > 0.15:
            scores.append(2.0)
            reasons.append(f"Operating margin {avg_om:.1%} > 15% (+2)")
        elif avg_om > 0.08:
            scores.append(1.0)
            reasons.append(f"Operating margin {avg_om:.1%} moderate (+1)")
        else:
            scores.append(0.0)
            reasons.append(f"Operating margin {avg_om:.1%} low (+0)")

    # Positive FCF -> 1 pt
    if fcf_vals:
        avg_fcf = sum(fcf_vals) / len(fcf_vals)
        max_points += 1
        if avg_fcf > 0:
            scores.append(1.0)
            reasons.append(f"FCF positive (avg ${avg_fcf:,.0f}) (+1)")
        else:
            scores.append(0.0)
            reasons.append(f"FCF negative (avg ${avg_fcf:,.0f}) (+0)")

    total = sum(scores)
    normalised = (total / max_points) * 10.0 if max_points > 0 else 5.0
    return normalised, max_points, reasons


def _score_growth(metrics: list[FinancialMetrics]) -> tuple[float, int, list[str]]:
    """Score growth metrics."""
    scores: list[float] = []
    max_points = 0
    reasons: list[str] = []

    rev_growth = [m.revenue_growth for m in metrics if m.revenue_growth is not None]
    earn_growth = [m.earnings_growth for m in metrics if m.earnings_growth is not None]
    fcf_growth = [m.fcf_growth for m in metrics if m.fcf_growth is not None]
    op_margins = [m.operating_margin for m in metrics if m.operating_margin is not None]

    # Revenue growth > 10% -> 3 pts
    if rev_growth:
        avg_rg = sum(rev_growth) / len(rev_growth)
        max_points += 3
        if avg_rg > 0.10:
            scores.append(3.0)
            reasons.append(f"Revenue growth {avg_rg:.1%} > 10% (+3)")
        elif avg_rg > 0.05:
            scores.append(1.5)
            reasons.append(f"Revenue growth {avg_rg:.1%} moderate (+1.5)")
        elif avg_rg > 0:
            scores.append(0.5)
            reasons.append(f"Revenue growth {avg_rg:.1%} low positive (+0.5)")
        else:
            scores.append(0.0)
            reasons.append(f"Revenue growth {avg_rg:.1%} negative (+0)")

    # Earnings growth > 10% -> 3 pts
    if earn_growth:
        avg_eg = sum(earn_growth) / len(earn_growth)
        max_points += 3
        if avg_eg > 0.10:
            scores.append(3.0)
            reasons.append(f"Earnings growth {avg_eg:.1%} > 10% (+3)")
        elif avg_eg > 0.05:
            scores.append(1.5)
            reasons.append(f"Earnings growth {avg_eg:.1%} moderate (+1.5)")
        elif avg_eg > 0:
            scores.append(0.5)
            reasons.append(f"Earnings growth {avg_eg:.1%} low positive (+0.5)")
        else:
            scores.append(0.0)
            reasons.append(f"Earnings growth {avg_eg:.1%} negative (+0)")

    # Positive FCF growth -> 2 pts
    if fcf_growth:
        avg_fg = sum(fcf_growth) / len(fcf_growth)
        max_points += 2
        if avg_fg > 0:
            scores.append(2.0)
            reasons.append(f"FCF growth {avg_fg:.1%} positive (+2)")
        else:
            scores.append(0.0)
            reasons.append(f"FCF growth {avg_fg:.1%} negative (+0)")

    # Improving margins -> 2 pts
    if len(op_margins) >= 2:
        max_points += 2
        # metrics are typically ordered most-recent first
        latest = op_margins[0]
        earliest = op_margins[-1]
        if earliest != 0 and latest > earliest:
            scores.append(2.0)
            reasons.append(f"Operating margin improving {earliest:.1%} -> {latest:.1%} (+2)")
        elif earliest != 0 and latest == earliest:
            scores.append(1.0)
            reasons.append(f"Operating margin stable at {latest:.1%} (+1)")
        else:
            scores.append(0.0)
            reasons.append(f"Operating margin declining {earliest:.1%} -> {latest:.1%} (+0)")

    total = sum(scores)
    normalised = (total / max_points) * 10.0 if max_points > 0 else 5.0
    return normalised, max_points, reasons


def _score_financial_health(metrics: list[FinancialMetrics]) -> tuple[float, int, list[str]]:
    """Score financial health / solvency metrics."""
    scores: list[float] = []
    max_points = 0
    reasons: list[str] = []

    cr_vals = [m.current_ratio for m in metrics if m.current_ratio is not None]
    de_vals = [m.debt_to_equity for m in metrics if m.debt_to_equity is not None]
    qr_vals = [m.quick_ratio for m in metrics if m.quick_ratio is not None]
    ic_vals = [m.interest_coverage for m in metrics if m.interest_coverage is not None]

    # Current ratio > 1.5 -> 2 pts
    if cr_vals:
        avg_cr = sum(cr_vals) / len(cr_vals)
        max_points += 2
        if avg_cr > 1.5:
            scores.append(2.0)
            reasons.append(f"Current ratio {avg_cr:.2f} > 1.5 (+2)")
        elif avg_cr > 1.0:
            scores.append(1.0)
            reasons.append(f"Current ratio {avg_cr:.2f} adequate (+1)")
        else:
            scores.append(0.0)
            reasons.append(f"Current ratio {avg_cr:.2f} < 1.0 (+0)")

    # Debt/equity < 0.5 -> 3 pts
    if de_vals:
        avg_de = sum(de_vals) / len(de_vals)
        max_points += 3
        if avg_de < 0.5:
            scores.append(3.0)
            reasons.append(f"D/E ratio {avg_de:.2f} < 0.5 (+3)")
        elif avg_de < 1.0:
            scores.append(1.5)
            reasons.append(f"D/E ratio {avg_de:.2f} moderate (+1.5)")
        else:
            scores.append(0.0)
            reasons.append(f"D/E ratio {avg_de:.2f} high (+0)")

    # Quick ratio > 1 -> 2 pts
    if qr_vals:
        avg_qr = sum(qr_vals) / len(qr_vals)
        max_points += 2
        if avg_qr > 1.0:
            scores.append(2.0)
            reasons.append(f"Quick ratio {avg_qr:.2f} > 1.0 (+2)")
        elif avg_qr > 0.7:
            scores.append(1.0)
            reasons.append(f"Quick ratio {avg_qr:.2f} adequate (+1)")
        else:
            scores.append(0.0)
            reasons.append(f"Quick ratio {avg_qr:.2f} low (+0)")

    # Interest coverage > 5 -> 3 pts
    if ic_vals:
        avg_ic = sum(ic_vals) / len(ic_vals)
        max_points += 3
        if avg_ic > 5.0:
            scores.append(3.0)
            reasons.append(f"Interest coverage {avg_ic:.1f}x > 5x (+3)")
        elif avg_ic > 2.0:
            scores.append(1.5)
            reasons.append(f"Interest coverage {avg_ic:.1f}x moderate (+1.5)")
        else:
            scores.append(0.0)
            reasons.append(f"Interest coverage {avg_ic:.1f}x low (+0)")

    total = sum(scores)
    normalised = (total / max_points) * 10.0 if max_points > 0 else 5.0
    return normalised, max_points, reasons


def _score_valuation(metrics: list[FinancialMetrics]) -> tuple[float, int, list[str]]:
    """Score valuation metrics (lower multiples = higher score)."""
    scores: list[float] = []
    max_points = 0
    reasons: list[str] = []

    pe_vals = [m.pe_ratio for m in metrics if m.pe_ratio is not None and m.pe_ratio > 0]
    pb_vals = [m.pb_ratio for m in metrics if m.pb_ratio is not None and m.pb_ratio > 0]
    ps_vals = [m.ps_ratio for m in metrics if m.ps_ratio is not None and m.ps_ratio > 0]
    ev_vals = [m.ev_to_ebitda for m in metrics if m.ev_to_ebitda is not None and m.ev_to_ebitda > 0]

    # P/E < 20 -> 2 pts
    if pe_vals:
        avg_pe = sum(pe_vals) / len(pe_vals)
        max_points += 2
        if avg_pe < 20:
            scores.append(2.0)
            reasons.append(f"P/E {avg_pe:.1f} < 20 (+2)")
        elif avg_pe < 30:
            scores.append(1.0)
            reasons.append(f"P/E {avg_pe:.1f} moderate (+1)")
        else:
            scores.append(0.0)
            reasons.append(f"P/E {avg_pe:.1f} expensive (+0)")

    # P/B < 3 -> 2 pts
    if pb_vals:
        avg_pb = sum(pb_vals) / len(pb_vals)
        max_points += 2
        if avg_pb < 3:
            scores.append(2.0)
            reasons.append(f"P/B {avg_pb:.1f} < 3 (+2)")
        elif avg_pb < 5:
            scores.append(1.0)
            reasons.append(f"P/B {avg_pb:.1f} moderate (+1)")
        else:
            scores.append(0.0)
            reasons.append(f"P/B {avg_pb:.1f} expensive (+0)")

    # P/S < 2 -> 3 pts
    if ps_vals:
        avg_ps = sum(ps_vals) / len(ps_vals)
        max_points += 3
        if avg_ps < 2:
            scores.append(3.0)
            reasons.append(f"P/S {avg_ps:.1f} < 2 (+3)")
        elif avg_ps < 5:
            scores.append(1.5)
            reasons.append(f"P/S {avg_ps:.1f} moderate (+1.5)")
        else:
            scores.append(0.0)
            reasons.append(f"P/S {avg_ps:.1f} expensive (+0)")

    # EV/EBITDA < 15 -> 3 pts
    if ev_vals:
        avg_ev = sum(ev_vals) / len(ev_vals)
        max_points += 3
        if avg_ev < 15:
            scores.append(3.0)
            reasons.append(f"EV/EBITDA {avg_ev:.1f} < 15 (+3)")
        elif avg_ev < 20:
            scores.append(1.5)
            reasons.append(f"EV/EBITDA {avg_ev:.1f} moderate (+1.5)")
        else:
            scores.append(0.0)
            reasons.append(f"EV/EBITDA {avg_ev:.1f} expensive (+0)")

    total = sum(scores)
    normalised = (total / max_points) * 10.0 if max_points > 0 else 5.0
    return normalised, max_points, reasons


# ---------------------------------------------------------------------------
# Per-ticker analysis
# ---------------------------------------------------------------------------


def _analyse_ticker(ticker: str, api: FinancialDataClient) -> dict[str, Any]:
    """Run the full fundamental scoring pipeline for a single ticker."""
    metrics = api.get_financial_metrics_sync(ticker, period_type="quarterly", limit=4)

    if not metrics:
        logger.warning("No financial metrics available for %s -- returning neutral", ticker)
        return {
            "signal": "neutral",
            "confidence": 0.2,
            "reasoning": f"Insufficient financial data available for {ticker}.",
            "metadata": {"ticker": ticker, "data_available": False},
        }

    # Score each category
    prof_score, prof_max, prof_reasons = _score_profitability(metrics)
    grow_score, grow_max, grow_reasons = _score_growth(metrics)
    health_score, health_max, health_reasons = _score_financial_health(metrics)
    val_score, val_max, val_reasons = _score_valuation(metrics)

    total_score = prof_score + grow_score + health_score + val_score
    total_max_datapoints = prof_max + grow_max + health_max + val_max
    max_possible_datapoints = 10 + 10 + 10 + 10

    # Determine signal direction
    if total_score > BULLISH_THRESHOLD:
        signal = "bullish"
    elif total_score < BEARISH_THRESHOLD:
        signal = "bearish"
    else:
        signal = "neutral"

    # Confidence: data coverage + score extremity
    data_coverage = total_max_datapoints / max_possible_datapoints if max_possible_datapoints > 0 else 0
    midpoint = MAX_TOTAL_SCORE / 2.0
    extremity = abs(total_score - midpoint) / midpoint
    confidence = min(1.0, 0.4 * data_coverage + 0.6 * extremity)
    confidence = round(max(0.1, confidence), 2)

    # Build reasoning
    all_reasons = (
        [f"--- Profitability ({prof_score:.1f}/10) ---"] + prof_reasons
        + [f"--- Growth ({grow_score:.1f}/10) ---"] + grow_reasons
        + [f"--- Financial Health ({health_score:.1f}/10) ---"] + health_reasons
        + [f"--- Valuation ({val_score:.1f}/10) ---"] + val_reasons
        + [f"=== TOTAL: {total_score:.1f}/{MAX_TOTAL_SCORE} -> {signal.upper()} ==="]
    )
    reasoning = "\n".join(all_reasons)

    # Rich table display
    table = Table(title=f"Fundamentals: {ticker}", show_header=True)
    table.add_column("Category", style="cyan")
    table.add_column("Score", style="magenta", justify="right")
    table.add_column("Max", justify="right")
    table.add_row("Profitability", f"{prof_score:.1f}", "10")
    table.add_row("Growth", f"{grow_score:.1f}", "10")
    table.add_row("Financial Health", f"{health_score:.1f}", "10")
    table.add_row("Valuation", f"{val_score:.1f}", "10")
    table.add_row("TOTAL", f"[bold]{total_score:.1f}[/bold]", f"[bold]{MAX_TOTAL_SCORE}[/bold]")
    console.print(table)

    return {
        "signal": signal,
        "confidence": confidence,
        "reasoning": reasoning,
        "agent_scores": {
            "profitability": round(prof_score, 2),
            "growth": round(grow_score, 2),
            "financial_health": round(health_score, 2),
            "valuation": round(val_score, 2),
            "total": round(total_score, 2),
            "quarters_analysed": len(metrics),
            "data_coverage": round(data_coverage, 2),
        },
    }


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------


def fundamentals_agent(state: AgentState) -> dict[str, Any]:
    """Fundamentals Analyst -- rule-based scoring of key financial ratios.

    Analyses profitability, growth, financial health, and valuation across
    the last 4 quarters.  Produces a composite score on a 0-40 scale and
    maps it to a bullish / neutral / bearish signal.

    Parameters
    ----------
    state : AgentState
        Must contain ``state["data"]["tickers"]``.

    Returns
    -------
    dict
        Partial state update: ``{"data": {"analyst_signals": {"fundamentals": ...}}}``.
    """
    data: dict[str, Any] = state["data"]
    tickers: list[str] = data["tickers"]

    console.rule("[bold cyan]Fundamentals Analyst[/bold cyan]")
    logger.info("Fundamentals agent running for tickers: %s", tickers)

    api = FinancialDataClient()
    signals: dict[str, Any] = {}

    for ticker in tickers:
        console.print(f"\n[bold]Analysing {ticker}...[/bold]")
        try:
            signals[ticker] = _analyse_ticker(ticker, api)
        except Exception:
            logger.exception("Error analysing %s in fundamentals agent", ticker)
            signals[ticker] = {
                "signal": "neutral",
                "confidence": 0.0,
                "reasoning": f"Analysis failed for {ticker}; defaulting to neutral.",
                "agent_scores": {},
            }

    return {"data": {"analyst_signals": {"fundamentals": signals}}}
