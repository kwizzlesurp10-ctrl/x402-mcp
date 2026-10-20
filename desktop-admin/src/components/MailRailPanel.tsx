import { useEffect, useState } from "react";
import { api, type MailRailHealth, type MailRailMessage, type MailRailStats } from "../api/client";
import { relativeTime } from "@dashboard/utils/time";

type MailRailPanelProps = {
  refreshKey: number;
};

export function MailRailPanel({ refreshKey }: MailRailPanelProps) {
  const [health, setHealth] = useState<MailRailHealth | null>(null);
  const [stats, setStats] = useState<MailRailStats | null>(null);
  const [outbox, setOutbox] = useState<MailRailMessage[]>([]);
  const [inbox, setInbox] = useState<MailRailMessage[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [h, s, ledger, inboxRes] = await Promise.all([
          api.mailrailHealth(),
          api.mailrailStats(),
          api.mailrailLedger(25),
          api.mailrailInbox(25),
        ]);
        if (cancelled) return;
        setHealth(h);
        setStats(s);
        setOutbox(ledger.events);
        setInbox(inboxRes.inbox);
        setError(null);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "MailRail fetch failed");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  return (
    <section id="panel-mailrail" className="panel" style={{ gridColumn: "span 12" }}>
      <h3>AgentMail / MailRail</h3>
      {error && <p style={{ color: "var(--red)", fontSize: 13 }}>{error}</p>}
      {health && (
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 12, fontSize: 13 }}>
          <span style={{ color: health.enabled ? "var(--green)" : "var(--amber)" }}>
            {health.enabled ? "enabled" : "disabled"}
          </span>
          <span>provider: <strong>{health.provider}</strong></span>
          <span>from: <span className="mono">{health.from_address || "—"}</span></span>
          <span>admin: <span className="mono">{health.admin_recipient || "—"}</span></span>
          {stats && (
            <span className="mono">
              outbox {stats.outbound_total ?? stats.outbox_count ?? outbox.length} · inbox{" "}
              {stats.inbound_total ?? stats.inbox_count ?? inbox.length}
            </span>
          )}
        </div>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <MailList title="Outbox (dispatches)" items={outbox} kind="outbox" />
        <MailList title="Inbox (inbound)" items={inbox} kind="inbox" />
      </div>
    </section>
  );
}

function MailList({
  title,
  items,
  kind,
}: {
  title: string;
  items: MailRailMessage[];
  kind: "outbox" | "inbox";
}) {
  return (
    <div>
      <h4 style={{ marginBottom: 8, fontSize: 13 }}>{title}</h4>
      {items.length === 0 ? (
        <p style={{ color: "var(--text-muted)", fontSize: 13 }}>No messages yet.</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, maxHeight: 220, overflow: "auto" }}>
          {items.map((m, i) => (
            <li
              key={m.event_id ?? m.inbound_id ?? `${kind}-${i}`}
              style={{
                fontSize: 12,
                marginBottom: 8,
                paddingBottom: 8,
                borderBottom: "1px solid var(--border)",
              }}
            >
              <div className="mono" style={{ color: "var(--text-muted)" }}>
                {m.ts ? relativeTime(m.ts) : "—"}
              </div>
              <strong>{m.subject ?? "(no subject)"}</strong>
              <div style={{ color: "var(--text-muted)", marginTop: 2 }}>
                {kind === "outbox" ? `to ${m.to ?? "—"}` : `from ${m.sender ?? m.from ?? "—"}`}
                {m.status === "dispatch_failed" || m.delivered === false ? " · failed" : ""}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
