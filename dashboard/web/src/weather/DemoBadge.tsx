import { ReactNode } from "react";

/** Marks a widget (or control) that shows a demo-only field. The only place the label text lives. */
export function DemoBadge() {
  return (
    <span
      className="demo-badge"
      title="Uses a field only the demo data source provides"
      style={{
        marginLeft: 8,
        padding: "1px 6px",
        borderRadius: 4,
        background: "#fde68a",
        color: "#78350f",
        fontSize: 11,
        fontWeight: 600,
        textTransform: "uppercase",
        letterSpacing: 0.4,
      }}
    >
      demo-only
    </span>
  );
}

/** A titled card; `demo` adds the badge next to the title. */
export function Widget({ title, demo = false, children }: { title: string; demo?: boolean; children: ReactNode }) {
  return (
    <section style={{ border: "1px solid #ddd", borderRadius: 6, padding: 12, marginBottom: 16 }}>
      <h3 style={{ margin: "0 0 8px" }}>
        {title}
        {demo && <DemoBadge />}
      </h3>
      {children}
    </section>
  );
}
