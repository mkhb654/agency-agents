import type {
  AnalystCategory,
  AnalystConfig,
  AnalystSignal,
  AnalysisRequest,
  AnalysisResult,
  BacktestRequest,
  BacktestResult,
  ModelOption,
  SignalDirection,
  TradeAction,
  TradeDecision,
  WSMessage,
} from "@/types";

const API_BASE = "/api";

// ─── Helpers ────────────────────────────────────────────────────────────────

async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    ...options,
  });

  if (!res.ok) {
    const body = await res.text().catch(() => "Unknown error");
    throw new Error(`API ${res.status}: ${body}`);
  }

  return res.json() as Promise<T>;
}

// ─── API Client ─────────────────────────────────────────────────────────────

export async function fetchAnalysts(): Promise<AnalystConfig[]> {
  try {
    const res = await request<{ analysts: { name: string; display_name: string; description: string }[]; total: number }>("/analysts");
    // Map backend shape to frontend AnalystConfig
    const categoryMap: Record<string, AnalystCategory> = {
      ben_graham: "investor_personas",
      warren_buffett: "investor_personas",
      peter_lynch: "investor_personas",
      cathie_wood: "investor_personas",
      michael_burry: "investor_personas",
      stanley_druckenmiller: "investor_personas",
      fundamentals_analyst: "analytical",
      technical_analyst: "analytical",
      sentiment_analyst: "analytical",
      valuation_analyst: "analytical",
      macro_analyst: "analytical",
      risk_manager: "decision",
      portfolio_manager: "decision",
    };
    return res.analysts.map((a) => ({
      id: a.name,
      name: a.display_name,
      description: a.description,
      category: categoryMap[a.name] ?? "analytical",
    }));
  } catch {
    return getDefaultAnalysts();
  }
}

export async function fetchModels(): Promise<ModelOption[]> {
  try {
    const res = await request<{ models: { provider: string; model_id: string; is_default: boolean }[]; total: number }>("/models");
    const nameMap: Record<string, string> = {
      "openai:gpt-4.1": "GPT-4.1 (OpenAI)",
      "anthropic:claude-sonnet-4-20250514": "Claude Sonnet 4 (Anthropic)",
      "google:gemini-2.0-flash": "Gemini 2.0 Flash (Google)",
      "groq:llama-3.3-70b-versatile": "Llama 3.3 70B (Groq)",
      "deepseek:deepseek-chat": "DeepSeek Chat",
      "ollama:llama3.2": "Llama 3.2 (Ollama - Free)",
    };
    return res.models.map((m) => ({
      provider: m.provider,
      model_id: m.model_id,
      display_name: nameMap[`${m.provider}:${m.model_id}`] ?? `${m.model_id} (${m.provider})`,
    }));
  } catch {
    return getDefaultModels();
  }
}

export async function runAnalysis(
  req: AnalysisRequest,
): Promise<AnalysisResult> {
  // Map frontend field names to backend expected names
  const backendReq = {
    tickers: req.tickers,
    analysts: req.analysts,
    model_provider: req.model_provider,
    model_name: req.model_id,
    start_date: req.start_date,
    end_date: req.end_date,
    show_reasoning: true,
  };

  const taskRes = await request<{ task_id: string; status: string; tickers: string[]; signals: unknown[]; decisions: unknown[]; message: string }>("/analyze", {
    method: "POST",
    body: JSON.stringify(backendReq),
  });

  // Poll for completion
  const taskId = taskRes.task_id;
  let attempts = 0;
  const maxAttempts = 120; // 2 minutes max

  while (attempts < maxAttempts) {
    await new Promise((r) => setTimeout(r, 2000));
    const status = await request<{ task_id: string; status: string; progress: number; message: string; result: Record<string, unknown> | null }>(`/tasks/${taskId}`);

    if (status.status === "completed" && status.result) {
      const signals: Record<string, AnalystSignal[]> = {};
      const rawSignals = (status.result.signals ?? []) as Array<{ analyst: string; ticker: string; signal: string; confidence: number; reasoning?: Record<string, unknown> }>;
      for (const s of rawSignals) {
        if (!signals[s.analyst]) signals[s.analyst] = [];
        signals[s.analyst].push({
          signal: s.signal as SignalDirection,
          confidence: s.confidence,
          reasoning: s.reasoning ?? {},
          agent_name: s.analyst,
          ticker: s.ticker,
        });
      }

      const rawDecisions = (status.result.decisions ?? []) as Array<{ action: string; ticker: string; quantity: number; confidence: number; reasoning: string }>;
      const decisions: TradeDecision[] = rawDecisions.map((d) => ({
        action: d.action as TradeAction,
        ticker: d.ticker,
        quantity: d.quantity,
        confidence: d.confidence,
        reasoning: d.reasoning,
      }));

      return {
        tickers: req.tickers,
        signals,
        decisions,
        risk_assessment: null,
        portfolio: null,
        timestamp: new Date().toISOString(),
      };
    }

    if (status.status === "failed") {
      throw new Error(status.message || "Analysis failed");
    }

    attempts++;
  }

  throw new Error("Analysis timed out");
}

