import type { MissionStep } from "../utils/mission";

export function MissionProgress({
  steps,
  open,
  onToggle,
}: {
  steps: MissionStep[];
  open: boolean;
  onToggle: () => void;
}) {
  const done = steps.filter((s) => s.done).length;
  return (
    <div className="panel" style={{ margin: "0 16px 8px" }}>
      <button type="button" onClick={onToggle} style={{ background: "transparent", border: "none", color: "var(--text)", cursor: "pointer" }}>
        Mission progress {done}/{steps.length} {open ? "▾" : "▸"}
      </button>
      {open && (
        <ol style={{ margin: "8px 0 0", paddingLeft: 20 }}>
          {steps.map((s) => (
            <li key={s.id} style={{ color: s.done ? "var(--green)" : "var(--text-muted)" }}>
              {s.done ? "✓" : "○"} {s.label}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}