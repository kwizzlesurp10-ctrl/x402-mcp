/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { McpInstructions } from "./McpInstructions";
import { ActiveStorefront } from "./ActiveStorefront";
import { demoCities } from "../fixtures/demo";

// The 20 backend public tools from app/tools_registry.py
const BACKEND_PUBLIC_TOOLS = [
  "x402.agent_card",
  "x402.discover",
  "x402.probe",
  "x402.pay_and_fetch",
  "x402.build_seller",
  "x402.verify",
  "x402.networks",
  "commerce.pro_requirements",
  "commerce.activate_pro",
  "commerce.credits_requirements",
  "commerce.purchase_credits",
  "swarm.research",
  "swarm.settle",
  "swarm.revenue",
  "pulse.base",
  "ops.metrics",
  "city.list",
  "city.sample",
  "city.check",
  "a2a.resolve_card",
];

describe("MCP Documentation & Storefront Adversarial Parity", () => {
  afterEach(() => {
    cleanup();
  });

  describe("McpInstructions 21 Tools Inventory & Completeness", () => {
    it("renders exactly 21 tools with zero omissions and zero duplicates", () => {
      const { container } = render(<McpInstructions />);

      // Find all rendered tool code elements using class "mono"
      const toolCodeElements = container.querySelectorAll("code.mono");
      const renderedNames = Array.from(toolCodeElements)
        .map((el) => el.textContent?.trim() || "")
        .filter((name) => name.includes(".") || name.startsWith("mn_"));

      const uniqueNames = new Set(renderedNames);

      // Verify each backend tool is accounted for
      for (const backendTool of BACKEND_PUBLIC_TOOLS) {
        expect(
          uniqueNames.has(backendTool),
          `Tool '${backendTool}' must be present in McpInstructions`
        ).toBe(true);
      }

      // Verify 21st tool mn_property_diligence is present
      expect(
        uniqueNames.has("mn_property_diligence"),
        "Tool 'mn_property_diligence' must be present in McpInstructions"
      ).toBe(true);

      // Verify exactly 21 unique tools
      expect(uniqueNames.size).toBe(21);
      expect(renderedNames.length).toBe(21);
    });

    it("verifies mn_property_diligence lists $0.01 USDC on Base", () => {
      render(<McpInstructions />);

      const diligenceElements = screen.getAllByText("mn_property_diligence");
      expect(diligenceElements.length).toBeGreaterThan(0);

      const priceBadges = screen.getAllByText("$0.01 USDC");
      expect(priceBadges.length).toBeGreaterThan(0);

      const baseBadges = screen.getAllByText("Base eip155:8453");
      expect(baseBadges.length).toBeGreaterThan(0);
    });
  });

  describe("ActiveStorefront catalog pricing", () => {
    it("renders MN Rental License Check at $0.01 from demo catalog", () => {
      render(
        <ActiveStorefront products={[]} demo cities={demoCities} />,
      );

      expect(screen.getByText("MN Rental License Check")).toBeDefined();
      expect(screen.getByText("$0.01")).toBeDefined();
    });
  });

  describe("demo.ts catalog parity", () => {
    it("configures Minneapolis at $0.01 on eip155:8453", () => {
      const mnCity = demoCities.find((c) => c.code === "mn");
      expect(mnCity).toBeDefined();
      expect(mnCity?.service_name).toBe("MN Rental License Check");
      expect(mnCity?.price).toBe("$0.01");
      expect(mnCity?.network).toBe("eip155:8453");
      expect(mnCity?.canonical_alias).toBe("/mn/property-check");
    });
  });
});
