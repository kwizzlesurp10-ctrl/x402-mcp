/** Formatting utilities — all USDC math in integer atomic units, format at render. */

/** Format atomic units (1e6) to human-readable USDC string */
export function formatUsdc(atomic: number): string {
  const human = atomic / 1_000_000;
  if (human === 0) return "$0.00";
  if (Math.abs(human) < 0.01) return `$${human.toFixed(6)}`;
  return `$${human.toFixed(2)}`;
}

/** Format a raw USDC human number (already divided) */
export function formatUsdcHuman(human: number): string {
  if (human === 0) return "$0.00";
  if (Math.abs(human) < 0.01) return `$${human.toFixed(6)}`;
  return `$${human.toFixed(2)}`;
}

/** Parse price string like "$0.01" to atomic units */
export function priceToAtomic(price: string): number {
  const num = parseFloat(price.replace(/[^0-9.]/g, ""));
  return Math.round(num * 1_000_000);
}

/** Truncate hash/address: 0x12ab…9f */
export function truncateHash(hash: string, chars = 4): string {
  if (hash.length <= chars * 2 + 4) return hash;
  return `${hash.slice(0, chars + 2)}…${hash.slice(-chars)}`;
}

/** Relative timestamp: "2m ago" */
export function relativeTime(iso: string): string {
  const now = Date.now();
  const then = new Date(iso).getTime();
  const diff = Math.max(0, now - then);

  if (diff < 60_000) return `${Math.floor(diff / 1_000)}s ago`;
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return `${Math.floor(diff / 86_400_000)}d ago`;
}

/** BaseScan URL for tx hash */
export function baseScanUrl(txHash: string, network?: string): string {
  const isTestnet =
    network?.includes("84532") || network?.toLowerCase().includes("sepolia");
  const base = isTestnet
    ? "https://sepolia.basescan.org"
    : "https://basescan.org";
  return `${base}/tx/${txHash}`;
}

/** Network label */
export function networkLabel(network: string): string {
  if (network.includes("8453") && !network.includes("84532"))
    return "Base Mainnet";
  if (network.includes("84532")) return "Base Sepolia";
  if (network.includes("137")) return "Polygon";
  if (network.includes("solana")) return "Solana";
  return network;
}

/** Network chip color */
export function networkColor(network: string): string {
  if (network.includes("8453") && !network.includes("84532")) return "#0052FF";
  return "#F5A623";
}
