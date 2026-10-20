import { parseUsdcToAtomic } from "./usdc";

/** Verified calls needed to close a negative net at the given per-call price. */
export function callsToBreakEven(netAtomic: number, priceHuman: string): number | null {
  const priceAtomic = parseUsdcToAtomic(priceHuman);
  if (priceAtomic == null || priceAtomic <= 0 || netAtomic >= 0) return null;
  return Math.ceil(Math.abs(netAtomic) / priceAtomic);
}