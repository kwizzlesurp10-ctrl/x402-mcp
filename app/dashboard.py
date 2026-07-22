"""Operator dashboard — single-file fintech terminal served at /dashboard.

Zero build step: inline CSS/JS, polls the live API (/health, /quota/{agent},
/.well-known/mcp, /upgrade). Amber-on-ink Bloomberg-terminal lineage; block
character meters and sparklines; live event tape driven by real polling events.
Tier thresholds (rate limit, quota warning) come from the manifest, not
hardcoded — the UI adapts when the agent upgrades to pro.
"""

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<title>x402 terminal</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
<style>
:root{
  --ink:#0A0D12; --panel:#10141B; --panel-2:#0D1117; --line:#1C232E;
  --amber:#FFB000; --amber-dim:#8A6200; --green:#2FD180; --red:#FF5C57;
  --text:#C7D0DC; --dim:#667181; --faint:#3A4553;
}
*{box-sizing:border-box;margin:0;padding:0}
html{background:var(--ink)}
body{
  font-family:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
  background:var(--ink);color:var(--text);font-size:13px;line-height:1.5;
  min-height:100vh;
}
::selection{background:var(--amber);color:var(--ink)}
a{color:var(--amber);text-decoration:none}
a:hover{text-decoration:underline}
button,input{font:inherit;color:inherit}
:focus-visible{outline:2px solid var(--amber);outline-offset:1px}

