# Codebase Research: agency-agents-main

**Date:** 2026-03-16
**Scope:** Full repository documentation as-is

---

## Summary

This repository contains four distinct systems: (1) **The Agency** — 102 specialized AI agent prompt files across 11 divisions, (2) **Hedge Fund** — a LangGraph multi-agent stock analysis system with React 19 frontend and FastAPI backend, (3) **MRO Parts Arbitrage** — a government-data-powered aviation parts intelligence system with a sales pipeline CRM, and (4) **Logistics Pricing** — an AutoResearch-style autonomous ML experiment framework for freight quoting. Supporting infrastructure includes shell scripts for agent linting/conversion/installation, CI via GitHub Actions, integrations for 8 AI coding tools, and research documents on RLVR and MRO data sources.

---

## 1. Agent Definitions (102 Agents)

The core content of the repo. Each agent is a Markdown file with YAML frontmatter (`name`, `description`, `color`) followed by structured sections.

### Division Breakdown

| Division | Path | Count | Examples |
|----------|------|-------|----------|
| Design | `design/` | 8 | brand-guardian, ui-designer, ux-architect, visual-storyteller, whimsy-injector, image-prompt-engineer, inclusive-visuals-specialist, ux-researcher |
| Engineering | `engineering/` | 14 | frontend-developer, backend-architect, ai-engineer, security-engineer, devops-automator, embedded-firmware-engineer, mobile-app-builder, rapid-prototyper, technical-writer, senior-developer, data-engineer, incident-response-commander, threat-detection-engineer, autonomous-optimization-architect |
| Marketing | `marketing/` | 13 | growth-hacker, seo-specialist, content-creator, tiktok-strategist, instagram-curator, twitter-engager, reddit-community-builder, social-media-strategist, app-store-optimizer, carousel-growth-engine, wechat-official-account, xiaohongshu-specialist, zhihu-strategist |
| Product | `product/` | 4 | sprint-prioritizer, trend-researcher, behavioral-nudge-engine, feedback-synthesizer |
| Project Mgmt | `project-management/` | 6 | project-shepherd, studio-operations, studio-producer, experiment-tracker, jira-workflow-steward, senior-project-manager |
| Spatial | `spatial-computing/` | 6 | visionos-spatial-engineer, xr-immersive-developer, xr-interface-architect, xr-cockpit-interaction-specialist, macos-spatial-metal-engineer, terminal-integration-specialist |
| Specialized | `specialized/` | 14 | agents-orchestrator, zk-steward, accounts-payable-agent, compliance-auditor, data-analytics-reporter, data-consolidation-agent, identity-graph-operator, lsp-index-engineer, report-distribution-agent, sales-data-extraction-agent, cultural-intelligence-strategist, developer-advocate, model-qa |
| Strategy | `strategy/` | 1 | nexus-strategy (+ EXECUTIVE-BRIEF.md, QUICKSTART.md) |
| Support | `support/` | 6 | analytics-reporter, executive-summary-generator, finance-tracker, infrastructure-maintainer, legal-compliance-checker, support-responder |
| Testing | `testing/` | 8 | accessibility-auditor, api-tester, evidence-collector, performance-benchmarker, reality-checker, test-results-analyzer, tool-evaluator, workflow-optimizer |
| Game Dev | `game-development/` | 19 | 5 root (game-designer, level-designer, narrative-designer, technical-artist, game-audio-engineer) + engine subdirs below |

### Game Development Sub-Directories

| Engine | Path | Count | Agents |
|--------|------|-------|--------|
| Unity | `game-development/unity/` | 4 | unity-architect, unity-editor-tool-developer, unity-multiplayer-engineer, unity-shader-graph-artist |
| Unreal | `game-development/unreal-engine/` | 4 | unreal-multiplayer-architect, unreal-systems-engineer, unreal-technical-artist, unreal-world-builder |
| Godot | `game-development/godot/` | 3 | godot-gameplay-scripter, godot-multiplayer-engineer, godot-shader-developer |
| Roblox | `game-development/roblox-studio/` | 3 | roblox-avatar-creator, roblox-experience-designer, roblox-systems-scripter |

