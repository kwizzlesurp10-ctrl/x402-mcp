import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MailRailPanel } from "./MailRailPanel";

vi.mock("../api/client", () => ({
  api: {
    mailrailHealth: vi.fn().mockResolvedValue({
      ok: true,
      enabled: true,
      provider: "mock",
      from_address: "agents@x402.test",
      admin_recipient: "ops@x402.test",
      has_api_key: false,
      has_webhook: false,
      has_smtp: false,
    }),
    mailrailStats: vi.fn().mockResolvedValue({ outbox_count: 1, inbox_count: 0 }),
    mailrailLedger: vi.fn().mockResolvedValue({
      events: [{ subject: "City catalog browse", to: "ops@x402.test", ts: new Date().toISOString() }],
      count: 1,
    }),
    mailrailInbox: vi.fn().mockResolvedValue({ inbox: [], count: 0 }),
  },
}));

describe("MailRailPanel", () => {
  it("renders AgentMail heading and outbox subject", async () => {
    render(<MailRailPanel refreshKey={1} />);
    expect(screen.getByText("AgentMail / MailRail")).toBeInTheDocument();
    expect(await screen.findByText("City catalog browse")).toBeInTheDocument();
  });
});
