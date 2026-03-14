"""CLI entry point for the Agency Hedge Fund.

Provides both argument-based and interactive modes for running
analysis, backtesting, and launching the API server.

Usage:
    python -m hedge_fund.main                     # Interactive mode
    python -m hedge_fund.main analyze AAPL GOOGL  # Direct analysis
    python -m hedge_fund.main backtest AAPL --start 2023-01-01
    python -m hedge_fund.main serve               # Start API server
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text
from rich import box

console = Console()

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------

def _setup_logging(verbose: bool = False) -> None:
    """Configure logging with rich handler."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
    )
    # Suppress noisy third-party loggers
    for name in ("httpx", "httpcore", "urllib3", "asyncio"):
        logging.getLogger(name).setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Available analysts (mirrors routes.py)
# ---------------------------------------------------------------------------

ANALYST_CHOICES = {
    "ben_graham": "Ben Graham - Value investing",
    "warren_buffett": "Warren Buffett - Quality moats",
    "peter_lynch": "Peter Lynch - GARP",
    "cathie_wood": "Cathie Wood - Disruptive innovation",
    "michael_burry": "Michael Burry - Contrarian deep-value",
    "stanley_druckenmiller": "Stanley Druckenmiller - Macro-driven",
}

MODEL_CHOICES = {
    "openai": "gpt-4.1",
    "anthropic": "claude-sonnet-4-20250514",
    "google": "gemini-2.0-flash",
    "groq": "llama-3.3-70b-versatile",
    "deepseek": "deepseek-chat",
    "ollama": "llama3.2",
}


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _print_banner() -> None:
    """Print the application banner."""
    banner = Text()
    banner.append("THE AGENCY", style="bold cyan")
    banner.append(" - AI Hedge Fund\n", style="bold white")
    banner.append("Multi-agent analysis powered by LangGraph", style="dim")
    console.print(Panel(banner, border_style="cyan", padding=(1, 2)))


def _print_analysis_results(result: dict, show_reasoning: bool = False) -> None:
    """Display analysis results using rich tables."""
    # Signals table
    signals = result.get("signals", [])
    if signals:
        table = Table(
            title="Analyst Signals",
            box=box.ROUNDED,
            title_style="bold magenta",
            header_style="bold",
        )
        table.add_column("Analyst", style="cyan", min_width=20)
        table.add_column("Ticker", style="white", min_width=8)
        table.add_column("Signal", min_width=10)
        table.add_column("Confidence", justify="right", min_width=12)

        for sig in signals:
            signal_val = sig.get("signal", "neutral")
            if signal_val == "bullish":
                signal_style = "bold green"
            elif signal_val == "bearish":
                signal_style = "bold red"
            else:
                signal_style = "yellow"

            confidence = sig.get("confidence", 0)
            conf_bar = _confidence_bar(confidence)

            table.add_row(
                sig.get("analyst", "Unknown"),
                sig.get("ticker", ""),
                Text(signal_val.upper(), style=signal_style),
                conf_bar,
            )

        console.print(table)
        console.print()

    # Decisions table
    decisions = result.get("decisions", [])
    if decisions:
        table = Table(
            title="Trade Decisions",
            box=box.ROUNDED,
            title_style="bold magenta",
            header_style="bold",
        )
        table.add_column("Ticker", style="white", min_width=8)
        table.add_column("Action", min_width=10)
        table.add_column("Quantity", justify="right", min_width=10)
        table.add_column("Confidence", justify="right", min_width=12)
        table.add_column("Reasoning", max_width=50)

        for dec in decisions:
            action = dec.get("action", "hold")
            action_styles = {
                "buy": "bold green",
                "sell": "bold red",
                "short": "bold red",
                "cover": "bold green",
                "hold": "dim white",
            }

            table.add_row(
                dec.get("ticker", ""),
                Text(action.upper(), style=action_styles.get(action, "white")),
                str(dec.get("quantity", 0)),
                f"{dec.get('confidence', 0):.0f}%",
                dec.get("reasoning", "")[:50],
            )

        console.print(table)

    if show_reasoning and signals:
        for sig in signals:
            reasoning = sig.get("reasoning", {})
            if reasoning:
                console.print(
                    Panel(
                        str(reasoning),
                        title=f"{sig.get('analyst', 'Unknown')} - {sig.get('ticker', '')}",
                        border_style="dim",
                    )
                )


