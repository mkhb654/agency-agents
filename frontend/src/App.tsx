import { useState } from "react";
import {
  LayoutDashboard,
  History,
  Settings,
  TrendingUp,
  Menu,
  X,
} from "lucide-react";
import { clsx } from "clsx";
import type { AppView } from "@/types";
import Dashboard from "@/components/Dashboard";
import BacktestView from "@/components/BacktestView";

// ─── Navigation items ───────────────────────────────────────────────────────

const NAV_ITEMS: { id: AppView; label: string; icon: typeof LayoutDashboard }[] = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "backtest", label: "Backtest", icon: History },
  { id: "settings", label: "Settings", icon: Settings },
];

// ─── Settings Panel ─────────────────────────────────────────────────────────

function SettingsPanel() {
  return (
    <div className="max-w-2xl space-y-6">
      <div className="glass-card p-6 space-y-5">
        <h2 className="text-lg font-semibold text-slate-100">General Settings</h2>

        <div className="space-y-4">
          <div>
            <label className="label-text" htmlFor="api-url">
              API URL
            </label>
            <input
              id="api-url"
              type="text"
              defaultValue="http://localhost:8000"
              className="input-field font-mono text-sm"
            />
            <p className="text-[10px] text-slate-500 mt-1">
              Backend API server address for analysis and backtest endpoints.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label-text" htmlFor="initial-cash-setting">
                Default Initial Cash
              </label>
              <input
                id="initial-cash-setting"
                type="number"
                defaultValue={100000}
                min={1000}
                step={10000}
                className="input-field font-mono"
              />
            </div>
            <div>
              <label className="label-text" htmlFor="risk-free-rate">
                Risk-Free Rate
              </label>
              <input
                id="risk-free-rate"
                type="number"
                defaultValue={0.045}
                min={0}
                max={1}
                step={0.005}
                className="input-field font-mono"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label-text" htmlFor="max-position">
                Max Position Size (%)
              </label>
              <input
                id="max-position"
                type="number"
                defaultValue={25}
                min={1}
                max={100}
                className="input-field font-mono"
              />
            </div>
            <div>
              <label className="label-text" htmlFor="margin-req">
                Margin Requirement (%)
              </label>
              <input
                id="margin-req"
                type="number"
                defaultValue={50}
                min={10}
                max={100}
                className="input-field font-mono"
              />
            </div>
          </div>
        </div>
      </div>

      <div className="glass-card p-6 space-y-5">
        <h2 className="text-lg font-semibold text-slate-100">LLM Provider Keys</h2>
        <p className="text-xs text-slate-400">
          API keys are stored locally and sent with each request to the backend.
          Only the key for your selected provider is required.
        </p>

        <div className="space-y-3">
          {[
            { id: "openai", label: "OpenAI" },
            { id: "anthropic", label: "Anthropic" },
            { id: "google", label: "Google AI" },
            { id: "groq", label: "Groq" },
            { id: "deepseek", label: "DeepSeek" },
          ].map((provider) => (
            <div key={provider.id}>
              <label className="label-text" htmlFor={`key-${provider.id}`}>
                {provider.label} API Key
              </label>
              <input
                id={`key-${provider.id}`}
                type="password"
                placeholder={`Enter your ${provider.label} API key...`}
                className="input-field font-mono text-xs"
              />
            </div>
          ))}
        </div>
      </div>

      <div className="glass-card p-6 space-y-4">
        <h2 className="text-lg font-semibold text-slate-100">About</h2>
        <div className="space-y-2 text-sm text-slate-400">
          <p>
            <span className="font-semibold text-slate-300">Agency Hedge Fund</span>{" "}
            is an AI-powered multi-agent system that combines legendary investor
            philosophies with quantitative analysis to make trading decisions.
          </p>
          <p>
            Each agent independently analyzes stocks using financial data, then a
            portfolio manager synthesizes all signals into concrete trade decisions
            while a risk manager enforces position limits and portfolio constraints.
          </p>
        </div>
        <div className="flex items-center gap-4 pt-2">
          <div className="text-xs text-slate-500">
            <span className="font-medium text-slate-400">Version</span> 1.0.0
          </div>
          <div className="text-xs text-slate-500">
            <span className="font-medium text-slate-400">Backend</span> FastAPI + LangGraph
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Main App ───────────────────────────────────────────────────────────────

export default function App() {
  const [activeView, setActiveView] = useState<AppView>("dashboard");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="min-h-screen flex flex-col">
      {/* ── Header ──────────────────────────────────────────────────── */}
      <header className="h-14 border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-lg flex items-center justify-between px-4 lg:px-6 shrink-0 z-40 sticky top-0">
        <div className="flex items-center gap-3">
          {/* Mobile menu button */}
          <button
            type="button"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="lg:hidden btn-ghost p-2"
          >
            {sidebarOpen ? <X size={18} /> : <Menu size={18} />}
          </button>

          {/* Logo */}
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-emerald-500 to-cyan-500 flex items-center justify-center shadow-lg shadow-emerald-900/30">
              <TrendingUp size={16} className="text-white" />
            </div>
            <div>
              <h1 className="text-sm font-bold tracking-tight text-slate-100">
                Agency <span className="text-gradient">Hedge Fund</span>
              </h1>
              <p className="text-[9px] text-slate-500 font-medium uppercase tracking-widest leading-none">
                AI-Powered Multi-Agent Trading
              </p>
            </div>
          </div>
        </div>

        {/* Right side */}
        <div className="flex items-center gap-3">
          <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-800/60 border border-slate-700/30">
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-[10px] text-slate-400 font-medium">System Ready</span>
          </div>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* ── Sidebar ─────────────────────────────────────────────────── */}
        {/* Mobile overlay */}
        {sidebarOpen && (
          <div
            className="fixed inset-0 bg-black/50 z-30 lg:hidden"
            onClick={() => setSidebarOpen(false)}
          />
        )}

        <aside
          className={clsx(
            "fixed lg:static inset-y-0 left-0 z-30 w-56 bg-slate-950 border-r border-slate-800/60 flex flex-col transition-transform duration-200 lg:translate-x-0 pt-14 lg:pt-0",
            sidebarOpen ? "translate-x-0" : "-translate-x-full",
          )}
        >
          <nav className="flex-1 p-3 space-y-1">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const isActive = activeView === item.id;

              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    setActiveView(item.id);
                    setSidebarOpen(false);
                  }}
                  className={clsx(
                    "w-full",
                    isActive ? "nav-item-active" : "nav-item-inactive",
                  )}
                >
                  <Icon size={16} />
                  {item.label}
                </button>
              );
            })}
          </nav>

          {/* Sidebar footer */}
          <div className="p-4 border-t border-slate-800/60">
            <div className="text-[10px] text-slate-600 space-y-0.5">
              <p>6 Investor Persona Agents</p>
              <p>4 Analytical Agents</p>
              <p>2 Decision Agents</p>
            </div>
          </div>
        </aside>

        {/* ── Main content ────────────────────────────────────────────── */}
        <main className="flex-1 overflow-y-auto">
          <div className="p-4 lg:p-6 max-w-[1600px] mx-auto">
            {/* Page title */}
            <div className="mb-6">
              <h2 className="text-xl font-bold text-slate-100">
                {activeView === "dashboard" && "Analysis Dashboard"}
                {activeView === "backtest" && "Backtesting"}
                {activeView === "settings" && "Settings"}
              </h2>
              <p className="text-xs text-slate-500 mt-1">
                {activeView === "dashboard" &&
                  "Configure and run multi-agent analysis on any stock ticker."}
                {activeView === "backtest" &&
                  "Simulate historical performance of the AI trading system."}
                {activeView === "settings" &&
                  "Configure API connections, portfolio parameters, and LLM providers."}
              </p>
            </div>

            {/* View content */}
            {activeView === "dashboard" && <Dashboard />}
            {activeView === "backtest" && <BacktestView />}
            {activeView === "settings" && <SettingsPanel />}
          </div>
        </main>
      </div>
    </div>
  );
}
