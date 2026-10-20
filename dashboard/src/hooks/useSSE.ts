import { useCallback, useEffect, useRef, useState } from "react";
import { API } from "../api/client";
import { backoffMs, shouldReconnect, STATS_POLL_MS, type ServerStatus } from "./sseReconnect";

export type { ServerStatus };
export type StreamEvent = {
  type?: string;
  ts: string;
  tool?: string;
  agent_id?: string;
  meta?: Record<string, unknown>;
};

export function useSSE(enabled: boolean, onEvent: (e: StreamEvent) => void) {
  const [status, setStatus] = useState<ServerStatus>("checking");
  const [reconnectNonce, setReconnectNonce] = useState(0);
  const esRef = useRef<EventSource | null>(null);
  const reconnectAttemptRef = useRef(0);

  const connect = useCallback(() => {
    if (!enabled) return;
    esRef.current?.close();
    const es = new EventSource(`${API}/events`);
    esRef.current = es;
    es.onopen = () => {
      reconnectAttemptRef.current = 0;
      setStatus("connected");
    };
    es.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data) as StreamEvent;
        if (data.type === "heartbeat") {
          reconnectAttemptRef.current = 0;
          setStatus("connected");
          return;
        }
        onEvent(data);
        reconnectAttemptRef.current = 0;
        setStatus("connected");
      } catch {
        /* ignore */
      }
    };
    es.onerror = () => {
      setStatus("degraded");
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
    if (!enabled || status !== "degraded") return;
    const id = setInterval(async () => {
      try {
        await fetch(`${API}/stats`);
        setStatus("degraded"); // still polling
      } catch {
        setStatus("disconnected");
      }
    }, STATS_POLL_MS);
    return () => clearInterval(id);
  }, [enabled, status]);

  return { status, reconnect: connect };
}