def _print_backtest_results(result: dict) -> None:
    """Display backtest results using rich formatting."""
    metrics = result.get("metrics", {})

    # Summary panel
    final_value = result.get("final_value", 0)
    initial_cash = result.get("initial_cash", 100_000)
    total_return = metrics.get("total_return_pct", 0)

    return_style = "bold green" if total_return >= 0 else "bold red"

    summary_text = Text()
    summary_text.append(f"Initial Capital:  ", style="dim")
    summary_text.append(f"${initial_cash:,.2f}\n", style="white")
    summary_text.append(f"Final Value:      ", style="dim")
    summary_text.append(f"${final_value:,.2f}\n", style=return_style)
    summary_text.append(f"Total Return:     ", style="dim")
    summary_text.append(f"{total_return:+.2f}%\n", style=return_style)
    summary_text.append(f"Annualised Return:", style="dim")
    summary_text.append(f" {metrics.get('annualized_return_pct', 0):+.2f}%\n", style=return_style)
    summary_text.append(f"Period:           ", style="dim")
    summary_text.append(f"{result.get('start_date', '')} -> {result.get('end_date', '')}", style="white")

    console.print(Panel(summary_text, title="Backtest Summary", border_style="cyan", padding=(1, 2)))

    # Risk metrics table
    table = Table(
        title="Risk Metrics",
        box=box.ROUNDED,
        title_style="bold magenta",
        header_style="bold",
    )
    table.add_column("Metric", style="cyan", min_width=20)
    table.add_column("Value", justify="right", min_width=15)

    risk_items = [
        ("Sharpe Ratio", f"{metrics.get('sharpe_ratio', 0):.3f}"),
        ("Sortino Ratio", f"{metrics.get('sortino_ratio', 0):.3f}"),
        ("Calmar Ratio", f"{metrics.get('calmar_ratio', 0):.3f}"),
        ("Max Drawdown", f"{metrics.get('max_drawdown_pct', 0):.2f}%"),
        ("Volatility", f"{metrics.get('volatility_pct', 0):.2f}%"),
    ]

    for name, value in risk_items:
        table.add_row(name, value)

    console.print(table)

    # Trade statistics table
    table = Table(
        title="Trade Statistics",
        box=box.ROUNDED,
        title_style="bold magenta",
        header_style="bold",
    )
    table.add_column("Metric", style="cyan", min_width=20)
    table.add_column("Value", justify="right", min_width=15)

    trade_items = [
        ("Total Trades", str(metrics.get("total_trades", 0))),
        ("Winning Trades", str(metrics.get("winning_trades", 0))),
        ("Losing Trades", str(metrics.get("losing_trades", 0))),
        ("Win Rate", f"{metrics.get('win_rate_pct', 0):.1f}%"),
        ("Profit Factor", f"{metrics.get('profit_factor', 0):.2f}"),
        ("Average Win", f"${metrics.get('avg_win', 0):,.2f}"),
        ("Average Loss", f"${metrics.get('avg_loss', 0):,.2f}"),
        ("Largest Win", f"${metrics.get('largest_win', 0):,.2f}"),
        ("Largest Loss", f"${metrics.get('largest_loss', 0):,.2f}"),
    ]

    for name, value in trade_items:
        table.add_row(name, value)

    console.print(table)

    # Benchmark comparison
    benchmark = result.get("benchmark", {})
    if benchmark:
        table = Table(
            title="Benchmark Comparison (SPY)",
            box=box.ROUNDED,
            title_style="bold magenta",
            header_style="bold",
        )
        table.add_column("Metric", style="cyan", min_width=20)
        table.add_column("Value", justify="right", min_width=15)

        bench_items = [
            ("Benchmark Return", f"{benchmark.get('benchmark_return', 0) * 100:.2f}%"),
            ("Alpha", f"{benchmark.get('alpha', 0) * 100:+.2f}%"),
            ("Beta", f"{benchmark.get('beta', 0):.3f}"),
            ("Information Ratio", f"{benchmark.get('information_ratio', 0):.3f}"),
            ("Correlation", f"{benchmark.get('correlation', 0):.3f}"),
            ("Tracking Error", f"{benchmark.get('tracking_error', 0) * 100:.2f}%"),
        ]

        for name, value in bench_items:
            table.add_row(name, value)

        console.print(table)


