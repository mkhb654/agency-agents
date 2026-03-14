// ─── Signal & Analysis Types ────────────────────────────────────────────────

export type SignalDirection = "bullish" | "bearish" | "neutral";

export type TradeAction = "buy" | "sell" | "short" | "cover" | "hold";

export type VolatilityRegime = "low" | "normal" | "high" | "extreme";

export interface AnalystSignal {
  signal: SignalDirection;
  confidence: number;
  reasoning: string | Record<string, unknown>;
  agent_name: string;
  ticker: string;
  agent_scores?: Record<string, number>;
}

export interface TradeDecision {
  action: TradeAction;
  ticker: string;
  quantity: number;
  confidence: number;
  reasoning: string;
  limit_price?: number | null;
}

export interface RiskAssessment {
  remaining_position_limit: number;
  current_var?: number | null;
  max_drawdown_pct?: number | null;
  volatility_regime?: VolatilityRegime | null;
  correlation_risk?: number | null;
  risk_score?: number | null;
  warnings: string[];
}

export interface Position {
  ticker: string;
  shares: number;
  avg_entry_price: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
}

export interface PortfolioState {
  cash: number;
  positions: Record<string, Position>;
  short_positions: Record<string, Position>;
  margin_used: number;
  realized_gains: number;
  trade_history: TradeDecision[];
  long_market_value: number;
  short_market_value: number;
  total_equity: number;
  total_exposure: number;
}

// ─── Analyst & Model Configuration ──────────────────────────────────────────

export type AnalystCategory = "investor_personas" | "analytical" | "decision";

export interface AnalystConfig {
  id: string;
  name: string;
  description: string;
  category: AnalystCategory;
}

export interface ModelOption {
  provider: string;
  model_id: string;
  display_name: string;
}

// ─── Analysis Request / Result ──────────────────────────────────────────────

export interface AnalysisRequest {
  tickers: string[];
  analysts: string[];
  model_provider: string;
  model_id: string;
  start_date?: string;
  end_date?: string;
}

export interface AnalysisResult {
  tickers: string[];
  signals: Record<string, AnalystSignal[]>;
  decisions: TradeDecision[];
  risk_assessment: RiskAssessment | null;
  portfolio: PortfolioState | null;
  timestamp: string;
}

// ─── Backtest Types ─────────────────────────────────────────────────────────

export interface BacktestRequest {
  tickers: string[];
  start_date: string;
  end_date: string;
  initial_cash: number;
  analysts: string[];
  model_provider: string;
  model_id: string;
}

export interface EquityPoint {
  date: string;
  equity: number;
  benchmark?: number;
}

export interface PerformanceMetrics {
  total_return: number;
  annualized_return: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown: number;
  win_rate: number;
  profit_factor: number;
  total_trades: number;
  avg_trade_return: number;
  volatility: number;
  calmar_ratio: number;
  best_trade: number;
  worst_trade: number;
}

export interface BacktestResult {
  equity_curve: EquityPoint[];
  benchmark_curve: EquityPoint[];
  metrics: PerformanceMetrics;
  trades: TradeDecision[];
  final_portfolio: PortfolioState;
}

// ─── WebSocket Message Types ────────────────────────────────────────────────

export type WSMessageType =
  | "analysis_started"
  | "agent_signal"
  | "risk_assessment"
  | "trade_decision"
  | "portfolio_update"
  | "analysis_complete"
  | "analysis_error"
  | "backtest_progress"
  | "backtest_complete";

export interface WSMessage {
  type: WSMessageType;
  data: unknown;
  timestamp: string;
}

export interface WSAnalysisStarted {
  type: "analysis_started";
  data: { tickers: string[]; analysts: string[] };
}

export interface WSAgentSignal {
  type: "agent_signal";
  data: AnalystSignal;
}

export interface WSTradeDecision {
  type: "trade_decision";
  data: TradeDecision;
}

export interface WSAnalysisComplete {
  type: "analysis_complete";
  data: AnalysisResult;
}

export interface WSAnalysisError {
  type: "analysis_error";
  data: { error: string };
}

// ─── View Types ─────────────────────────────────────────────────────────────

export type AppView = "dashboard" | "backtest" | "settings";
