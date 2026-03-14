import type {
  AnalystConfig,
  AnalysisRequest,
  AnalysisResult,
  BacktestRequest,
  BacktestResult,
  ModelOption,
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
    return await request<AnalystConfig[]>("/analysts");
  } catch {
    // Return default analysts when API is unavailable
    return getDefaultAnalysts();
  }
}

export async function fetchModels(): Promise<ModelOption[]> {
  try {
    return await request<ModelOption[]>("/models");
  } catch {
    return getDefaultModels();
  }
}

export async function runAnalysis(
  req: AnalysisRequest,
): Promise<AnalysisResult> {
  return request<AnalysisResult>("/analysis", {
    method: "POST",
    body: JSON.stringify(req),
  });
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
  ];
}
