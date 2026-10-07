import { ReactNode } from "react";
import "./DemoBadge.css";

/** Marks a widget (or control) that shows a demo-only field. The only place the label text lives. */
export function DemoBadge() {
  return (
    <span className="demo-badge" title="Uses a field only the demo data source provides">
      demo-only
    </span>
  );
}

/**
 * Section-level note, shown once instead of a badge on every card. Pair it with <DemoMarker /> on
 * the individual values it covers.
 */
export function DemoNote({ children }: { children: ReactNode }) {
  return (
    <p className="demo-note">
      <DemoBadge />
      <span>{children}</span>
    </p>
  );
}

/** Small marker on a single demo-only value inside a section that carries a <DemoNote />. */
export function DemoMarker() {
  return (
    <span className="demo-marker" title="Demo-only field">
      <span className="visually-hidden">demo-only</span>
    </span>
  );
}

/** A titled card; `demo` adds the badge next to the title. */
export function Widget({ title, demo = false, children }: { title: string; demo?: boolean; children: ReactNode }) {
  return (
    <section className="widget">
      <h3 className="widget-title">
        {title}
        {demo && <DemoBadge />}
      </h3>
      {children}
    </section>
  );
}
