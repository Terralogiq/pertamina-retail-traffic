import { ReactNode, useEffect } from "react";
import { Link, useLocation, useMatch } from "react-router-dom";
import { PRODUCT_NAME, Wordmark } from "../theme/Wordmark";
import { SitePicker, useSiteList } from "./SitePicker";
import "./AppShell.css";

/** Site pages sit under the overview: Overview stays highlighted there (aria-current="true", not "page"). */
const NAV = [
  {
    to: "/",
    label: "Overview",
    current: (path: string) => (path === "/" ? "page" : path.startsWith("/site/") ? "true" : undefined),
  },
  { to: "/rain", label: "Traffic vs rain", current: (path: string) => (path.startsWith("/rain") ? "page" : undefined) },
  { to: "/places", label: "Places vs traffic", current: (path: string) => (path.startsWith("/places") ? "page" : undefined) },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const sites = useSiteList(pathname);
  const siteId = useMatch("/site/:site_id")?.params.site_id ?? "";
  return (
    <div className="shell">
      <header className="shell-header">
        <Link to="/" className="shell-home">
          <Wordmark />
        </Link>
        <nav className="shell-nav" aria-label="Main">
          {NAV.map((item) => {
            const current = item.current(pathname);
            return (
              <Link
                key={item.to}
                to={item.to}
                className={current ? "shell-nav-link active" : "shell-nav-link"}
                aria-current={current}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <SitePicker sites={sites} currentId={siteId} />
      </header>
      <main className="shell-main">{children}</main>
      <footer className="shell-footer">by Terralogiq</footer>
    </div>
  );
}

/** Sets the tab title: "<page> · Pertamina Retail SPBU traffic". */
export function usePageTitle(page: string) {
  useEffect(() => {
    document.title = `${page} · ${PRODUCT_NAME}`;
  }, [page]);
}

/**
 * Page heading row: the page's only <h1>, an optional line of context, and optional actions.
 */
export function Page({
  title,
  context,
  actions,
  children,
}: {
  title: string;
  context?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}) {
  usePageTitle(title);
  return (
    <div className="page">
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
