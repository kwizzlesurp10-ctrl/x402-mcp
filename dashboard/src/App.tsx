import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type DoctorCheck, type LedgerRow, type OsSnapshot, type PulseResponse, type StatsResponse, type SwarmProduct, type SwarmRevenue, type WalletResponse } from "./api/client";
import { ActiveStorefront } from "./components/ActiveStorefront";
import { CommandPalette } from "./components/CommandPalette";
import { OsHealthPanel } from "./components/OsHealthPanel";
import { PulsePanel } from "./components/PulsePanel";
import { SwarmActivity } from "./components/SwarmActivity";
import { Inspector402 } from "./components/Inspector402";
import { MissionProgress } from "./components/MissionProgress";
import { OnboardingTour } from "./components/OnboardingTour";
import { PanelHelp } from "./components/PanelHelp";
import { RateSparkline } from "./components/RateSparkline";
import { SellerWizard } from "./components/SellerWizard";
import { VirtualizedLedger } from "./components/VirtualizedLedger";
import { WalletPanel } from "./components/WalletPanel";
import { OperatorHeader } from "./components/OperatorHeader";
import { demoActivity, demoDoctor, demoOs, demoRevenue, demoSpend, demoStats } from "./fixtures/demo";
import { explain } from "./glossary";
import { useSSE, type StreamEvent } from "./hooks/useSSE";
import { downloadText, ledgerToCsv } from "./utils/ledger";
import { calculateFinances } from "./utils/finance";
import { deriveMissionSteps } from "./utils/mission";
import { formatUsdcAtomic } from "./utils/usdc";
import { relativeTime } from "./utils/time";

import { ParallaxProtocolHero } from "./components/ParallaxProtocolHero";
import { FoundationTicker } from "./components/FoundationTicker";
import { ChainDistributionBar } from "./components/ChainDistributionBar";
import { FacilitatorLeaderboard } from "./components/FacilitatorLeaderboard";
import { BazaarResourceExplorer } from "./components/BazaarResourceExplorer";
import { Bubble } from "./components/canvasui/Bubble";

