import { CopyButton } from "./CopyButton";
import { PanelHelp } from "./PanelHelp";
import { formatUsdcAtomic } from "../utils/usdc";

export type WalletSnapshot = {
  receive_address: string | null;
  vault_address: string | null;
  balances: {
    sepolia_usdc_atomic: number | null;
    mainnet_usdc_atomic: number | null;
  };
  faucet_url: string;
  note: string;
};

const LOW_BALANCE_ATOMIC = 50_000; // ~5 testnet payments at $0.01

export function WalletPanel({ wallet, density }: { wallet: WalletSnapshot | null; density: string }) {
  if (!wallet) {
    return (
      <p style={{ color: "var(--text-muted)", fontSize: 14 }}>
        Wallet data unavailable — is the API running?
      </p>
    );
  }

  const sepolia = wallet.balances.sepolia_usdc_atomic;
  const low = sepolia != null && sepolia < LOW_BALANCE_ATOMIC;

  return (
    <div>
      <p style={{ color: "var(--text-muted)", fontSize: 13, marginTop: 0 }}>{wallet.note}</p>
      <div style={{ marginBottom: 8 }}>
        <strong>{density === "guided" ? "Receive payments at" : "Receive"}</strong>
        <div className="mono" style={{ fontSize: 12, wordBreak: "break-all" }}>
          {wallet.receive_address ?? "Not set — add X402_PAY_TO_ADDRESS"}
        </div>
        {wallet.receive_address && <CopyButton value={wallet.receive_address} label="Address" />}
      </div>
      <div style={{ marginBottom: 8 }}>
        <strong>{density === "guided" ? "Pay from (vault)" : "Vault"}</strong>
        <PanelHelp term="facilitator" title="Vault" />
        <div className="mono" style={{ fontSize: 12, wordBreak: "break-all" }}>
          {wallet.vault_address ?? "Optional — set EVM_PRIVATE_KEY for paying"}
        </div>
        {wallet.vault_address && <CopyButton value={wallet.vault_address} label="Vault" />}
      </div>
      <div className="mono" style={{ fontSize: 13 }}>
        <div>Sepolia USDC: {sepolia == null ? "—" : formatUsdcAtomic(sepolia)}</div>
        <div>
          Mainnet USDC:{" "}
          {wallet.balances.mainnet_usdc_atomic == null
            ? "—"
            : formatUsdcAtomic(wallet.balances.mainnet_usdc_atomic)}
        </div>
      </div>
      {low && (
        <p style={{ color: "var(--amber)", fontSize: 13 }}>
          Low testnet balance — fund via faucet before paid fetches.
        </p>
      )}
      <a href={wallet.faucet_url} target="_blank" rel="noreferrer">
        Base Sepolia CDP faucet
      </a>
    </div>
  );
}