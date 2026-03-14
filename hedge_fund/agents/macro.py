"""Macro Analyst Agent (LLM-POWERED).

Analyses macroeconomic trends relevant to each ticker by examining:

  1. **Sector momentum** -- is the company's sector expanding or contracting?
  2. **Interest-rate sensitivity** -- how leveraged is the company?
  3. **Currency exposure** -- international revenue / FX risk
  4. **Commodity dependency** -- cost-structure sensitivity to commodities

The agent gathers available financial data (metrics, line items) and feeds
a structured prompt to the LLM, which synthesises a macro outlook and
returns a directional signal with reasoning.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field
from rich.console import Console
from rich.panel import Panel

from hedge_fund.data.api import FinancialDataClient
from hedge_fund.data.models import FinancialMetrics, LineItem
from hedge_fund.graph.state import AgentState
from hedge_fund.llm.models import call_llm

logger = logging.getLogger(__name__)
console = Console()

# Line items useful for macro context
_MACRO_LINE_ITEMS = [
    "revenue",
    "net_income",
    "total_debt",
    "cash_and_equivalents",
    "total_assets",
    "total_equity",
    "interest_expense",
    "depreciation_and_amortization",
    "capital_expenditure",
    "operating_cash_flow",
    "free_cash_flow",
]


# ---------------------------------------------------------------------------
# LLM response schema
# ---------------------------------------------------------------------------


class MacroAssessment(BaseModel):
    """Structured output from the LLM macro analysis."""

    signal: str = Field(description="One of: bullish, bearish, neutral")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence 0-1")
    sector_outlook: str = Field(description="Brief assessment of sector momentum")
    interest_rate_impact: str = Field(description="How rate environment affects this company")
    currency_exposure: str = Field(description="FX risk assessment")
    commodity_dependency: str = Field(description="Commodity input cost risk")
    overall_reasoning: str = Field(description="Synthesised macro thesis in 2-4 sentences")


# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------


def _build_financial_summary(
    ticker: str,
    metrics: list[FinancialMetrics],
    line_items: list[LineItem],
) -> str:
    """Build a concise text summary of key financial data for the LLM prompt."""
    parts: list[str] = [f"Financial data for {ticker}:"]

    if metrics:
        m = metrics[0]
        parts.append(f"\nMost recent period: {m.period}")
        if m.revenue is not None:
            parts.append(f"  Revenue: ${m.revenue:,.0f}")
        if m.net_income is not None:
            parts.append(f"  Net income: ${m.net_income:,.0f}")
        if m.revenue_growth is not None:
            parts.append(f"  Revenue growth: {m.revenue_growth:.1%}")
        if m.earnings_growth is not None:
            parts.append(f"  Earnings growth: {m.earnings_growth:.1%}")
        if m.operating_margin is not None:
            parts.append(f"  Operating margin: {m.operating_margin:.1%}")
        if m.net_profit_margin is not None:
            parts.append(f"  Net profit margin: {m.net_profit_margin:.1%}")
        if m.return_on_equity is not None:
            parts.append(f"  Return on equity: {m.return_on_equity:.1%}")
        if m.debt_to_equity is not None:
            parts.append(f"  Debt/equity: {m.debt_to_equity:.2f}")
        if m.current_ratio is not None:
            parts.append(f"  Current ratio: {m.current_ratio:.2f}")
        if m.interest_coverage is not None:
            parts.append(f"  Interest coverage: {m.interest_coverage:.1f}x")
        if m.pe_ratio is not None:
            parts.append(f"  P/E ratio: {m.pe_ratio:.1f}")
        if m.market_cap is not None:
            parts.append(f"  Market cap: ${m.market_cap:,.0f}")

        if len(metrics) > 1:
            parts.append("\nQuarterly trend (newest to oldest):")
            for q in metrics:
                rev = f"${q.revenue:,.0f}" if q.revenue else "N/A"
                ni = f"${q.net_income:,.0f}" if q.net_income else "N/A"
                parts.append(f"  {q.period}: Rev={rev}, NI={ni}")

    if line_items:
        li = line_items[0]
        parts.append("\nBalance sheet highlights (latest):")
        if li.total_debt is not None:
            parts.append(f"  Total debt: ${li.total_debt:,.0f}")
        if li.cash_and_equivalents is not None:
            parts.append(f"  Cash: ${li.cash_and_equivalents:,.0f}")
        if li.total_assets is not None:
            parts.append(f"  Total assets: ${li.total_assets:,.0f}")
        if li.total_equity is not None:
            parts.append(f"  Total equity: ${li.total_equity:,.0f}")
        if li.interest_expense is not None:
            parts.append(f"  Interest expense: ${li.interest_expense:,.0f}")
        if li.depreciation_and_amortization is not None:
            parts.append(f"  D&A: ${li.depreciation_and_amortization:,.0f}")
        if li.capital_expenditure is not None:
            parts.append(f"  CapEx: ${li.capital_expenditure:,.0f}")
        if li.operating_cash_flow is not None:
            parts.append(f"  Operating cash flow: ${li.operating_cash_flow:,.0f}")
        if li.free_cash_flow is not None:
            parts.append(f"  Free cash flow: ${li.free_cash_flow:,.0f}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Per-ticker analysis
# ---------------------------------------------------------------------------


def _analyse_ticker(ticker: str, api: FinancialDataClient) -> dict[str, Any]:
    """Run macro analysis for a single ticker via LLM."""
    metrics: list[FinancialMetrics] = api.get_financial_metrics_sync(
        ticker, period_type="quarterly", limit=4,
    )
    line_items: list[LineItem] = api.search_line_items_sync(
        ticker, line_items=_MACRO_LINE_ITEMS, period_type="quarterly", limit=4,
    )

    if not metrics and not line_items:
        logger.warning("No financial data for macro analysis of %s", ticker)
        return {
            "signal": "neutral",
            "confidence": 0.15,
            "reasoning": f"No financial data available for macro analysis of {ticker}.",
            "agent_scores": {},
        }

    financial_summary = _build_financial_summary(ticker, metrics, line_items)

    system_message = (
        "You are an experienced macroeconomic analyst at a hedge fund. "
        "Your job is to evaluate how macroeconomic conditions affect a "
        "specific company's stock outlook. Consider current macro trends "
        "including interest rates, inflation, sector rotation, currency "
        "movements, and commodity prices. Base your analysis on the "
        "financial data provided and your knowledge of macro conditions."
    )

    prompt = (
        f"Analyse the macroeconomic outlook for {ticker} based on the following financial data.\n\n"
        f"{financial_summary}\n\n"
        "Evaluate the following macro factors and their likely impact on this company:\n\n"
        "1. **Sector Momentum**: Based on the company's financial trajectory (revenue growth, "
        "margin trends), assess whether its sector is in an expansion or contraction phase. "
        "Consider cyclical vs defensive characteristics.\n\n"
        "2. **Interest Rate Sensitivity**: Examine the company's debt levels, interest coverage, "
        "and margin structure. How vulnerable is it to rising rates? Would falling rates be a tailwind?\n\n"
        "3. **Currency Exposure**: Based on the company's size, sector, and financial profile, "
        "estimate its likely international revenue exposure and FX risk.\n\n"
        "4. **Commodity Dependency**: Consider the company's cost structure (gross margins, "
        "operating margins). How sensitive might it be to commodity price fluctuations?\n\n"
        "Provide your overall macro assessment as bullish, bearish, or neutral with a "
        "confidence level (0.0-1.0). Include specific reasoning for each factor and a "
        "synthesised 2-4 sentence thesis."
    )

    try:
        result = call_llm(
            prompt=prompt,
            system_message=system_message,
            response_model=MacroAssessment,
            agent_name="macro_analyst",
        )

        if isinstance(result, MacroAssessment):
            assessment = result.model_dump()
        elif isinstance(result, dict):
            assessment = result
        else:
            logger.warning("LLM returned unexpected type for %s; using text fallback", ticker)
            return _text_fallback(ticker, str(result))

        signal_str = assessment.get("signal", "neutral").lower().strip()
        if signal_str not in ("bullish", "bearish", "neutral"):
            signal_str = "neutral"

        confidence = round(min(1.0, max(0.1, assessment.get("confidence", 0.5))), 2)

        reasoning_lines = [
            f"Macro analysis for {ticker}:",
            "",
            f"Sector Outlook: {assessment.get('sector_outlook', 'N/A')}",
            f"Interest Rate Impact: {assessment.get('interest_rate_impact', 'N/A')}",
            f"Currency Exposure: {assessment.get('currency_exposure', 'N/A')}",
            f"Commodity Dependency: {assessment.get('commodity_dependency', 'N/A')}",
            "",
            f"Overall: {assessment.get('overall_reasoning', 'N/A')}",
            f"Signal: {signal_str.upper()} (confidence: {confidence:.0%})",
        ]

        # Rich display
        panel_content = (
            f"[cyan]Sector:[/cyan] {assessment.get('sector_outlook', 'N/A')}\n"
            f"[cyan]Rates:[/cyan] {assessment.get('interest_rate_impact', 'N/A')}\n"
            f"[cyan]FX:[/cyan] {assessment.get('currency_exposure', 'N/A')}\n"
            f"[cyan]Commodities:[/cyan] {assessment.get('commodity_dependency', 'N/A')}\n\n"
            f"[bold]Thesis:[/bold] {assessment.get('overall_reasoning', 'N/A')}\n"
            f"[bold]Signal:[/bold] {signal_str.upper()} ({confidence:.0%})"
        )
        console.print(Panel(panel_content, title=f"Macro: {ticker}", border_style="blue"))

        return {
            "signal": signal_str,
            "confidence": confidence,
            "reasoning": "\n".join(reasoning_lines),
            "agent_scores": {
                "sector_outlook": assessment.get("sector_outlook"),
                "interest_rate_impact": assessment.get("interest_rate_impact"),
                "currency_exposure": assessment.get("currency_exposure"),
                "commodity_dependency": assessment.get("commodity_dependency"),
                "overall_reasoning": assessment.get("overall_reasoning"),
            },
        }

    except Exception:
        logger.exception("LLM macro analysis failed for %s", ticker)
        return _neutral_fallback(ticker, "LLM analysis failed; returning neutral signal.")


def _text_fallback(ticker: str, text: str) -> dict[str, Any]:
    """Parse a plain-text LLM response when structured output fails."""
    text_lower = text.lower()
    if "bullish" in text_lower:
        signal = "bullish"
        confidence = 0.4
    elif "bearish" in text_lower:
        signal = "bearish"
        confidence = 0.4
    else:
        signal = "neutral"
        confidence = 0.3

    return {
        "signal": signal,
        "confidence": confidence,
        "reasoning": f"Macro analysis for {ticker} (text fallback):\n{text[:1000]}",
        "agent_scores": {"fallback": True},
    }


def _neutral_fallback(ticker: str, reason: str) -> dict[str, Any]:
    """Return a neutral signal when analysis cannot be performed."""
    return {
        "signal": "neutral",
        "confidence": 0.15,
        "reasoning": f"Macro analysis for {ticker}: {reason}",
        "agent_scores": {"error": True},
    }


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------


def macro_agent(state: AgentState) -> dict[str, Any]:
    """Macro Analyst -- LLM-powered macroeconomic trend analysis.

    Evaluates sector momentum, interest-rate sensitivity, currency exposure,
    and commodity dependency for each ticker.  Uses the configured LLM to
    synthesise a macro outlook based on available financial data.

    Parameters
    ----------
    state : AgentState
        Must contain ``state["data"]["tickers"]``.

    Returns
    -------
    dict
        Partial state update: ``{"data": {"analyst_signals": {"macro": ...}}}``.
    """
    data: dict[str, Any] = state["data"]
    tickers: list[str] = data["tickers"]

    console.rule("[bold blue]Macro Analyst[/bold blue]")
    logger.info("Macro agent running for tickers: %s", tickers)

    api = FinancialDataClient()
    signals: dict[str, Any] = {}

    for ticker in tickers:
        console.print(f"\n[bold]Analysing {ticker}...[/bold]")
        try:
            signals[ticker] = _analyse_ticker(ticker, api)
        except Exception:
            logger.exception("Error in macro agent for %s", ticker)
            signals[ticker] = _neutral_fallback(ticker, "Unexpected error during macro analysis.")

    return {"data": {"analyst_signals": {"macro": signals}}}
