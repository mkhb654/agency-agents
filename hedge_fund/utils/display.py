"""Rich console display utilities for the AI hedge fund.

Provides formatted, coloured output for trade decisions, analyst signals,
risk assessments, and portfolio summaries using the ``rich`` library.
"""

from __future__ import annotations

import logging
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

logger = logging.getLogger(__name__)

console = Console()

# ---------------------------------------------------------------------------
# Colour / style mappings
# ---------------------------------------------------------------------------

_ACTION_STYLES: dict[str, str] = {
    "buy": "bold green",
    "sell": "bold red",
    "short": "bold magenta",
    "cover": "bold cyan",
    "hold": "dim",
}

_SIGNAL_STYLES: dict[str, str] = {
    "bullish": "bold green",
    "bearish": "bold red",
    "neutral": "yellow",
}

_REGIME_STYLES: dict[str, str] = {
    "low": "green",
    "normal": "yellow",
    "high": "red",
    "extreme": "bold red",
}


def _confidence_style(confidence: float) -> str:
    """Return a rich style string based on confidence level (0-100)."""
    if confidence >= 75:
        return "bold green"
    elif confidence >= 50:
        return "yellow"
    elif confidence >= 25:
        return "orange3"
    else:
        return "red"


# ---------------------------------------------------------------------------
# Trade decisions
# ---------------------------------------------------------------------------


def print_trading_decisions(decisions: dict[str, dict[str, Any]]) -> None:
    """Display a formatted table of trade decisions.

    Parameters
    ----------
    decisions:
        Dict mapping ticker -> TradeDecision dict (action, quantity, confidence,
        reasoning, etc.).
    """
    if not decisions:
        console.print(Panel("[dim]No trading decisions to display.[/dim]", title="Trade Decisions"))
        return

    table = Table(
        title="Trade Decisions",
        show_header=True,
        header_style="bold white",
        border_style="blue",
        show_lines=True,
        expand=False,
    )

    table.add_column("Ticker", style="bold white", min_width=8)
    table.add_column("Action", min_width=8, justify="center")
    table.add_column("Quantity", min_width=10, justify="right")
    table.add_column("Confidence", min_width=12, justify="center")
    table.add_column("Reasoning", min_width=30, max_width=60)

    for ticker, decision in sorted(decisions.items()):
        action = decision.get("action", "hold")
        quantity = decision.get("quantity", 0)
        confidence = decision.get("confidence", 0.0)
        reasoning = decision.get("reasoning", "")

        action_style = _ACTION_STYLES.get(action, "white")
        conf_style = _confidence_style(confidence)

        # Truncate long reasoning
        if len(reasoning) > 80:
            reasoning = reasoning[:77] + "..."

        table.add_row(
            ticker,
            Text(action.upper(), style=action_style),
            Text(f"{quantity:,}", style=action_style) if quantity > 0 else Text("-", style="dim"),
            Text(f"{confidence:.0f}%", style=conf_style),
            Text(reasoning, style="white"),
        )

    console.print()
    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# Analyst signals
# ---------------------------------------------------------------------------


def print_analyst_signals(analyst_signals: dict[str, dict[str, Any]]) -> None:
    """Display a coloured summary of analyst signals per analyst per ticker.

    Parameters
    ----------
    analyst_signals:
        Dict mapping analyst_name -> {ticker -> signal_dict}.
        Each signal_dict should contain at minimum ``signal`` and ``confidence``.
    """
    if not analyst_signals:
        console.print(Panel("[dim]No analyst signals to display.[/dim]", title="Analyst Signals"))
        return

    # Collect all tickers
    all_tickers: set[str] = set()
    for ticker_signals in analyst_signals.values():
        if isinstance(ticker_signals, dict):
            all_tickers.update(ticker_signals.keys())
    sorted_tickers = sorted(all_tickers)

    table = Table(
        title="Analyst Signals",
        show_header=True,
        header_style="bold white",
        border_style="cyan",
        show_lines=True,
        expand=False,
    )

    table.add_column("Analyst", style="bold white", min_width=20)
    for ticker in sorted_tickers:
        table.add_column(ticker, min_width=16, justify="center")

    for analyst_name, ticker_signals in sorted(analyst_signals.items()):
        row: list[Text | str] = [_format_analyst_name(analyst_name)]

        for ticker in sorted_tickers:
            signal_data = ticker_signals.get(ticker, {}) if isinstance(ticker_signals, dict) else {}
            if not signal_data:
                row.append(Text("-", style="dim"))
                continue

            signal = signal_data.get("signal", "neutral")
            confidence = signal_data.get("confidence", 0.0)
            signal_style = _SIGNAL_STYLES.get(signal, "white")

            cell = Text()
            cell.append(signal.upper(), style=signal_style)
            cell.append(f"\n{confidence:.0f}%", style=_confidence_style(confidence))
            row.append(cell)

        table.add_row(*row)

    console.print()
    console.print(table)
    console.print()


