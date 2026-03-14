import { clsx } from "clsx";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import type { SignalDirection } from "@/types";

interface SignalBadgeProps {
  signal: SignalDirection;
  confidence?: number;
  size?: "sm" | "md" | "lg";
  showIcon?: boolean;
}

const sizeClasses = {
  sm: "px-2 py-0.5 text-[10px] gap-0.5",
  md: "px-2.5 py-1 text-xs gap-1",
  lg: "px-3.5 py-1.5 text-sm gap-1.5",
} as const;

const iconSizes = {
  sm: 10,
  md: 12,
  lg: 14,
} as const;

export default function SignalBadge({
  signal,
  confidence,
  size = "md",
  showIcon = true,
}: SignalBadgeProps) {
  const Icon =
    signal === "bullish"
      ? TrendingUp
      : signal === "bearish"
        ? TrendingDown
        : Minus;

  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-full font-semibold tracking-wide uppercase",
        sizeClasses[size],
        signal === "bullish" &&
          "bg-emerald-500/15 text-emerald-400 border border-emerald-500/25",
        signal === "bearish" &&
          "bg-red-500/15 text-red-400 border border-red-500/25",
        signal === "neutral" &&
          "bg-amber-500/15 text-amber-400 border border-amber-500/25",
      )}
    >
      {showIcon && <Icon size={iconSizes[size]} />}
      <span>{signal}</span>
      {confidence != null && (
        <span className="opacity-75 ml-0.5">
          {Math.round(confidence)}%
        </span>
      )}
    </span>
  );
}
