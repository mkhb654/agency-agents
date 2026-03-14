import { useState, useCallback, type KeyboardEvent } from "react";
import { Plus, X } from "lucide-react";
import { clsx } from "clsx";

interface TickerInputProps {
  tickers: string[];
  onChange: (tickers: string[]) => void;
  maxTickers?: number;
}

const COMMON_TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META"];

export default function TickerInput({
  tickers,
  onChange,
  maxTickers = 20,
}: TickerInputProps) {
  const [inputValue, setInputValue] = useState("");
  const [inputError, setInputError] = useState("");

  const addTicker = useCallback(
    (raw: string) => {
      const ticker = raw.trim().toUpperCase();

      if (!ticker) return;
      if (!/^[A-Z]{1,5}$/.test(ticker)) {
        setInputError("Ticker must be 1-5 letters");
        return;
      }
      if (tickers.includes(ticker)) {
        setInputError(`${ticker} already added`);
        return;
      }
      if (tickers.length >= maxTickers) {
        setInputError(`Maximum ${maxTickers} tickers`);
        return;
      }

      setInputError("");
      setInputValue("");
      onChange([...tickers, ticker]);
    },
    [tickers, onChange, maxTickers],
  );

  const removeTicker = useCallback(
    (ticker: string) => {
      onChange(tickers.filter((t) => t !== ticker));
    },
    [tickers, onChange],
  );

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addTicker(inputValue);
    }
  };

  return (
    <div className="space-y-3">
      <label className="label-text">Tickers</label>

      {/* Input row */}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => {
              setInputValue(e.target.value.toUpperCase());
              setInputError("");
            }}
            onKeyDown={handleKeyDown}
            placeholder="Enter ticker symbol..."
            className={clsx(
              "input-field uppercase font-mono tracking-wider",
              inputError && "border-red-500/60 focus:ring-red-500/40",
            )}
            maxLength={5}
          />
        </div>
        <button
          type="button"
          onClick={() => addTicker(inputValue)}
          disabled={!inputValue.trim()}
          className="btn-primary px-3"
          aria-label="Add ticker"
        >
          <Plus size={16} />
          <span className="hidden sm:inline">Add</span>
        </button>
      </div>

      {/* Error message */}
      {inputError && (
        <p className="text-xs text-red-400 animate-in">{inputError}</p>
      )}

      {/* Selected tickers */}
      {tickers.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {tickers.map((ticker) => (
            <span
              key={ticker}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg
                         bg-emerald-500/10 text-emerald-400 border border-emerald-500/20
                         text-sm font-mono font-semibold tracking-wider
                         transition-all duration-150 group"
            >
              {ticker}
              <button
                type="button"
                onClick={() => removeTicker(ticker)}
                className="p-0.5 rounded hover:bg-emerald-500/20 transition-colors"
                aria-label={`Remove ${ticker}`}
              >
                <X size={12} className="opacity-60 group-hover:opacity-100" />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Quick-select */}
      <div className="space-y-1.5">
        <span className="text-[10px] font-medium uppercase tracking-widest text-slate-500">
          Popular
        </span>
        <div className="flex flex-wrap gap-1.5">
          {COMMON_TICKERS.filter((t) => !tickers.includes(t)).map((ticker) => (
            <button
              key={ticker}
              type="button"
              onClick={() => addTicker(ticker)}
              className="px-2.5 py-1 rounded-md text-xs font-mono font-medium
                         bg-slate-800/60 text-slate-400 border border-slate-700/40
                         hover:bg-slate-700/60 hover:text-slate-300 hover:border-slate-600/50
                         transition-all duration-150"
            >
              {ticker}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
