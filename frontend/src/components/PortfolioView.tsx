import { useMemo } from "react";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import {
  Wallet,
  TrendingUp,
  TrendingDown,
  DollarSign,
  BarChart3,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
} from "lucide-react";
import { clsx } from "clsx";
import type { PortfolioState, TradeDecision } from "@/types";
import MetricCard from "./MetricCard";
import SignalBadge from "./SignalBadge";

interface PortfolioViewProps {
  portfolio: PortfolioState | null;
  decisions: TradeDecision[];
}

const PIE_COLORS = [
  "#10b981", // emerald
  "#06b6d4", // cyan
  "#8b5cf6", // violet
  "#f59e0b", // amber
  "#ec4899", // pink
  "#3b82f6", // blue
  "#f97316", // orange
  "#14b8a6", // teal
];

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: value >= 1000 ? 0 : 2,
  }).format(value);
}

function formatPct(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

const ACTION_CONFIG = {
  buy: { color: "text-emerald-400", bg: "bg-emerald-500/15", icon: ArrowUpRight },
  sell: { color: "text-red-400", bg: "bg-red-500/15", icon: ArrowDownRight },
  short: { color: "text-orange-400", bg: "bg-orange-500/15", icon: ArrowDownRight },
  cover: { color: "text-cyan-400", bg: "bg-cyan-500/15", icon: ArrowUpRight },
  hold: { color: "text-slate-400", bg: "bg-slate-500/15", icon: Minus },
} as const;

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{ name: string; value: number }>;
}

function PieTooltip({ active, payload }: CustomTooltipProps) {
  if (!active || !payload?.[0]) return null;
  const entry = payload[0];
  return (
    <div className="glass-card px-3 py-2 text-xs">
      <span className="text-slate-300 font-medium">{entry.name}</span>
      <span className="text-slate-400 ml-2">{formatCurrency(entry.value)}</span>
    </div>
  );
}