def _confidence_bar(confidence: float) -> Text:
    """Create a visual confidence bar."""
    filled = int(confidence / 10)
    empty = 10 - filled

    if confidence >= 70:
        style = "green"
    elif confidence >= 40:
        style = "yellow"
    else:
        style = "red"

    text = Text()
    text.append("=" * filled, style=style)
    text.append("-" * empty, style="dim")
    text.append(f" {confidence:.0f}%", style=style)
    return text


# ---------------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------------

def _interactive_mode() -> None:
    """Run the interactive questionary-based configuration wizard."""
    try:
        import questionary
        from questionary import Style
    except ImportError:
        console.print(
            "[red]questionary package not installed. "
            "Use argument mode or install: pip install questionary[/red]"
        )
        sys.exit(1)

    custom_style = Style([
        ("qmark", "fg:#5f87ff bold"),
        ("question", "fg:#ffffff bold"),
        ("answer", "fg:#00ff5f bold"),
        ("pointer", "fg:#5f87ff bold"),
        ("highlighted", "fg:#5f87ff bold"),
        ("selected", "fg:#00ff5f"),
    ])

    _print_banner()

    # Mode selection
    mode = questionary.select(
        "What would you like to do?",
        choices=[
            questionary.Choice("Run Analysis", value="analyze"),
            questionary.Choice("Run Backtest", value="backtest"),
            questionary.Choice("Start API Server", value="serve"),
        ],
        style=custom_style,
    ).ask()

    if mode is None:
        sys.exit(0)

    if mode == "serve":
        _cmd_serve(host=None, port=None, reload=False)
        return

    # Ticker input
    ticker_input = questionary.text(
        "Enter stock tickers (comma-separated):",
        default="AAPL, GOOGL, MSFT",
        style=custom_style,
    ).ask()

    if ticker_input is None:
        sys.exit(0)

    tickers = [t.strip().upper() for t in ticker_input.split(",") if t.strip()]
    if not tickers:
        console.print("[red]No tickers provided.[/red]")
        sys.exit(1)

    # Date range
    today = date.today()
    default_start = (today - timedelta(days=90)).isoformat()

    start_date = questionary.text(
        "Start date (YYYY-MM-DD):",
        default=default_start if mode == "analyze" else "2023-01-01",
        style=custom_style,
    ).ask()

    end_date = questionary.text(
        "End date (YYYY-MM-DD):",
        default=today.isoformat(),
        style=custom_style,
    ).ask()

    if start_date is None or end_date is None:
        sys.exit(0)

    # Analyst selection
    analyst_choices = [
        questionary.Choice(display, value=key, checked=True)
        for key, display in ANALYST_CHOICES.items()
    ]

    selected_analysts = questionary.checkbox(
        "Select analysts to use:",
        choices=analyst_choices,
        style=custom_style,
    ).ask()

    if selected_analysts is None:
        sys.exit(0)

    if not selected_analysts:
        selected_analysts = list(ANALYST_CHOICES.keys())

    # Model selection
    provider = questionary.select(
        "Select LLM provider:",
        choices=[
            questionary.Choice(f"{p} ({m})", value=p)
            for p, m in MODEL_CHOICES.items()
        ],
        style=custom_style,
    ).ask()

    if provider is None:
        sys.exit(0)

    model_name = MODEL_CHOICES[provider]

    # Show reasoning toggle
    show_reasoning = questionary.confirm(
        "Show detailed analyst reasoning?",
        default=False,
        style=custom_style,
    ).ask()

    if show_reasoning is None:
        sys.exit(0)

    # Mode-specific options
    if mode == "backtest":
        step_str = questionary.text(
            "Step size in months:",
            default="1",
            style=custom_style,
        ).ask()
        step_months = int(step_str) if step_str else 1

        cash_str = questionary.text(
            "Initial cash ($):",
            default="100000",
            style=custom_style,
        ).ask()
        initial_cash = float(cash_str) if cash_str else 100_000.0

        _cmd_backtest(
            tickers=tickers,
            start_date=start_date,
            end_date=end_date,
            step_months=step_months,
            initial_cash=initial_cash,
            analysts=selected_analysts,
            model_name=model_name,
            model_provider=provider,
        )
    else:
        _cmd_analyze(
            tickers=tickers,
            start_date=start_date,
            end_date=end_date,
            analysts=selected_analysts,
            model_name=model_name,
            model_provider=provider,
            show_reasoning=show_reasoning,
        )


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------