### Agent File Format

Required YAML frontmatter: `name`, `description`, `color`. Optional field: `tools` (observed in marketing agents, e.g., `"WebFetch, WebSearch, Read, Write, Edit"`). Recommended body sections: Identity & Memory, Core Mission, Critical Rules, Technical Deliverables, Workflow Process, Communication Style, Learning & Memory, Success Metrics. Linter warns on missing sections, errors on missing frontmatter fields.

### Multi-Agent Workflow Examples (`examples/`)

| File | Description |
|------|-------------|
| `nexus-spatial-discovery.md` | 8 agents working in parallel for product discovery |
| `workflow-landing-page.md` | Landing page creation workflow |
| `workflow-startup-mvp.md` | Idea to shipped MVP coordination |
| `workflow-with-memory.md` | Memory-integrated workflow demonstration |

---

## 2. Hedge Fund System

**Path:** `hedge_fund/`
**Stack:** Python 3.11+, FastAPI, LangGraph, LangChain, Pydantic 2.0, SQLAlchemy 2.0

### Architecture

Multi-agent investment analysis system. Specialized analyst agents run in parallel via LangGraph StateGraph, followed by a rule-based risk manager and an LLM-powered portfolio manager.

### LangGraph Workflow (`graph/workflow.py`)

```
START → start_node → [analyst_1, analyst_2, ..., analyst_N] (parallel fan-out)
      → risk_manager_agent (fan-in) → portfolio_manager_agent → END
```

**State** (`graph/state.py`): TypedDict `AgentState` with `data` (merge_dicts reducer), `messages` (list, operator.add), `metadata` (merge_dicts).

### Module Map

| Module | Key File | Purpose |
|--------|----------|---------|
| Entry | `__main__.py`, `main.py` (~900 lines) | CLI: interactive wizard or argument mode (analyze, backtest, serve) |
| Config | `config.py` (~171 lines) | Pydantic Settings — LLM provider enum, API keys, portfolio defaults |
| Agents | `agents/*.py` (13 files) | Investment strategy agents (see table below) |
| Graph | `graph/workflow.py` (~420 lines) | LangGraph state machine, analyst registry, fan-out/fan-in |
| Graph | `graph/state.py` (~190 lines) | AgentState TypedDict definition |
| Data | `data/api.py` (~500 lines) | FinancialDataClient — async httpx client for financialdatasets.ai |
| Data | `data/crawler.py` (~650 lines) | FreeCrawler — yfinance-based free alternative (no API key) |
| Data | `data/cache.py` (~380 lines) | TTL-based in-memory cache, singleton, thread-safe, LRU eviction (10K max) |
| Data | `data/models.py` (~450 lines) | Pydantic models: Price, FinancialMetrics, AnalystSignal, Position, PortfolioState, RiskAssessment, TradeDecision |
| LLM | `llm/models.py` (~380 lines) | Multi-provider factory: OpenAI, Anthropic, Google, Groq, DeepSeek, Ollama |
| API | `api/server.py` | FastAPI app factory, CORS, lifespan handler |
| API | `api/routes.py` (~800 lines) | REST endpoints + WebSocket streaming |
| Backtest | `backtesting/engine.py` | Historical simulation engine with SPY benchmark comparison |
| Backtest | `backtesting/portfolio.py` | Portfolio state (buy/sell/short/cover) |
| Backtest | `backtesting/metrics.py` | Sharpe, Sortino, max drawdown, win rate |
| Utils | `utils/display.py`, `utils/progress.py` | Rich console formatting, progress tracking |

### Agent List

