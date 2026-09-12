/**
 * @vitest-environment jsdom
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { SwarmAssessment } from "../api/client";
import { SwarmAssessmentPanel } from "./SwarmAssessmentPanel";

const assessment: SwarmAssessment = {
  generated_at: new Date().toISOString(),
  signals: { mcp_tools: 42, head: "abc123" },
  profit_routes: [
    {
      id: "mn_invest",
      name: "Invest in /mn/property-check",
      priority_score: 8.5,
      raw_score: 8.5,
      blocked_by: [],
      human_gated: false,
      status_note: "Top focus",
      next_action: "Ship value",
    },
    {
      id: "content_flywheel",
      name: "Content flywheel",
      priority_score: 5.2,
      raw_score: 5.2,
      blocked_by: [],
      human_gated: true,
      status_note: "Human only",
      next_action: "Draft outreach",
    },
  ],
  recommended_route: {
    id: "mn_invest",
    name: "Invest in /mn/property-check",
    priority_score: 8.5,
    why: "Top focus",
    next_action: "Ship value",
  },
  backlog: [
    { charter: "orchestrator", title: "Orchestrator", status: "partial", human_gated: false, detail: "exists" },
    { charter: "outreach", title: "Outreach", status: "human_gated", human_gated: true, detail: "humans send" },
    { charter: "advertising", title: "Advertising", status: "human_gated", human_gated: true, detail: "ad spend gated" },
  ],
  immediate_technical_actions: [
    { charter: "ops_monitoring", title: "Ops monitoring", detail: "Add alerts" },
  ],
  human_gates: ["Outreach", "Advertising"],
  scoring_model: { weights: {}, note: "inspectable" },
};

describe("SwarmAssessmentPanel", () => {
  afterEach(() => cleanup());
  it("shows top route and actionable backlog in standard density", () => {
    render(<SwarmAssessmentPanel assessment={assessment} density="standard" />);
    expect(screen.getByText("Top route")).toBeDefined();
    expect(screen.getAllByText("Invest in /mn/property-check").length).toBeGreaterThan(0);
    expect(screen.getByText("Orchestrator")).toBeDefined();
    expect(screen.queryByText("Outreach")).toBeNull();
    expect(screen.getByText(/Human-gated items \(2\)/)).toBeDefined();
  });

  it("collapses human-gated backlog until expanded", () => {
    render(<SwarmAssessmentPanel assessment={assessment} density="standard" />);
    expect(screen.queryByText("Outreach")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Human-gated items/i }));
    expect(screen.getByText("Outreach")).toBeDefined();
    expect(screen.getByText("Advertising")).toBeDefined();
  });

  it("shows immediate technical actions in operator density", () => {
    render(<SwarmAssessmentPanel assessment={assessment} density="operator" />);
    expect(screen.getByText("Ops monitoring")).toBeDefined();
    expect(screen.getByText("Add alerts")).toBeDefined();
  });

  it("shows compact top route only in guided density", () => {
    render(<SwarmAssessmentPanel assessment={assessment} density="guided" />);
    expect(screen.getByText("Top route")).toBeDefined();
    expect(screen.getAllByText("Invest in /mn/property-check")).toHaveLength(1);
    expect(screen.queryByText("Orchestrator")).toBeNull();
    expect(screen.queryByText(/Human-gated items/i)).toBeNull();
  });
});
