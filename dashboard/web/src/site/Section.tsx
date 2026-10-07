import { CSSProperties, ReactNode } from "react";
import "./Section.css";

/** One titled region of the site page. `id` is the in-page anchor; `actions` sit at the end of the heading row. */
export function Section({
  id,
  title,
  note,
  actions,
  children,
}: {
  id: string;
  title: string;
  note?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="site-section" id={id} aria-labelledby={`${id}-title`}>
      <div className="site-section-head">
        <div className="site-section-heading">
          <h2 id={`${id}-title`}>{title}</h2>
          {note && <p className="site-section-note">{note}</p>}
        </div>
        {actions && <div className="site-section-actions">{actions}</div>}
      </div>
      {children}
    </section>
  );
}

/** A sub-block inside a section: small heading, then content. Not a card. */
export function Block({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <div className="site-block">
      <div className="site-block-head">
        <h3>{title}</h3>
        {aside && <span className="site-block-aside">{aside}</span>}
      </div>
      {children}
    </div>
  );
}

/** Placeholder with the final height of what loads into it, so content arriving doesn't move the page. */
export function Skeleton({ height, label = "Loading" }: { height: number; label?: string }) {
  return (
    <div
      className="skeleton"
      role="status"
      aria-label={label}
      style={{ "--skeleton-height": `${height}px` } as CSSProperties}
    />
  );
}

/** Inline notice for an empty or failed block. `tone` error is announced. */
export function Notice({ tone = "empty", children }: { tone?: "empty" | "error"; children: ReactNode }) {
  return (
    <p className={`site-notice site-notice-${tone}`} role={tone === "error" ? "alert" : undefined}>
      {children}
    </p>
  );
}
