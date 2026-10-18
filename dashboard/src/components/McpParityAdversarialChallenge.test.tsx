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

    it("verifies mn_property_diligence has $0.85 USDC price and Base network", () => {
      render(<McpInstructions />);

      const diligenceElements = screen.getAllByText("mn_property_diligence");
      expect(diligenceElements.length).toBeGreaterThan(0);

      const priceBadges = screen.getAllByText("$0.85 USDC");
      expect(priceBadges.length).toBeGreaterThan(0);

      const baseBadges = screen.getAllByText("Base eip155:8453");
      expect(baseBadges.length).toBeGreaterThan(0);
    });
  });

  describe("ActiveStorefront MARC-HD Diligence & Pricing Verification", () => {
    it("renders MARC-HD Compliance Verification at $0.85 on Base eip155:8453", () => {
      render(<ActiveStorefront products={[]} revenueRows={[]} activityEvents={[]} />);

      expect(screen.getByText("MARC-HD Compliance Verification")).toBeDefined();
      expect(screen.getByText("$0.85")).toBeDefined();

      const networkBadges = screen.getAllByText(/Network: Base eip155:8453/i);
      expect(networkBadges.length).toBeGreaterThan(0);

      // Verify the 4 compliance indicators
      expect(screen.getByText("✓ Habitability Score (0-100)")).toBeDefined();
      expect(screen.getByText("✓ License Tier Diligence (T1-T3)")).toBeDefined();
      expect(screen.getByText("✓ 4-Class Verdict Engine")).toBeDefined();
      expect(screen.getByText("✓ ArcGIS REST Parity")).toBeDefined();
    });
  });

  describe("demo.ts MARC-HD Parity Verification", () => {
    it("configures Minneapolis as MARC-HD at $0.85 on eip155:8453", () => {
      const mnCity = demoCities.find((c) => c.code === "mn");
      expect(mnCity).toBeDefined();
      expect(mnCity?.service_name).toBe("MARC-HD Compliance Verification");
      expect(mnCity?.price).toBe("$0.85");
      expect(mnCity?.network).toBe("eip155:8453");
      expect(mnCity?.canonical_alias).toBe("/mn/property-check");
    });
  });
});