| File | Style | Type |
|------|-------|------|
| `agents/warren_buffett.py` | Quality moats, intrinsic value | LLM persona |
| `agents/ben_graham.py` | Deep value, margin of safety | LLM persona |
| `agents/peter_lynch.py` | Growth at reasonable price (GARP) | LLM persona |
| `agents/michael_burry.py` | Contrarian deep-value | LLM persona |
| `agents/cathie_wood.py` | Disruptive innovation | LLM persona |
| `agents/stanley_druckenmiller.py` | Global macro, momentum | LLM persona |
| `agents/fundamentals.py` | Financial statement analysis | LLM analytical |
| `agents/technicals.py` | RSI, MACD, moving averages | LLM analytical |
| `agents/sentiment.py` | News/social sentiment | LLM analytical |
| `agents/valuation.py` | DCF, P/E, EV/EBITDA | LLM analytical |
| `agents/macro.py` | Macroeconomic environment | LLM analytical |
| `agents/risk_manager.py` (~550 lines) | Volatility, VaR, drawdown, correlation | **Pure rule-based (no LLM)** |
| `agents/portfolio_manager.py` (~600 lines) | Trade decisions, constraint enforcement | **LLM + deterministic constraints** |

### LLM Provider Configuration (`config.py`)

| Provider | Default Model | Endpoint |
|----------|--------------|----------|
| OpenAI | `gpt-4.1` | OpenAI API |
| Anthropic | `claude-sonnet-4-20250514` | Anthropic API |
| Google | `gemini-2.0-flash` | Google API |
| Groq | `llama-3.3-70b-versatile` | Groq API |
| DeepSeek | `deepseek-chat` | DeepSeek API |
| Ollama | `llama3.2` | localhost:11434 |

### API Endpoints (`api/routes.py`)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/health` | GET | Health check |
| `/api/analysts` | GET | List available analysts |
| `/api/models` | GET | List LLM models |
| `/api/analyze` | POST | Async analysis (returns task_id) |
| `/api/backtest` | POST | Async backtest (returns task_id) |
| `/api/tasks/{task_id}` | GET | Poll task status |
| `/api/portfolio` | GET | Current portfolio state |
| `/ws/analysis` | WS | Subscribe to task progress |

### Execution Flow

1. User provides tickers, date range, analyst selection, model choice
2. LangGraph workflow fans out to selected analysts (parallel)
3. Each analyst calls LLM via `call_llm()` → returns `AnalystSignal` (signal, confidence, reasoning)
4. Risk manager (rule-based) computes per-ticker limits: volatility regime, VaR, drawdown, position caps
5. Portfolio manager (LLM) makes trade decisions within deterministic constraints
6. Decisions validated and clamped before output

---

## 3. Frontend Application

**Path:** `frontend/`
**Stack:** React 19, TypeScript 5.7, Vite 6, Tailwind CSS 4, Recharts, Lucide icons

### Components

| Component | Purpose |
|-----------|---------|
| `src/App.tsx` | Root component |
| `src/components/Dashboard.tsx` (~500 lines) | Main analysis view, agent selection |
| `src/components/BacktestView.tsx` (~700 lines) | Backtest execution, equity curves |
| `src/components/PortfolioView.tsx` (~400 lines) | Portfolio holdings, P&L |
| `src/components/AgentPanel.tsx` (~300 lines) | Agent signal cards, confidence, reasoning |
| `src/components/TickerInput.tsx` (~150 lines) | Ticker input with validation |
| `src/components/SignalBadge.tsx` (~60 lines) | Bullish/bearish/neutral indicator |
| `src/components/MetricCard.tsx` (~100 lines) | Metric display card |
| `src/hooks/useAnalysis.ts` | Analysis state hook |
| `src/lib/api.ts` (~450 lines) | HTTP + WebSocket client (REST polling, WS streaming) |
| `src/types/index.ts` (~280 lines) | TypeScript interfaces for all API types |

---

## 4. MRO Arbitrage System

**Path:** `mro-arbitrage/`
**Language:** Python (stdlib + urllib + scikit-learn)

### Scripts