export async function runBacktest(
  req: BacktestRequest,
): Promise<BacktestResult> {
  return request<BacktestResult>("/backtest", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

// ─── WebSocket ──────────────────────────────────────────────────────────────

export interface WSOptions {
  onMessage: (msg: WSMessage) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: Event) => void;
}

export function createWSConnection(options: WSOptions): {
  send: (data: unknown) => void;
  close: () => void;
} {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/analysis`;

  const ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    options.onOpen?.();
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data as string) as WSMessage;
      options.onMessage(msg);
    } catch {
      console.error("Failed to parse WebSocket message");
    }
  };

  ws.onclose = () => {
    options.onClose?.();
  };

  ws.onerror = (error) => {
    options.onError?.(error);
  };

  return {
    send: (data: unknown) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(data));
      }
    },
    close: () => {
      ws.close();
    },
  };
}

// ─── Default Data (when API is unavailable) ─────────────────────────────────

function getDefaultAnalysts(): AnalystConfig[] {
  return [
    {
      id: "warren_buffett",
      name: "Warren Buffett",
      description: "Value investing, durable competitive advantages, owner earnings",
      category: "investor_personas",
    },
    {
      id: "ben_graham",
      name: "Ben Graham",
      description: "Deep value, margin of safety, net-net analysis",
      category: "investor_personas",
    },
    {
      id: "peter_lynch",
      name: "Peter Lynch",
      description: "Growth at a reasonable price (GARP), know what you own",
      category: "investor_personas",
    },
    {
      id: "cathie_wood",
      name: "Cathie Wood",
      description: "Disruptive innovation, exponential growth, long-term tech trends",
      category: "investor_personas",
    },
    {
      id: "michael_burry",
      name: "Michael Burry",
      description: "Contrarian deep value, asymmetric bets, fraud detection",
      category: "investor_personas",
    },
    {
      id: "stanley_druckenmiller",
      name: "Stanley Druckenmiller",
      description: "Macro-driven, concentrated positions, risk/reward asymmetry",
      category: "investor_personas",
    },
    {
      id: "fundamentals_analyst",
      name: "Fundamentals Analyst",
      description: "Financial statements, ratios, earnings quality analysis",
      category: "analytical",
    },
    {
      id: "technical_analyst",
      name: "Technical Analyst",
      description: "Price action, momentum, volume, chart patterns",
      category: "analytical",
    },
    {
      id: "sentiment_analyst",
      name: "Sentiment Analyst",
      description: "News sentiment, insider trading, social signals",
      category: "analytical",
    },
    {
      id: "valuation_analyst",
      name: "Valuation Analyst",
      description: "DCF modeling, comparable analysis, intrinsic value estimation",
      category: "analytical",
    },
    {
      id: "risk_manager",
      name: "Risk Manager",
      description: "Position sizing, portfolio risk, correlation analysis, VaR",
      category: "decision",
    },
    {
      id: "portfolio_manager",
      name: "Portfolio Manager",
      description: "Final trade decisions, signal aggregation, order execution",
      category: "decision",
    },
  ];
}

function getDefaultModels(): ModelOption[] {
  return [
    { provider: "openai", model_id: "gpt-4.1", display_name: "GPT-4.1 (OpenAI)" },
    { provider: "openai", model_id: "gpt-4o", display_name: "GPT-4o (OpenAI)" },
    { provider: "openai", model_id: "gpt-4o-mini", display_name: "GPT-4o Mini (OpenAI)" },
    { provider: "anthropic", model_id: "claude-sonnet-4-20250514", display_name: "Claude Sonnet 4 (Anthropic)" },
    { provider: "anthropic", model_id: "claude-haiku-4-20250414", display_name: "Claude Haiku 4 (Anthropic)" },
    { provider: "google", model_id: "gemini-2.0-flash", display_name: "Gemini 2.0 Flash (Google)" },
    { provider: "groq", model_id: "llama-3.3-70b-versatile", display_name: "Llama 3.3 70B (Groq)" },
    { provider: "deepseek", model_id: "deepseek-chat", display_name: "DeepSeek Chat" },
    { provider: "ollama", model_id: "qwen3:14b", display_name: "Qwen3 14B (Ollama - Free)" },
    { provider: "ollama", model_id: "llama3.2", display_name: "Llama 3.2 (Ollama - Free)" },
  ];
}
