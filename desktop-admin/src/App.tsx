import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  getApiBase,
  type DoctorCheck,
  type LedgerRow,
  type OsSnapshot,
  type PulseResponse,
  type StatsResponse,
  type SwarmAssessment,
  type SwarmProduct,
  type SwarmRevenue,
  type WalletResponse,
} from "./api/client";
import { readStoredApiBase } from "./config";
import { AdminHeader } from "./components/AdminHeader";
import { MailRailPanel } from "./components/MailRailPanel";
import { SettingsDialog } from "./components/SettingsDialog";
import { ActiveStorefront } from "@dashboard/components/ActiveStorefront";
import { CommandPalette } from "@dashboard/components/CommandPalette";
import { Inspector402 } from "@dashboard/components/Inspector402";
import { OsHealthPanel } from "@dashboard/components/OsHealthPanel";
import { PanelHelp } from "@dashboard/components/PanelHelp";
import { PulsePanel } from "@dashboard/components/PulsePanel";
import { RateSparkline } from "@dashboard/components/RateSparkline";
import { SellerWizard } from "@dashboard/components/SellerWizard";
import { SwarmActivity } from "@dashboard/components/SwarmActivity";
import { SwarmAssessmentPanel } from "@dashboard/components/SwarmAssessmentPanel";
import { VirtualizedLedger } from "@dashboard/components/VirtualizedLedger";
import { WalletPanel } from "@dashboard/components/WalletPanel";
import { useSSE, type StreamEvent } from "./hooks/useSSE";
import { calculateFinances } from "@dashboard/utils/finance";
import { downloadText, ledgerToCsv } from "@dashboard/utils/ledger";
import { formatUsdcAtomic } from "@dashboard/utils/usdc";
import { relativeTime } from "@dashboard/utils/time";

const DENSITY = "operator" as const;

function EmptyPanel({ title, action, command }: { title: string; action: string; command?: string }) {
  return (
    <div style={{ color: "var(--text-muted)", fontSize: 14 }}>
      <strong>{title}</strong>
      <p>{action}</p>
      {command && (
        <pre className="mono" style={{ background: "#0b0f14", padding: 8, borderRadius: 8 }}>
          {command}
        </pre>
      )}
    </div>
  );
}

