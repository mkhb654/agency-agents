import { useState } from "react";
import { ChevronDown, ChevronUp, Brain, Users, BarChart3, ShieldCheck } from "lucide-react";
import { clsx } from "clsx";
import type { AnalystSignal, AnalystCategory } from "@/types";
import SignalBadge from "./SignalBadge";

interface AgentPanelProps {
  signals: AnalystSignal[];
  loading?: boolean;
}

const CATEGORY_CONFIG: Record<
  AnalystCategory,
  { label: string; icon: typeof Brain; color: string }
> = {
  investor_personas: {
    label: "Investor Personas",
    icon: Users,
    color: "text-violet-400",
  },
  analytical: {
    label: "Analytical Agents",
    icon: BarChart3,
    color: "text-cyan-400",
  },
  decision: {
    label: "Decision Agents",
    icon: ShieldCheck,
    color: "text-amber-400",
  },
};

const AGENT_CATEGORY_MAP: Record<string, AnalystCategory> = {
  warren_buffett: "investor_personas",
  ben_graham: "investor_personas",
  peter_lynch: "investor_personas",
  cathie_wood: "investor_personas",
  michael_burry: "investor_personas",
  stanley_druckenmiller: "investor_personas",
  fundamentals_analyst: "analytical",
  technical_analyst: "analytical",
  sentiment_analyst: "analytical",
  valuation_analyst: "analytical",
  risk_manager: "decision",
  portfolio_manager: "decision",
};

function getCategory(agentName: string): AnalystCategory {
  const normalized = agentName.toLowerCase().replace(/\s+/g, "_");
  return AGENT_CATEGORY_MAP[normalized] ?? "analytical";
}

function formatAgentName(name: string): string {
  return name
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatReasoning(reasoning: string | Record<string, unknown>): string {
  if (typeof reasoning === "string") return reasoning;
  try {
    // Convert object reasoning to readable text
    const entries = Object.entries(reasoning);
    return entries
      .map(([key, val]) => {
        const label = key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
        return `${label}: ${typeof val === "string" ? val : JSON.stringify(val)}`;
      })
      .join("\n\n");
  } catch {
    return JSON.stringify(reasoning, null, 2);
  }
}

function AgentCard({ signal }: { signal: AnalystSignal }) {
  const [expanded, setExpanded] = useState(false);

  const confidencePct = signal.confidence > 1 ? signal.confidence : signal.confidence * 100;

  return (
    <div className="glass-card-hover p-4 space-y-3 animate-in">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <div
            className={clsx(
              "w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold shrink-0",
              signal.signal === "bullish" && "bg-emerald-500/15 text-emerald-400",
              signal.signal === "bearish" && "bg-red-500/15 text-red-400",
              signal.signal === "neutral" && "bg-amber-500/15 text-amber-400",
            )}
          >
            {formatAgentName(signal.agent_name).charAt(0)}
          </div>
          <div className="min-w-0">
            <h4 className="text-sm font-semibold text-slate-200 truncate">
              {formatAgentName(signal.agent_name)}
            </h4>
            {signal.ticker && (
              <span className="text-[10px] font-mono text-slate-500 tracking-wider">
                {signal.ticker}
              </span>
            )}
          </div>
        </div>

        <SignalBadge signal={signal.signal} confidence={confidencePct} size="sm" />
      </div>

      {/* Confidence bar */}
      <div className="space-y-1">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-medium text-slate-500 uppercase tracking-wider">
            Confidence
          </span>
          <span className="text-xs font-mono font-semibold text-slate-300">
            {confidencePct.toFixed(0)}%
          </span>
        </div>
        <div className="h-1.5 bg-slate-700/50 rounded-full overflow-hidden">
          <div
            className={clsx(
              "h-full rounded-full transition-all duration-700 ease-out",
              signal.signal === "bullish" && "bg-gradient-to-r from-emerald-600 to-emerald-400",
              signal.signal === "bearish" && "bg-gradient-to-r from-red-600 to-red-400",
              signal.signal === "neutral" && "bg-gradient-to-r from-amber-600 to-amber-400",
            )}
            style={{ width: `${Math.min(confidencePct, 100)}%` }}
          />
        </div>
      </div>

      {/* Reasoning toggle */}
      {signal.reasoning && (
        <div>
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-300 transition-colors"
          >
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            <span>{expanded ? "Hide" : "Show"} reasoning</span>
          </button>

          {expanded && (
            <div className="mt-2 p-3 rounded-lg bg-slate-900/60 border border-slate-700/30 animate-in">
              <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">
                {formatReasoning(signal.reasoning)}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SkeletonCard() {
  return (
    <div className="glass-card p-4 space-y-3">
      <div className="flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-lg bg-slate-700/50 shimmer" />
        <div className="space-y-1.5 flex-1">
          <div className="h-3.5 w-32 rounded bg-slate-700/50 shimmer" />
          <div className="h-2.5 w-16 rounded bg-slate-700/50 shimmer" />
        </div>
        <div className="h-6 w-20 rounded-full bg-slate-700/50 shimmer" />
      </div>
      <div className="h-1.5 rounded-full bg-slate-700/50 shimmer" />
    </div>
  );
}

export default function AgentPanel({ signals, loading }: AgentPanelProps) {
  // Group signals by category
  const grouped = signals.reduce<Record<AnalystCategory, AnalystSignal[]>>(
    (acc, sig) => {
      const cat = getCategory(sig.agent_name);
      acc[cat].push(sig);
      return acc;
    },
    { investor_personas: [], analytical: [], decision: [] },
  );

  // Sort each group by confidence descending
  for (const group of Object.values(grouped)) {
    group.sort((a, b) => {
      const aConf = a.confidence > 1 ? a.confidence : a.confidence * 100;
      const bConf = b.confidence > 1 ? b.confidence : b.confidence * 100;
      return bConf - aConf;
    });
  }

  if (!loading && signals.length === 0) {
    return (
      <div className="glass-card p-8 text-center">
        <Brain size={32} className="mx-auto text-slate-600 mb-3" />
        <p className="text-sm text-slate-400">
          No agent signals yet. Run an analysis to see results.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {(Object.entries(CATEGORY_CONFIG) as [AnalystCategory, typeof CATEGORY_CONFIG.investor_personas][]).map(
        ([category, config]) => {
          const categorySignals = grouped[category];
          if (!loading && categorySignals.length === 0) return null;

          const CategoryIcon = config.icon;

          return (
            <div key={category} className="space-y-3">
              {/* Category header */}
              <div className="flex items-center gap-2">
                <CategoryIcon size={14} className={config.color} />
                <h3 className={clsx("text-xs font-semibold uppercase tracking-wider", config.color)}>
                  {config.label}
                </h3>
                <span className="text-[10px] text-slate-600 font-mono">
                  ({categorySignals.length})
                </span>
              </div>

              {/* Cards */}
              <div className="grid gap-2">
                {loading && categorySignals.length === 0 ? (
                  <>
                    <SkeletonCard />
                    <SkeletonCard />
                  </>
                ) : (
                  categorySignals.map((sig, i) => (
                    <AgentCard key={`${sig.agent_name}-${sig.ticker}-${i}`} signal={sig} />
                  ))
                )}
              </div>
            </div>
          );
        },
      )}
    </div>
  );
}
