import { ReactNode, useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import "./AppShell.css";

export const PRODUCT_NAME = "Pertamina Retail traffic";

/** Text wordmark until the official logo arrives (bead .9.2 swaps this for the SVG). */
export function Wordmark() {
  return (
    <span className="wordmark">
      <span className="wordmark-brand">Pertamina Retail</span>
      <span className="wordmark-product">SPBU traffic</span>
    </span>
  );
}

/** Site pages sit under the overview, so they keep "Overview" active. */
const NAV = [
  { to: "/", label: "Overview", matches: (path: string) => path === "/" || path.startsWith("/site/") },
  { to: "/rain", label: "Traffic vs rain", matches: (path: string) => path.startsWith("/rain") },
];

export function AppShell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  return (
    <div className="shell">
      <header className="shell-header">
        <Link to="/" className="shell-home" aria-label={`${PRODUCT_NAME}: overview`}>
          <Wordmark />
        </Link>
        <nav className="shell-nav" aria-label="Main">
          {NAV.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              className={item.matches(pathname) ? "shell-nav-link active" : "shell-nav-link"}
              aria-current={item.matches(pathname) ? "page" : undefined}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </header>
      <main className="shell-main">{children}</main>
    </div>
  );
}

/** Sets the tab title: "<page> · Pertamina Retail traffic". */
export function usePageTitle(page: string) {
  useEffect(() => {
    document.title = `${page} · ${PRODUCT_NAME}`;
  }, [page]);
}

/**
 * Page heading row: the page's only <h1>, an optional line of context, and optional actions.
 * `fill` pages (the overview map) take the full height under the header instead of scrolling.
 */
export function Page({
  title,
  context,
  actions,
  fill = false,
  children,
}: {
  title: string;
  context?: ReactNode;
  actions?: ReactNode;
  fill?: boolean;
  children: ReactNode;
}) {
  usePageTitle(title);
  return (
    <div className={fill ? "page page-fill" : "page"}>
      <div className="page-header">
        <div className="page-heading">
          <h1>{title}</h1>
          {context && <div className="page-context">{context}</div>}
        </div>
        {actions && <div className="page-actions">{actions}</div>}
      </div>
      <div className="page-body">{children}</div>
    </div>
  );
}
