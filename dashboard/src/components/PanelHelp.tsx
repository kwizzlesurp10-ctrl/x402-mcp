import { explain } from "../glossary";

export function PanelHelp({ term, title }: { term: string; title: string }) {
  return (
    <button
      type="button"
      title={explain(term)}
      aria-label={`What is ${title}?`}
      style={{
        marginLeft: 6,
        width: 18,
        height: 18,
        borderRadius: "50%",
        border: "1px solid var(--border)",
        background: "transparent",
        color: "var(--text-muted)",
        cursor: "help",
        fontSize: 11,
      }}
    >
      ?
    </button>
  );
}