| File | Lines | Purpose |
|------|-------|---------|
| `run_all.py` | 75 | Pipeline orchestrator — runs all scripts sequentially with timeouts |
| `web_dashboard.py` | 830+ | Full web dashboard (localhost:5050) — KPIs, heatmap, suppliers, deals |
| `dashboard.py` | 290 | CLI intelligence dashboard |
| `lookup_part.py` | 421 | Universal part lookup — queries 8 sources per part |
| `deal_calculator.py` | 292 | Interactive P&L calculator with quick mode |
| `arbitrage_detector.py` | 336 | Identifies 6 arbitrage strategy types |
| `ingest_usaspending.py` | 365 | Government contract pricing via USAspending.gov API |
| `ingest_faa_registry.py` | 245 | FAA Aircraft Registry (370K aircraft CSV) |
| `ingest_sdr.py` | 443 | Demand signals from SDR failure patterns |
| `ingest_ebay.py` | 268 | Market price validation via eBay |
| `monitor_ads.py` | 217 | AD-driven mandatory parts demand |
| `build_price_db.py` | 225 | Parts pricing database from USAspending (51 part queries) |
| `supplier_directory.py` | 225 | Supplier directory from government contracts |
| `analyze_sec_filings.py` | 225 | SEC filing analysis (TransDigm, HEICO, FTAI) |
| `analyze_trade_flows.py` | 250 | Trade flow analysis |

### Data Files (`data/`)

| File | Records | Source |
|------|---------|--------|
| `usaspending_aviation_awards.json` | 300 | USAspending.gov |
| `parts_price_database.json` / `.csv` | 76-77 | USAspending.gov (51 queries) |
| `demand_signals.json` | 15 | SDR failure rate analysis |
| `arbitrage_scorecard.json` | 15 | Composite profit ranking |
| `ad_demand_analysis.json` | 6 | Active ADs ($604M demand) |
| `ebay_price_validation.json` | 14 | eBay market checks |
| `arbitrage_opportunities.json` | 21 | 3 signal types |
| `supplier_directory.json` | 69 | Government contract suppliers |
| `competitive_intelligence.json` | — | TransDigm/HEICO/FTAI data |
| `engine_maintenance_research.json` | — | Engine shop visit economics |
| `pma_landscape_research.json` | — | PMA market ($11.4B) |
| `trade_flow_analysis.json` | — | Geographic trade corridors |

### Sales Pipeline (`pipeline/`)

| Path | Content |
|------|---------|
| `pipeline/README.md` | Quick reference for Monday morning execution |
| `pipeline/MASTER-RANKING.md` | 36 contacts ranked (Play 1: Buy/Sell Parts, Play 2: AI Development) — $1.09M-$1.7M pipeline |
| `pipeline/PITCH-SCRIPT.md` | Pitch framework: 3-min version, Q&A responses, key numbers, delivery notes |
| `pipeline/allclear/ACTION-PLAN.md` | AllClear Aerospace ($225K opportunity) — Raul (VP), Bill Boucek (CEO), on-prem architecture, competitive analysis vs SalesPatriot/SalesEdge |
| `pipeline/allclear/VIDEO-SCRIPT-4MIN.md` | 4-minute Loom video script for AllClear team |
| `pipeline/tier-1-close-this-month/` | AllClear, Metals Distribution (Ryan), Defense Company |
| `pipeline/tier-2-build-this-month/` | Sophia, Gary/Steve, Paul, Flyline, Dubai/Saudi |
| `pipeline/tier-3-nurture/` | French CEVA retiree, Time-Critical Logistics |
| `pipeline/air-med-aviation/` | Moulay Boufous (chairman) |

### CRM Documents

| File | Lines | Content |
|------|-------|---------|
| `CONTACTS-AND-PIPELINE.md` | 800+ | 36 contacts from MRO Conference (Miami, March 2026), tiered by priority, with email/text templates |
| `CONTACT-RESEARCH.md` | 500+ | Deep research on 26 companies — revenue, employees, AI status, strategy |

### Data Flow

```
USAspending API → ingest_usaspending.py → usaspending_aviation_awards.json
                  build_price_db.py      → parts_price_database.json
                                          supplier_directory.json
FAA SDR data    → ingest_sdr.py         → demand_signals.json
                                          arbitrage_scorecard.json
FAA AD data     → monitor_ads.py        → ad_demand_analysis.json
eBay search     → ingest_ebay.py        → ebay_price_validation.json
All above       → arbitrage_detector.py → arbitrage_opportunities.json
All above       → web_dashboard.py      → localhost:5050
All above       → lookup_part.py        → (interactive terminal)
```

---

## 5. Logistics Pricing System

