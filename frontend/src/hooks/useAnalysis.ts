import { useCallback, useEffect, useRef, useState } from "react";
import type {
  AnalysisRequest,
  AnalysisResult,
  AnalystSignal,
  TradeDecision,
  WSMessage,
} from "@/types";
import { createWSConnection, runAnalysis } from "@/lib/api";

export interface UseAnalysisReturn {
  /** Whether an analysis is currently running */
  loading: boolean;
  /** Final analysis result (null until complete) */
  result: AnalysisResult | null;
  /** Streaming signals received so far */
  streamingSignals: AnalystSignal[];
  /** Streaming trade decisions received so far */
  streamingDecisions: TradeDecision[];
  /** Error message if the analysis failed */
  error: string | null;
  /** Whether the WebSocket is connected */
  connected: boolean;
  /** Kick off an analysis run */
  analyze: (request: AnalysisRequest) => Promise<void>;
  /** Clear all results and errors */
  reset: () => void;
}

export function useAnalysis(): UseAnalysisReturn {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [streamingSignals, setStreamingSignals] = useState<AnalystSignal[]>([]);
  const [streamingDecisions, setStreamingDecisions] = useState<TradeDecision[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);

  const wsRef = useRef<{ send: (data: unknown) => void; close: () => void } | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  // Cleanup on unmount
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      wsRef.current?.close();
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
    };
  }, []);

  const connectWS = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
    }

    const conn = createWSConnection({
      onMessage: (msg: WSMessage) => {
        if (!mountedRef.current) return;

        switch (msg.type) {
          case "agent_signal": {
            const signal = msg.data as AnalystSignal;
            setStreamingSignals((prev) => [...prev, signal]);
            break;
          }
          case "trade_decision": {
            const decision = msg.data as TradeDecision;
            setStreamingDecisions((prev) => [...prev, decision]);
            break;
          }
          case "analysis_complete": {
            const analysisResult = msg.data as AnalysisResult;
            setResult(analysisResult);
            setLoading(false);
            break;
          }
          case "analysis_error": {
            const errData = msg.data as { error: string };
            setError(errData.error);
            setLoading(false);
            break;
          }
          default:
            break;
        }
      },
      onOpen: () => {
        if (mountedRef.current) setConnected(true);
      },
      onClose: () => {
        if (mountedRef.current) {
          setConnected(false);
          // Auto-reconnect after 3 seconds
          reconnectTimerRef.current = setTimeout(() => {
            if (mountedRef.current) connectWS();
          }, 3000);
        }
      },
      onError: () => {
        if (mountedRef.current) setConnected(false);
      },
    });

    wsRef.current = conn;
  }, []);

  // Try to connect WS on mount
  useEffect(() => {
    connectWS();
  }, [connectWS]);

  const analyze = useCallback(
    async (request: AnalysisRequest) => {
      setLoading(true);
      setError(null);
      setResult(null);
      setStreamingSignals([]);
      setStreamingDecisions([]);

      // Try WebSocket first
      if (connected && wsRef.current) {
        wsRef.current.send({ type: "run_analysis", data: request });
        return;
      }

      // Fall back to REST API
      try {
        const analysisResult = await runAnalysis(request);
        if (mountedRef.current) {
          setResult(analysisResult);

          // Populate streaming signals from the result for display
          if (analysisResult.signals) {
            const allSignals: AnalystSignal[] = [];
            for (const signals of Object.values(analysisResult.signals)) {
              allSignals.push(...signals);
            }
            setStreamingSignals(allSignals);
          }
          if (analysisResult.decisions) {
            setStreamingDecisions(analysisResult.decisions);
          }
        }
      } catch (err) {
        if (mountedRef.current) {
          setError(err instanceof Error ? err.message : "Analysis failed");
        }
      } finally {
        if (mountedRef.current) {
          setLoading(false);
        }
      }
    },
    [connected],
  );

  const reset = useCallback(() => {
    setLoading(false);
    setResult(null);
    setStreamingSignals([]);
    setStreamingDecisions([]);
    setError(null);
  }, []);

  return {
    loading,
    result,
    streamingSignals,
    streamingDecisions,
    error,
    connected,
    analyze,
    reset,
  };
}
