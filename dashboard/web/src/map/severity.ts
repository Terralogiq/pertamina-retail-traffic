// Pure helpers for the overview: per-site severity, ranking, the "now" summary and marker clustering.
import type { BandId } from "../theme/palette";
import type { LatestLeg, Site } from "./api";
import { BAND_RANK, BASELINE_FULL, Basis, isSlowed, legBand } from "./bands";

export interface SiteState {
  site: Site;
  /** Worst band over the site's legs; "none" when no leg has a reading. */
  band: BandId;
  basis: Basis;
  /** The leg with the largest delay, and that delay; null without data. */
  worstLeg: string | null;
  worstDelay: number | null;
}

export function siteState(site: Site, latest: Map<string, LatestLeg>): SiteState {
  let band: BandId = "none";
  let basis: Basis = "none";
  let worstLeg: string | null = null;
  let worstDelay: number | null = null;
  for (const leg of site.legs) {
    const row = latest.get(leg.selected_route_id);
    const b = legBand(row);
    if (BAND_RANK[b.band] > BAND_RANK[band]) {
      band = b.band;
      basis = b.basis;
    }
    if (row?.delay_s != null && (worstDelay === null || row.delay_s > worstDelay)) {
      worstDelay = row.delay_s;
      worstLeg = leg.leg;
    }
  }
  return { site, band, basis, worstLeg, worstDelay };
}

/** Worst first: band, then the larger delay (unknown last), then name, so the order is stable between refreshes. */
export function rankSites(sites: Site[], latest: Map<string, LatestLeg>): SiteState[] {
  return sites
    .map((s) => siteState(s, latest))
    .sort(
      (a, b) =>
        BAND_RANK[b.band] - BAND_RANK[a.band] ||
        (b.worstDelay ?? -Infinity) - (a.worstDelay ?? -Infinity) ||
        a.site.name.localeCompare(b.site.name),
    );
}

export interface Summary {
  total: number;
  /** Sites with at least one reading. */
  reporting: number;
  slowed: number;
  worst: SiteState | null;
  /** Newest slot over every leg; null without data. */
  slotTime: string | null;
  /** Lowest baseline_samples over every leg with data, capped at BASELINE_FULL; null without data. */
  baseline: number | null;
}

export function summarize(ranked: SiteState[], latest: Map<string, LatestLeg>): Summary {
  const rows = [...latest.values()];
  const withDelay = ranked.filter((s) => s.worstDelay !== null);
  const slots = rows.map((r) => r.slot_time).sort();
  return {
    total: ranked.length,
    reporting: ranked.filter((s) => s.band !== "none").length,
    slowed: ranked.filter((s) => isSlowed(s.band)).length,
    worst: withDelay.length ? withDelay.reduce((a, b) => (b.worstDelay! > a.worstDelay! ? b : a)) : null,
    slotTime: slots.length ? slots[slots.length - 1] : null,
    baseline: rows.length ? Math.min(...rows.map((r) => Math.min(r.baseline_samples ?? 0, BASELINE_FULL))) : null,
  };
}

/** Whole days until the baseline is full at 48 slots a day; 0 when full. */
export const baselineDaysLeft = (samples: number): number => Math.max(0, Math.ceil((BASELINE_FULL - samples) / 48));

export interface Point {
  id: string;
  lat: number;
  lng: number;
}

/** Web Mercator world pixel at a zoom level (256 px tiles). */
function toPixel(p: { lat: number; lng: number }, zoom: number): { x: number; y: number } {
  const scale = 256 * 2 ** zoom;
  const sin = Math.sin((p.lat * Math.PI) / 180);
  return {
    x: ((p.lng + 180) / 360) * scale,
    y: (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * scale,
  };
}

export interface Cluster {
  ids: string[];
  lat: number;
  lng: number;
}

/**
 * Greedy grouping of points closer than `radiusPx` on screen at `zoom`. Points are taken in the order
 * given (pass them worst first so the anchor of each group is its worst site); a group sits at its
 * members' mean position.
 */
export function clusterPoints(points: Point[], zoom: number, radiusPx = 40): Cluster[] {
  const groups: { anchor: { x: number; y: number }; members: Point[] }[] = [];
  for (const p of points) {
    const px = toPixel(p, zoom);
    const hit = groups.find((g) => Math.hypot(g.anchor.x - px.x, g.anchor.y - px.y) < radiusPx);
    if (hit) hit.members.push(p);
    else groups.push({ anchor: px, members: [p] });
  }
  return groups.map((g) => ({
    ids: g.members.map((m) => m.id),
    lat: g.members.reduce((s, m) => s + m.lat, 0) / g.members.length,
    lng: g.members.reduce((s, m) => s + m.lng, 0) / g.members.length,
  }));
}