type Density = "guided" | "standard" | "operator";

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
  const [demo, setDemo] = useState(import.meta.env.VITE_DEMO_DEFAULT === "true");
  const [density, setDensity] = useState<Density>(() => (localStorage.getItem("density") as Density) || "standard");
  const [wizardOpen, setWizardOpen] = useState(true);
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [doctor, setDoctor] = useState<DoctorCheck[]>([]);
  const [spend, setSpend] = useState<LedgerRow[]>([]);
  const [revenue, setRevenue] = useState<LedgerRow[]>([]);
  const [wallet, setWallet] = useState<WalletResponse | null>(null);
  const [pulse, setPulse] = useState<PulseResponse | null>(null);
  const [os, setOs] = useState<OsSnapshot | null>(null);
  const [products, setProducts] = useState<SwarmProduct[]>([]);
  const [swarmRevenue, setSwarmRevenue] = useState<SwarmRevenue | null>(null);
  const [activity, setActivity] = useState<StreamEvent[]>([]);
  const [probeDone, setProbeDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [sellerOpen, setSellerOpen] = useState(false);
  const [prevCalls, setPrevCalls] = useState<number | null>(null);
  const [resetToast, setResetToast] = useState(false);
  const [rateHistory, setRateHistory] = useState<number[]>([]);
  const [missionOpen, setMissionOpen] = useState(true);
  const [ledgerFilterNetwork, setLedgerFilterNetwork] = useState("");
  const [ledgerFilterAgent, setLedgerFilterAgent] = useState("");
  const [tourOpen, setTourOpen] = useState(() => !localStorage.getItem("tourSeen"));



  const refresh = useCallback(async () => {
    if (demo) {
      setStats(demoStats);
      setDoctor(demoDoctor);
      setSpend(demoSpend);
      setRevenue(demoRevenue);
      setActivity(demoActivity);
      setProducts([
        {
          product_id: "demo-1",
          topic: "zk-rollup landscape",
          cost_basis_usdc: 0.03,
          price_usdc: 0.09,
          margin_usdc: 0.06,
          markup: 3,
          network: "eip155:84532",
          status: "sold",
          sources: ["https://exa.example/search", "https://eth.example/onchain"],
          revenue_usdc: 0.09,
        },
        {
          product_id: "demo-2",
          topic: "stablecoin flows",
          cost_basis_usdc: 0.02,
          price_usdc: 0.06,
          margin_usdc: 0.04,
          markup: 3,
          network: "eip155:84532",
          status: "listed",
          sources: ["https://exa.example/search"],
          revenue_usdc: 0,
        },
      ]);
      setSwarmRevenue({
        total_spend_usdc: 0.05,
        total_revenue_usdc: 0.09,
        realized_margin_usdc: 0.04,
        ltv_cac: 1.8,
        target_ltv_cac: 3,
        listed_count: 2,
        sold_count: 1,
        products: [],
        source_scores: [],
        recommendations: ["portfolio LTV:CAC 1.8 below target 3.0: raise markup or cut upstream spend"],
      });
      setWallet({
        receive_address: "0xDemoReceive000000000000000000000001",
        vault_address: "0xDemoVault0000000000000000000000001",
        balances: { sepolia_usdc_atomic: 50_000_000, mainnet_usdc_atomic: 0 },
        faucet_url: "https://docs.cdp.coinbase.com/faucets/introduction/quickstart",
        network: "eip155:84532",
        note: "Demo wallet — no real keys.",
      });
      setRateHistory([10, 9, 8, 7, 8, 9, 10]);
      setOs(demoOs);
      setPulse({
        generated_at: new Date().toISOString(),
        chain: { name: "Base", network: "eip155:8453" },
        latest_block: 24_500_000,
        eth_price_usd: 3120.44,
        network: { block_time_s: 2.0, tps_est: 42.7, gas_limit: 240_000_000, gas_target: 120_000_000 },
        fees: {
          base_fee_gwei: 0.024,
          priority_fee_gwei: 0.001,
          next_base_fee_gwei: 0.023,
          next_base_fee_change_pct: -4.2,
        },
        utilization: {
          now_pct: 38,
          avg_pct: 44,
          trend: "falling",
          headroom_x: 2.6,
          series_pct: [52, 49, 47, 45, 43, 40, 38],
        },
        settlement_cost: {
          eth_transfer: { usd: 0.0015 },
          erc20_usdc_transfer: { usd: 0.0038 },
          x402_settle: { usd: 0.0041 },
        },
        assessment: {
          congestion: "low",
          verdict: "SETTLE_NOW",
          rationale: "Base fees are low and utilization is falling — settlement is cheap right now.",
          window: "Next ~10 min favorable",
        },
      });
      setError(null);
      return;
    }
    try {
      const [s, d, sp, rev, w, pr, srev] = await Promise.all([
        api.stats(),
        api.doctor(),
        api.ledgerSpend(),
        api.ledgerRevenue(),
        api.wallet(),
        api.swarmProducts(),
        api.swarmRevenue(),
      ]);
      setStats(s);
      setDoctor(d.checks);
      setSpend(sp);
      setRevenue(rev);
      setWallet(w);
      setProducts(pr);
      setSwarmRevenue(srev);
      api.pulse().then(setPulse).catch(() => {});
      api.os().then(setOs).catch(() => {});
      const rateRemaining = s.agents.length
        ? Math.min(...s.agents.map((a) => a.rate_limit_remaining))
        : 10;
      setRateHistory((prev) => [...prev, rateRemaining].slice(-24));
      setError(null);
      const totalCalls = s.agents.reduce((n, a) => n + a.calls_this_month, 0);
      if (prevCalls != null && totalCalls < prevCalls) {
        setResetToast(true);
        setTimeout(() => setResetToast(false), 5000);
      }
      setPrevCalls(totalCalls);
      if (!d.summary.ready) setWizardOpen(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to reach API — run `make up`");
    }
  }, [demo, prevCalls]);

  const onEvent = useCallback((e: StreamEvent) => {
    setActivity((prev) => [e, ...prev].slice(0, 200));
    refresh();
  }, [refresh]);

  const { status: serverStatus, reconnect } = useSSE(!demo, onEvent);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    localStorage.setItem("density", density);
  }, [density]);

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

  const finances = useMemo(
    () => calculateFinances(revenue, spend),
    [revenue, spend],
  );
  const netAtomic = finances.netMarginAtomic;

  const walletSepoliaAtomic = wallet?.balances.sepolia_usdc_atomic ?? null;

  const missionSteps = useMemo(
    () =>
      deriveMissionSteps({
        stats,
        spend,
        revenue,
        activity,
        apiError: error,
        liveOk: serverStatus === "connected" || serverStatus === "degraded",
        probeDone,
        walletSepoliaAtomic,
        doctor,
      }),
    [stats, spend, revenue, activity, error, serverStatus, probeDone, walletSepoliaAtomic, doctor],
  );

  const totalCalls = stats?.agents.reduce((n, a) => n + a.calls_this_month, 0) ?? 0;
  const quotaLimit = stats?.config.free_tier_monthly_quota ?? 500;
  const showPersistence = stats?.config.redis_mode === "memory";
  const actionsEnabled = import.meta.env.VITE_DASHBOARD_ACTIONS === "true";

  const scrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const paletteActions = useMemo(
    () => [
      { id: "hero", label: "Go to net position", run: () => scrollTo("panel-hero") },
      { id: "wallet", label: "Go to wallet", run: () => scrollTo("panel-wallet") },
      { id: "swarm", label: "Go to swarm activity", run: () => scrollTo("panel-swarm") },
      { id: "os", label: "Go to host OS health", run: () => scrollTo("panel-os") },
      { id: "inspector", label: "Go to 402 Inspector", run: () => scrollTo("panel-inspector") },
      { id: "spend", label: "Go to spend ledger", run: () => scrollTo("panel-spend") },
      { id: "revenue", label: "Go to revenue ledger", run: () => scrollTo("panel-revenue") },
      { id: "demo", label: "Toggle demo mode", run: () => setDemo((d) => !d) },
      { id: "density-guided", label: "Density: Guided", run: () => setDensity("guided") },
      { id: "density-operator", label: "Density: Operator", run: () => setDensity("operator") },
      { id: "wizard", label: "Open setup wizard", run: () => setWizardOpen(true) },
      { id: "seller", label: "Open seller wizard", run: () => setSellerOpen(true) },
      { id: "filter-sepolia", label: "Filter ledgers: Sepolia", run: () => setLedgerFilterNetwork("eip155:84532") },
      { id: "filter-clear", label: "Clear ledger filters", run: () => { setLedgerFilterNetwork(""); setLedgerFilterAgent(""); } },
    ],
    [],
  );

  const finishTour = () => {
    localStorage.setItem("tourSeen", "1");
    setTourOpen(false);
    setWizardOpen(true);
  };

  const alerts = [];
  if (serverStatus === "disconnected") alerts.push("API disconnected");
  if (os?.disk && os.disk.percent >= 70) alerts.push(`Disk at ${os.disk.percent.toFixed(0)}%`);



  return (
    <Bubble
      size={30}
      trail={24}
      follow={0.5}
      blend={14}
      speed={2}
      refraction={80}
      dispersion={1}
      frost={0}
      shine={0.25}
      rim={0.5}
      iridescence={1}
      intensity={0.9}

      colorA={[0.2902, 0.4549, 0.7216]}
      colorB={[0.4118, 0.4118, 0.4157]}
    >
      <div>
        {demo && (
        <div style={{ background: "var(--amber)", color: "#000", textAlign: "center", padding: 4, fontWeight: 700, textTransform: "uppercase" }}>
          DEMO — Sample data only
        </div>
      )}
      {showPersistence && (
        <div
          style={{
            background: revenue.length ? "var(--red)" : "var(--amber)",
            color: "#000",
            padding: 8,
            textAlign: "center",
          }}
        >
          In-memory store — quota resets on restart. Set REDIS_URL before selling to real buyers.
        </div>
      )}
      {resetToast && (
        <div className="panel" style={{ margin: 8 }}>
          Server restarted — in-memory counters reset.
        </div>
      )}
      {serverStatus === "disconnected" && (
        <div className="panel" style={{ margin: 8, borderColor: "var(--red)" }}>
          <strong style={{ color: "var(--red)" }}>Disconnected</strong>
          <p>Dashboard can&apos;t reach the server at {import.meta.env.VITE_PUBLIC_API_BASE_URL || "/api"}.</p>
          {error && <p style={{ color: "var(--text-muted)", fontSize: 12 }}>{error}</p>}
          <button type="button" onClick={reconnect} style={{ marginTop: 8 }}>Retry Connection</button>
        </div>
      )}

      <OperatorHeader
        status={serverStatus}
        lastSync={pulse?.generated_at || null}
        netMarginAtomic={finances.netMarginAtomic}
        grossRevenueAtomic={finances.grossRevenueAtomic}
        spendAtomic={finances.spendAtomic}
        alerts={alerts}
        onRetry={reconnect}
      />
      <div
        className="panel mc-header"
        style={{
          margin: "0 16px 16px 16px",
          display: "flex",
          gap: 16,
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          padding: "10px 24px",
          background: "linear-gradient(135deg, rgba(15, 23, 42, 0.8) 0%, rgba(6, 9, 14, 0.9) 100%)",
        }}
      >
        <div className="mc-header-actions" style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <div
            className="mc-mode-badge"
            role="button"
            tabIndex={0}
            onClick={() => setDemo((d) => !d)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setDemo((d) => !d);
              }
            }}
            title={
              demo
                ? "Currently in Public Ecosystem Showcase Mode. Click to switch to Private Operator Terminal."
                : "Currently in Private Operator Terminal Mode. Click to switch to Public Ecosystem Showcase."
            }
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "4px 12px",
              borderRadius: 20,
              background: demo ? "rgba(245, 158, 11, 0.15)" : "rgba(0, 240, 255, 0.15)",
              border: demo ? "1px solid rgba(245, 158, 11, 0.4)" : "1px solid rgba(0, 240, 255, 0.4)",
              cursor: "pointer",
              fontSize: 11,
              fontFamily: "var(--font-mono, monospace)",
              fontWeight: 600,
              color: demo ? "#F59E0B" : "#00F0FF",
            }}
          >
            <span
              style={{
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: demo ? "#F59E0B" : "#00F0FF",
                boxShadow: demo ? "0 0 8px #F59E0B" : "0 0 8px #00F0FF",
              }}
            />
            <span className="mc-mode-full">{demo ? "🌐 Public Ecosystem Showcase" : "🛡️ Private Operator Terminal"}</span>
            <span className="mc-mode-short">{demo ? "🌐 Showcase" : "🛡️ Operator"}</span>
          </div>

          <label style={{ fontSize: 13, color: "var(--text-muted)", cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }}>
            <input
              type="checkbox"
              aria-label="Demo"
              checked={demo}
              onChange={(e) => setDemo(e.target.checked)}
            />{" "}
            Demo
          </label>
          <select
            value={density}
            onChange={(e) => setDensity(e.target.value as Density)}
            aria-label="Density mode"
            style={{
              background: "rgba(0,0,0,0.4)",
              color: "var(--text)",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: 6,
              padding: "5px 10px",
              fontSize: 12,
            }}
          >
            <option value="guided">Guided</option>
            <option value="standard">Standard</option>
            <option value="operator">Operator</option>
          </select>
          <button type="button" onClick={() => setWizardOpen(true)} style={{ background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.12)", color: "#fff", padding: "6px 14px", borderRadius: 6, fontSize: 12, cursor: "pointer" }}>
            Setup
          </button>
          <button type="button" onClick={() => setSellerOpen(true)} style={{ background: "linear-gradient(135deg, var(--neon-cyan), var(--base))", border: "none", color: "#000", fontWeight: 700, padding: "6px 16px", borderRadius: 6, fontSize: 12, cursor: "pointer" }}>
            Sell
          </button>
          <button type="button" onClick={() => setPaletteOpen(true)} className="mono hide-mobile" style={{ background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.12)", color: "var(--text-muted)", padding: "6px 12px", borderRadius: 6, fontSize: 12, cursor: "pointer" }}>
            ⌘K
          </button>
          <button type="button" onClick={() => setMissionOpen((v) => !v)} style={{ background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.12)", color: "#fff", padding: "6px 14px", borderRadius: 6, fontSize: 12, cursor: "pointer" }}>
            Mission
          </button>
          <button type="button" onClick={() => setTourOpen(true)} className="hide-mobile" style={{ background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.12)", color: "#fff", padding: "6px 14px", borderRadius: 6, fontSize: 12, cursor: "pointer" }}>
            Tour
          </button>
        </div>
      </div>

      <MissionProgress steps={missionSteps} open={missionOpen} onToggle={() => setMissionOpen((v) => !v)} />

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
          aria-label="Setup wizard"
        >
          <div className="panel mc-modal-panel" style={{ width: 520, maxHeight: "80vh", overflow: "auto" }}>
            <h2>First-run setup</h2>
            <p style={{ color: "var(--text-muted)" }}>Complete these checks before going live.</p>
            <ul style={{ listStyle: "none", padding: 0 }}>
              {doctor.map((c) => (
                <li key={c.id} style={{ marginBottom: 12 }}>
                  <span
                    style={{
                      color:
                        c.status === "pass"
                          ? "var(--green)"
                          : c.status === "fail"
                            ? "var(--red)"
                            : "var(--amber)",
                    }}
                  >
                    {c.status.toUpperCase()}
                  </span>{" "}
                  <strong>{c.name}</strong>: {c.message}
                  {c.fix && <pre className="mono" style={{ fontSize: 12 }}>{c.fix}</pre>}
                </li>
              ))}
            </ul>
            <button type="button" onClick={() => setWizardOpen(false)}>
              Continue to dashboard
            </button>
          </div>
        </div>
      )}

      <div className="mc-ticker-wrap hide-mobile" style={{ padding: "0 16px" }}>
        <FoundationTicker />
      </div>

      <main className="grid-12">
        <div className="hide-mobile" style={{ gridColumn: "span 12" }}>
          <ParallaxProtocolHero />
        </div>

        <div className="hide-mobile" style={{ display: "contents" }}>
          <ChainDistributionBar density={density} />
          <BazaarResourceExplorer density={density} />
          <FacilitatorLeaderboard density={density} />
        </div>

        <section id="panel-hero" className="panel" style={{ gridColumn: "span 3" }}>
          <h3>
            {density === "guided" ? "Money left after costs" : "Net position"}
            <PanelHelp term="net" title="Net position" />
          </h3>
          <div
            className="mono"
            style={{ fontSize: 32, color: netAtomic >= 0 ? "var(--green)" : "var(--usdc)" }}
          >
            {formatUsdcAtomic(netAtomic)}
          </div>
          {netAtomic < 0 && (
            <div style={{ marginTop: 8 }}>
              <div style={{ height: 6, background: "var(--border)", borderRadius: 4 }}>
                <div
                  style={{
                    width: `${Math.min(100, Math.abs(netAtomic) / 100_000)}%`,
                    height: "100%",
                    background: "var(--amber)",
                  }}
                />
              </div>
              <small>Break-even: sell ~{Math.ceil(Math.abs(netAtomic) / 10_000)} calls at $0.01</small>
            </div>
          )}
          {netAtomic >= 0 && revenue.length > 0 && (
            <small style={{ color: "var(--green)" }}>Self-sustaining</small>
          )}
        </section>

        {/* Compact quota stays on mobile as a second hero stat */}
        <section className="panel" style={{ gridColumn: "span 3" }}>
          <h3>
            Quota <PanelHelp term="quota" title="Quota" />
          </h3>
          {totalCalls === 0 ? (
            <EmptyPanel
              title="No calls yet"
              action="Run your first free discovery."
              command="discover_services via MCP"
            />
          ) : (
            <>
              <div className="mono">
                {totalCalls} / {quotaLimit}
              </div>
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

        <section id="panel-wallet" className="panel hide-mobile" style={{ gridColumn: "span 3" }}>
          <h3>
            Wallet <PanelHelp term="atomic units" title="Wallet" />
          </h3>
          <WalletPanel wallet={wallet} density={density} />
        </section>

        <section className="panel hide-mobile" style={{ gridColumn: "span 3" }}>
          <h3>
            Rate <PanelHelp term="quota" title="Rate limit" />
          </h3>
          <RateSparkline series={rateHistory} />
          <div className="mono">{stats?.agents[0]?.rate_limit_remaining ?? "—"} / min left</div>
        </section>

        <div className="hide-mobile" style={{ display: "contents" }}>
          <OsHealthPanel os={os} />
          <ActiveStorefront products={products} revenueRows={revenue} activityEvents={activity} />
        </div>

        <section id="panel-activity" className="panel" style={{ gridColumn: "span 8" }}>
          <h3>Activity</h3>
          {activity.length === 0 ? (
            <EmptyPanel title="Quiet" action="Tool calls appear here via SSE." />
          ) : (
            <ul style={{ listStyle: "none", padding: 0, maxHeight: 240, overflow: "auto" }}>
              {activity.map((e, i) => (
                <li key={i} className="mono" style={{ fontSize: 12, marginBottom: 4 }}>
                  <span title={e.ts}>{relativeTime(e.ts)}</span> [{e.agent_id}] {e.tool} →{" "}
                  {String((e.meta as { quota_remaining?: number })?.quota_remaining ?? "—")}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel hide-mobile" style={{ gridColumn: "span 4" }}>
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

        {density === "operator" && (
          <>
            <div className="hide-mobile" style={{ display: "contents" }}>
              <PulsePanel pulse={pulse} />
              <SwarmActivity events={activity} products={products} revenue={swarmRevenue ?? undefined} />
            </div>
            <section id="panel-spend" className="panel hide-mobile" style={{ gridColumn: "span 6" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <h3 style={{ margin: 0 }}>Spend ledger</h3>
                {spend.length > 0 && (
                  <button
                    type="button"
                    onClick={() => downloadText("spend.csv", ledgerToCsv(spend), "text/csv")}
                  >
                    CSV
                  </button>
                )}
              </div>
              {spend.length === 0 ? (
                <EmptyPanel
                  title="Nothing spent"
                  action="Good. Try a $0 testnet fetch first."
                  command="pay_and_fetch on Sepolia"
                />
              ) : (
                <VirtualizedLedger
                  rows={spend}
                  kind="spend"
                  filterNetwork={ledgerFilterNetwork || undefined}
                  filterAgent={ledgerFilterAgent || undefined}
                />
              )}
            </section>
            <section id="panel-revenue" className="panel hide-mobile" style={{ gridColumn: "span 6" }}>
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
            <section id="panel-inspector" className="panel hide-mobile" style={{ gridColumn: "span 12" }}>
              <Inspector402 onProbed={(r) => setProbeDone(r != null && !("error" in (r ?? {})))} />
            </section>
          </>
        )}
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

      {tourOpen && <OnboardingTour onDone={finishTour} />}

      {density !== "operator" && (
        <footer style={{ padding: 16, color: "var(--text-muted)", fontSize: 12 }}>
          Glossary: {explain("402")}
        </footer>
      )}
    </div>
    </Bubble>
  );
}