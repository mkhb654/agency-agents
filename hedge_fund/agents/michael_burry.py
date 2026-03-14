"""Michael Burry Agent -- Contrarian deep value, find mispricing, skeptical by default.

Looks for overvaluation, accounting red flags, debt deterioration, and
sector bubble indicators. The LLM channels Burry's contrarian, data-obsessed
personality to identify opportunities the crowd is missing.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from hedge_fund.data.api import FinancialDataClient
from hedge_fund.data.models import AnalystSignal, FinancialMetrics, LineItem, Price
from hedge_fund.graph.state import AgentState
from hedge_fund.llm.models import call_llm

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
AGENT_SYSTEM_PROMPT = """\
You are Michael Burry, M.D., the founder of Scion Asset Management and one of \
the few investors who predicted and profited from the 2008 subprime mortgage \
crisis. You are a neurologist turned hedge fund manager, and your analytical \
rigour borders on the obsessive.

Your investment philosophy is forged in contrarianism and deep, independent \
fundamental research:

1. **Contrarian by Nature.** You go where others refuse to look. You read \
10-K filings, credit default swap contracts, and mortgage pool prospectuses \
that nobody else bothers to open. When the consensus is overwhelming bullish, \
your instinct is to dig for cracks in the foundation. "I'm a natural loner. \
I see things other people don't."

2. **Mispricing is Everywhere.** Markets are not efficient. They are driven by \
narratives, momentum, and herd behaviour. Your job is to find the gap between \
price and reality -- in both directions. You are as comfortable going long on an \
unloved stock as you are shorting a crowded favourite.

3. **Accounting Forensics.** You trust cash flow more than earnings. When cash \
flow from operations diverges significantly from reported net income, you smell \
manipulation or aggressive accounting. You scrutinise revenue recognition, \
off-balance-sheet liabilities, and one-time adjustments with a forensic \
accountant's eye. "Reported earnings are a construction; free cash flow is a fact."

4. **Debt is the Accelerant.** Debt amplifies both returns and ruin. You watch \
for companies where leverage is rising while earnings quality is falling -- this \
is the classic setup for a blowup. Interest coverage ratios, debt maturity \
schedules, and covenant compliance are central to your analysis.

5. **Sector Bubble Detection.** You look for sectors where valuations have \
detached from fundamentals, driven by easy money and speculative fervour. \
You identified the housing bubble, the passive indexing bubble, and the water \
scarcity crisis before they became mainstream concerns.

6. **Asymmetric Bets.** You look for situations where the downside is limited \
but the upside (or the payout from a short) is enormous. You are willing to \
endure years of mark-to-market losses if your thesis is sound. "Sometimes \
the best investments are the ones that hurt the most before they pay off."

7. **Independent Thinking.** You do not attend conferences, you do not care \
about consensus estimates, and you do not follow price targets. Your research \
is conducted in isolation, driven by curiosity and a deep reading of primary \
sources. You are blunt, sometimes abrasive, and unapologetic about your views.

Your tone is terse, data-heavy, and occasionally acerbic. You communicate in \
short, declarative sentences. You reference specific filing details, debt \
covenants, and cash flow line items. You have no patience for promotional \
management teams or Wall Street analysts who cannot read a balance sheet.

When you are bullish, it is because you have found a deeply misunderstood \
company trading far below its asset value or earning power. When you are bearish, \
it is because you see a house of cards held together by leverage and optimism.

