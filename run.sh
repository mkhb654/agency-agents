#!/usr/bin/env bash
# ==============================================================================
# Agency Hedge Fund - Launch Script
#
# Usage:
#   ./run.sh              # Interactive CLI mode
#   ./run.sh cli           # Interactive CLI mode (explicit)
#   ./run.sh api           # Start FastAPI server only
#   ./run.sh web           # Start API server + frontend dev server
#   ./run.sh backtest      # Run backtesting (interactive)
#   ./run.sh analyze       # Run analysis (interactive)
#   ./run.sh help          # Show this help
#
# Environment:
#   Copy .env.example to .env and set your API keys before running.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colours for output
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Colour

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

log_info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

show_help() {
    echo ""
    echo -e "${CYAN}Agency Hedge Fund${NC} - AI-powered multi-agent hedge fund"
    echo ""
    echo "Usage: ./run.sh [command] [options]"
    echo ""
    echo "Commands:"
    echo "  cli           Run the interactive CLI (default)"
    echo "  analyze       Run analysis on tickers"
    echo "  backtest      Run historical backtesting"
    echo "  api           Start the FastAPI server"
    echo "  web           Start API server + frontend"
    echo "  help          Show this help message"
    echo ""
    echo "Options (passed through to the CLI):"
    echo "  -v, --verbose     Enable debug logging"
    echo "  Additional options depend on the command (use --help)"
    echo ""
    echo "Examples:"
    echo "  ./run.sh                                    # Interactive mode"
    echo "  ./run.sh analyze AAPL GOOGL MSFT            # Analyse tickers"
    echo "  ./run.sh backtest AAPL -s 2023-01-01        # Run backtest"
    echo "  ./run.sh api --port 8080                    # Start API on port 8080"
    echo "  ./run.sh web                                # Full stack (API + frontend)"
    echo ""
}

check_python() {
    if command -v python3 &>/dev/null; then
        PYTHON=python3
    elif command -v python &>/dev/null; then
        PYTHON=python
    else
        log_error "Python 3.11+ is required but not found."
        log_error "Install Python: https://www.python.org/downloads/"
        exit 1
    fi

    # Verify version (single invocation instead of three)
    local version_info
    version_info=$($PYTHON -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}'); exit(0 if (v.major, v.minor) >= (3, 11) else 1)") || {
        log_error "Python 3.11+ is required (found $version_info)."
        exit 1
    }

    log_ok "Python $version_info found"
}

check_env() {
    if [[ -f ".env" ]]; then
        log_ok ".env file found"
    elif [[ -f ".env.example" ]]; then
        log_warn "No .env file found. Copying from .env.example"
        cp .env.example .env
        log_warn "Please edit .env with your API keys before running analysis."
    else
        log_warn "No .env file found. Some features may not work without API keys."
    fi
}

install_deps() {
    if [[ -f "pyproject.toml" ]]; then
        if command -v poetry &>/dev/null; then
            if ! poetry check --quiet 2>/dev/null; then
                log_info "Installing Python dependencies with Poetry..."
                poetry install --no-interaction
            else
                log_ok "Dependencies already installed"
            fi
        elif $PYTHON -m pip --version &>/dev/null; then
            # Check if key packages are installed
            if ! $PYTHON -c "import fastapi, rich, pydantic" 2>/dev/null; then
                log_info "Installing Python dependencies with pip..."
                $PYTHON -m pip install -e "." --quiet 2>/dev/null || {
                    log_warn "pip install failed, trying individual packages..."
                    $PYTHON -m pip install fastapi uvicorn rich questionary pydantic pydantic-settings numpy httpx --quiet
                }
            else
                log_ok "Core dependencies already installed"
            fi
        else
            log_error "Neither Poetry nor pip found. Cannot install dependencies."
            exit 1
        fi
    fi
}

# ---------------------------------------------------------------------------
# Command runners
# ---------------------------------------------------------------------------

run_module() {
    local label="$1"; shift
    log_info "Starting $label..."
    echo ""
    $PYTHON -m hedge_fund.main "$@"
}

run_web() {
    log_info "Starting full stack (API + Frontend)..."
    echo ""

    # Start API server in background
    log_info "Starting API server on port 8000..."
    $PYTHON -m hedge_fund.main serve &
    API_PID=$!

    # Give the API server a moment to start
    sleep 2

    # Check if frontend exists
    FRONTEND_DIR="$SCRIPT_DIR/frontend"
    if [[ -d "$FRONTEND_DIR" ]]; then
        cd "$FRONTEND_DIR"

        # Check for package manager and install deps
        if command -v pnpm &>/dev/null; then
            PKG_MGR=pnpm
        elif command -v yarn &>/dev/null; then
            PKG_MGR=yarn
        elif command -v npm &>/dev/null; then
            PKG_MGR=npm
        else
            log_error "No Node.js package manager found (pnpm, yarn, or npm)."
            log_error "Install Node.js: https://nodejs.org/"
            kill "$API_PID" 2>/dev/null || true
            exit 1
        fi

        if [[ ! -d "node_modules" ]]; then
            log_info "Installing frontend dependencies..."
            $PKG_MGR install
        fi

        log_info "Starting frontend dev server..."
        $PKG_MGR run dev &
        FRONTEND_PID=$!

        cd "$SCRIPT_DIR"

        echo ""
        log_ok "Full stack running:"
        log_ok "  API:      http://localhost:8000"
        log_ok "  Frontend: http://localhost:3000"
        log_ok "  API Docs: http://localhost:8000/docs"
        echo ""
        log_info "Press Ctrl+C to stop all services."

        # Wait for either process to exit
        trap 'log_info "Shutting down..."; kill $API_PID $FRONTEND_PID 2>/dev/null; exit 0' INT TERM
        wait -n "$API_PID" "$FRONTEND_PID" 2>/dev/null || true

        # Clean up
        kill "$API_PID" "$FRONTEND_PID" 2>/dev/null || true
    else
        log_warn "Frontend directory not found at $FRONTEND_DIR"
        log_info "Running API server only. API docs at http://localhost:8000/docs"

        trap 'log_info "Shutting down..."; kill $API_PID 2>/dev/null; exit 0' INT TERM
        wait "$API_PID"
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

COMMAND="${1:-}"

# Remove the command from args so the rest can be passed through
if [[ -n "$COMMAND" ]]; then
    shift
fi

# Pre-flight checks
check_python
check_env

case "$COMMAND" in
    ""|cli)
        install_deps
        run_module "interactive CLI" "$@"
        ;;
    analyze)
        install_deps
        run_module "analysis" analyze "$@"
        ;;
    backtest)
        install_deps
        run_module "backtest" backtest "$@"
        ;;
    api)
        install_deps
        run_module "API server" serve "$@"
        ;;
    web)
        install_deps
        run_web "$@"
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        log_error "Unknown command: $COMMAND"
        show_help
        exit 1
        ;;
esac