export default function PortfolioView({ portfolio, decisions }: PortfolioViewProps) {
  // Build pie chart data
  const pieData = useMemo(() => {
    if (!portfolio) return [];

    const data: { name: string; value: number }[] = [];

    for (const [ticker, pos] of Object.entries(portfolio.positions)) {
      if (pos.market_value > 0) {
        data.push({ name: ticker, value: pos.market_value });
      }
    }

    if (portfolio.cash > 0) {
      data.push({ name: "Cash", value: portfolio.cash });
    }

    return data;
  }, [portfolio]);

  // Compute summary values
  const totalValue = portfolio?.total_equity ?? 0;
  const invested = portfolio
    ? portfolio.long_market_value + portfolio.short_market_value
    : 0;
  const totalReturn = portfolio
    ? (totalValue - 100_000) / 100_000
    : 0;
  const unrealizedPnl = portfolio
    ? Object.values(portfolio.positions).reduce(
        (sum, p) => sum + p.unrealized_pnl,
        0,
      )
    : 0;

  if (!portfolio && decisions.length === 0) {
    return (
      <div className="glass-card p-8 text-center">
        <Wallet size={32} className="mx-auto text-slate-600 mb-3" />
        <p className="text-sm text-slate-400">
          No portfolio data available. Run an analysis to see portfolio state.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Portfolio summary cards */}
      {portfolio && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <MetricCard
            label="Total Value"
            value={totalValue}
            format="currency"
            change={totalReturn !== 0 ? totalReturn : undefined}
            icon={<DollarSign size={16} />}
          />
          <MetricCard
            label="Cash"
            value={portfolio.cash}
            format="currency"
            icon={<Wallet size={16} />}
          />
          <MetricCard
            label="Invested"
            value={invested}
            format="currency"
            icon={<BarChart3 size={16} />}
          />
          <MetricCard
            label="Unrealized P&L"
            value={unrealizedPnl}
            format="currency"
            change={totalValue > 0 ? unrealizedPnl / totalValue : undefined}
            icon={unrealizedPnl >= 0 ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
          />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Holdings table */}
        <div className="lg:col-span-2 glass-card overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-700/40">
            <h3 className="text-sm font-semibold text-slate-200">Holdings</h3>
          </div>

          {portfolio && Object.keys(portfolio.positions).length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr>
                    <th className="table-header">Ticker</th>
                    <th className="table-header text-right">Shares</th>
                    <th className="table-header text-right">Avg Price</th>
                    <th className="table-header text-right">Current</th>
                    <th className="table-header text-right">Value</th>
                    <th className="table-header text-right">P&L</th>
                    <th className="table-header text-right">P&L %</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(portfolio.positions).map(([ticker, pos]) => {
                    const pnl = pos.unrealized_pnl;
                    const pnlPct =
                      pos.avg_entry_price > 0
                        ? (pos.current_price - pos.avg_entry_price) /
                          pos.avg_entry_price
                        : 0;
                    const isProfit = pnl >= 0;

                    return (
                      <tr key={ticker} className="hover:bg-slate-800/40 transition-colors">
                        <td className="table-cell font-mono font-semibold text-slate-200 tracking-wider">
                          {ticker}
                        </td>
                        <td className="table-cell text-right font-mono">
                          {pos.shares.toLocaleString()}
                        </td>
                        <td className="table-cell text-right font-mono">
                          {formatCurrency(pos.avg_entry_price)}
                        </td>
                        <td className="table-cell text-right font-mono">
                          {formatCurrency(pos.current_price)}
                        </td>
                        <td className="table-cell text-right font-mono font-medium">
                          {formatCurrency(pos.market_value)}
                        </td>
                        <td
                          className={clsx(
                            "table-cell text-right font-mono font-medium",
                            isProfit ? "text-emerald-400" : "text-red-400",
                          )}
                        >
                          {isProfit ? "+" : ""}
                          {formatCurrency(pnl)}
                        </td>
                        <td
                          className={clsx(
                            "table-cell text-right font-mono font-medium",
                            isProfit ? "text-emerald-400" : "text-red-400",
                          )}
                        >
                          {isProfit ? "+" : ""}
                          {formatPct(pnlPct)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-6 text-center text-sm text-slate-500">
              No current holdings
            </div>
          )}
        </div>

        {/* Allocation pie chart */}
        <div className="glass-card p-4">
          <h3 className="text-sm font-semibold text-slate-200 mb-4">Allocation</h3>

          {pieData.length > 0 ? (
            <div className="space-y-4">
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={55}
                    outerRadius={80}
                    paddingAngle={2}
                    dataKey="value"
                    nameKey="name"
                    strokeWidth={0}
                  >
                    {pieData.map((_entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={PIE_COLORS[index % PIE_COLORS.length]}
                        opacity={0.85}
                      />
                    ))}
                  </Pie>
                  <Tooltip content={<PieTooltip />} />
                </PieChart>
              </ResponsiveContainer>

              {/* Legend */}
              <div className="space-y-1.5">
                {pieData.map((entry, index) => {
                  const total = pieData.reduce((s, e) => s + e.value, 0);
                  const pct = total > 0 ? (entry.value / total) * 100 : 0;
                  return (
                    <div key={entry.name} className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2">
                        <div
                          className="w-2.5 h-2.5 rounded-sm"
                          style={{
                            backgroundColor: PIE_COLORS[index % PIE_COLORS.length],
                          }}
                        />
                        <span className="text-slate-300 font-medium">{entry.name}</span>
                      </div>
                      <span className="text-slate-500 font-mono">{pct.toFixed(1)}%</span>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center h-48 text-sm text-slate-500">
              No allocation data
            </div>
          )}
        </div>
      </div>

      {/* Trade decisions table */}
      {decisions.length > 0 && (
        <div className="glass-card overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-700/40">
            <h3 className="text-sm font-semibold text-slate-200">Trade Decisions</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr>
                  <th className="table-header">Action</th>
                  <th className="table-header">Ticker</th>
                  <th className="table-header text-right">Quantity</th>
                  <th className="table-header text-right">Confidence</th>
                  <th className="table-header">Reasoning</th>
                </tr>
              </thead>
              <tbody>
                {decisions.map((d, i) => {
                  const actionCfg = ACTION_CONFIG[d.action];
                  const ActionIcon = actionCfg.icon;

                  return (
                    <tr key={`${d.ticker}-${d.action}-${i}`} className="hover:bg-slate-800/40 transition-colors">
                      <td className="table-cell">
                        <span
                          className={clsx(
                            "inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold uppercase",
                            actionCfg.bg,
                            actionCfg.color,
                          )}
                        >
                          <ActionIcon size={10} />
                          {d.action}
                        </span>
                      </td>
                      <td className="table-cell font-mono font-semibold text-slate-200 tracking-wider">
                        {d.ticker}
                      </td>
                      <td className="table-cell text-right font-mono">
                        {d.quantity.toLocaleString()}
                      </td>
                      <td className="table-cell text-right">
                        <SignalBadge
                          signal={
                            d.confidence > 60
                              ? "bullish"
                              : d.confidence > 40
                                ? "neutral"
                                : "bearish"
                          }
                          confidence={d.confidence}
                          size="sm"
                          showIcon={false}
                        />
                      </td>
                      <td className="table-cell text-slate-400 max-w-xs truncate" title={d.reasoning}>
                        {d.reasoning}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