def _cmd_analyze(
    tickers: list[str],
    start_date: str,
    end_date: str,
    analysts: Optional[list[str]] = None,
    model_name: str = "gpt-4.1",
    model_provider: str = "openai",
    show_reasoning: bool = False,
) -> None:
    """Run analysis and display results."""
    console.print()
    console.print(
        f"[bold cyan]Analysing {len(tickers)} ticker(s):[/bold cyan] "
        f"{', '.join(tickers)}"
    )
    console.print(f"[dim]Period: {start_date} -> {end_date}[/dim]")
    console.print(f"[dim]Model: {model_provider}/{model_name}[/dim]")
    console.print(f"[dim]Analysts: {', '.join(analysts or list(ANALYST_CHOICES.keys()))}[/dim]")
    console.print()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Running analysis...", total=None)

        try:
            from hedge_fund.graph.workflow import run_hedge_fund  # type: ignore[import-not-found]

            result = run_hedge_fund(
                tickers=tickers,
                start_date=start_date,
                end_date=end_date,
                selected_analysts=analysts,
                model_name=model_name,
                model_provider=model_provider,
            )

            progress.update(task, completed=100, total=100)

            if isinstance(result, dict):
                # run_hedge_fund may return:
                #   - {ticker: TradeDecision} directly
                #   - {"decisions": [...], "analyst_signals": {...}} full state
                # Normalise for display
                if "decisions" in result or "signals" in result:
                    display_result = result
                else:
                    # Convert {ticker: decision} to display format
                    decisions_list = []
                    for ticker_key, dec in result.items():
                        if isinstance(dec, dict):
                            dec.setdefault("ticker", ticker_key)
                            decisions_list.append(dec)
                        elif hasattr(dec, "action"):
                            decisions_list.append({
                                "action": dec.action,
                                "ticker": getattr(dec, "ticker", ticker_key),
                                "quantity": getattr(dec, "quantity", 0),
                                "confidence": getattr(dec, "confidence", 0),
                                "reasoning": getattr(dec, "reasoning", ""),
                            })
                    display_result = {"decisions": decisions_list, "signals": []}
                _print_analysis_results(display_result, show_reasoning)
            else:
                console.print("[yellow]Analysis returned unexpected format.[/yellow]")

        except ImportError:
            progress.update(task, completed=100, total=100)
            console.print(
                Panel(
                    "[yellow]The graph module (hedge_fund.graph.workflow) could not be loaded.\n"
                    "This may be due to missing dependencies (langgraph, langchain).\n\n"
                    "Install with: pip install langgraph langchain langchain-openai[/yellow]",
                    title="Module Not Available",
                    border_style="yellow",
                )
            )
            # Show placeholder
            _print_analysis_results({
                "signals": [],
                "decisions": [
                    {"action": "hold", "ticker": t, "quantity": 0, "confidence": 0, "reasoning": "Awaiting implementation"}
                    for t in tickers
                ],
            })

        except Exception as exc:
            progress.update(task, completed=100, total=100)
            console.print(f"[bold red]Analysis failed:[/bold red] {exc}")
            logging.getLogger(__name__).error("Analysis error", exc_info=True)


