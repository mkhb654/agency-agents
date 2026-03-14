"""Progress tracking for the hedge fund analysis pipeline.

Provides a :class:`ProgressTracker` that wraps ``rich.progress.Progress`` to
show per-agent, per-ticker completion status in the terminal.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

logger = logging.getLogger(__name__)

console = Console()


# ---------------------------------------------------------------------------
# Agent display names and style
# ---------------------------------------------------------------------------

_AGENT_DISPLAY_NAMES: dict[str, str] = {
    "ben_graham": "Ben Graham",
    "warren_buffett": "Warren Buffett",
    "peter_lynch": "Peter Lynch",
    "cathie_wood": "Cathie Wood",
    "michael_burry": "Michael Burry",
    "stanley_druckenmiller": "Stan Druckenmiller",
    "risk_manager": "Risk Manager",
    "portfolio_manager": "Portfolio Manager",
}


def _display_name(agent_name: str) -> str:
    """Convert an agent key to a human-readable display name."""
    return _AGENT_DISPLAY_NAMES.get(agent_name, agent_name.replace("_", " ").title())


# ---------------------------------------------------------------------------
# ProgressTracker
# ---------------------------------------------------------------------------


class ProgressTracker:
    """Track and display progress of the hedge fund analysis pipeline.

    Wraps ``rich.progress.Progress`` to provide a convenient API for
    multi-agent, multi-ticker workflows.

    Usage::

        tracker = ProgressTracker(agents=["ben_graham", "risk_manager"],
                                   tickers=["AAPL", "GOOGL"])
        with tracker:
            tracker.start_agent("ben_graham")
            tracker.advance_ticker("ben_graham", "AAPL")
            tracker.advance_ticker("ben_graham", "GOOGL")
            tracker.complete_agent("ben_graham")

    Parameters
    ----------
    agents:
        List of agent names that will run.
    tickers:
        List of ticker symbols being analysed.
    show_tickers:
        If ``True``, create sub-tasks for each ticker within each agent.
    """

    def __init__(
        self,
        agents: Optional[list[str]] = None,
        tickers: Optional[list[str]] = None,
        show_tickers: bool = True,
    ) -> None:
        self._agents = agents or []
        self._tickers = tickers or []
        self._show_tickers = show_tickers

        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=30),
            MofNCompleteColumn(),
            TextColumn("[dim]{task.fields[status]}"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
            expand=False,
        )

        # Maps: agent_name -> TaskID for the top-level agent task
        self._agent_tasks: dict[str, TaskID] = {}
        # Maps: (agent_name, ticker) -> TaskID for per-ticker sub-tasks
        self._ticker_tasks: dict[tuple[str, str], TaskID] = {}
        # Overall pipeline task
        self._pipeline_task: Optional[TaskID] = None

        # Tracking state
        self._completed_agents: set[str] = set()
        self._completed_tickers: dict[str, set[str]] = {}
        self._started = False

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> ProgressTracker:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the progress display and initialise all tasks."""
        if self._started:
            return

        self._progress.start()
        self._started = True

        # Pipeline-level task
        total_steps = len(self._agents)
        self._pipeline_task = self._progress.add_task(
            "Pipeline",
            total=total_steps,
            status="running",
        )

        # Per-agent tasks
        for agent_name in self._agents:
            ticker_count = len(self._tickers) if self._show_tickers else 1
            task_id = self._progress.add_task(
                f"  {_display_name(agent_name)}",
                total=ticker_count,
                status="pending",
            )
            self._agent_tasks[agent_name] = task_id
            self._completed_tickers[agent_name] = set()

        logger.debug(
            "ProgressTracker started: %d agents, %d tickers",
            len(self._agents),
            len(self._tickers),
        )

    def stop(self) -> None:
        """Stop the progress display."""
        if not self._started:
            return

        # Mark pipeline as complete
        if self._pipeline_task is not None:
            self._progress.update(self._pipeline_task, status="done")

        self._progress.stop()
        self._started = False

    # ------------------------------------------------------------------
    # Agent-level tracking
    # ------------------------------------------------------------------

    def start_agent(self, agent_name: str) -> None:
        """Mark an agent as actively running.

        Parameters
        ----------
        agent_name:
            The agent identifier (e.g. ``"ben_graham"``).
        """
        task_id = self._agent_tasks.get(agent_name)
        if task_id is not None:
            self._progress.update(task_id, status="running")
            logger.debug("Agent started: %s", agent_name)

    def complete_agent(self, agent_name: str) -> None:
        """Mark an agent as finished.

        Parameters
        ----------
        agent_name:
            The agent identifier.
        """
        task_id = self._agent_tasks.get(agent_name)
        if task_id is not None:
            # Fill remaining progress
            remaining = len(self._tickers) - len(self._completed_tickers.get(agent_name, set()))
            if remaining > 0:
                self._progress.advance(task_id, advance=remaining)
            self._progress.update(task_id, status="done")

        self._completed_agents.add(agent_name)

        # Advance pipeline
        if self._pipeline_task is not None:
            self._progress.advance(self._pipeline_task)

        logger.debug("Agent completed: %s", agent_name)

    def fail_agent(self, agent_name: str, error: str = "error") -> None:
        """Mark an agent as failed.

        Parameters
        ----------
        agent_name:
            The agent identifier.
        error:
            Short error description to display.
        """
        task_id = self._agent_tasks.get(agent_name)
        if task_id is not None:
            self._progress.update(task_id, status=f"FAILED: {error}")

        # Still advance pipeline to avoid stalling
        if self._pipeline_task is not None:
            self._progress.advance(self._pipeline_task)

        logger.warning("Agent failed: %s — %s", agent_name, error)

    # ------------------------------------------------------------------
    # Ticker-level tracking
    # ------------------------------------------------------------------

    def advance_ticker(self, agent_name: str, ticker: str) -> None:
        """Mark a ticker as completed for a given agent.

        Parameters
        ----------
        agent_name:
            The agent identifier.
        ticker:
            The ticker symbol that was processed.
        """
        if agent_name not in self._completed_tickers:
            self._completed_tickers[agent_name] = set()

        if ticker in self._completed_tickers[agent_name]:
            return  # already counted

        self._completed_tickers[agent_name].add(ticker)

        task_id = self._agent_tasks.get(agent_name)
        if task_id is not None:
            self._progress.advance(task_id)
            completed = len(self._completed_tickers[agent_name])
            total = len(self._tickers)
            pct = (completed / total * 100) if total > 0 else 100
            self._progress.update(
                task_id,
                status=f"{ticker} ({pct:.0f}%)",
            )

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    def add_agent(self, agent_name: str) -> None:
        """Dynamically add an agent to track (after construction).

        Parameters
        ----------
        agent_name:
            The agent identifier.
        """
        if agent_name in self._agent_tasks:
            return  # already tracked

        self._agents.append(agent_name)
        self._completed_tickers[agent_name] = set()

        if self._started:
            ticker_count = len(self._tickers) if self._show_tickers else 1
            task_id = self._progress.add_task(
                f"  {_display_name(agent_name)}",
                total=ticker_count,
                status="pending",
            )
            self._agent_tasks[agent_name] = task_id

            # Update pipeline total
            if self._pipeline_task is not None:
                self._progress.update(self._pipeline_task, total=len(self._agents))

    @property
    def completion_pct(self) -> float:
        """Return overall completion as a percentage (0-100)."""
        if not self._agents:
            return 100.0
        return len(self._completed_agents) / len(self._agents) * 100.0

    @property
    def is_complete(self) -> bool:
        """Return ``True`` if all agents have completed."""
        return len(self._completed_agents) >= len(self._agents)

    def summary(self) -> dict[str, Any]:
        """Return a summary dict of progress state.

        Returns
        -------
        dict
            Keys: ``total_agents``, ``completed_agents``, ``failed_agents``,
            ``completion_pct``, ``per_agent``.
        """
        per_agent: dict[str, dict[str, Any]] = {}
        for agent_name in self._agents:
            completed_tickers = self._completed_tickers.get(agent_name, set())
            per_agent[agent_name] = {
                "completed_tickers": len(completed_tickers),
                "total_tickers": len(self._tickers),
                "is_complete": agent_name in self._completed_agents,
            }

        return {
            "total_agents": len(self._agents),
            "completed_agents": len(self._completed_agents),
            "completion_pct": self.completion_pct,
            "per_agent": per_agent,
        }

    def print_summary(self) -> None:
        """Print a static summary table (useful after progress display stops)."""
        table = Table(
            title="Pipeline Execution Summary",
            show_header=True,
            header_style="bold white",
            border_style="blue",
        )

        table.add_column("Agent", style="bold white", min_width=20)
        table.add_column("Status", min_width=10, justify="center")
        table.add_column("Tickers", min_width=10, justify="center")

        for agent_name in self._agents:
            completed = self._completed_tickers.get(agent_name, set())
            is_done = agent_name in self._completed_agents
            total = len(self._tickers)

            if is_done:
                status = "[green]DONE[/green]"
            elif completed:
                status = f"[yellow]{len(completed)}/{total}[/yellow]"
            else:
                status = "[dim]PENDING[/dim]"

            table.add_row(
                _display_name(agent_name),
                status,
                f"{len(completed)}/{total}",
            )

        console.print()
        console.print(table)
        console.print(
            f"\n[bold]Overall: {self.completion_pct:.0f}% complete "
            f"({len(self._completed_agents)}/{len(self._agents)} agents)[/bold]"
        )
        console.print()
