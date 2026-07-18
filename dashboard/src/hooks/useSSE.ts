import { useCallback, useEffect, useRef, useState } from "react";
import { backoffMs, shouldReconnect, STATS_POLL_MS, type LiveStatus } from "./sseReconnect";

export type { LiveStatus };
export type StreamEvent = {
  type?: string;
  ts: string;
  tool?: string;
  agent_id?: string;
  meta?: Record<string, unknown>;
};

export function useSSE(enabled: boolean, onEvent: (e: StreamEvent) => void) {
  const [status, setStatus] = useState<LiveStatus>("dead");
  const [reconnectNonce, setReconnectNonce] = useState(0);
  const esRef = useRef<EventSource | null>(null);
  const reconnectAttemptRef = useRef(0);

  const connect = useCallback(() => {
    if (!enabled) return;
    esRef.current?.close();
    const es = new EventSource("/api/events");
    esRef.current = es;
    es.onopen = () => {
      reconnectAttemptRef.current = 0;
      setStatus("live");
    };
    es.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data) as StreamEvent;
        if (data.type === "heartbeat") {
          reconnectAttemptRef.current = 0;
          setStatus("live");
          return;
        }
        onEvent(data);
        reconnectAttemptRef.current = 0;
        setStatus("live");
      } catch {
        /* ignore */
      }
    };
    es.onerror = () => {
      setStatus("polling");
      es.close();
      setReconnectNonce((n) => n + 1);
    };
  }, [enabled, onEvent]);

  useEffect(() => {
    connect();
    return () => esRef.current?.close();
  }, [connect]);

  useEffect(() => {
    if (!shouldReconnect(status, enabled)) return;

    const delay = backoffMs(reconnectAttemptRef.current);
    reconnectAttemptRef.current += 1;
    const reconnectId = setTimeout(() => connect(), delay);
    return () => clearTimeout(reconnectId);
  }, [status, enabled, reconnectNonce, connect]);

  useEffect(() => {
    if (!enabled || status !== "polling") return;
    const id = setInterval(async () => {
      try {
        await fetch("/api/stats");
        setStatus("polling");
      } catch {
        setStatus("dead");
      }
    }, STATS_POLL_MS);
    return () => clearInterval(id);
  }, [enabled, status]);

  return { status, reconnect: connect };
}