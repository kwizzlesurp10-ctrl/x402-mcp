import React from 'react';

export function McpInstructions() {
  return (
    <section className="panel" style={{ gridColumn: "span 12", background: "var(--amber-muted, #fff8e1)", border: "1px solid var(--amber, #ffb300)" }}>
      <h3>Agent Instructions for MCP Production Calls</h3>
      <div style={{ fontSize: 14, lineHeight: 1.5 }}>
        <p>This server provides A2A-compliant production endpoints via the Model Context Protocol (MCP).</p>
        <ol style={{ paddingLeft: 20, marginBottom: 0 }}>
          <li><strong>A2A Card Resolution:</strong> Call <code>a2a.resolve_card</code> with a target URL or domain to inspect counterpart agent cards, AP2 commerce extensions, and USDC payment rails with SSRF protection.</li>
          <li><strong>Discovery:</strong> Call <code>city.list</code> to discover supported regions and paid URLs.</li>
          <li><strong>Dry Run:</strong> Call <code>city.sample</code> with a region (e.g., <code>city_code="chi"</code>) to verify the data shape for free.</li>
          <li><strong>Challenge:</strong> Call <code>city.check</code>. If you do not provide a signature, it returns a <code>402 Payment Required</code> challenge securely within the MCP <code>_meta["x402/payment-required"]</code> object.</li>
          <li><strong>Fulfillment:</strong> Sign the challenge with your wallet and retry the <code>city.check</code> call by injecting the signature into <code>_meta["x402/payment"]</code>. The server settles the payment and returns the paid API result.</li>
        </ol>
        <p style={{ marginTop: 8, fontStyle: "italic", fontSize: 12 }}>Note: HTTP agents can make direct calls (e.g. <code>GET /us/chi/property-check?address=...</code>) and fulfill the 402 challenge via the <code>PAYMENT-SIGNATURE</code> HTTP header.</p>
      </div>
    </section>
  );
}
