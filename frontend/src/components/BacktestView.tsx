import { useState, useCallback, useEffect } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  ReferenceLine,
} from "recharts";
import {
  Play,
  Loader2,
  AlertCircle,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Calendar,
  TrendingUp,
  BarChart3,
  Activity,
  Target,
  Award,
  Skull,
} from "lucide-react";
import { clsx } from "clsx";
import type {
  AnalystConfig,
  BacktestResult,
  ModelOption,
  TradeDecision,
} from "@/types";
import { fetchAnalysts, fetchModels, runBacktest } from "@/lib/api";
import TickerInput from "./TickerInput";
import MetricCard from "./MetricCard";

const TRADES_PER_PAGE = 15;

interface ChartTooltipProps {
  active?: boolean;
  payload?: Array<{
    name: string;
    value: number;
    stroke: string;
  }>;
  label?: string;
}

function ChartTooltip({ active, payload, label }: ChartTooltipProps) {
  if (!active || !payload?.length) return null;

  return (
    <div className="glass-card px-3 py-2 text-xs space-y-1 shadow-lg">
      <p className="text-slate-400 font-medium">{label}</p>
      {payload.map((entry) => (
        <div key={entry.name} className="flex items-center gap-2">
          <div
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: entry.stroke }}
          />
          <span className="text-slate-300">{entry.name}:</span>
          <span className="text-slate-100 font-mono font-medium">
            ${entry.value.toLocaleString("en-US", { maximumFractionDigits: 0 })}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function BacktestView() {
  // ── Config state ────────────────────────────────────────────────────────
  const [analysts, setAnalysts] = useState<AnalystConfig[]>([]);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [tickers, setTickers] = useState<string[]>([]);
  const [selectedAnalysts, setSelectedAnalysts] = useState<Set<string>>(new Set());
  const [selectedModel, setSelectedModel] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [initialCash, setInitialCash] = useState(100000);

  // ── Result state ────────────────────────────────────────────────────────
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // ── Pagination ──────────────────────────────────────────────────────────
  const [tradePage, setTradePage] = useState(0);

  // ── Load config on mount ────────────────────────────────────────────────
  useEffect(() => {
    const load = async () => {
      const [a, m] = await Promise.all([fetchAnalysts(), fetchModels()]);
      setAnalysts(a);
      setModels(m);
      setSelectedAnalysts(new Set(a.map((x) => x.id)));
      if (m.length > 0 && m[0]) setSelectedModel(m[0].model_id);

      // Default: 1 year back
      const today = new Date();
      const yearAgo = new Date(today);
      yearAgo.setFullYear(yearAgo.getFullYear() - 1);
      setEndDate(today.toISOString().split("T")[0] ?? "");
      setStartDate(yearAgo.toISOString().split("T")[0] ?? "");
    };
    void load();
  }, []);

  // ── Handlers ────────────────────────────────────────────────────────────
  const toggleAnalyst = useCallback((id: string) => {
    setSelectedAnalysts((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleRunBacktest = useCallback(async () => {
    if (tickers.length === 0 || selectedAnalysts.size === 0) return;

    const model = models.find((m) => m.model_id === selectedModel);

    setLoading(true);
    setError(null);
    setResult(null);
    setTradePage(0);

    try {
      const res = await runBacktest({
        tickers,
        start_date: startDate,
        end_date: endDate,
        initial_cash: initialCash,
        analysts: Array.from(selectedAnalysts),
        model_provider: model?.provider ?? "openai",
        model_id: selectedModel,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backtest failed");
    } finally {
      setLoading(false);
    }
  }, [tickers, selectedAnalysts, selectedModel, models, startDate, endDate, initialCash]);

  // ── Derived values ──────────────────────────────────────────────────────
  const paginatedTrades: TradeDecision[] = result
    ? result.trades.slice(
        tradePage * TRADES_PER_PAGE,
        (tradePage + 1) * TRADES_PER_PAGE,
      )
    : [];
  const totalTradePages = result
    ? Math.ceil(result.trades.length / TRADES_PER_PAGE)
    : 0;

  // Build combined chart data
  const chartData = result
    ? result.equity_curve.map((pt, i) => ({
        date: pt.date,
        Portfolio: pt.equity,
        Benchmark: result.benchmark_curve[i]?.equity ?? initialCash,
      }))
    : [];

  const canRun =
    tickers.length > 0 &&
    selectedAnalysts.size > 0 &&
    startDate &&
    endDate &&
    !loading;

  return (
    <div className="space-y-6">
      {/* ── Configuration panel ─────────────────────────────────────── */}
      <div className="glass-card p-5">
        <h2 className="text-sm font-semibold text-slate-200 mb-4">
          Backtest Configuration
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-5">
          {/* Tickers */}
          <div className="md:col-span-2 xl:col-span-1">
            <TickerInput tickers={tickers} onChange={setTickers} />
          </div>

          {/* Date range */}
          <div className="space-y-3">
            <label className="label-text">Date Range</label>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-[10px] text-slate-500 font-medium mb-1 block">
                  Start
                </label>
                <div className="relative">
                  <input
                    type="date"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    className="input-field text-xs"
                  />
                  <Calendar
                    size={12}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none"
                  />
                </div>
              </div>
              <div>
                <label className="text-[10px] text-slate-500 font-medium mb-1 block">
                  End
                </label>
                <div className="relative">
                  <input
                    type="date"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    className="input-field text-xs"
                  />
                  <Calendar
                    size={12}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Initial cash & model */}
          <div className="space-y-3">
            <div>
              <label className="label-text" htmlFor="initial-cash">
                Initial Cash
              </label>
              <input
                id="initial-cash"
                type="number"
                value={initialCash}
                onChange={(e) => setInitialCash(Number(e.target.value))}
                min={1000}
                step={10000}
                className="input-field font-mono"
              />
            </div>
            <div>
              <label className="label-text" htmlFor="bt-model-select">
                Model
              </label>
              <div className="relative">
                <select
                  id="bt-model-select"
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  className="input-field appearance-none pr-10 text-xs"
                >
                  {models.map((m) => (
                    <option key={m.model_id} value={m.model_id}>
                      {m.display_name}
                    </option>
                  ))}
                </select>
                <ChevronDown
                  size={14}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none"
                />
              </div>
            </div>
          </div>

          {/* Analysts */}
          <div className="space-y-3">
            <label className="label-text">Analysts</label>
            <div className="max-h-48 overflow-y-auto space-y-1 pr-1">
              {analysts.map((a) => (
                <label
                  key={a.id}
                  className="flex items-center gap-2 py-1 cursor-pointer group"
                >
                  <div
                    className={clsx(
                      "w-3 h-3 rounded border transition-all shrink-0",
                      selectedAnalysts.has(a.id)
                        ? "bg-emerald-500 border-emerald-500"
                        : "border-slate-600 group-hover:border-slate-500",
                    )}
                  >
                    {selectedAnalysts.has(a.id) && (
                      <svg viewBox="0 0 14 14" className="w-full h-full text-white p-0.5">
                        <path
                          d="M3 7l3 3 5-5"
                          stroke="currentColor"
                          strokeWidth="2"
                          fill="none"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    )}
                  </div>
                  <input
                    type="checkbox"
                    className="sr-only"
                    checked={selectedAnalysts.has(a.id)}
                    onChange={() => toggleAnalyst(a.id)}
                  />
                  <span className="text-xs text-slate-300 group-hover:text-slate-200 transition-colors">
                    {a.name}
                  </span>
                </label>
              ))}
            </div>
          </div>
        </div>

        {/* Run button */}
        <div className="mt-5 flex items-center gap-3">
          <button
            type="button"
            onClick={handleRunBacktest}
            disabled={!canRun}
            className="btn-primary"
          >
            {loading ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                Running Backtest...
              </>
            ) : (
              <>
                <Play size={16} />
                Run Backtest
              </>
            )}
          </button>

          {error && (
            <div className="flex items-center gap-2 text-xs text-red-400">
              <AlertCircle size={14} />
              {error}
            </div>
          )}
        </div>
      </div>

      {/* ── Loading state ───────────────────────────────────────────── */}
      {loading && (
        <div className="glass-card p-12 text-center animate-in">
          <Loader2 size={36} className="mx-auto text-emerald-400 animate-spin mb-4" />
          <p className="text-sm text-slate-400">
            Running backtest simulation... This may take a few minutes.
          </p>
        </div>
      )}

      {/* ── Results ─────────────────────────────────────────────────── */}
      {result && (
        <>
          {/* Performance metrics */}
          <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
            <MetricCard
              label="Total Return"
              value={result.metrics.total_return}
              format="percentage"
              change={result.metrics.total_return}
              icon={<TrendingUp size={16} />}
            />
            <MetricCard
              label="Sharpe Ratio"
              value={result.metrics.sharpe_ratio}
              format="ratio"
              icon={<BarChart3 size={16} />}
            />
            <MetricCard
              label="Max Drawdown"
              value={result.metrics.max_drawdown}
              format="percentage"
              icon={<Activity size={16} />}
            />
            <MetricCard
              label="Win Rate"
              value={result.metrics.win_rate}
              format="percentage"
              icon={<Target size={16} />}
            />
            <MetricCard
              label="Best Trade"
              value={result.metrics.best_trade}
              format="percentage"
              change={result.metrics.best_trade}
              icon={<Award size={16} />}
            />
            <MetricCard
              label="Worst Trade"
              value={result.metrics.worst_trade}
              format="percentage"
              change={result.metrics.worst_trade}
              icon={<Skull size={16} />}
            />
          </div>

          {/* Additional metrics row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricCard
              label="Annualized Return"
              value={result.metrics.annualized_return}
              format="percentage"
              change={result.metrics.annualized_return}
            />
            <MetricCard
              label="Sortino Ratio"
              value={result.metrics.sortino_ratio}
              format="ratio"
            />
            <MetricCard
              label="Calmar Ratio"
              value={result.metrics.calmar_ratio}
              format="ratio"
            />
            <MetricCard
              label="Total Trades"
              value={result.metrics.total_trades}
              format="integer"
            />
          </div>

          {/* Equity curve chart */}
          <div className="glass-card p-5">
            <h3 className="text-sm font-semibold text-slate-200 mb-4">
              Equity Curve
            </h3>
            <ResponsiveContainer width="100%" height={400}>
              <LineChart
                data={chartData}
                margin={{ top: 5, right: 20, left: 10, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis
                  dataKey="date"
                  stroke="#475569"
                  tick={{ fill: "#64748b", fontSize: 11 }}
                  tickLine={{ stroke: "#334155" }}
                  tickFormatter={(val: string) => {
                    const d = new Date(val);
                    return d.toLocaleDateString("en-US", {
                      month: "short",
                      year: "2-digit",
                    });
                  }}
                  interval="preserveStartEnd"
                  minTickGap={60}
                />
                <YAxis
                  stroke="#475569"
                  tick={{ fill: "#64748b", fontSize: 11 }}
                  tickLine={{ stroke: "#334155" }}
                  tickFormatter={(val: number) =>
                    `$${(val / 1000).toFixed(0)}k`
                  }
                  domain={["auto", "auto"]}
                />
                <Tooltip content={<ChartTooltip />} />
                <Legend
                  wrapperStyle={{ fontSize: "12px", color: "#94a3b8" }}
                />
                <ReferenceLine
                  y={initialCash}
                  stroke="#475569"
                  strokeDasharray="6 3"
                  label={{
                    value: "Initial",
                    fill: "#64748b",
                    fontSize: 10,
                    position: "right",
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="Portfolio"
                  stroke="#10b981"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4, fill: "#10b981", stroke: "#0f172a", strokeWidth: 2 }}
                />
                <Line
                  type="monotone"
                  dataKey="Benchmark"
                  stroke="#64748b"
                  strokeWidth={1.5}
                  strokeDasharray="5 5"
                  dot={false}
                  activeDot={{ r: 3, fill: "#64748b", stroke: "#0f172a", strokeWidth: 2 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Trade history table */}
          <div className="glass-card overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-700/40 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-200">
                Trade History
                <span className="ml-2 text-xs text-slate-500 font-normal">
                  ({result.trades.length} trades)
                </span>
              </h3>

              {/* Pagination controls */}
              {totalTradePages > 1 && (
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setTradePage((p) => Math.max(0, p - 1))}
                    disabled={tradePage === 0}
                    className="btn-ghost p-1.5"
                  >
                    <ChevronLeft size={14} />
                  </button>
                  <span className="text-xs text-slate-400 font-mono">
                    {tradePage + 1} / {totalTradePages}
                  </span>
                  <button
                    type="button"
                    onClick={() =>
                      setTradePage((p) =>
                        Math.min(totalTradePages - 1, p + 1),
                      )
                    }
                    disabled={tradePage >= totalTradePages - 1}
                    className="btn-ghost p-1.5"
                  >
                    <ChevronRight size={14} />
                  </button>
                </div>
              )}
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr>
                    <th className="table-header">#</th>
                    <th className="table-header">Action</th>
                    <th className="table-header">Ticker</th>
                    <th className="table-header text-right">Quantity</th>
                    <th className="table-header text-right">Confidence</th>
                    <th className="table-header">Reasoning</th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedTrades.map((trade, i) => {
                    const globalIndex = tradePage * TRADES_PER_PAGE + i + 1;
                    const actionColors: Record<string, string> = {
                      buy: "text-emerald-400 bg-emerald-500/15",
                      sell: "text-red-400 bg-red-500/15",
                      short: "text-orange-400 bg-orange-500/15",
                      cover: "text-cyan-400 bg-cyan-500/15",
                      hold: "text-slate-400 bg-slate-500/15",
                    };

                    return (
                      <tr
                        key={`trade-${globalIndex}`}
                        className="hover:bg-slate-800/40 transition-colors"
                      >
                        <td className="table-cell text-slate-500 font-mono text-xs">
                          {globalIndex}
                        </td>
                        <td className="table-cell">
                          <span
                            className={clsx(
                              "px-2 py-0.5 rounded text-xs font-semibold uppercase",
                              actionColors[trade.action] ?? "text-slate-400",
                            )}
                          >
                            {trade.action}
                          </span>
                        </td>
                        <td className="table-cell font-mono font-semibold text-slate-200 tracking-wider">
                          {trade.ticker}
                        </td>
                        <td className="table-cell text-right font-mono">
                          {trade.quantity.toLocaleString()}
                        </td>
                        <td className="table-cell text-right">
                          <span className="font-mono text-xs">
                            {trade.confidence.toFixed(0)}%
                          </span>
                        </td>
                        <td className="table-cell text-slate-400 max-w-sm truncate text-xs" title={trade.reasoning}>
                          {trade.reasoning || "--"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
