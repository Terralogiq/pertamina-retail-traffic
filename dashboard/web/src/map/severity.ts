// Pure helpers for the overview: per-site severity, ranking, the "now" summary and marker clustering.
import type { BandId } from "../theme/palette";
import type { LatestLeg, Site } from "./api";
import { BAND_RANK, BASELINE_FULL, Basis, isSlowed, legBand, legContext } from "./bands";

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
    const b = legBand(row, legContext(site, leg.selected_route_id));
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

export type SiteSort = "worst" | "name" | "city";
export type SiteFilter = "all" | "slowed";

/** The list as shown: `ranked` is already worst first; filter to slowed sites, then re-sort by name or city (name breaks ties). */
export function orderSites(ranked: SiteState[], sort: SiteSort, filter: SiteFilter): SiteState[] {
  const rows = filter === "slowed" ? ranked.filter((s) => isSlowed(s.band)) : ranked;
  if (sort === "worst") return rows;
  const city = (s: SiteState) => s.site.city ?? "";
  return [...rows].sort((a, b) => (sort === "city" ? city(a).localeCompare(city(b)) : 0) || a.site.name.localeCompare(b.site.name));
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
  const slots = rows.map((r) => r.slot_time).sort();
  return {
    total: ranked.length,
    reporting: ranked.filter((s) => s.band !== "none").length,
    slowed: ranked.filter((s) => isSlowed(s.band)).length,
    // The first ranked site with a delay, so "Worst" matches the head of the list (rank is band first, then delay).
    worst: ranked.find((s) => s.worstDelay !== null) ?? null,
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

/** Screen footprint of a marker pill (largest label, "+3.4 min" / "N sites"), used to keep markers from overlapping. */
export const MARKER_BOX = { width: 96, height: 32 };
/** Phone footprint: the pill shows only the band shape (or a group count), see MapMarker `compact`. */
export const MARKER_BOX_COMPACT = { width: 48, height: 30 }; // widest compact pill: a group with a 2-digit count

/**
 * Groups points whose markers would overlap on screen at `zoom`. Starts with one group per point (pass them
 * worst first, so each group's first member is its worst site) and keeps merging any two groups whose marker
 * boxes, centred on the members' mean position, overlap, until none do. A merge can move a group onto a third
 * one, which is why it loops.
 */
export function clusterPoints(points: Point[], zoom: number, box = MARKER_BOX): Cluster[] {
  let groups = points.map((p) => ({ members: [p], px: toPixel(p, zoom) }));
  const centre = (members: Point[]) => {
    const pxs = members.map((m) => toPixel(m, zoom));
    return { x: pxs.reduce((s, q) => s + q.x, 0) / pxs.length, y: pxs.reduce((s, q) => s + q.y, 0) / pxs.length };
  };
  for (;;) {
    let merged = false;
    outer: for (let i = 0; i < groups.length; i++) {
      for (let j = i + 1; j < groups.length; j++) {
        const a = groups[i].px, b = groups[j].px;
        if (Math.abs(a.x - b.x) < box.width && Math.abs(a.y - b.y) < box.height) {
          const members = [...groups[i].members, ...groups[j].members];
          groups = [...groups.slice(0, i), { members, px: centre(members) }, ...groups.slice(i + 1, j), ...groups.slice(j + 1)];
          merged = true;
          break outer;
        }
      }
    }
    if (!merged) break;
  }
  return groups.map((g) => ({
    ids: g.members.map((m) => m.id),
    lat: g.members.reduce((s, m) => s + m.lat, 0) / g.members.length,
    lng: g.members.reduce((s, m) => s + m.lng, 0) / g.members.length,
  }));
}
