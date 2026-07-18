export type OsLevel = "ok" | "warn" | "critical";

export const LEVEL_COLOR: Record<OsLevel, string> = {
  ok: "var(--green)",
  warn: "var(--amber)",
  critical: "var(--red)",
};

// Mirrors server defaults in app/config.py (OS_CPU/MEM/DISK_WARN/CRIT_PCT).
const THRESHOLDS = {
  cpu: [75, 90],
  memory: [80, 92],
  disk: [85, 95],
} as const;

export function metricLevel(metric: keyof typeof THRESHOLDS, pct: number): OsLevel {
  const [warnAt, critAt] = THRESHOLDS[metric];
  if (pct >= critAt) return "critical";
  if (pct >= warnAt) return "warn";
  return "ok";
}

export function formatUptime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "—";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}
