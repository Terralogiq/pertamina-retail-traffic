import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { SiteDetail } from "../site";
import type { Site } from "../map/api";
import { AppShell, Page } from "./AppShell";
import { SitePicker, shortSiteLabel, siteOptionLabel, sortSites } from "./SitePicker";

const count = (html: string, needle: string) => html.split(needle).length - 1;

function renderAt(path: string) {
  return renderToStaticMarkup(
    <MemoryRouter initialEntries={[path]}>
      <AppShell>
        <Routes>
          <Route path="/" element={<Page title="Overview">map</Page>} />
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

describe("AppShell brand", () => {
  it("shows the logo image and product line in the home link, so the name is the product name", () => {
    const html = renderAt("/");
    expect(html).toMatch(/<a [^>]*class="shell-home"[^>]*><span class="wordmark"><img [^>]*alt="Pertamina Retail"/);
    expect(html).toMatch(/<img [^>]*width="770" height="202"/);
    expect(html).toMatch(/<span class="wordmark-product">SPBU traffic<\/span>/);
  });

  it("ends with a footer credit", () => {
    expect(renderAt("/")).toContain('<footer class="shell-footer">by Terralogiq</footer>');
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

const site = (site_id: string, name: string, city: string | null): Site => ({
  site_id,
  name,
  place_id: "p",
  road_name: null,
  city,
  road_type: null,
  road_class: "urban",
  timezone: "Asia/Jakarta",
  location: { lat: 0, lng: 0 },
  legs: [],
});
const SITES = [site("c", "SPBU B", "Medan"), site("a", "SPBU Z", "Bandar Lampung"), site("b", "SPBU A", "Medan"), site("d", "SPBU Q", null)];

function renderPicker(sites: Site[] | null | undefined, currentId: string) {
  return renderToStaticMarkup(
    <MemoryRouter>
      <SitePicker sites={sites} currentId={currentId} />
    </MemoryRouter>,
  );
}

describe("SitePicker", () => {
  it("is in the shell header with a label, disabled while sites load", () => {
    const html = renderAt("/");
    expect(html).toMatch(/<label [^>]*for="site-picker"[^>]*>Site<\/label>/);
    expect(html).toMatch(/<select [^>]*id="site-picker"[^>]*disabled/);
    expect(html).toContain("Loading sites…");
    expect(count(html, 'aria-current="page"')).toBe(1);
  });

  it("sorts by city then name, sites without a city last, and labels options name · city", () => {
    expect(sortSites(SITES).map((s) => s.site_id)).toEqual(["a", "b", "c", "d"]);
    expect(siteOptionLabel(SITES[0])).toBe("SPBU B · Medan");
    expect(siteOptionLabel(SITES[3])).toBe("SPBU Q");
  });

  it("selects the current site on a site page", () => {
    const html = renderPicker(sortSites(SITES), "b");
    expect(html).toMatch(/<option value="b" title="SPBU A · Medan" selected="">A · Medan<\/option>/);
    expect(html).not.toContain("disabled=\"\" selected");
    expect(count(html, "<option")).toBe(5);
  });

  it("shows the placeholder elsewhere and for an unknown code", () => {
    for (const id of ["", "nope"]) {
      const html = renderPicker(sortSites(SITES), id);
      expect(html).toMatch(/<option value="" disabled="" selected="">Go to site…<\/option>/);
      expect(html).not.toMatch(/<select [^>]*disabled/);
    }
  });

  it("renders nothing when /api/sites failed", () => {
    expect(renderPicker(null, "")).toBe("");
  });

  it("is a form: a visible Site label, a select that only changes local state, and a Go button", () => {
    const html = renderPicker(sortSites(SITES), "");
    expect(html).toMatch(/^<form class="shell-picker">/);
    expect(html).toMatch(/<label [^>]*for="site-picker"[^>]*>Site<\/label>/);
    expect(html).not.toMatch(/<label [^>]*visually-hidden/);
    expect(html).toMatch(/<button type="submit"[^>]*>Go<\/button>/);
  });

  it("does not throw on a malformed site code in the path", () => {
    expect(() => renderAt("/site/%E0")).not.toThrow();
    expect(() => renderAt("/site/%")).not.toThrow();
  });
});

describe("shortSiteLabel", () => {
  const named = (name: string, city: string | null) => shortSiteLabel(site("x", name, city));

  it("drops the SPBU Pertamina prefix and a trailing repeat of the city", () => {
    expect(named("SPBU Pertamina 61.761.03 - MT Haryono Balikpapan", "Balikpapan")).toBe("61.761.03 - MT Haryono · Balikpapan");
    expect(named("SPBU 34.121.03", "Jakarta Selatan")).toBe("34.121.03 · Jakarta Selatan");
    expect(named("spbu pertamina KM57A, Karawang", "karawang")).toBe("KM57A · karawang");
  });

  it("keeps a name that holds no prefix or city, and omits a missing city", () => {
    expect(named("Pertamina Tirtayasa", "Bandar Lampung")).toBe("Pertamina Tirtayasa · Bandar Lampung");
    expect(named("SPBU Pertamina 24.351.97", null)).toBe("24.351.97");
  });

  it("never returns an empty name", () => {
    expect(named("SPBU", "Medan")).toBe("SPBU · Medan");
    expect(named("Medan", "Medan")).toBe("Medan · Medan");
    expect(named("SPBUKU Medan", "Medan")).toBe("SPBUKU · Medan");
  });
});
