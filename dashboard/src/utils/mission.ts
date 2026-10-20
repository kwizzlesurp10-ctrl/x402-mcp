import type { DoctorCheck, LedgerRow, StatsResponse } from "../api/client";
import type { StreamEvent } from "../hooks/useSSE";
import { sumLedgerAtomic } from "./ledger";

export type MissionStep = {
  id: string;
  label: string;
  done: boolean;
  panel?: string;
};

export function deriveMissionSteps(input: {
  stats: StatsResponse | null;
  spend: LedgerRow[];
  revenue: LedgerRow[];
  activity: StreamEvent[];
  apiError: string | null;
  liveOk: boolean;
  probeDone: boolean;
  walletSepoliaAtomic: number | null;
  doctor: DoctorCheck[];
}): MissionStep[] {
  const tools = new Set(input.activity.map((e) => e.tool).filter(Boolean));
  const netAtomic =
    sumLedgerAtomic(input.revenue) - sumLedgerAtomic(input.spend, true);
  const discovered = tools.has("discover_services");
  const probed = tools.has("get_payment_requirements") || input.probeDone;
  const paid = tools.has("pay_and_fetch") || input.spend.length > 0;
  const hasRevenue = input.revenue.length > 0;
  const sellerReady = input.doctor.find((c) => c.id === "pay_to")?.status === "pass";

  return [
    { id: "server", label: "Server up", done: !input.apiError && input.stats != null, panel: "wizard" },
    { id: "dashboard", label: "Dashboard connected", done: input.liveOk, panel: "activity" },
    { id: "discovery", label: "First discovery", done: discovered, panel: "activity" },
    { id: "probe", label: "First probe", done: probed, panel: "inspector" },
    {
      id: "funded",
      label: "Testnet funded",
      done: (input.walletSepoliaAtomic ?? 0) > 0 || input.doctor.find((c) => c.id === "buyer_key")?.status === "pass",
      panel: "wizard",
    },
    { id: "paid_fetch", label: "First paid fetch", done: paid, panel: "spend" },
    { id: "seller", label: "First seller config", done: sellerReady, panel: "seller" },
    { id: "revenue", label: "First verified revenue", done: hasRevenue, panel: "revenue" },
    { id: "net", label: "Net ≥ 0", done: netAtomic >= 0 && hasRevenue, panel: "hero" },
  ];
}