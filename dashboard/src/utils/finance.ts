import { type LedgerRow } from "../api/client";
import { sumLedgerAtomic } from "./ledger";

export function calculateFinances(revenue: LedgerRow[], spend: LedgerRow[]) {
  const grossRevenueAtomic = sumLedgerAtomic(revenue);
  const spendAtomic = sumLedgerAtomic(spend, true);
  // Fees and Refunds are assumed not perfectly tracked or mapped yet, setting placeholders
  // We subtract spend from gross revenue to get net margin.
  const refundsAtomic = 0;
  const feesAtomic = 0;
  const netMarginAtomic = grossRevenueAtomic - spendAtomic - refundsAtomic - feesAtomic;

  return {
    grossRevenueAtomic,
    spendAtomic,
    refundsAtomic,
    feesAtomic,
    netMarginAtomic,
    settlementCount: revenue.length,
  };
}