def _format_analyst_name(name: str) -> str:
    """Convert snake_case analyst name to title case."""
    return name.replace("_", " ").title()


# ---------------------------------------------------------------------------
# Risk assessment
# ---------------------------------------------------------------------------


def print_risk_assessment(risk_assessment: dict[str, dict[str, Any]]) -> None:
    """Display risk metrics in a formatted table.

    Parameters
    ----------
    risk_assessment:
        Dict mapping ticker -> risk assessment dict with fields like
        ``remaining_position_limit``, ``volatility_regime``, ``current_var``,
        ``max_drawdown_pct``, ``risk_score``, ``warnings``.
    """
    if not risk_assessment:
        console.print(Panel("[dim]No risk assessment data to display.[/dim]", title="Risk Assessment"))
        return

    table = Table(
        title="Risk Assessment",
        show_header=True,
        header_style="bold white",
        border_style="red",
        show_lines=True,
        expand=False,
    )

    table.add_column("Ticker", style="bold white", min_width=8)
    table.add_column("Regime", min_width=10, justify="center")
    table.add_column("Risk Score", min_width=12, justify="center")
    table.add_column("Position Limit", min_width=14, justify="right")
    table.add_column("VaR (95%)", min_width=12, justify="right")
    table.add_column("Max Drawdown", min_width=13, justify="right")
    table.add_column("Warnings", min_width=20, max_width=50)

    for ticker, assessment in sorted(risk_assessment.items()):
        regime = assessment.get("volatility_regime", "normal")
        risk_score = assessment.get("risk_score", 0.0)
        limit = assessment.get("remaining_position_limit", 0.0)
        var = assessment.get("current_var", 0.0)
        drawdown = assessment.get("max_drawdown_pct", 0.0)
        warnings = assessment.get("warnings", [])

        regime_style = _REGIME_STYLES.get(regime, "white")

        # Risk score colour
        if risk_score >= 70:
            score_style = "bold red"
        elif risk_score >= 40:
            score_style = "yellow"
        else:
            score_style = "green"

        # Warnings text
        warnings_text = "; ".join(warnings) if warnings else "-"
        if len(warnings_text) > 60:
            warnings_text = warnings_text[:57] + "..."

        table.add_row(
            ticker,
            Text(regime.upper(), style=regime_style),
            Text(f"{risk_score:.1f}", style=score_style),
            Text(f"${limit:,.0f}", style="white"),
            Text(f"${var:,.0f}", style="red" if var > 0 else "dim"),
            Text(f"{drawdown:.1f}%", style="red" if drawdown > 15 else "white"),
            Text(warnings_text, style="dim yellow" if warnings else "dim"),
        )

    console.print()
    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# Portfolio summary
# ---------------------------------------------------------------------------


