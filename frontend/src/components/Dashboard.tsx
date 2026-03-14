import { useState, useCallback, useEffect } from "react";
import {
  Play,
  RotateCcw,
  ChevronDown,
  Loader2,
  AlertCircle,
  Wifi,
  WifiOff,
  Calendar,
} from "lucide-react";
import { clsx } from "clsx";
import type { AnalystConfig, AnalystCategory, ModelOption } from "@/types";
import { fetchAnalysts, fetchModels } from "@/lib/api";
import { useAnalysis } from "@/hooks/useAnalysis";
import TickerInput from "./TickerInput";
import AgentPanel from "./AgentPanel";
import PortfolioView from "./PortfolioView";

const CATEGORY_LABELS: Record<AnalystCategory, string> = {
  investor_personas: "Investor Personas",
  analytical: "Analytical",
  decision: "Decision",
};

export default function Dashboard() {
  // ── Config state ────────────────────────────────────────────────────────
  const [analysts, setAnalysts] = useState<AnalystConfig[]>([]);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [tickers, setTickers] = useState<string[]>([]);
  const [selectedAnalysts, setSelectedAnalysts] = useState<Set<string>>(new Set());
  const [selectedModel, setSelectedModel] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [activeTab, setActiveTab] = useState<"signals" | "portfolio">("signals");

  // ── Analysis hook ───────────────────────────────────────────────────────
  const {
    loading,
    result,
    streamingSignals,
    streamingDecisions,
    error,
    connected,
    analyze,
    reset,
  } = useAnalysis();

  // ── Load config on mount ────────────────────────────────────────────────
  useEffect(() => {
    const load = async () => {
      const [a, m] = await Promise.all([fetchAnalysts(), fetchModels()]);
      setAnalysts(a);
      setModels(m);

      // Select all analysts by default
      setSelectedAnalysts(new Set(a.map((x) => x.id)));

      // Select first model
      if (m.length > 0 && m[0]) {
        setSelectedModel(m[0].model_id);
      }

      // Default date range: 3 months back from today
      const today = new Date();
      const threeMonthsAgo = new Date(today);
      threeMonthsAgo.setMonth(threeMonthsAgo.getMonth() - 3);
      setEndDate(today.toISOString().split("T")[0] ?? "");
      setStartDate(threeMonthsAgo.toISOString().split("T")[0] ?? "");
    };
    void load();
  }, []);

  // ── Handlers ────────────────────────────────────────────────────────────
  const toggleAnalyst = useCallback((id: string) => {
    setSelectedAnalysts((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const selectAllInCategory = useCallback(
    (category: AnalystCategory) => {
      const categoryIds = analysts
        .filter((a) => a.category === category)
        .map((a) => a.id);
      setSelectedAnalysts((prev) => {
        const next = new Set(prev);
        const allSelected = categoryIds.every((id) => next.has(id));
        if (allSelected) {
          categoryIds.forEach((id) => next.delete(id));
        } else {
          categoryIds.forEach((id) => next.add(id));
        }
        return next;
      });
    },
    [analysts],
  );

  const handleRunAnalysis = useCallback(async () => {
    if (tickers.length === 0) return;
    if (selectedAnalysts.size === 0) return;

    const model = models.find((m) => m.model_id === selectedModel);

    await analyze({
      tickers,
      analysts: Array.from(selectedAnalysts),
      model_provider: model?.provider ?? "openai",
      model_id: selectedModel,
      start_date: startDate || undefined,
      end_date: endDate || undefined,
    });
  }, [tickers, selectedAnalysts, selectedModel, models, startDate, endDate, analyze]);

  const handleReset = useCallback(() => {
    reset();
    setActiveTab("signals");
  }, [reset]);

  // Group analysts by category
  const groupedAnalysts = analysts.reduce<Record<AnalystCategory, AnalystConfig[]>>(
    (acc, a) => {
      acc[a.category].push(a);
      return acc;
    },
    { investor_personas: [], analytical: [], decision: [] },
  );

  const canRun = tickers.length > 0 && selectedAnalysts.size > 0 && !loading;

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
      {/* ── Left panel: Configuration ─────────────────────────────── */}
      <div className="xl:col-span-4 2xl:col-span-3 space-y-5">
        {/* Connection indicator */}
        <div className="flex items-center gap-2 text-xs">
          {connected ? (
            <>
              <Wifi size={12} className="text-emerald-400" />
              <span className="text-emerald-400 font-medium">Live</span>
            </>
          ) : (
            <>
              <WifiOff size={12} className="text-slate-500" />
              <span className="text-slate-500">Offline</span>
            </>
          )}
        </div>

        {/* Ticker input */}
        <div className="glass-card p-4">
          <TickerInput tickers={tickers} onChange={setTickers} />
        </div>

        {/* Analyst selection */}
        <div className="glass-card p-4 space-y-4">
          <label className="label-text">Analysts</label>

          {(Object.entries(groupedAnalysts) as [AnalystCategory, AnalystConfig[]][]).map(
            ([category, categoryAnalysts]) => {
              if (categoryAnalysts.length === 0) return null;
              const allSelected = categoryAnalysts.every((a) =>
                selectedAnalysts.has(a.id),
              );

              return (
                <div key={category} className="space-y-2">
                  <button
                    type="button"
                    onClick={() => selectAllInCategory(category)}
                    className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-400 hover:text-slate-300 transition-colors"
                  >
                    <div
                      className={clsx(
                        "w-3.5 h-3.5 rounded border transition-all",
                        allSelected
                          ? "bg-emerald-500 border-emerald-500"
                          : "border-slate-600",
                      )}
                    >
                      {allSelected && (
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
                    {CATEGORY_LABELS[category]}
                  </button>

                  <div className="space-y-1 ml-5">
                    {categoryAnalysts.map((analyst) => (
                      <label
                        key={analyst.id}
                        className="flex items-start gap-2.5 py-1.5 cursor-pointer group"
                      >
                        <div
                          className={clsx(
                            "w-3.5 h-3.5 rounded border mt-0.5 transition-all shrink-0",
                            selectedAnalysts.has(analyst.id)
                              ? "bg-emerald-500 border-emerald-500"
                              : "border-slate-600 group-hover:border-slate-500",
                          )}
                        >
                          {selectedAnalysts.has(analyst.id) && (
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
                          checked={selectedAnalysts.has(analyst.id)}
                          onChange={() => toggleAnalyst(analyst.id)}
                        />
                        <div className="min-w-0">
                          <span className="text-sm text-slate-300 group-hover:text-slate-200 transition-colors font-medium">
                            {analyst.name}
                          </span>
                          <p className="text-[10px] text-slate-500 leading-tight mt-0.5 line-clamp-2">
                            {analyst.description}
                          </p>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>
              );
            },
          )}
        </div>

        {/* Model selection */}
        <div className="glass-card p-4 space-y-3">
          <label className="label-text" htmlFor="model-select">
            LLM Model
          </label>
          <div className="relative">
            <select
              id="model-select"
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="input-field appearance-none pr-10"
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

        {/* Date range */}
        <div className="glass-card p-4 space-y-3">
          <label className="label-text">Date Range</label>
          <div className="grid grid-cols-2 gap-3">
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

        {/* Action buttons */}
        <div className="flex gap-2">
          <button
            type="button"
            onClick={handleRunAnalysis}
            disabled={!canRun}
            className="btn-primary flex-1"
          >
            {loading ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                Analyzing...
              </>
            ) : (
              <>
                <Play size={16} />
                Run Analysis
              </>
            )}
          </button>
          {(result || error) && (
            <button
              type="button"
              onClick={handleReset}
              className="btn-secondary"
            >
              <RotateCcw size={16} />
            </button>
          )}
        </div>

        {/* Error display */}
        {error && (
          <div className="flex items-start gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/20 animate-in">
            <AlertCircle size={14} className="text-red-400 mt-0.5 shrink-0" />
            <p className="text-xs text-red-300">{error}</p>
          </div>
        )}
      </div>

      {/* ── Right panel: Results ──────────────────────────────────── */}
      <div className="xl:col-span-8 2xl:col-span-9 space-y-4">
        {/* Tab bar */}
        <div className="flex gap-1 p-1 rounded-lg bg-slate-800/40 border border-slate-700/30 w-fit">
          <button
            type="button"
            onClick={() => setActiveTab("signals")}
            className={clsx(
              "px-4 py-2 rounded-md text-sm font-medium transition-all duration-150",
              activeTab === "signals"
                ? "bg-slate-700/80 text-slate-100 shadow-sm"
                : "text-slate-400 hover:text-slate-300",
            )}
          >
            Agent Signals
            {streamingSignals.length > 0 && (
              <span className="ml-2 px-1.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 text-[10px] font-semibold">
                {streamingSignals.length}
              </span>
            )}
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("portfolio")}
            className={clsx(
              "px-4 py-2 rounded-md text-sm font-medium transition-all duration-150",
              activeTab === "portfolio"
                ? "bg-slate-700/80 text-slate-100 shadow-sm"
                : "text-slate-400 hover:text-slate-300",
            )}
          >
            Portfolio
            {streamingDecisions.length > 0 && (
              <span className="ml-2 px-1.5 py-0.5 rounded-full bg-cyan-500/20 text-cyan-400 text-[10px] font-semibold">
                {streamingDecisions.length}
              </span>
            )}
          </button>
        </div>

        {/* Tab content */}
        {activeTab === "signals" ? (
          <AgentPanel signals={streamingSignals} loading={loading} />
        ) : (
          <PortfolioView
            portfolio={result?.portfolio ?? null}
            decisions={streamingDecisions}
          />
        )}
      </div>
    </div>
  );
}
