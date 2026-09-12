import { describe, expect, it } from "vitest";
import type { SwarmBacklogItem } from "../api/client";
import { backlogStatusColor, routeScoreColor, splitBacklog, topProfitRoutes } from "./swarmAssessment";

const sampleBacklog: SwarmBacklogItem[] = [
  { charter: "orchestrator", title: "Orchestrator", status: "partial", human_gated: false, detail: "exists" },
  { charter: "outreach", title: "Outreach", status: "human_gated", human_gated: true, detail: "gated" },
  { charter: "advertising", title: "Advertising", status: "human_gated", human_gated: true, detail: "gated" },
  { charter: "security_hardener", title: "Security", status: "done", human_gated: false, detail: "shipped" },
];

describe("splitBacklog", () => {
  it("separates human-gated items from actionable backlog", () => {
    const { actionable, humanGated } = splitBacklog(sampleBacklog);
    expect(actionable).toHaveLength(2);
    expect(humanGated).toHaveLength(2);
    expect(humanGated.every((b) => b.human_gated)).toBe(true);
    expect(actionable.every((b) => !b.human_gated)).toBe(true);
  });
});

describe("topProfitRoutes", () => {
  it("returns the first N routes from assessment", () => {
    const assessment = {
      generated_at: "2026-01-01T00:00:00Z",
      signals: {},
      profit_routes: [
        { id: "a", name: "A", priority_score: 9, raw_score: 9, blocked_by: [], human_gated: false, status_note: "", next_action: "" },
        { id: "b", name: "B", priority_score: 8, raw_score: 8, blocked_by: [], human_gated: false, status_note: "", next_action: "" },
        { id: "c", name: "C", priority_score: 7, raw_score: 7, blocked_by: [], human_gated: false, status_note: "", next_action: "" },
        { id: "d", name: "D", priority_score: 6, raw_score: 6, blocked_by: [], human_gated: false, status_note: "", next_action: "" },
      ],
      recommended_route: { id: "a", name: "A", priority_score: 9, why: "", next_action: "" },
      backlog: [],
      immediate_technical_actions: [],
      human_gates: [],
      scoring_model: { weights: {}, note: "" },
    };
    expect(topProfitRoutes(assessment, 2).map((r) => r.id)).toEqual(["a", "b"]);
  });
});

describe("color helpers", () => {
  it("maps route scores to semantic colors", () => {
    expect(routeScoreColor(8)).toBe("var(--green)");
    expect(routeScoreColor(6)).toBe("var(--neon-cyan)");
    expect(routeScoreColor(4)).toBe("var(--amber)");
    expect(routeScoreColor(1)).toBe("var(--text-muted)");
  });

  it("maps backlog status to semantic colors", () => {
    expect(backlogStatusColor("done")).toBe("var(--green)");
    expect(backlogStatusColor("human_gated")).toBe("var(--text-muted)");
  });
});