def print_portfolio_summary(portfolio: dict[str, Any]) -> None:
    """Display a comprehensive portfolio state with P&L breakdown.

    Parameters
    ----------
    portfolio:
        Dict with portfolio state fields: ``cash``, ``positions``,
        ``short_positions``, ``margin_used``, ``realized_gains``, etc.
        Can be a serialised :class:`PortfolioState`.
    """
    if not portfolio:
        console.print(Panel("[dim]No portfolio data to display.[/dim]", title="Portfolio"))
        return

    cash = portfolio.get("cash", 0.0)
    positions = portfolio.get("positions", {})
    short_positions = portfolio.get("short_positions", {})
    margin_used = portfolio.get("margin_used", 0.0)
    realized_gains = portfolio.get("realized_gains", 0.0)

    # Compute totals
    long_value = 0.0
    long_pnl = 0.0
    for pos_data in positions.values():
        if isinstance(pos_data, dict):
            shares = pos_data.get("shares", 0)
            current = pos_data.get("current_price", 0)
            entry = pos_data.get("avg_entry_price", 0)
            mv = shares * current
            long_value += mv
            long_pnl += shares * (current - entry)

    short_value = 0.0
    short_pnl = 0.0
    for pos_data in short_positions.values():
        if isinstance(pos_data, dict):
            shares = abs(pos_data.get("shares", 0))
            current = pos_data.get("current_price", 0)
            entry = pos_data.get("avg_entry_price", 0)
            mv = shares * current
            short_value += mv
            short_pnl += shares * (entry - current)  # profit if price fell

    total_equity = cash + long_value - short_value
    total_unrealized = long_pnl + short_pnl
    total_pnl = realized_gains + total_unrealized

    # Summary panel
    summary_lines: list[str] = [
        f"[bold]Cash:[/bold]            ${cash:>14,.2f}",
        f"[bold]Long Value:[/bold]      ${long_value:>14,.2f}",
        f"[bold]Short Value:[/bold]     ${short_value:>14,.2f}",
        f"[bold]Total Equity:[/bold]    ${total_equity:>14,.2f}",
        "",
        f"[bold]Margin Used:[/bold]     ${margin_used:>14,.2f}",
        "",
        f"[bold]Realized P&L:[/bold]    ${realized_gains:>14,.2f}",
        f"[bold]Unrealized P&L:[/bold]  ${total_unrealized:>14,.2f}",
    ]

    pnl_style = "green" if total_pnl >= 0 else "red"
    summary_lines.append(f"[bold]Total P&L:[/bold]       [{pnl_style}]${total_pnl:>14,.2f}[/{pnl_style}]")

    console.print()
    console.print(Panel("\n".join(summary_lines), title="Portfolio Summary", border_style="green"))

    # Positions table
    if positions or short_positions:
        pos_table = Table(
            title="Open Positions",
            show_header=True,
            header_style="bold white",
            border_style="green",
            show_lines=True,
            expand=False,
        )

        pos_table.add_column("Ticker", style="bold white", min_width=8)
        pos_table.add_column("Side", min_width=6, justify="center")
        pos_table.add_column("Shares", min_width=10, justify="right")
        pos_table.add_column("Entry", min_width=10, justify="right")
        pos_table.add_column("Current", min_width=10, justify="right")
        pos_table.add_column("Mkt Value", min_width=12, justify="right")
        pos_table.add_column("P&L", min_width=12, justify="right")
        pos_table.add_column("P&L %", min_width=8, justify="right")

        # Long positions
        for ticker, pos_data in sorted(positions.items()):
            if isinstance(pos_data, dict):
                shares = pos_data.get("shares", 0)
                entry = pos_data.get("avg_entry_price", 0)
                current = pos_data.get("current_price", 0)
                if shares == 0:
                    continue
                mv = shares * current
                pnl = shares * (current - entry)
                pnl_pct = ((current - entry) / entry * 100) if entry > 0 else 0.0
                pnl_style = "green" if pnl >= 0 else "red"

                pos_table.add_row(
                    ticker,
                    Text("LONG", style="green"),
                    f"{shares:,.0f}",
                    f"${entry:,.2f}",
                    f"${current:,.2f}",
                    f"${mv:,.2f}",
                    Text(f"${pnl:,.2f}", style=pnl_style),
                    Text(f"{pnl_pct:+.1f}%", style=pnl_style),
                )

        # Short positions
        for ticker, pos_data in sorted(short_positions.items()):
            if isinstance(pos_data, dict):
                shares = abs(pos_data.get("shares", 0))
                entry = pos_data.get("avg_entry_price", 0)
                current = pos_data.get("current_price", 0)
                if shares == 0:
                    continue
                mv = shares * current
                pnl = shares * (entry - current)
                pnl_pct = ((entry - current) / entry * 100) if entry > 0 else 0.0
                pnl_style = "green" if pnl >= 0 else "red"

                pos_table.add_row(
                    ticker,
                    Text("SHORT", style="magenta"),
                    f"{shares:,.0f}",
                    f"${entry:,.2f}",
                    f"${current:,.2f}",
                    f"${mv:,.2f}",
                    Text(f"${pnl:,.2f}", style=pnl_style),
                    Text(f"{pnl_pct:+.1f}%", style=pnl_style),
                )

        console.print(pos_table)

    # Trade history summary
    trade_history = portfolio.get("trade_history", [])
    if trade_history:
        console.print(f"\n[dim]Trade history: {len(trade_history)} executed trades[/dim]")

    console.print()
