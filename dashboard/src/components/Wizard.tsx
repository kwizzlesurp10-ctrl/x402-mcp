import type { DoctorCheck } from "../types/api";

interface WizardProps {
  checks: DoctorCheck[];
  open: boolean;
  onClose: () => void;
}

export function Wizard({ checks, open, onClose }: WizardProps) {
  if (!open) return null;

  const allPassed = checks.every((c) => c.passed);

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0, 0, 0, 0.7)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 100,
      }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
      role="dialog"
      aria-label="Setup wizard"
    >
      <div
        style={{
          background: "var(--color-panel)",
          border: "1px solid var(--color-border)",
          borderRadius: "12px",
          padding: "24px",
          maxWidth: "520px",
          width: "90vw",
          maxHeight: "80vh",
          overflow: "auto",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <h2 style={{ fontSize: "16px", fontWeight: 600 }}>
            {allPassed ? "Setup Complete" : "First-Run Setup"}
          </h2>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              color: "var(--color-text-muted)",
              fontSize: "18px",
              cursor: "pointer",
              padding: "4px",
            }}
            aria-label="Close wizard"
          >
            x
          </button>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          {checks.map((check) => (
            <div
              key={check.id}
              style={{
                padding: "10px 12px",
                borderRadius: "8px",
                border: `1px solid ${check.passed ? "var(--color-border)" : "rgba(229, 72, 77, 0.3)"}`,
                background: check.passed ? "transparent" : "rgba(229, 72, 77, 0.05)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span
                  className={`dot ${check.passed ? "dot-green" : "dot-red"}`}
                  aria-hidden="true"
                />
                <span style={{ fontWeight: 500, fontSize: "13px" }}>
                  {check.passed ? "Pass" : "Fail"}
                </span>
                <span style={{ fontSize: "13px" }}>{check.label}</span>
              </div>
              {check.detail && (
                <div
                  className="mono"
                  style={{
                    fontSize: "11px",
                    color: "var(--color-text-muted)",
                    marginTop: "4px",
                    marginLeft: "20px",
                  }}
                >
                  {check.detail}
                </div>
              )}
              {check.fix && !check.passed && (
                <div
                  style={{
                    marginTop: "6px",
                    marginLeft: "20px",
                    padding: "6px 10px",
                    background: "var(--color-base)",
                    borderRadius: "4px",
                    fontSize: "12px",
                  }}
                >
                  <span style={{ color: "var(--color-text-muted)" }}>Fix: </span>
                  <code className="mono" style={{ color: "var(--color-amber)", fontSize: "11px" }}>
                    {check.fix}
                  </code>
                </div>
              )}
            </div>
          ))}
        </div>

        {allPassed && (
          <div style={{ marginTop: "16px", textAlign: "center", color: "var(--color-green)", fontSize: "14px" }}>
            All checks passed — you're ready to go!
          </div>
        )}
      </div>
    </div>
  );
}
