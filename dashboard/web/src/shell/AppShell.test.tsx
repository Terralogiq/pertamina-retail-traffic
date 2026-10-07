import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { SiteDetail } from "../site";
import { AppShell, Page } from "./AppShell";

const count = (html: string, needle: string) => html.split(needle).length - 1;

function renderAt(path: string) {
  return renderToStaticMarkup(
    <MemoryRouter initialEntries={[path]}>
      <AppShell>
        <Routes>
          <Route path="/" element={<Page title="Overview" fill>map</Page>} />
          <Route path="/rain" element={<Page title="Traffic vs rain">rain</Page>} />
          <Route path="/site/:site_id" element={<SiteDetail />} />
        </Routes>
      </AppShell>
    </MemoryRouter>,
  );
}

describe("AppShell nav", () => {
  it("marks exactly one link as the current page on /", () => {
    const html = renderAt("/");
    expect(count(html, 'aria-current="page"')).toBe(1);
    expect(html).toMatch(/aria-current="page"[^>]*>Overview</);
  });

  it("marks Rain as the page on /rain", () => {
    const html = renderAt("/rain");
    expect(count(html, 'aria-current="page"')).toBe(1);
    expect(html).toMatch(/aria-current="page"[^>]*>Traffic vs rain</);
  });

  it("keeps Overview highlighted with aria-current=true on a site page", () => {
    const html = renderAt("/site/x");
    expect(count(html, 'aria-current="page"')).toBe(0);
    expect(html).toMatch(/aria-current="true"[^>]*>Overview</);
  });

  it("names the home link by its visible text only", () => {
    const html = renderAt("/");
    expect(html).toMatch(/<a [^>]*class="shell-home"[^>]*>/);
    expect(html).not.toMatch(/<a [^>]*class="shell-home"[^>]*aria-label/);
    expect(html).not.toMatch(/<a [^>]*aria-label[^>]*class="shell-home"/);
  });
});

describe("Page", () => {
  it("renders the single h1 on each screen", () => {
    for (const path of ["/", "/rain", "/site/x"]) expect(count(renderAt(path), "<h1"), path).toBe(1);
  });

  it("titles the site page from the route", () => {
    expect(renderAt("/site/x")).toContain("<h1>Site x</h1>");
  });
});
