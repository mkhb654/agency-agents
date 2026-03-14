"""Sentiment Analyst Agent (HYBRID: rule-based insider scoring + LLM news sentiment).

Two independent signals are combined:

  1. **Insider Trade Scoring** (30% weight)
     - Net buy ratio = (buys - sells) / total
     - Large insider buys (>$100k) receive extra weight
     - Score maps to [-1, +1]

  2. **News Headline Sentiment** (70% weight)
     - Each headline is classified by an LLM as positive / negative / neutral
       with a confidence score
     - Headlines are weighted by recency (exponential decay, 15-day half-life)
     - Aggregate sentiment maps to [-1, +1]

The combined score determines the final signal direction.
"""

from __future__ import annotations

import datetime
import logging
import math
from typing import Any

from pydantic import BaseModel, Field
from rich.console import Console
from rich.table import Table

from hedge_fund.data.api import FinancialDataClient
from hedge_fund.data.models import CompanyNews, InsiderTrade
from hedge_fund.graph.state import AgentState
from hedge_fund.llm.models import call_llm

logger = logging.getLogger(__name__)
console = Console()

# ---------------------------------------------------------------------------
# Weights
# ---------------------------------------------------------------------------

INSIDER_WEIGHT = 0.30
NEWS_WEIGHT = 0.70
LARGE_TRADE_THRESHOLD = 100_000  # USD


# ---------------------------------------------------------------------------
# LLM response schemas for news sentiment
# ---------------------------------------------------------------------------


class HeadlineSentiment(BaseModel):
    """LLM-structured output for a single headline classification."""

    sentiment: str = Field(description="One of: positive, negative, neutral")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence 0-1")
    reasoning: str = Field(description="Brief explanation")


class NewsSentimentBatch(BaseModel):
    """LLM-structured output for a batch of headlines."""

    sentiments: list[HeadlineSentiment]


# ---------------------------------------------------------------------------
# Insider trade scoring
# ---------------------------------------------------------------------------


def _score_insider_trades(trades: list[InsiderTrade]) -> tuple[float, float, str]:
    """Score insider trading activity.  Returns (signal, confidence, reason)."""
    if not trades:
        return 0.0, 0.2, "No insider trades found in the lookback window."

    buy_count = 0
    sell_count = 0
    buy_value = 0.0
    sell_value = 0.0
    large_buy_count = 0
    large_sell_count = 0

    for trade in trades:
        tx_type = trade.transaction_type.lower().strip()
        value = trade.total_value or (trade.shares * (trade.price_per_share or 0))

        if tx_type in ("buy", "purchase", "p-purchase", "a-award"):
            buy_count += 1
            buy_value += value
            if value > LARGE_TRADE_THRESHOLD:
                large_buy_count += 1
        elif tx_type in ("sell", "sale", "s-sale", "disposition"):
            sell_count += 1
            sell_value += value
            if value > LARGE_TRADE_THRESHOLD:
                large_sell_count += 1

    total = buy_count + sell_count
    if total == 0:
        return 0.0, 0.2, "No classifiable insider trades."

    net_ratio = (buy_count - sell_count) / total
    total_value = buy_value + sell_value
    value_ratio = (buy_value - sell_value) / total_value if total_value > 0 else 0.0
    large_bonus = (large_buy_count - large_sell_count) * 0.1

    # Combine: 50% count-based, 30% value-based, 20% large-trade bonus
    raw_signal = 0.50 * net_ratio + 0.30 * value_ratio + 0.20 * large_bonus
    signal = max(-1.0, min(1.0, raw_signal))

    confidence = min(1.0, 0.3 + 0.05 * total + 0.1 * (large_buy_count + large_sell_count))
    confidence = round(confidence, 2)

    reason_parts = [
        f"Insider trades ({len(trades)} in window): {buy_count} buys (${buy_value:,.0f}), "
        f"{sell_count} sells (${sell_value:,.0f}).",
        f"Net ratio={net_ratio:+.2f}, value ratio={value_ratio:+.2f}.",
    ]
    if large_buy_count or large_sell_count:
        reason_parts.append(
            f"Large trades (>${LARGE_TRADE_THRESHOLD:,}): "
            f"{large_buy_count} buys, {large_sell_count} sells."
        )
    direction = "bullish" if signal > 0.1 else "bearish" if signal < -0.1 else "neutral"
    reason_parts.append(f"Insider signal: {signal:+.2f} ({direction}).")

    return signal, confidence, "\n".join(reason_parts)


