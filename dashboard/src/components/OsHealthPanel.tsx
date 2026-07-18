import type { OsSnapshot } from "../api/client";
import { formatUptime, LEVEL_COLOR, metricLevel, type OsLevel } from "../utils/osHealth";

function Bar({ label, pct, level, detail }: { label: string; pct: number; level: OsLevel; detail: string }) {
  return (
    <div style={{ flex: "1 1 160px", minWidth: 140 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, textTransform: "uppercase", color: "var(--text-muted)" }}>
        <span>{label}</span>
        <span className="mono" style={{ color: LEVEL_COLOR[level] }}>
          {pct.toFixed(1)}%
        </span>
      </div>
      <div style={{ height: 6, background: "var(--border)", borderRadius: 4, marginTop: 4 }}>
        <div
          style={{
            width: `${Math.min(100, Math.max(0, pct))}%`,
            height: "100%",
            borderRadius: 4,
            background: LEVEL_COLOR[level],
          }}
        />
      </div>
      <div className="mono" style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
        {detail}
      </div>
    </div>
  );
}

export function OsHealthPanel({ os }: { os: OsSnapshot | null }) {
  if (!os) {
    return (
      <section id="panel-os" className="panel" style={{ gridColumn: "span 12" }}>
        <h3 style={{ margin: 0 }}>Host OS Health</h3>
        <div style={{ color: "var(--text-muted)", fontSize: 14, marginTop: 8 }}>
          Fetching host telemetry…
        </div>
      </section>
    );
  }

  const usedMemMb = os.memory.total_mb - os.memory.available_mb;
  const usedDiskGb = os.disk.total_gb - os.disk.free_gb;

  return (
    <section id="panel-os" className="panel" style={{ gridColumn: "span 12" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <h3 style={{ margin: 0 }}>Host OS Health</h3>
        <span
          className="mono"
          style={{
            display: "inline-block",
            padding: "4px 12px",
            borderRadius: 999,
            fontSize: 13,
            fontWeight: 700,
            color: "#000",
            background: LEVEL_COLOR[os.status],
          }}
        >
          {os.status.toUpperCase()}
        </span>
      </div>

      <div style={{ display: "flex", gap: 24, flexWrap: "wrap", margin: "12px 0" }}>
        <Bar
          label="CPU"
          pct={os.cpu.percent}
          level={metricLevel("cpu", os.cpu.percent)}
          detail={`${os.cpu.cores_logical ?? "?"} logical cores`}
        />
        <Bar
          label="Memory"
          pct={os.memory.percent}
          level={metricLevel("memory", os.memory.percent)}
          detail={`${(usedMemMb / 1024).toFixed(1)} / ${(os.memory.total_mb / 1024).toFixed(1)} GB`}
        />
        <Bar
          label="Disk"
          pct={os.disk.percent}
          level={metricLevel("disk", os.disk.percent)}
          detail={`${usedDiskGb.toFixed(0)} / ${os.disk.total_gb.toFixed(0)} GB on ${os.disk.path}`}
        />
      </div>

      {os.concerns.length > 0 && (
        <div style={{ color: "var(--amber)", fontSize: 13, marginBottom: 6 }}>
          ▸ {os.concerns.join(" · ")}
        </div>
      )}

      <div className="mono" style={{ fontSize: 12, color: "var(--text-muted)" }}>
        {os.system.process_count} processes · up {formatUptime(os.system.uptime_seconds)}
        {os.process ? ` · server ${os.process.rss_mb.toFixed(0)} MB rss` : ""}
        {os.network?.recv_kbps != null
          ? ` · net ↓${os.network.recv_kbps.toFixed(1)} ↑${os.network.sent_kbps?.toFixed(1) ?? "?"} KB/s`
          : ""}
      </div>
    </section>
  );
}
