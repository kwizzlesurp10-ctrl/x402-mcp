import { useState } from "react";

const STEPS = [
  { title: "Setup wizard", body: "Doctor checks tell you exactly what to fix in .env before going live." },
  { title: "Demo mode", body: "Toggle Demo to preview every panel with zero wallet — great for screenshots." },
  { title: "Mission progress", body: "Track clone → discovery → probe → paid fetch → revenue in the header drawer." },
  { title: "402 Inspector", body: "Paste a URL to probe PAYMENT-REQUIRED headers without spending USDC." },
  { title: "Sell something", body: "Build seller requirements and copy a minimal FastAPI 402 gate snippet." },
];

export function OnboardingTour({ onDone }: { onDone: () => void }) {
  const [step, setStep] = useState(0);
  const current = STEPS[step];

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.75)",
        zIndex: 25,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
      role="dialog"
      aria-label="Onboarding tour"
    >
      <div className="panel" style={{ width: 400 }}>
        <p style={{ color: "var(--text-muted)", margin: 0 }}>
          Step {step + 1} of {STEPS.length}
        </p>
        <h3>{current.title}</h3>
        <p>{current.body}</p>
        <div style={{ display: "flex", gap: 8 }}>
          {step < STEPS.length - 1 ? (
            <button type="button" onClick={() => setStep((s) => s + 1)}>
              Next
            </button>
          ) : (
            <button type="button" onClick={onDone}>
              Done
            </button>
          )}
          <button type="button" onClick={onDone}>
            Skip
          </button>
        </div>
      </div>
    </div>
  );
}