# ---------------------------------------------------------------------------
# News sentiment scoring (LLM-powered)
# ---------------------------------------------------------------------------


def _classify_headlines_llm(headlines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Use LLM to classify a batch of headlines as positive/negative/neutral."""
    if not headlines:
        return []

    headline_text = "\n".join(
        f"{i + 1}. [{h.get('date', 'unknown')}] {h['title']}"
        for i, h in enumerate(headlines)
    )

    system_msg = (
        "You are a financial sentiment analyst. For each news headline, classify "
        "the sentiment as exactly one of: positive, negative, or neutral. "
        "Provide a confidence score (0.0 to 1.0) and a brief reasoning. "
        "Consider the headline's likely impact on the company's stock price."
    )

    prompt = (
        f"Classify the sentiment of each of these {len(headlines)} news headlines:\n\n"
        f"{headline_text}\n\n"
        "For each headline, return the sentiment (positive/negative/neutral), "
        "confidence (0.0-1.0), and brief reasoning. "
        f"Return exactly {len(headlines)} classifications in order."
    )

    try:
        result = call_llm(
            prompt=prompt,
            system_message=system_msg,
            response_model=NewsSentimentBatch,
            agent_name="sentiment_analyst",
        )

        if isinstance(result, NewsSentimentBatch):
            sentiments = [s.model_dump() for s in result.sentiments]
        elif isinstance(result, dict) and "sentiments" in result:
            sentiments = result["sentiments"]
        else:
            sentiments = []

        # Pad to correct length
        while len(sentiments) < len(headlines):
            sentiments.append({"sentiment": "neutral", "confidence": 0.3, "reasoning": "No classification"})

        return [
            {
                "sentiment": (s.get("sentiment", "neutral") if isinstance(s, dict) else getattr(s, "sentiment", "neutral")),
                "confidence": (s.get("confidence", 0.5) if isinstance(s, dict) else getattr(s, "confidence", 0.5)),
                "reasoning": (s.get("reasoning", "") if isinstance(s, dict) else getattr(s, "reasoning", "")),
            }
            for s in sentiments[: len(headlines)]
        ]

    except Exception:
        logger.exception("LLM headline classification failed; falling back to neutral")

    return [{"sentiment": "neutral", "confidence": 0.3, "reasoning": "LLM unavailable"} for _ in headlines]


def _score_news_sentiment(
    news: list[CompanyNews],
    reference_date: datetime.date | None = None,
) -> tuple[float, float, str]:
    """Score news sentiment with recency weighting.  Returns (signal, confidence, reason)."""
    if not news:
        return 0.0, 0.2, "No news articles found for this ticker."

    reference_date = reference_date or datetime.date.today()

    headline_dicts = [
        {"title": n.title, "date": str(n.date), "source": n.source or "unknown"}
        for n in news
    ]

    classifications = _classify_headlines_llm(headline_dicts)

    sentiment_map = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}
    weighted_sum = 0.0
    weight_total = 0.0
    positive_count = 0
    negative_count = 0
    neutral_count = 0
    details: list[str] = []

    for i, (article, classification) in enumerate(zip(news, classifications)):
        sent_label = classification.get("sentiment", "neutral").lower()
        sent_value = sentiment_map.get(sent_label, 0.0)
        sent_confidence = classification.get("confidence", 0.5)

        # Recency weight: exponential decay with half-life of 15 days
        days_ago = max(0, (reference_date - article.date).days)
        recency_weight = math.exp(-0.693 * days_ago / 15.0)

        combined_weight = recency_weight * sent_confidence
        weighted_sum += sent_value * combined_weight
        weight_total += combined_weight

        if sent_label == "positive":
            positive_count += 1
        elif sent_label == "negative":
            negative_count += 1
        else:
            neutral_count += 1

        if i < 5:
            details.append(
                f"  [{article.date}] {article.title[:80]}... -> {sent_label} "
                f"(conf={sent_confidence:.0%}, recency={recency_weight:.2f})"
            )

    signal = max(-1.0, min(1.0, weighted_sum / weight_total)) if weight_total > 0 else 0.0

    total = positive_count + negative_count + neutral_count
    dominant = max(positive_count, negative_count, neutral_count) if total > 0 else 0
    agreement = dominant / total if total > 0 else 0.0
    confidence = min(1.0, 0.2 + 0.3 * agreement + 0.02 * total)
    confidence = round(confidence, 2)

    reason_parts = [
        f"News sentiment ({len(news)} articles): {positive_count} positive, "
        f"{negative_count} negative, {neutral_count} neutral.",
    ]
    if details:
        reason_parts.append("Top headlines:")
        reason_parts.extend(details)
    direction = "bullish" if signal > 0.1 else "bearish" if signal < -0.1 else "neutral"
    reason_parts.append(f"Aggregate news signal: {signal:+.2f} ({direction}).")

    return signal, confidence, "\n".join(reason_parts)


# ---------------------------------------------------------------------------
# Per-ticker analysis
# ---------------------------------------------------------------------------


def _analyse_ticker(ticker: str, api: FinancialDataClient) -> dict[str, Any]:
    """Run the full sentiment analysis pipeline for a single ticker."""
    lookback = datetime.date.today() - datetime.timedelta(days=90)

    trades: list[InsiderTrade] = api.get_insider_trades_sync(ticker, start_date=lookback)
    news: list[CompanyNews] = api.get_company_news_sync(ticker, start_date=lookback)

    insider_signal, insider_conf, insider_reason = _score_insider_trades(trades)
    news_signal, news_conf, news_reason = _score_news_sentiment(news)

    combined_signal = INSIDER_WEIGHT * insider_signal + NEWS_WEIGHT * news_signal
    combined_confidence = INSIDER_WEIGHT * insider_conf + NEWS_WEIGHT * news_conf
    combined_confidence = round(min(1.0, max(0.1, combined_confidence)), 2)

    if combined_signal > 0.15:
        signal = "bullish"
    elif combined_signal < -0.15:
        signal = "bearish"
    else:
        signal = "neutral"

    reasoning_lines = [
        f"Sentiment analysis for {ticker}:",
        "",
        f"=== Insider Trades (weight={INSIDER_WEIGHT:.0%}) ===",
        insider_reason,
        "",
        f"=== News Sentiment (weight={NEWS_WEIGHT:.0%}) ===",
        news_reason,
        "",
        f"Combined signal: {combined_signal:+.3f} -> {signal.upper()}",
    ]

    # Rich table display
    table = Table(title=f"Sentiment: {ticker}", show_header=True)
    table.add_column("Component", style="cyan")
    table.add_column("Signal", justify="right")
    table.add_column("Confidence", justify="right")
    table.add_column("Weight", justify="right")
    table.add_row("Insider Trades", f"{insider_signal:+.2f}", f"{insider_conf:.0%}", f"{INSIDER_WEIGHT:.0%}")
    table.add_row("News Headlines", f"{news_signal:+.2f}", f"{news_conf:.0%}", f"{NEWS_WEIGHT:.0%}")
    table.add_row(
        "[bold]Combined[/bold]",
        f"[bold]{combined_signal:+.3f}[/bold]",
        f"[bold]{combined_confidence:.0%}[/bold]",
        "100%",
    )
    console.print(table)

    return {
        "signal": signal,
        "confidence": combined_confidence,
        "reasoning": "\n".join(reasoning_lines),
        "agent_scores": {
            "combined_signal": round(combined_signal, 4),
            "insider_signal": round(insider_signal, 4),
            "insider_confidence": insider_conf,
            "news_signal": round(news_signal, 4),
            "news_confidence": news_conf,
            "insider_trades_count": len(trades),
            "news_articles_count": len(news),
        },
    }


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------


def sentiment_agent(state: AgentState) -> dict[str, Any]:
    """Sentiment Analyst -- hybrid insider-trade scoring + LLM news sentiment.

    Fetches insider trades (last 90 days) and company news, scores each
    component independently, and combines with 30% insider / 70% news
    weighting to produce a final signal.

    Parameters
    ----------
    state : AgentState
        Must contain ``state["data"]["tickers"]``.

    Returns
    -------
    dict
        Partial state update: ``{"data": {"analyst_signals": {"sentiment": ...}}}``.
    """
    data: dict[str, Any] = state["data"]
    tickers: list[str] = data["tickers"]

    console.rule("[bold yellow]Sentiment Analyst[/bold yellow]")
    logger.info("Sentiment agent running for tickers: %s", tickers)

    api = FinancialDataClient()
    signals: dict[str, Any] = {}

    for ticker in tickers:
        console.print(f"\n[bold]Analysing {ticker}...[/bold]")
        try:
            signals[ticker] = _analyse_ticker(ticker, api)
        except Exception:
            logger.exception("Error in sentiment agent for %s", ticker)
            signals[ticker] = {
                "signal": "neutral",
                "confidence": 0.0,
                "reasoning": f"Analysis failed for {ticker}; defaulting to neutral.",
                "agent_scores": {},
            }

    return {"data": {"analyst_signals": {"sentiment": signals}}}
