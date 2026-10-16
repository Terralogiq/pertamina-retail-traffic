import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { BASELINE_FULL } from "./bands";
import { BaselineNotice, NowSummary } from "./Overview";
import type { SiteState, Summary } from "./severity";

const html = (node: ReactElement) => renderToStaticMarkup(<MemoryRouter>{node}</MemoryRouter>);

describe("BaselineNotice", () => {
  it("shows the reading count and no calendar date while the usual time is provisional", () => {
    const out = html(<BaselineNotice samples={30} />);
    expect(out).toContain(`30 of ${BASELINE_FULL}`);
    expect(out).toContain("not ready yet");
    expect(out).not.toContain("day");
  });
  it("is hidden when full or without data", () => {
    expect(html(<BaselineNotice samples={BASELINE_FULL} />)).toBe("");
    expect(html(<BaselineNotice samples={null} />)).toBe("");
  });
});

describe("NowSummary", () => {
  const base: Summary = { total: 10, reporting: 10, slowed: 3, worst: null, slotTime: "2026-10-07T07:30:00Z", baseline: 30 };
  it("states slowed sites and the reading time", () => {
    const out = html(<NowSummary summary={base} />);
    expect(out).toContain("3 of 10");
    expect(out).toContain("14:30 WIB");
  });
  it("names the worst site with its leg and delay, linked to its page", () => {
    const worst = {
      site: { site_id: "b", name: "Bravo" },
      band: "jam",
      basis: "speed",
      worstLeg: "approach",
      worstDelay: 50,
    } as unknown as SiteState;
    const out = html(<NowSummary summary={{ ...base, worst }} />);
    expect(out).toContain("Worst:");
    expect(out).toContain('href="/site/b"');
    expect(out).toContain("Bravo");
    expect(out).toContain("50 s");
  });
  it("omits Worst when no site has a delay", () => {
    expect(html(<NowSummary summary={base} />)).not.toContain("Worst:");
  });
  it("waits for data", () => {
    expect(html(<NowSummary summary={{ ...base, reporting: 0 }} />)).toContain("Waiting for the first traffic readings");
  });
});