/* ---- top bar ---- */
header{
  display:flex;align-items:center;gap:16px;flex-wrap:wrap;
  border-bottom:1px solid var(--line);padding:10px 20px;
  background:var(--panel-2);position:sticky;top:0;z-index:5;
}
.wordmark{font-family:"Space Grotesk",sans-serif;font-weight:700;font-size:15px;
  letter-spacing:.14em;color:#fff}
.wordmark b{color:var(--amber);font-weight:700}
.lamp{width:9px;height:9px;border-radius:50%;background:var(--faint);display:inline-block;
  vertical-align:middle;margin-right:6px}
.lamp.ok{background:var(--green);box-shadow:0 0 8px var(--green);animation:pulse 2.4s infinite}
.lamp.err{background:var(--red);box-shadow:0 0 8px var(--red)}
@keyframes pulse{50%{opacity:.55}}
@media (prefers-reduced-motion:reduce){.lamp.ok{animation:none}.tape-line{animation:none!important}body.offline main{transition:none}}
.bar-item{color:var(--dim);font-size:11px;letter-spacing:.06em;text-transform:uppercase}
.bar-item strong{color:var(--text);font-weight:500;text-transform:none;letter-spacing:0}
#clock{margin-left:auto;color:var(--amber);font-size:12px;letter-spacing:.08em}

/* offline: dim the board, keep the header readable */
body.offline main{opacity:.45;transition:opacity .4s ease}
body.offline #svc-status{color:var(--red)}

/* ---- grid ---- */
main{display:grid;gap:1px;background:var(--line);
  grid-template-columns:repeat(12,1fr);
  grid-template-areas:
    "health health health health quota quota quota quota rev rev rev rev"
    "tools tools tools tools tools tools tools tools rev rev rev rev"
    "tape tape tape tape tape tape tape tape tape tape tape tape";
  border-bottom:1px solid var(--line);
}
@media (max-width:960px){
  main{grid-template-columns:1fr;grid-template-areas:"health" "quota" "tools" "rev" "tape"}
}
section{background:var(--panel);padding:14px 18px 18px;min-width:0}
#p-health{grid-area:health}#p-quota{grid-area:quota}
#p-tools{grid-area:tools}#p-rev{grid-area:rev}#p-tape{grid-area:tape;background:var(--panel-2)}
h2{font-size:11px;font-weight:600;letter-spacing:.18em;text-transform:uppercase;
  color:var(--dim);margin-bottom:12px;display:flex;align-items:center;gap:8px}
h2::after{content:"";flex:1;height:1px;background:var(--line)}
h2 .count{color:var(--faint);letter-spacing:0;font-weight:400}

/* ---- key/value rows ---- */
.kv{display:grid;grid-template-columns:150px 1fr;gap:4px 14px;font-size:12.5px}
.kv dt{color:var(--dim)}
.kv dd{color:var(--text);overflow-wrap:anywhere}
.kv dd.on{color:var(--green)} .kv dd.off{color:var(--red)}
.spark{color:var(--amber);letter-spacing:1px;margin-right:8px}

/* ---- quota meters ---- */
.meter-label{display:flex;justify-content:space-between;color:var(--dim);
  font-size:11px;letter-spacing:.08em;text-transform:uppercase;margin:12px 0 2px}
.meter{font-size:14px;letter-spacing:1px;color:var(--amber);white-space:nowrap;overflow:hidden}
.meter .rest{color:var(--faint)}
.meter.hot{color:var(--red)}
.tier-badge{display:inline-block;border:1px solid var(--amber);color:var(--amber);
  padding:1px 8px;font-size:11px;letter-spacing:.14em;text-transform:uppercase}
.tier-badge.pro{border-color:var(--green);color:var(--green)}
.agent-row{display:flex;gap:8px;margin-bottom:6px}
.agent-row input{flex:1;background:var(--ink);border:1px solid var(--line);
  padding:6px 10px;color:var(--text);min-width:0}
.agent-row input::placeholder{color:var(--faint)}
.agent-row button{background:var(--amber);border:none;color:var(--ink);
  font-weight:600;padding:6px 14px;cursor:pointer;letter-spacing:.06em}
.agent-row button:hover{background:#ffc233}
.hint{color:var(--faint);font-size:11.5px;margin-top:10px}
.hint kbd{border:1px solid var(--line);padding:0 5px;font-size:10.5px;color:var(--dim)}

/* ---- tools table ---- */
table{width:100%;border-collapse:collapse;font-size:12.5px}
th{color:var(--dim);font-weight:500;text-align:left;font-size:10.5px;
  letter-spacing:.14em;text-transform:uppercase;padding:4px 10px 6px 0;
  border-bottom:1px solid var(--line)}
td{padding:5px 10px 5px 0;border-bottom:1px solid var(--panel-2);vertical-align:top}
tbody tr:hover td{background:rgba(255,176,0,.05)}
td.tool{color:var(--amber)}
td.env{color:var(--dim);font-size:11.5px}
td .req{display:inline-block;border:1px solid var(--line);color:var(--dim);
  padding:0 6px;font-size:10.5px;letter-spacing:.06em;margin:0 6px 2px 0}
td .req.on{border-color:var(--green);color:var(--green)}
td .req.off{border-color:var(--red);color:var(--red)}
.chip{display:inline-block;border:1px solid var(--amber-dim);color:var(--amber);
  padding:0 7px;font-size:10.5px;letter-spacing:.12em;text-transform:uppercase}
.chip.pro{border-color:var(--green);color:var(--green)}

/* ---- revenue panel ---- */
.price{font-family:"Space Grotesk",sans-serif;font-weight:700;font-size:26px;color:#fff}
.price small{font-size:12px;color:var(--dim);font-weight:500}
.rev-block{border:1px solid var(--line);padding:10px 12px;margin-bottom:10px;background:var(--panel-2)}
.rev-block.featured{border-color:var(--amber-dim)}
.rev-block .name{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--dim);margin-bottom:4px}
.rev-block ul{list-style:none;margin-top:6px;font-size:12px;color:var(--dim)}
.rev-block li b{color:var(--text);font-weight:500}

/* ---- event tape ---- */
#tape{font-size:12px;max-height:200px;overflow-y:auto}
.tape-line{display:flex;gap:12px;padding:1.5px 0;animation:fadein .25s ease}
@keyframes fadein{from{opacity:0}to{opacity:1}}
.tape-line .t{color:var(--faint)}
.tape-line .ok{color:var(--green)} .tape-line .err{color:var(--red)}
.tape-line .msg{color:var(--dim)}
#tape-paused{color:var(--amber);font-size:10px;letter-spacing:.14em;display:none}
footer{padding:10px 20px;color:var(--faint);font-size:11px;letter-spacing:.06em}
</style>
</head>
<body>
<header>
  <span class="wordmark">X402<b>/</b>TERMINAL</span>
  <span class="bar-item"><span id="lamp" class="lamp"></span><strong id="svc-status">connecting…</strong></span>
  <span class="bar-item">facilitator <strong id="bar-facilitator">—</strong></span>
  <span class="bar-item">wallet <strong id="bar-wallet">—</strong></span>
  <span class="bar-item">latency <strong id="bar-latency">—</strong></span>
  <span id="clock">—</span>
</header>

<main>
  <section id="p-health">
    <h2>Service health</h2>
    <dl class="kv">
      <dt>service</dt><dd id="h-service">—</dd>
      <dt>status</dt><dd id="h-status">—</dd>
      <dt>transport</dt><dd id="h-transport">—</dd>
      <dt>protocol</dt><dd id="h-protocol">—</dd>
      <dt>default network</dt><dd id="h-network">—</dd>
      <dt>facilitator</dt><dd id="h-facilitator">—</dd>
      <dt>wallet key</dt><dd id="h-wallet">—</dd>
      <dt>poll latency</dt><dd><span id="h-spark" class="spark" aria-hidden="true"></span><span id="h-latency">—</span></dd>
      <dt>last poll</dt><dd id="h-lastpoll">—</dd>
      <dt>manifest</dt><dd><a href="/.well-known/mcp">/.well-known/mcp</a></dd>
    </dl>
  </section>

  <section id="p-quota">
    <h2>Agent quota</h2>
    <div class="agent-row">
      <input id="agent-input" placeholder="agent id" value="dashboard-agent" spellcheck="false" aria-label="Agent ID">
      <button id="agent-go" type="button">Query</button>
    </div>
    <dl class="kv">
      <dt>agent</dt><dd id="q-agent">—</dd>
      <dt>tier</dt><dd><span id="q-tier" class="tier-badge">—</span></dd>
      <dt>calls this month</dt><dd id="q-calls">—</dd>
      <dt>tool credits</dt><dd id="q-credits">—</dd>
    </dl>
    <div class="meter-label"><span>Monthly quota</span><span id="q-quota-num">—</span></div>
    <div class="meter" id="q-quota-meter" aria-hidden="true">░░░░░░░░░░░░░░░░░░░░░░░░</div>
    <div class="meter-label"><span>Rate limit / min</span><span id="q-rate-num">—</span></div>
    <div class="meter" id="q-rate-meter" aria-hidden="true">░░░░░░░░░░░░░░░░░░░░░░░░</div>
    <p class="hint">Reads /quota/&lt;agent&gt; without consuming a call. Auto-refreshes every 5s. Press <kbd>/</kbd> to focus.</p>
  </section>

  <section id="p-tools">
    <h2>Tool matrix <span class="count" id="tools-count"></span></h2>
    <table>
      <thead><tr><th>Tool</th><th>Tier</th><th>Requires</th></tr></thead>
      <tbody id="tools-body"><tr><td class="env" colspan="3">Loading manifest…</td></tr></tbody>
    </table>
  </section>

  <section id="p-rev">
    <h2>Revenue paths</h2>
    <div class="rev-block featured">
      <div class="name">Pro tier</div>
      <div class="price" id="r-pro-price">—<small> / month · USDC via x402</small></div>
      <ul id="r-pro-list"></ul>
    </div>
    <div class="rev-block">
      <div class="name">Tool credits</div>
      <div class="price" id="r-credit-price">—<small> · per pack</small></div>
      <ul id="r-credit-list"></ul>
    </div>
    <div class="rev-block">
      <div class="name">Free tier</div>
      <ul id="r-free-list"></ul>
    </div>
  </section>

  <section id="p-store">
    <h2>Storefront <span class="count" id="store-count"></span></h2>
    <dl>
      <dt>realized revenue</dt><dd id="s-revenue">—</dd>
      <dt>upstream spend</dt><dd id="s-spend">—</dd>
      <dt>listings</dt><dd id="s-listed">—</dd>
    </dl>
    <table>
      <thead><tr><th>Listing</th><th>Price</th><th>Earned</th></tr></thead>
      <tbody id="store-body"><tr><td class="env" colspan="3">Loading listings…</td></tr></tbody>
    </table>
    <table>
      <thead><tr><th>Settled sale</th><th>Amount</th><th>Tx</th></tr></thead>
      <tbody id="sales-body"><tr><td class="env" colspan="3">Loading sales…</td></tr></tbody>
    </table>
    <table>
      <thead><tr><th>Demand (402s served)</th><th>Views</th><th>Sold</th></tr></thead>
      <tbody id="demand-body"><tr><td class="env" colspan="3">Loading demand…</td></tr></tbody>
    </table>
  </section>

  <section id="p-tape">
    <h2>Event tape <span class="count" id="tape-count"></span> <span id="tape-paused">⏸ paused</span></h2>
    <div id="tape" role="log" aria-live="polite"></div>
  </section>
</main>
<footer>x402 micropayments mcp · buyer + seller tooling · quota engine live</footer>

<script>
"use strict";
/* __INJECT_TOKEN__ */
const $ = (id) => document.getElementById(id);
const BLOCKS = 24;
const SPARK_CHARS = "▁▂▃▄▅▆▇█";
const SPARK_LEN = 20;

/* ---- event tape (pauses while hovered so lines can be read/copied) ---- */
let tapeTotal = 0, tapePaused = false;
const tapeBuffer = [];

function tapeLine(kind, msg, ts){
  const line = document.createElement("div");
  line.className = "tape-line";
  line.innerHTML = `<span class="t">${ts}Z</span><span class="${kind}">${kind === "ok" ? "OK " : "ERR"}</span><span class="msg"></span>`;
  line.querySelector(".msg").textContent = msg;
  const el = $("tape");
  el.prepend(line);
  while (el.children.length > 60) el.removeChild(el.lastChild);
}

function tape(kind, msg){
  tapeTotal += 1;
  $("tape-count").textContent = `· ${tapeTotal}`;
  const ts = new Date().toISOString().slice(11,19);
  if (tapePaused){ tapeBuffer.push([kind, msg, ts]); return; }
  tapeLine(kind, msg, ts);
}

$("tape").addEventListener("mouseenter", () => {
  tapePaused = true;
  $("tape-paused").style.display = "inline";
});
$("tape").addEventListener("mouseleave", () => {
  tapePaused = false;
  $("tape-paused").style.display = "none";
  while (tapeBuffer.length) tapeLine(...tapeBuffer.shift());
});

/* ---- block meters (half-step resolution via ▒) ---- */
function meter(el, used, total, warnAt){
  const safeTotal = Math.max(total, 1);
  const exact = Math.min(1, used / safeTotal) * BLOCKS;
  const filled = Math.floor(exact);
  const half = exact - filled >= 0.5 && filled < BLOCKS ? 1 : 0;
  el.innerHTML = "▓".repeat(filled) + "▒".repeat(half)
    + `<span class="rest">${"░".repeat(BLOCKS - filled - half)}</span>`;
  el.classList.toggle("hot", used / safeTotal >= (warnAt ?? 0.8));
}

/* ---- latency sparkline ---- */
const latencies = [];
function spark(ms){
  latencies.push(ms);
  if (latencies.length > SPARK_LEN) latencies.shift();
  const max = Math.max(...latencies, 1);
  $("h-spark").textContent = latencies
    .map(v => SPARK_CHARS[Math.min(7, Math.round((v / max) * 7))]).join("");
  $("h-latency").textContent = `${Math.round(ms)} ms`;
  $("bar-latency").textContent = `${Math.round(ms)} ms`;
}

/* env requirement tags: painted live from /health config flags */
let envStatus = {};
function paintEnvTags(){
  document.querySelectorAll("[data-env]").forEach(el => {
    const ok = envStatus[el.dataset.env];
    el.classList.toggle("on", ok === true);
    el.classList.toggle("off", ok === false);
    el.title = ok === true ? `${el.dataset.env} configured`
      : ok === false ? `${el.dataset.env} not set — tool will error` : "";
  });
}

async function getJSON(path, extra){
  const hdrs = Object.assign({accept:"application/json"}, extra || {});
  const res = await fetch(path, {headers:hdrs});
  if (!res.ok) throw new Error(`${path} → HTTP ${res.status}`);
  return res.json();
}

async function pollHealth(){
  const t0 = performance.now();
  try{
    const h = await getJSON("/health");
    spark(performance.now() - t0);
    document.body.classList.remove("offline");
    $("lamp").className = "lamp ok";
    $("svc-status").textContent = h.status;
    $("h-service").textContent = h.service;
    $("h-status").textContent = h.status;
    $("h-status").className = h.status === "ok" ? "on" : "off";
    $("h-facilitator").textContent = h.x402_facilitator;
    $("bar-facilitator").textContent = new URL(h.x402_facilitator).host;
    const w = h.wallet_configured;
    $("h-wallet").textContent = w ? "configured" : "not configured (probe-only)";
    $("h-wallet").className = w ? "on" : "off";
    $("bar-wallet").textContent = w ? "armed" : "probe-only";
    envStatus = {
      EVM_PRIVATE_KEY: !!h.wallet_configured,
      X402_PAY_TO_ADDRESS: !!h.pay_to_configured,
    };
    paintEnvTags();
    $("h-lastpoll").textContent = new Date().toISOString().slice(11,19) + "Z";
    tape("ok", "health poll — service ok");
  }catch(e){
    document.body.classList.add("offline");
    $("lamp").className = "lamp err";
    $("svc-status").textContent = "unreachable";
    tape("err", e.message);
  }
}

/* tier config from the manifest; per-tier limits drive the meters */
let tiers = null;

async function pollQuota(){
  const agent = $("agent-input").value.trim();
  if (!agent) return;
  try{
    const authH = typeof __OP_TOKEN__ === "string" ? {authorization:"Bearer "+__OP_TOKEN__} : {};
    const {meta} = await getJSON(`/quota/${encodeURIComponent(agent)}`, authH);
    $("q-agent").textContent = meta.agent_id;
    $("q-tier").textContent = meta.tier;
    $("q-tier").className = "tier-badge" + (meta.tier === "pro" ? " pro" : "");
    $("q-calls").textContent = meta.calls_this_month;
    $("q-credits").textContent = meta.tool_credits_remaining;
    const tier = tiers?.[meta.tier];
    const warnAt = tier?.quota_warning_threshold ?? 0.8;
    const total = meta.calls_this_month + meta.quota_remaining;
    $("q-quota-num").textContent = `${meta.quota_remaining} left of ${total} · ${Math.round((meta.calls_this_month / Math.max(total,1)) * 100)}% used`;
    meter($("q-quota-meter"), meta.calls_this_month, total, warnAt);
    const rateTotal = tier?.rate_limit_per_minute ?? meta.rate_limit_remaining;
    $("q-rate-num").textContent = `${meta.rate_limit_remaining} left of ${rateTotal}`;
    meter($("q-rate-meter"), rateTotal - meta.rate_limit_remaining, rateTotal, warnAt);
    tape("ok", `quota poll — ${meta.agent_id}: ${meta.quota_remaining} calls left (${meta.tier})`);
  }catch(e){ tape("err", e.message); }
}

/* ---- storefront: what is listed, and what has actually been paid ----
   Polled far slower than health/quota on purpose. These three endpoints read
   the ledgers and registry, which are Redis-backed in production on a plan
   with a monthly command budget — a tab left open all day at the 5s cadence
   would eat a meaningful share of it. Skipped entirely while the tab is
   hidden, for the same reason. */
const usd = (n) => "$" + Number(n || 0).toFixed(Math.abs(Number(n)) < 0.01 ? 6 : 2);

async function pollStore(){
  if (document.hidden) return;
  try{
    const [products, report, sales, demand] = await Promise.all([
      getJSON("/swarm/products"),
      getJSON("/swarm/revenue"),
      getJSON("/ledger/revenue"),
      getJSON("/demand"),
    ]);

    $("s-revenue").textContent = usd(report.total_revenue_usdc);
    $("s-spend").textContent = usd(report.total_spend_usdc);
    $("s-listed").textContent = `${report.listed_count} listed · ${report.sold_count} sold`;
    $("store-count").textContent = `· ${products.length}`;

    $("store-body").innerHTML = products.length ? products.map(p => `
      <tr>
        <td class="tool" title="${p.product_id}">${p.topic}</td>
        <td>${usd(p.price_usdc)}</td>
        <td>${p.revenue_usdc ? usd(p.revenue_usdc) : "—"}</td>
      </tr>`).join("") : `<tr><td class="env" colspan="3">nothing listed</td></tr>`;

    $("sales-body").innerHTML = sales.length ? sales.slice(0, 8).map(s => `
      <tr>
        <td class="tool">${s.ts.slice(0, 19).replace("T", " ")} · ${s.product_id || "—"}</td>
        <td>${usd(s.amount_usdc)}</td>
        <td class="env">${s.tx ? s.tx.slice(0, 10) + "…" : "—"}</td>
      </tr>`).join("") : `<tr><td class="env" colspan="3">no settled sales yet</td></tr>`;

    /* Views with no sales is a price/product signal; zero views is a discovery
       signal. Showing both stops those two being read as the same thing. */
    const d = demand.resources || [];
    $("demand-body").innerHTML = d.length ? d.map(r => `
      <tr>
        <td class="tool">${r.resource}</td>
        <td>${r.challenges_served}</td>
        <td>${r.sales_settled}${r.conversion === null ? "" : ` <span class="env">(${(r.conversion*100).toFixed(0)}%)</span>`}</td>
      </tr>`).join("") : `<tr><td class="env" colspan="3">no 402s served yet</td></tr>`;
  }catch(e){ tape("err", e.message); }
}

async function loadManifest(){
  try{
    const m = await getJSON("/.well-known/mcp");
    $("h-transport").textContent = m.transport.join(" · ");
    $("h-protocol").textContent = `x402 ${m.x402.protocol_version}`;
    $("h-network").textContent = m.x402.default_network;
    $("tools-count").textContent = `· ${m.tools.length}`;
    $("tools-body").innerHTML = m.tools.map(t => `
      <tr>
        <td class="tool">${t.name}</td>
        <td><span class="chip${t.tier === "pro" ? " pro" : ""}">${t.tier}</span></td>
        <td class="env">${t.requires_env ? t.requires_env.map(v => `<span class="req" data-env="${v}">env ${v}</span>`).join("") : "—"}</td>
      </tr>`).join("");
    paintEnvTags();
    tiers = m.tiers;
    const free = m.tiers.free, pro = m.tiers.pro;
    $("r-pro-price").firstChild.textContent = pro.price_x402;
    $("r-pro-list").innerHTML =
      `<li><b>${pro.monthly_quota.toLocaleString()}</b> calls / month</li>` +
      `<li><b>${pro.rate_limit_per_minute}</b> calls / minute</li>` +
      `<li>tools: <b>${pro.payment_tools.join(" → ")}</b></li>`;
    $("r-free-list").innerHTML =
      `<li><b>${free.monthly_quota}</b> calls / month</li>` +
      `<li><b>${free.rate_limit_per_minute}</b> calls / minute</li>` +
      `<li>warning at <b>${Math.round(free.quota_warning_threshold * 100)}%</b> burn</li>`;
    tape("ok", `manifest loaded — ${m.tools.length} tools registered`);
  }catch(e){ tape("err", e.message); }
}

async function loadUpgrade(){
  try{
    const u = await getJSON("/upgrade");
    const tc = u.tool_credits;
    $("r-credit-price").firstChild.textContent = tc.pack_price;
    $("r-credit-list").innerHTML =
      `<li><b>${tc.pack_size}</b> credits per pack</li>` +
      `<li>tools: <b>${tc.payment_tool} → ${tc.purchase_tool}</b></li>`;
  }catch(e){ tape("err", e.message); }
}

function tick(){
  $("clock").textContent = new Date().toISOString().replace("T"," ").slice(0,19) + " UTC";
}

$("agent-go").addEventListener("click", pollQuota);
$("agent-input").addEventListener("keydown", (e) => { if (e.key === "Enter") pollQuota(); });
document.addEventListener("keydown", (e) => {
  if (e.key === "/" && document.activeElement !== $("agent-input")){
    e.preventDefault();
    $("agent-input").focus();
    $("agent-input").select();
  }
});

tick(); setInterval(tick, 1000);
(async () => { await loadManifest(); loadUpgrade(); pollHealth(); pollQuota(); pollStore(); })();
setInterval(pollHealth, 5000);
setInterval(pollQuota, 5000);
setInterval(pollStore, 30000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) pollStore(); });
</script>
</body>
</html>
"""
