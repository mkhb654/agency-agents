import { clsx } from "clsx";
import { TrendingUp, TrendingDown } from "lucide-react";
import type { ReactNode } from "react";

type FormatType = "currency" | "percentage" | "ratio" | "number" | "integer";

interface MetricCardProps {
  label: string;
  value: number | string;
  change?: number | null;
  format?: FormatType;
  icon?: ReactNode;
  className?: string;
}

function formatValue(value: number | string, format: FormatType): string {
  if (typeof value === "string") return value;

  switch (format) {
    case "currency":
      return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        minimumFractionDigits: 0,
        maximumFractionDigits: value >= 1000 ? 0 : 2,
        notation: value >= 1_000_000 ? "compact" : "standard",
      }).format(value);
    case "percentage":
      return `${(value * 100).toFixed(2)}%`;
    case "ratio":
      return value.toFixed(2);
    case "integer":
      return Math.round(value).toLocaleString("en-US");
    case "number":
    default:
      return value.toLocaleString("en-US", {
        minimumFractionDigits: 0,
        maximumFractionDigits: 2,
      });
  }
}

export default function MetricCard({
  label,
  value,
  change,
  format = "number",
  icon,
  className,
}: MetricCardProps) {
  const isPositive = typeof change === "number" && change >= 0;
  const hasChange = typeof change === "number";

  return (
    <div
      className={clsx(
        "glass-card p-4 flex flex-col gap-2 animate-in",
        className,
      )}
    >
      <div className="flex items-center justify-between">
        <span className="stat-label">{label}</span>
        {icon && <span className="text-slate-500">{icon}</span>}
      </div>

      <div className="flex items-end justify-between gap-2">
        <span
          className={clsx(
            "stat-value",
            hasChange && isPositive && "text-emerald-400",
            hasChange && !isPositive && "text-red-400",
            !hasChange && "text-slate-100",
          )}
        >
          {formatValue(value, format)}
        </span>

        {hasChange && (
          <div
            className={clsx(
              "flex items-center gap-0.5 text-xs font-medium pb-1",
              isPositive ? "text-emerald-400" : "text-red-400",
            )}
          >
            {isPositive ? (
              <TrendingUp size={12} />
            ) : (
              <TrendingDown size={12} />
            )}
            <span>
              {isPositive ? "+" : ""}
              {(change * 100).toFixed(2)}%
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
