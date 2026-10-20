import type { SwarmAssessment, SwarmBacklogItem } from "../api/client";

export type BacklogBuckets = {
  actionable: SwarmBacklogItem[];
  humanGated: SwarmBacklogItem[];
};

export function splitBacklog(backlog: SwarmBacklogItem[]): BacklogBuckets {
  const actionable: SwarmBacklogItem[] = [];
  const humanGated: SwarmBacklogItem[] = [];
  for (const item of backlog) {
    if (item.human_gated) humanGated.push(item);
    else actionable.push(item);
  }
  return { actionable, humanGated };
}

export function topProfitRoutes(assessment: SwarmAssessment, limit = 3): SwarmAssessment["profit_routes"] {
  return assessment.profit_routes.slice(0, limit);
}

export function routeScoreColor(score: number): string {
  if (score >= 7) return "var(--green)";
  if (score >= 5) return "var(--neon-cyan)";
  if (score >= 3) return "var(--amber)";
  return "var(--text-muted)";
}

export function backlogStatusColor(status: string): string {
  switch (status) {
    case "done":
      return "var(--green)";
    case "active":
      return "var(--neon-cyan)";
    case "partial":
      return "var(--amber)";
    case "available":
      return "var(--usdc)";
    case "human_gated":
    case "human_assisted":
      return "var(--text-muted)";
    default:
      return "var(--text-muted)";
  }
}