export default function App() {
  const [apiBase, setApiBaseState] = useState(readStoredApiBase());
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [doctor, setDoctor] = useState<DoctorCheck[]>([]);
  const [doctorReady, setDoctorReady] = useState(true);
  const [spend, setSpend] = useState<LedgerRow[]>([]);
  const [revenue, setRevenue] = useState<LedgerRow[]>([]);
  const [wallet, setWallet] = useState<WalletResponse | null>(null);
  const [pulse, setPulse] = useState<PulseResponse | null>(null);
  const [os, setOs] = useState<OsSnapshot | null>(null);
  const [products, setProducts] = useState<SwarmProduct[]>([]);
  const [swarmRevenue, setSwarmRevenue] = useState<SwarmRevenue | null>(null);
  const [swarmAssessment, setSwarmAssessment] = useState<SwarmAssessment | null>(null);
  const [activity, setActivity] = useState<StreamEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [sellerOpen, setSellerOpen] = useState(false);
  const [rateHistory, setRateHistory] = useState<number[]>([]);
  const [ledgerFilterNetwork] = useState("");
  const [ledgerFilterAgent, setLedgerFilterAgent] = useState("");
  const [wizardOpen, setWizardOpen] = useState(false);
  const autoDoctorPromptedRef = useRef(false);

  const refresh = useCallback(async () => {
    try {
      const [s, d, sp, rev, w, pr, srev, sass] = await Promise.all([
        api.stats(),
        api.doctor(),
        api.ledgerSpend(),
        api.ledgerRevenue(),
        api.wallet(),
        api.swarmProducts(),
        api.swarmRevenue(),
        api.swarmAssessment(),
      ]);
      setStats(s);
      setDoctor(d.checks);
      setDoctorReady(d.summary.ready);
      setSpend(sp);
      setRevenue(rev);
      setWallet(w);
      setProducts(pr);
      setSwarmRevenue(srev);
      setSwarmAssessment(sass);
      api.pulse().then(setPulse).catch(() => setPulse(null));
      api.os().then(setOs).catch(() => setOs(null));
      const rateRemaining = s.agents.length
        ? Math.min(...s.agents.map((a) => a.rate_limit_remaining))
        : 10;
      setRateHistory((prev) => [...prev, rateRemaining].slice(-24));
      setError(null);
      setRefreshKey((k) => k + 1);
      if (!d.summary.ready && !autoDoctorPromptedRef.current) {
        setWizardOpen(true);
        autoDoctorPromptedRef.current = true;
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to reach API — run `make api`");
    }
  }, []);

  const onEvent = useCallback(
    (e: StreamEvent) => {
      setActivity((prev) => [e, ...prev].slice(0, 200));
      refresh();
    },
    [refresh],
  );

  const { status: serverStatus, reconnect } = useSSE(true, onEvent, apiBase);

  useEffect(() => {
    refresh();
  }, [refresh, apiBase]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const finances = useMemo(() => calculateFinances(revenue, spend), [revenue, spend]);
  const netAtomic = finances.netMarginAtomic;
  const totalCalls = stats?.agents.reduce((n, a) => n + a.calls_this_month, 0) ?? 0;
  const quotaLimit = stats?.config.free_tier_monthly_quota ?? 500;
  const actionsEnabled = import.meta.env.VITE_DASHBOARD_ACTIONS === "true";

  const paletteActions = useMemo(
    () => [
      { id: "refresh", label: "Refresh all panels", run: () => refresh() },
      { id: "settings", label: "API settings", run: () => setSettingsOpen(true) },
      { id: "seller", label: "Open seller wizard", run: () => setSellerOpen(true) },
      { id: "doctor", label: "Open doctor wizard", run: () => setWizardOpen(true) },
      {
        id: "filter-spend",
        label: "Filter spend ledger by agent",
        run: () => setLedgerFilterAgent(prompt("Agent id prefix") ?? ""),
      },
    ],
    [refresh],
  );

  return (
    <div className="mc-root" style={{ minHeight: "100vh", background: "var(--color-base)" }}>
      <AdminHeader
        apiBase={getApiBase()}
        serverStatus={serverStatus}
        doctorReady={doctorReady}
        onOpenSettings={() => setSettingsOpen(true)}
        onReconnect={reconnect}
        onRefresh={refresh}
      />

      {error && (
        <div style={{ padding: "8px 16px", background: "rgba(229,72,77,0.15)", color: "var(--red)" }}>
          {error}
        </div>
      )}

      {wizardOpen && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.7)",
            zIndex: 10,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
          role="dialog"
          aria-label="Doctor checks"
        >
          <div className="panel mc-modal-panel" style={{ width: 520, maxHeight: "80vh", overflow: "auto" }}>
            <h2>Doctor / config health</h2>
            <ul style={{ listStyle: "none", padding: 0 }}>
              {doctor.map((c) => (
                <li key={c.id} style={{ marginBottom: 12 }}>
                  <span
                    style={{
                      color:
                        c.status === "pass" ? "var(--green)" : c.status === "fail" ? "var(--red)" : "var(--amber)",
                    }}
                  >
                    {c.status.toUpperCase()}
                  </span>{" "}
                  <strong>{c.name}</strong>: {c.message}
                  {c.fix && <pre className="mono" style={{ fontSize: 12 }}>{c.fix}</pre>}
                </li>
              ))}
            </ul>
            <button type="button" onClick={() => setWizardOpen(false)}>Close</button>
          </div>
        </div>
      )}

      <main className="grid-12" style={{ padding: 16 }}>
        <section id="panel-hero" className="panel" style={{ gridColumn: "span 3" }}>
          <h3>
            Net position
            <PanelHelp term="net" title="Net position" />
          </h3>
          <div className="mono" style={{ fontSize: 32, color: netAtomic >= 0 ? "var(--green)" : "var(--usdc)" }}>
            {formatUsdcAtomic(netAtomic)}
          </div>
        </section>

        <section className="panel" style={{ gridColumn: "span 3" }}>
          <h3>Quota <PanelHelp term="quota" title="Quota" /></h3>
          {totalCalls === 0 ? (
            <EmptyPanel title="No calls yet" action="Run your first free discovery." command="discover_services via MCP" />
          ) : (
            <>
              <div className="mono">{totalCalls} / {quotaLimit}</div>
              <div style={{ height: 8, background: "var(--border)", borderRadius: 4, marginTop: 8 }}>
                <div
                  style={{
                    width: `${Math.min(100, (totalCalls / quotaLimit) * 100)}%`,
                    height: "100%",
                    background: totalCalls / quotaLimit >= 0.8 ? "var(--amber)" : "var(--usdc)",
                  }}
                />
              </div>
            </>
          )}
        </section>

        <section id="panel-wallet" className="panel" style={{ gridColumn: "span 3" }}>
          <h3>Wallet <PanelHelp term="atomic units" title="Wallet" /></h3>
          <WalletPanel wallet={wallet} density={DENSITY} />
        </section>

        <section className="panel" style={{ gridColumn: "span 3" }}>
          <h3>Rate <PanelHelp term="quota" title="Rate limit" /></h3>
          <RateSparkline series={rateHistory} />
          <div className="mono">{stats?.agents[0]?.rate_limit_remaining ?? "—"} / min left</div>
        </section>

        <OsHealthPanel os={os} />
        <ActiveStorefront products={products} revenueRows={revenue} activityEvents={activity} />

        <SwarmAssessmentPanel assessment={swarmAssessment} density={DENSITY} />

        <PulsePanel pulse={pulse} />
        <SwarmActivity events={activity} products={products} revenue={swarmRevenue ?? undefined} />

        <MailRailPanel refreshKey={refreshKey} />

        <section id="panel-activity" className="panel" style={{ gridColumn: "span 8" }}>
          <h3>Activity stream</h3>
          {activity.length === 0 ? (
            <EmptyPanel title="Quiet" action="Tool calls appear here via SSE." />
          ) : (
            <ul style={{ listStyle: "none", padding: 0, maxHeight: 240, overflow: "auto" }}>
              {activity.map((e, i) => (
                <li key={i} className="mono" style={{ fontSize: 12, marginBottom: 4 }}>
                  <span title={e.ts}>{relativeTime(e.ts)}</span> [{e.agent_id}] {e.tool}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel" style={{ gridColumn: "span 4" }}>
          <h3>Agent lanes</h3>
          {["scout", "warden", "treasurer", "archivist", "merchant", "sovereign"].map((lane) => {
            const agent = stats?.agents.find((a) => a.agent_id.startsWith(lane));
            return (
              <div key={lane} style={{ marginBottom: 8 }}>
                <strong>{lane}</strong>{" "}
                <span className="mono">{agent?.calls_this_month ?? 0} calls</span>
              </div>
            );
          })}
        </section>

        <section id="panel-spend" className="panel" style={{ gridColumn: "span 6" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h3 style={{ margin: 0 }}>Spend ledger</h3>
            {spend.length > 0 && (
              <button type="button" onClick={() => downloadText("spend.csv", ledgerToCsv(spend), "text/csv")}>
                CSV
              </button>
            )}
          </div>
          {spend.length === 0 ? (
            <EmptyPanel title="Nothing spent" action="Try a $0 testnet fetch first." command="pay_and_fetch on Sepolia" />
          ) : (
            <VirtualizedLedger
              rows={spend}
              kind="spend"
              filterNetwork={ledgerFilterNetwork || undefined}
              filterAgent={ledgerFilterAgent || undefined}
            />
          )}
        </section>

        <section id="panel-revenue" className="panel" style={{ gridColumn: "span 6" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h3 style={{ margin: 0 }}>Revenue ledger</h3>
            {revenue.length > 0 && (
              <button
                type="button"
                onClick={() =>
                  downloadText("revenue.jsonl", revenue.map((r) => JSON.stringify(r)).join("\n"), "application/jsonl")
                }
              >
                JSONL
              </button>
            )}
          </div>
          {revenue.length === 0 ? (
            <EmptyPanel title="No revenue yet" action="Build seller requirements and verify a payment." />
          ) : (
            <VirtualizedLedger
              rows={revenue}
              kind="revenue"
              filterNetwork={ledgerFilterNetwork || undefined}
              filterAgent={ledgerFilterAgent || undefined}
            />
          )}
        </section>

        <section id="panel-inspector" className="panel" style={{ gridColumn: "span 12" }}>
          <Inspector402 onProbed={() => undefined} />
        </section>
      </main>

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        actions={paletteActions}
        receiveAddress={wallet?.receive_address}
        vaultAddress={wallet?.vault_address}
      />

      <SellerWizard
        open={sellerOpen}
        onClose={() => setSellerOpen(false)}
        netAtomic={netAtomic}
        actionsEnabled={actionsEnabled}
      />

      <SettingsDialog
        open={settingsOpen}
        apiBase={apiBase}
        onClose={() => setSettingsOpen(false)}
        onSaved={(url) => setApiBaseState(url)}
      />
    </div>
  );
}