You must produce a JSON response with the following fields:
- signal: one of "bullish", "bearish", or "neutral"
- confidence: a float between 0.0 and 1.0
- reasoning: a concise paragraph (2-4 sentences) in your blunt, contrarian voice
"""


# ---------------------------------------------------------------------------
# Deterministic scoring helpers
# ---------------------------------------------------------------------------

def _score_overvaluation(metrics: list[FinancialMetrics]) -> tuple[float, str]:
    """Score 0-10 for overvaluation risk (higher = more overvalued = more bearish)."""
    score = 0.0
    details: list[str] = []

    # High PE with declining earnings
    pe_values = [m.pe_ratio for m in metrics if m.pe_ratio is not None]
    earnings_growth_vals = [m.earnings_growth for m in metrics if m.earnings_growth is not None]

    if pe_values:
        latest_pe = pe_values[-1]
        if latest_pe > 50:
            score += 3.0
            details.append(f"PE ratio {latest_pe:.1f} -- nosebleed territory.")
        elif latest_pe > 30:
            score += 2.0
            details.append(f"PE ratio {latest_pe:.1f} -- elevated valuation.")
        elif latest_pe > 20:
            score += 1.0
            details.append(f"PE ratio {latest_pe:.1f} -- moderately priced.")
        else:
            details.append(f"PE ratio {latest_pe:.1f} -- not obviously overvalued.")
    else:
        details.append("No PE data.")

    # Declining earnings combined with high valuation
    if earnings_growth_vals and pe_values:
        latest_eg = earnings_growth_vals[-1]
        if latest_eg < 0 and pe_values[-1] > 25:
            score += 3.0
            details.append(
                f"Earnings declining ({latest_eg:.1%}) with elevated PE -- classic overvaluation setup."
            )
        elif latest_eg < 0:
            score += 1.5
            details.append(f"Earnings declining ({latest_eg:.1%}).")
    elif earnings_growth_vals:
        if earnings_growth_vals[-1] < -0.10:
            score += 2.0
            details.append(f"Significant earnings decline ({earnings_growth_vals[-1]:.1%}).")

    # Price to book (extreme values)
    pb_values = [m.price_to_book for m in metrics if m.price_to_book is not None]
    if pb_values:
        latest_pb = pb_values[-1]
        if latest_pb > 10:
            score += 2.5
            details.append(f"P/B {latest_pb:.1f} -- absurdly elevated.")
        elif latest_pb > 5:
            score += 1.5
            details.append(f"P/B {latest_pb:.1f} -- high.")
        elif latest_pb > 3:
            score += 0.5
            details.append(f"P/B {latest_pb:.1f} -- moderate.")
        else:
            details.append(f"P/B {latest_pb:.1f} -- reasonable.")

    # EV/EBITDA if available
    ev_ebitda_vals = [m.ev_to_ebitda for m in metrics if m.ev_to_ebitda is not None]
    if ev_ebitda_vals:
        latest_ev = ev_ebitda_vals[-1]
        if latest_ev > 30:
            score += 1.5
            details.append(f"EV/EBITDA {latest_ev:.1f} -- stretched.")
        elif latest_ev > 15:
            score += 0.5
            details.append(f"EV/EBITDA {latest_ev:.1f} -- above average.")
        else:
            details.append(f"EV/EBITDA {latest_ev:.1f} -- reasonable.")

    return min(score, 10.0), " ".join(details)


def _score_debt_risk(metrics: list[FinancialMetrics], line_items: list[LineItem]) -> tuple[float, str]:
    """Score 0-10 for debt risk (higher = worse)."""
    score = 0.0
    details: list[str] = []

    # Debt-to-equity trend
    de_values = [m.debt_to_equity for m in metrics if m.debt_to_equity is not None]
    if len(de_values) >= 2:
        latest_de = de_values[-1]
        trend = de_values[-1] - de_values[0]
        if latest_de > 3.0:
            score += 3.0
            details.append(f"D/E {latest_de:.2f} -- dangerously leveraged.")
        elif latest_de > 1.5:
            score += 2.0
            details.append(f"D/E {latest_de:.2f} -- elevated leverage.")
        elif latest_de > 0.8:
            score += 1.0
            details.append(f"D/E {latest_de:.2f} -- moderate leverage.")
        else:
            details.append(f"D/E {latest_de:.2f} -- conservative.")

        if trend > 0.5:
            score += 2.0
            details.append(f"Leverage increasing rapidly (+{trend:.2f} over period).")
        elif trend > 0:
            score += 0.5
            details.append("Leverage creeping upward.")
        else:
            details.append("Leverage stable or declining.")
    elif de_values:
        latest_de = de_values[-1]
        if latest_de > 2.0:
            score += 2.5
            details.append(f"D/E {latest_de:.2f} -- high leverage (limited history).")
        else:
            details.append(f"D/E {latest_de:.2f} (limited history).")
    else:
        details.append("No debt-to-equity data.")

    # Interest coverage
    interest_coverage_vals = [m.interest_coverage for m in metrics if m.interest_coverage is not None]
    if interest_coverage_vals:
        latest_ic = interest_coverage_vals[-1]
        if latest_ic < 1.5:
            score += 3.0
            details.append(f"Interest coverage {latest_ic:.1f}x -- barely covering interest payments.")
        elif latest_ic < 3.0:
            score += 2.0
            details.append(f"Interest coverage {latest_ic:.1f}x -- thin margin of safety.")
        elif latest_ic < 5.0:
            score += 1.0
            details.append(f"Interest coverage {latest_ic:.1f}x -- adequate.")
        else:
            details.append(f"Interest coverage {latest_ic:.1f}x -- comfortable.")

    # Total debt relative to cash flow
    total_debt_vals = [getattr(item, "total_debt", None) for item in line_items]
    ocf_vals = [getattr(item, "operating_cash_flow", None) for item in line_items]
    td = next((v for v in reversed(total_debt_vals) if v is not None), None)
    ocf = next((v for v in reversed(ocf_vals) if v is not None), None)

    if td is not None and ocf is not None and ocf > 0:
        debt_to_ocf = td / ocf
        if debt_to_ocf > 8:
            score += 2.0
            details.append(f"Debt/OCF {debt_to_ocf:.1f}x -- would take 8+ years to repay from cash flow.")
        elif debt_to_ocf > 4:
            score += 1.0
            details.append(f"Debt/OCF {debt_to_ocf:.1f}x -- manageable but high.")
        else:
            details.append(f"Debt/OCF {debt_to_ocf:.1f}x -- manageable.")

    return min(score, 10.0), " ".join(details)


def _score_cash_flow_divergence(line_items: list[LineItem]) -> tuple[float, str]:
    """Score 0-10 for cash flow vs earnings divergence (accounting red flags)."""
    score = 0.0
    details: list[str] = []

    ni_vals = [getattr(item, "net_income", None) for item in line_items]
    ocf_vals = [getattr(item, "operating_cash_flow", None) for item in line_items]

    ni_vals_clean = [v for v in ni_vals if v is not None]
    ocf_vals_clean = [v for v in ocf_vals if v is not None]

    if not ni_vals_clean or not ocf_vals_clean:
        return 0.0, "Insufficient data for cash flow divergence analysis."

    # Use paired values
    paired: list[tuple[float, float]] = []
    for ni, ocf in zip(ni_vals, ocf_vals):
        if ni is not None and ocf is not None:
            paired.append((ni, ocf))

    if not paired:
        return 0.0, "Cannot pair net income and operating cash flow data."

    # Recent divergence
    latest_ni, latest_ocf = paired[-1]
    if latest_ni > 0 and latest_ocf < latest_ni * 0.5:
        score += 4.0
        details.append(
            f"OCF (${latest_ocf:,.0f}) is less than half of net income (${latest_ni:,.0f}) "
            f"-- significant accounting red flag."
        )
    elif latest_ni > 0 and latest_ocf < latest_ni * 0.8:
        score += 2.0
        details.append("OCF trailing net income -- mild accounting concern.")
    elif latest_ni > 0 and latest_ocf > latest_ni:
        details.append("OCF exceeds net income -- cash flow quality is good.")
    elif latest_ni <= 0:
        details.append(f"Net income is negative (${latest_ni:,.0f}) -- no divergence analysis needed.")

    # Trend: widening gap between earnings and cash flow
    if len(paired) >= 3:
        ratios = [ocf / ni if ni != 0 else 1.0 for ni, ocf in paired]
        if ratios[-1] < ratios[0] and ratios[-1] < 0.8:
            score += 3.0
            details.append("Cash flow quality deteriorating over time -- growing divergence.")
        elif ratios[-1] < ratios[0]:
            score += 1.0
            details.append("Slight deterioration in cash flow quality ratio.")
        else:
            details.append("Cash flow quality stable or improving.")

    # Cumulative check: net income positive but cumulative OCF negative
    cum_ni = sum(ni for ni, _ in paired)
    cum_ocf = sum(ocf for _, ocf in paired)
    if cum_ni > 0 and cum_ocf < 0:
        score += 3.0
        details.append(
            "Cumulative net income positive but cumulative OCF negative -- "
            "severe earnings quality issue."
        )

    return min(score, 10.0), " ".join(details)


def _score_bubble_indicators(metrics: list[FinancialMetrics], prices: list[Price]) -> tuple[float, str]:
    """Score 0-10 for sector/stock bubble indicators."""
    score = 0.0
    details: list[str] = []

    # Price momentum (excessive run-up)
    if len(prices) >= 50:
        recent_price = prices[-1].close
        price_6m_ago = prices[len(prices) // 2].close if len(prices) > 1 else recent_price
        price_start = prices[0].close

        if price_start > 0:
            total_return = (recent_price - price_start) / price_start
            if total_return > 1.0:
                score += 3.0
                details.append(f"Price up {total_return:.0%} over the period -- parabolic move.")
            elif total_return > 0.5:
                score += 1.5
                details.append(f"Price up {total_return:.0%} -- strong run-up.")
            elif total_return < -0.3:
                details.append(f"Price down {total_return:.0%} -- already correcting.")
            else:
                details.append(f"Price change {total_return:.0%} -- moderate.")

        # Volatility spike (large daily swings = speculative behavior)
        if len(prices) >= 20:
            returns = []
            for i in range(1, len(prices)):
                if prices[i - 1].close > 0:
                    returns.append((prices[i].close - prices[i - 1].close) / prices[i - 1].close)
            if returns:
                avg_abs_return = sum(abs(r) for r in returns) / len(returns)
                if avg_abs_return > 0.04:
                    score += 2.0
                    details.append(f"Avg daily absolute move {avg_abs_return:.1%} -- extreme volatility.")
                elif avg_abs_return > 0.025:
                    score += 1.0
                    details.append(f"Avg daily absolute move {avg_abs_return:.1%} -- elevated volatility.")
    else:
        details.append("Insufficient price history for momentum analysis.")

    # Revenue multiple extreme
    ps_values = [m.price_to_sales for m in metrics if m.price_to_sales is not None]
    if ps_values:
        latest_ps = ps_values[-1]
        if latest_ps > 20:
            score += 3.0
            details.append(f"P/S {latest_ps:.1f} -- extreme revenue multiple, bubble territory.")
        elif latest_ps > 10:
            score += 2.0
            details.append(f"P/S {latest_ps:.1f} -- stretched revenue multiple.")
        elif latest_ps > 5:
            score += 1.0
            details.append(f"P/S {latest_ps:.1f} -- above average.")
        else:
            details.append(f"P/S {latest_ps:.1f} -- reasonable.")

    # Insider selling (if available via metrics proxy)
    # Note: this is a proxy -- in production we'd use InsiderTrade data
    fcf_yield_vals = [m.free_cash_flow_yield for m in metrics if m.free_cash_flow_yield is not None]
    if fcf_yield_vals:
        latest_fcfy = fcf_yield_vals[-1]
        if latest_fcfy < 0.01:
            score += 2.0
            details.append(f"FCF yield {latest_fcfy:.2%} -- negligible cash return to investors.")
        elif latest_fcfy < 0.03:
            score += 1.0
            details.append(f"FCF yield {latest_fcfy:.2%} -- low.")

    return min(score, 10.0), " ".join(details)


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------

def michael_burry_agent(state: AgentState) -> dict[str, Any]:
    """Run Michael Burry's contrarian analysis on every ticker in state.

    Returns updated state with analyst signals keyed by ``michael_burry``.

    NOTE: Burry's scoring is INVERTED -- high scores on overvaluation, debt risk,
    and cash flow divergence are BEARISH signals. The overall signal logic reflects this.
    """
    data: dict[str, Any] = state["data"]
    tickers: list[str] = data["tickers"]
    api = FinancialDataClient()
    signals: dict[str, Any] = {}

    for ticker in tickers:
        try:
            logger.info("Michael Burry analysing %s ...", ticker)

            # -- 1. Fetch data ------------------------------------------------
            metrics: list[FinancialMetrics] = api.get_financial_metrics(ticker, limit=10)
            line_items: list[LineItem] = api.get_line_items(
                ticker,
                line_items=[
                    "net_income",
                    "operating_cash_flow",
                    "total_debt",
                    "total_current_assets",
                    "total_liabilities",
                    "shares_outstanding",
                ],
                limit=10,
            )
            prices: list[Price] = api.get_prices(ticker, limit=252)

            # -- 2. Deterministic scoring (bearish indicators) -----------------
            overval_score, overval_details = _score_overvaluation(metrics)
            debt_score, debt_details = _score_debt_risk(metrics, line_items)
            divergence_score, divergence_details = _score_cash_flow_divergence(line_items)
            bubble_score, bubble_details = _score_bubble_indicators(metrics, prices)

            # Burry's risk score: higher = more red flags = more bearish
            risk_score = (overval_score + debt_score + divergence_score + bubble_score) / 4.0

            # -- 3. Build analysis summary ------------------------------------
            analysis_summary = (
                f"Ticker: {ticker}\n"
                f"Overall Risk/Overvaluation Score: {risk_score:.1f}/10 "
                f"(higher = more red flags)\n\n"
                f"Overvaluation ({overval_score:.1f}/10): {overval_details}\n"
                f"Debt Risk ({debt_score:.1f}/10): {debt_details}\n"
                f"Cash Flow Divergence ({divergence_score:.1f}/10): {divergence_details}\n"
                f"Bubble Indicators ({bubble_score:.1f}/10): {bubble_details}\n"
            )

            if prices:
                analysis_summary += f"\nCurrent Price: ${prices[-1].close:.2f}\n"

            # -- 4. LLM synthesis ---------------------------------------------
            llm_result = call_llm(
                system_prompt=AGENT_SYSTEM_PROMPT,
                user_message=(
                    f"Based on the following contrarian analysis, provide your "
                    f"investment signal for {ticker}. Remember: high risk scores "
                    f"indicate overvaluation and potential short opportunities. "
                    f"Low risk scores may indicate an overlooked value opportunity. "
                    f"Be skeptical by default. Respond with JSON containing "
                    f"'signal', 'confidence', and 'reasoning'.\n\n{analysis_summary}"
                ),
                response_model=AnalystSignal,
            )

            signals[ticker] = {
                "signal": llm_result.signal,
                "confidence": llm_result.confidence,
                "reasoning": llm_result.reasoning,
                "agent_scores": {
                    "overvaluation": overval_score,
                    "debt_risk": debt_score,
                    "cash_flow_divergence": divergence_score,
                    "bubble_indicators": bubble_score,
                    "overall_risk": risk_score,
                },
            }
            logger.info(
                "Burry on %s: %s (confidence %.0f%%)",
                ticker,
                llm_result.signal,
                llm_result.confidence * 100,
            )

        except Exception:
            logger.exception("Michael Burry agent failed on %s -- returning neutral.", ticker)
            signals[ticker] = {
                "signal": "neutral",
                "confidence": 0.0,
                "reasoning": f"Analysis failed for {ticker}; defaulting to neutral.",
                "agent_scores": {},
            }

    return {"data": {"analyst_signals": {"michael_burry": signals}}}
