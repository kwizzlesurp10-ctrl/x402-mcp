/**
 * @vitest-environment jsdom
 */
import { render } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { FoundationTicker } from "./FoundationTicker";

const COSTUME_OPERATORS = [
  "Visa",
  "Mastercard",
  "Stripe",
  "Amex",
  "AMEX",
  "Google",
  "AWS",
  "Adyen",
];

describe("FoundationTicker", () => {
  it("does not list payment or cloud brands as if they ran this node", () => {
    const { container } = render(<FoundationTicker />);
    const text = container.textContent ?? "";

    for (const name of COSTUME_OPERATORS) {
      expect(text).not.toMatch(new RegExp(`\\b${name}\\b`, "i"));
    }
  });

  it("states Linux Foundation is protocol-layer only and does not certify this node", () => {
    const { container } = render(<FoundationTicker />);
    const text = container.textContent ?? "";

    expect(text).toMatch(/Linux Foundation/i);
    expect(text).toMatch(/protocol layer/i);
    expect(text).toMatch(/not certified/i);
  });
});