**Path:** `logistics-pricing/`
**Stack:** Python (scikit-learn, numpy, pandas, xgboost optional)

### Files

| File | Purpose |
|------|---------|
| `prepare.py` | **IMMUTABLE** — Data loading, 26-feature engineering, COVID regime detection (rolling MA crossover), train/test split, verifiable evaluation function (MAPE + win rate + margin composite) |
| `pricing_model.py` | **AGENT MODIFIES** — Algorithm selection (XGBoost/LightGBM/Ridge/GradientBoosting/Ensemble), hyperparameters, feature selection, recency weighting |
| `generate_sample_data.py` | Generates 15,000 synthetic freight quotes with COVID regimes, seasonality, 15 lanes, win/loss outcomes |
| `program.md` | 5-phase AutoResearch program: baseline → time weighting → features → hyperparams → advanced |

### Processed Data (`processed/`)

| File | Description |
|------|-------------|
| `X_train.npy` | Training features (13,471 x 26) |
| `X_test.npy` | Test features (1,529 x 26) |
| `y_train.npy` / `y_test.npy` | Target (quoted price) |
| `w_train.npy` | Recency weights (exponential decay, 180-day half-life) |
| `test_actual_cost.npy` / `test_won.npy` | Margin/win evaluation data |
| `meta.json` | Feature names, split sizes, regime changes detected |
| `results.tsv` | Experiment log |

### Baseline Result

GradientBoosting with recency weighting: **4.72% MAPE, 60.2% win rate, 10.8% margin** (composite score -15.5). Ridge regression comparison: 9.55% MAPE (2x worse, score -3.1).

---

## 6. Research Documents

| File | Content |
|------|---------|
| `RLVR-research.md` (1,367 lines) | Comprehensive RLVR survey — 25 sections, 40+ sources. Covers GRPO algorithm, 8 variant algorithms (DAPO, Dr.GRPO, GSPO, CISPO, SAPO, RSPO, GMPO), JustRL recipe, DeepSeek-R1, distillation, efficiency vs intelligence debate, multi-turn agentic RL, safety, scaling laws, AutoResearch pattern, logistics pricing application |
| `MRO-data-sources.md` (241 lines) | 22 aviation MRO data sources tiered by access level (6 free Tier 1, 7 free Tier 2, 4 paid Tier 3, 5 scrapable Tier 4). Pipeline architecture: 5 layers (fleet, demand, pricing, supply, intelligence) |
| `docs/repit/research/rlvr-white-paper-research.md` | RLVR white paper survey — 31 papers across 16 sections. DeepSeek-R1 through LongRLVR (March 2026) |

---

## 7. Shell Scripts & CI

### Scripts

| Script | Path | Purpose |
|--------|------|---------|
| `lint-agents.sh` | `scripts/` (117 lines) | Validates agent frontmatter (3 required fields) and body structure (warns on missing sections, short bodies). Scans 12 agent directories. |
| `convert.sh` | `scripts/` (357 lines) | Converts agents to tool-specific formats: antigravity (`SKILL.md`), gemini-cli (extension + `SKILL.md`), opencode (`.md`), cursor (`.mdc`), aider (`CONVENTIONS.md`), windsurf (`.windsurfrules`) |
| `install.sh` | `scripts/` (492 lines) | Installs agents into local tool configs. Supports 8 tools: claude-code, copilot, antigravity, gemini-cli, opencode, cursor, aider, windsurf. Interactive selector UI with auto-detection. |
| `run.sh` | root (246 lines) | Launch script for hedge fund: `cli`, `api`, `web`, `backtest`, `analyze` modes. Checks Python 3.11+, manages deps via Poetry/pip, frontend via pnpm/yarn/npm. |

### CI (`.github/workflows/lint-agents.yml`)

Triggers on PRs touching agent directories. Runs `lint-agents.sh` on changed files only (uses `git diff --name-only --diff-filter=ACMR`).

### GitHub Templates

- `.github/ISSUE_TEMPLATE/bug-report.yml` — Fields: agent-file, description, suggestion
- `.github/ISSUE_TEMPLATE/new-agent-request.yml` — Fields: agent-name, category dropdown, description, use-cases
- `.github/PULL_REQUEST_TEMPLATE.md` — Checklist: template compliance, YAML, examples, testing