def _cmd_backtest(
    tickers: list[str],
    start_date: str,
    end_date: str,
    step_months: int = 1,
    initial_cash: float = 100_000.0,
    analysts: Optional[list[str]] = None,
    model_name: str = "gpt-4.1",
    model_provider: str = "openai",
) -> None:
    """Run a backtest and display results."""
    from hedge_fund.backtesting.engine import BacktestEngine

    console.print()
    console.print("[bold cyan]Starting Backtest[/bold cyan]")
    console.print(f"[dim]Tickers: {', '.join(tickers)}[/dim]")
    console.print(f"[dim]Period: {start_date} -> {end_date} (step={step_months}mo)[/dim]")
    console.print(f"[dim]Capital: ${initial_cash:,.2f}[/dim]")
    console.print(f"[dim]Model: {model_provider}/{model_name}[/dim]")
    console.print()

    engine = BacktestEngine(initial_cash=initial_cash)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Running backtest...", total=100)

        def on_progress(step: int, total: int, message: str) -> None:
            pct = (step / total * 100) if total > 0 else 0
            progress.update(task, completed=pct, description=message)

        engine.set_progress_callback(on_progress)

        try:
            result = engine.run(
                tickers=tickers,
                start_date=start_date,
                end_date=end_date,
                step_months=step_months,
                selected_analysts=analysts,
                model_name=model_name,
                model_provider=model_provider,
            )

            progress.update(task, completed=100)

        except Exception as exc:
            progress.update(task, completed=100)
            console.print(f"[bold red]Backtest failed:[/bold red] {exc}")
            logging.getLogger(__name__).error("Backtest error", exc_info=True)
            return

    console.print()
    _print_backtest_results(result.to_dict())

    # Trade log
    if result.trade_history:
        console.print()
        table = Table(
            title="Trade Log",
            box=box.SIMPLE,
            title_style="bold magenta",
            header_style="bold",
        )
        table.add_column("Date", style="dim", min_width=12)
        table.add_column("Action", min_width=8)
        table.add_column("Ticker", style="white", min_width=8)
        table.add_column("Shares", justify="right", min_width=8)
        table.add_column("Price", justify="right", min_width=10)
        table.add_column("P&L", justify="right", min_width=12)

        for trade in result.trade_history[-20:]:  # Show last 20 trades
            action_styles = {
                "buy": "green",
                "sell": "red",
                "short": "red",
                "cover": "green",
            }
            pnl_str = f"${trade.realized_pnl:+,.2f}" if trade.realized_pnl != 0 else "-"
            pnl_style = "green" if trade.realized_pnl > 0 else "red" if trade.realized_pnl < 0 else "dim"

            table.add_row(
                trade.date,
                Text(trade.action.upper(), style=action_styles.get(trade.action, "white")),
                trade.ticker,
                str(trade.shares),
                f"${trade.price:,.2f}",
                Text(pnl_str, style=pnl_style),
            )

        if len(result.trade_history) > 20:
            console.print(f"[dim](Showing last 20 of {len(result.trade_history)} trades)[/dim]")

        console.print(table)


