export type LiveStatus = "live" | "polling" | "dead";

export const STATS_POLL_MS = 10_000;
export const RECONNECT_BASE_MS = 2_000;
export const RECONNECT_MAX_MS = 30_000;

export function shouldReconnect(status: LiveStatus, enabled: boolean): boolean {
  return enabled && status === "polling";
}

export function backoffMs(attempt: number): number {
  const exp = RECONNECT_BASE_MS * 2 ** Math.max(0, attempt);
  return Math.min(exp, RECONNECT_MAX_MS);
}