---

## 8. Integrations (`integrations/`)

| Tool | Install Target | Format | Notes |
|------|---------------|--------|-------|
| Claude Code | `~/.claude/agents/` | Source `.md` (direct) | No conversion needed |
| GitHub Copilot | `~/.github/agents/` | Source `.md` (direct) | No conversion needed |
| Antigravity | `~/.gemini/antigravity/skills/` | `SKILL.md` per agent | risk/source/date_added fields |
| Gemini CLI | `~/.gemini/extensions/agency-agents/` | `skills/<slug>/SKILL.md` + `gemini-extension.json` manifest | Extension format |
| OpenCode | `.opencode/agent/` (project) | `.md` per agent | color field preserved |
| Cursor | `.cursor/rules/` (project) | `.mdc` per agent | globs/alwaysApply fields |
| Aider | `CONVENTIONS.md` (project) | Single consolidated file | All agents accumulated |
| Windsurf | `.windsurfrules` (project) | Single consolidated file | All agents accumulated |

Additional: `integrations/mcp-memory/` — MCP memory integration guide with setup script and example agent.

---

## 9. Configuration Files

| File | Key Contents |
|------|-------------|
| `pyproject.toml` | Name: `agency-hedge-fund`, Python ^3.11, deps: langchain, langgraph, fastapi, pydantic, httpx, pandas, numpy, rich, questionary. Dev: pytest, ruff, mypy. Ruff: line 120, target py311. |
| `frontend/package.json` | React 19, Recharts, Lucide, Tailwind CSS 4, Vite 6, TypeScript 5.7 |
| `.env.example` | LLM_PROVIDER, API keys (5 providers), FINANCIAL_DATASETS_API_KEY, portfolio defaults (100K cash, 50% margin, 25% max position), cache TTL 3600s, API port 8000, SQLite default DB |
| `.gitignore` | Python, Node.js, secrets, editors, logs, generated integrations |
| `.gitattributes` | LF line endings for `.md`, `.yml`, `.yaml`, `.sh` |
| `skills-lock.json` | External skill: `agent-browser` from `vercel-labs/agent-browser` with hash |
| `.claude/settings.local.json` | Permission config for Claude Code sessions |

---

## 10. Cross-Component Connections

1. **Hedge Fund ↔ Frontend:** `hedge_fund/api/server.py` serves REST + WebSocket endpoints consumed by `frontend/src/lib/api.ts`. Frontend renders agent analyses, portfolio, backtest results with Recharts equity curves.

2. **Agent Definitions ↔ Shell Scripts ↔ Integrations:** `lint-agents.sh` validates all 102 agent `.md` files. `convert.sh` transforms them for 6 tool formats. `install.sh` deploys to 8 tool targets. Generated files go to `integrations/<tool>/` (gitignored).

3. **MRO Arbitrage ↔ Research Docs:** `RLVR-research.md` documents the research journey from RLVR theory → AutoResearch pattern → logistics pricing → MRO arbitrage application. `MRO-data-sources.md` catalogs the 22 data sources feeding `ingest_*.py` scripts.

4. **Logistics Pricing ↔ RLVR Research:** The logistics pricing system implements the AutoResearch pattern documented in `RLVR-research.md` Section 22-23. Same architecture: immutable `prepare.py` (data/eval) + agent-modifiable `pricing_model.py` + `program.md` (research objectives).

5. **MRO Pipeline ↔ Web Dashboard:** `web_dashboard.py` (localhost:5050) serves the demo used in the AllClear pitch (`pipeline/allclear/VIDEO-SCRIPT-4MIN.md`, `pipeline/PITCH-SCRIPT.md`). The dashboard visualizes data from all `data/*.json` files.

6. **Data Layer Pattern:** Both hedge fund and MRO systems use a similar pattern — ingest from external APIs → JSON cache → analysis/detection → dashboard visualization. Hedge fund uses `data/cache.py` (in-memory TTL), MRO uses filesystem JSON.