def _cmd_serve(
    host: Optional[str] = None,
    port: Optional[int] = None,
    reload: bool = False,
) -> None:
    """Start the API server."""
    console.print()
    console.print("[bold cyan]Starting Agency Hedge Fund API Server[/bold cyan]")

    from hedge_fund.api.server import serve
    serve(host=host, port=port, reload=reload)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="hedge-fund",
        description="Agency Hedge Fund - AI-powered multi-agent analysis and backtesting",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose/debug logging.",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- analyze ---
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Run AI analysis on stock tickers.",
    )
    analyze_parser.add_argument(
        "tickers",
        nargs="+",
        help="Stock ticker symbols (e.g., AAPL GOOGL MSFT).",
    )
    analyze_parser.add_argument(
        "--start-date", "-s",
        default=None,
        help="Start date (YYYY-MM-DD). Default: 3 months ago.",
    )
    analyze_parser.add_argument(
        "--end-date", "-e",
        default=None,
        help="End date (YYYY-MM-DD). Default: today.",
    )
    analyze_parser.add_argument(
        "--analysts", "-a",
        nargs="*",
        default=None,
        help="Analyst names to use. Default: all.",
    )
    analyze_parser.add_argument(
        "--model",
        default="gpt-4.1",
        help="LLM model name (default: gpt-4.1).",
    )
    analyze_parser.add_argument(
        "--provider",
        default="openai",
        choices=list(MODEL_CHOICES.keys()),
        help="LLM provider (default: openai).",
    )
    analyze_parser.add_argument(
        "--show-reasoning",
        action="store_true",
        help="Show detailed analyst reasoning.",
    )

    # --- backtest ---
    backtest_parser = subparsers.add_parser(
        "backtest",
        help="Run a historical backtest.",
    )
    backtest_parser.add_argument(
        "tickers",
        nargs="+",
        help="Stock ticker symbols.",
    )
    backtest_parser.add_argument(
        "--start-date", "-s",
        required=True,
        help="Backtest start date (YYYY-MM-DD).",
    )
    backtest_parser.add_argument(
        "--end-date", "-e",
        default=None,
        help="Backtest end date (YYYY-MM-DD). Default: today.",
    )
    backtest_parser.add_argument(
        "--step-months",
        type=int,
        default=1,
        help="Months per analysis window (default: 1).",
    )
    backtest_parser.add_argument(
        "--cash",
        type=float,
        default=100_000.0,
        help="Initial cash balance (default: 100000).",
    )
    backtest_parser.add_argument(
        "--analysts", "-a",
        nargs="*",
        default=None,
        help="Analyst names to use.",
    )
    backtest_parser.add_argument(
        "--model",
        default="gpt-4.1",
        help="LLM model name.",
    )
    backtest_parser.add_argument(
        "--provider",
        default="openai",
        choices=list(MODEL_CHOICES.keys()),
        help="LLM provider.",
    )

    # --- serve ---
    serve_parser = subparsers.add_parser(
        "serve",
        help="Start the API server.",
    )
    serve_parser.add_argument(
        "--host",
        default=None,
        help="Bind host (default: from settings).",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Bind port (default: from settings).",
    )
    serve_parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development.",
    )

    return parser


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Main CLI entry point for the Agency Hedge Fund."""
    parser = _build_parser()
    args = parser.parse_args()

    _setup_logging(verbose=getattr(args, "verbose", False))

    if args.command is None:
        # No subcommand: run interactive mode
        _interactive_mode()
        return

    today = date.today()

    if args.command == "analyze":
        tickers = [t.upper() for t in args.tickers]
        start_date = args.start_date or (today - timedelta(days=90)).isoformat()
        end_date = args.end_date or today.isoformat()

        _print_banner()
        _cmd_analyze(
            tickers=tickers,
            start_date=start_date,
            end_date=end_date,
            analysts=args.analysts,
            model_name=args.model,
            model_provider=args.provider,
            show_reasoning=args.show_reasoning,
        )

    elif args.command == "backtest":
        tickers = [t.upper() for t in args.tickers]
        end_date = args.end_date or today.isoformat()

        _print_banner()
        _cmd_backtest(
            tickers=tickers,
            start_date=args.start_date,
            end_date=end_date,
            step_months=args.step_months,
            initial_cash=args.cash,
            analysts=args.analysts,
            model_name=args.model,
            model_provider=args.provider,
        )

    elif args.command == "serve":
        _print_banner()
        _cmd_serve(
            host=args.host,
            port=args.port,
            reload=args.reload,
        )


if __name__ == "__main__":
    main()
