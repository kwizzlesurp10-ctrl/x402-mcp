/**
 * @vitest-environment jsdom
 */
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Header } from "./Header";

describe("Header", () => {
  it("does not costume live mode as a Private Operator Terminal", () => {
    render(
      <Header
        network="eip155:8453"
        tier="free"
        status="connected"
        demo={false}
        onToggleDemo={vi.fn()}
        density="standard"
        onDensityChange={vi.fn()}
        onOpenWizard={vi.fn()}
      />,
    );

    expect(screen.queryByText(/Private Operator Terminal/i)).toBeNull();
    expect(screen.queryByText(/Public Ecosystem Showcase/i)).toBeNull();
    expect(screen.getByLabelText(/demo mode/i)).toBeDefined();
  });
});
