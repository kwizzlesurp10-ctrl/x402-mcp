/** USDC amounts stored as integer atomic units (6 decimals). Format at render only. */

export function formatUsdcAtomic(atomic: number | null | undefined): string {
  if (atomic == null || Number.isNaN(atomic)) return "—";
  const sign = atomic < 0 ? "-" : "";
  const abs = Math.abs(atomic);
  const whole = Math.floor(abs / 1_000_000);
  const frac = abs % 1_000_000;
  return `${sign}$${whole}.${String(frac).padStart(6, "0").replace(/0+$/, "").padEnd(2, "0")}`;
}

export function parseUsdcToAtomic(human: string): number | null {
  const cleaned = human.replace(/[$,\s]/g, "");
  if (!/^\d+(\.\d+)?$/.test(cleaned)) return null;
  const [whole, frac = ""] = cleaned.split(".");
  const padded = (frac + "000000").slice(0, 6);
  return Number(whole) * 1_000_000 + Number(padded);
}

export function extractAtomicFrom402(obj: unknown): number | null {
  if (!obj || typeof obj !== "object") return null;
  const record = obj as Record<string, unknown>;
  const candidates = [
    record.maxAmountRequired,
    record.amount,
    record.maxAmount,
  ];
  for (const c of candidates) {
    if (typeof c === "string" && /^\d+$/.test(c)) return Number(c);
    if (typeof c === "number" && Number.isFinite(c)) return Math.round(c);
  }
  return null;
}