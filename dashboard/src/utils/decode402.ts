export function decodePaymentRequiredBase64(input: string): unknown {
  const trimmed = input.trim();
  if (!trimmed) throw new Error("Empty input");
  const json = atob(trimmed.replace(/\s/g, ""));
  return JSON.parse(json);
}

export function truncateHash(hash: string, head = 6, tail = 4): string {
  if (hash.length <= head + tail + 3) return hash;
  return `${hash.slice(0, head + 2)}…${hash.slice(-tail)}`;
}

export function basescanUrl(network: string, tx: string): string {
  if (network.includes("84532")) {
    return `https://sepolia.basescan.org/tx/${tx}`;
  }
  return `https://basescan.org/tx/${tx}`;
}