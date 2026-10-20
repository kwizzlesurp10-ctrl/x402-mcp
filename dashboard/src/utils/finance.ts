import { type LedgerRow } from "../api/client";
import { sumLedgerAtomic, verifiedRevenueRows } from "./ledger";

export function calculateFinances(revenue: LedgerRow[], spend: LedgerRow[]) {
  // Only verified external Base-mainnet settlements are revenue; test ids,
  // testnet, self-payments and unknown payers are reported separately.
  const verified = verifiedRevenueRows(revenue);
  const grossRevenueAtomic = sumLedgerAtomic(verified);
  const rawRevenueAtomic = sumLedgerAtomic(revenue);
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
    settlementCount: verified.length,
    rawRevenueAtomic,
    rawSettlementCount: revenue.length,
    excludedRevenueAtomic: rawRevenueAtomic - grossRevenueAtomic,
  };
}
