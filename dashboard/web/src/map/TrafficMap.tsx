import { ReactElement, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { createRoot } from "react-dom/client";
import { QueueRisk, RISK_LABELS, RISK_MARKER_TEXT, RISK_ORDER } from "../overview/model";
import { BANDS, CHART_INK } from "../theme/palette";
import { LatestLeg, Site } from "./api";
import { boundsOf, formatDelay, legColor, legContext, lineToPath, sitePoints } from "./bands";
import Legend, { QueueLegend } from "./Legend";
import { GroupPopup, LegPopup, SitePopup, buildGroupPopup, buildLegPopup, buildSitePopup } from "./LegPopup";
import { loadMaps } from "./maps";
import { MapMarker, QueueMarker } from "./MapMarker";
import { useMapPopup } from "./useMapPopup";
import { MARKER_BOX, MARKER_BOX_COMPACT, MARKER_BOX_WIDE, Point, SiteState, clusterPoints, rankSites, zoomToSeparate } from "./severity";

type Libs = Awaited<ReturnType<typeof loadMaps>>;

/** Initial zoom (Indonesia) until the fit below runs. */
const START = { center: { lat: -2.5, lng: 118 }, zoom: 5 };
/** On the overview, the legs are drawn from this zoom; below it the markers alone carry the picture. */
const LEGS_MIN_ZOOM = 14;
/** Marker pills sit above their point, so fits leave extra room at the top to keep the topmost pill inside the map. */
const FIT_PADDING = { top: 88, right: 56, bottom: 48, left: 56 };
/** Phones: the map is ~320 px wide, so the pills shrink to the band shape and the fit keeps less margin. */
const FIT_PADDING_COMPACT = { top: 40, right: 24, bottom: 24, left: 24 };
const COMPACT_QUERY = "(max-width: 767px)";

/** True while the viewport matches the shell's compact breakpoint. */
function useCompact(): boolean {
  const [compact, setCompact] = useState(() => typeof window !== "undefined" && window.matchMedia(COMPACT_QUERY).matches);
  useEffect(() => {
    const mq = window.matchMedia(COMPACT_QUERY);
    const onChange = () => setCompact(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return compact;
}

/** A marker pill sits above its point; a hover card is raised by about its height (pill, tail and hover lift) to clear it. */
const MARKER_CARD_LIFT_PX = 48;
/** The selected marker draws over its neighbours. */
const SELECTED_Z = 1000;

/** Pointer-enter handler for hover cards: a touch tap fires it too, but there a tap acts (select, zoom, pin) and has no hover. */
const hoverOnly = (show: () => void) => (e: Event) => {
  if ((e as PointerEvent).pointerType !== "touch") show();
};

/** A marker whose content is a small React tree; returns its cleanup. */
function reactMarker(
  libs: Libs,
  map: google.maps.Map,
  position: google.maps.LatLngLiteral,
  title: string,
  body: ReactElement,
): { marker: google.maps.marker.AdvancedMarkerElement; remove: () => void } {
  const el = document.createElement("div");
  const root = createRoot(el);
  root.render(body);
  const marker = new libs.marker.AdvancedMarkerElement({ map, position, title, content: el, gmpClickable: true });
  return {
    marker,
    remove: () => {
      marker.map = null;
      // Unmount after the current render pass; unmounting a root synchronously inside an effect cleanup warns.
      setTimeout(() => root.unmount());
    },
  };
}

interface Props {
  sites: Site[];
  latest: Map<string, LatestLeg>;
  /** Overview shows every site (grouped when they overlap) and selects one on click; the site map passes one site's id. */
  siteId?: string;
  onSelectSite?: (siteId: string) => void;
  /**
   * Overview "Queue risk" mode: each site's level sets its marker, and the risk key replaces the band key
   * (no legs, no hover cards). null while the levels load (no markers yet); undefined for live traffic.
   */
  queueRisks?: Map<string, QueueRisk> | null;
  /** Overview: the selected site's marker is raised and ringed, and the map pans (zooming out of a group marker) to it. */
  selectedId?: string | null;
}

/** Sites in risk order (list order), keeping the ranking within a level, so a cluster's first member is its highest risk. */
const byRisk = (ranked: SiteState[], risks: Map<string, QueueRisk>) => {
  const rank = (s: SiteState) => RISK_ORDER.indexOf(risks.get(s.site.site_id) ?? "low");
  return [...ranked].sort((a, b) => rank(a) - rank(b));
};

export default function TrafficMap({ sites, latest, siteId, onSelectSite, queueRisks, selectedId = null }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const [libs, setLibs] = useState<Libs | null>(null);
  const [map, setMap] = useState<google.maps.Map | null>(null);
  const [legendEl, setLegendEl] = useState<HTMLElement | null>(null);
  const [zoom, setZoom] = useState(START.zoom);
  const [error, setError] = useState("");

  const popup = useMapPopup(map, libs);
  const compact = useCompact();
  const fitPadding = compact ? FIT_PADDING_COMPACT : FIT_PADDING;
  const shown = useMemo(() => (siteId ? sites.filter((s) => s.site_id === siteId) : sites), [sites, siteId]);
  // Handlers read the callback through a ref so a new function identity does not redraw the overlays.
  const select = useRef(onSelectSite);
  select.current = onSelectSite;
  const shownRef = useRef(shown);
  shownRef.current = shown;
  // The marker effect's last clustering input, so a selection can work out the zoom that separates its marker.
  const clusterInput = useRef<{ points: Point[]; box: typeof MARKER_BOX } | null>(null);
  const clickable = !!onSelectSite;
  const riskMode = queueRisks !== undefined;
  const showLegs = !riskMode && (!!siteId || zoom >= LEGS_MIN_ZOOM);
  // Group markers depend on the zoom on the overview only; the site map never regroups.
  const groupZoom = siteId ? 0 : zoom;

  // Create the map once.
  useEffect(() => {
    let cancelled = false;
    loadMaps()
      .then((l) => {
        if (cancelled) return;
        const m = new l.maps.Map(el.current!, {
          ...START,
          mapId: l.mapId,
          mapTypeControl: false,
          streetViewControl: false,
          fullscreenControl: false,
          clickableIcons: false,
          // Fits land between integer zooms; on a ~320 px phone map the next integer down merges most markers.
          isFractionalZoomEnabled: true,
        });
        // `idle`, not `zoom_changed`: one update when the zoom (or fit) settles, not one per animation step.
        m.addListener("idle", () => setZoom(Math.floor((m.getZoom() ?? START.zoom) * 4) / 4));
        // The legend is a map control so it stacks above Google's logo and Terms instead of covering them.
        const legend = document.createElement("div");
        // On the site map the fit leaves room at the top, where the compact legend cannot cover the legs.
        m.controls[siteId ? l.core.ControlPosition.TOP_LEFT : l.core.ControlPosition.LEFT_BOTTOM].push(legend);
        setLegendEl(legend);
        setLibs(l);
        setMap(m);
      })
      .catch((e) => !cancelled && setError("The map could not load. Check your connection and reload the page."));
    return () => {
      cancelled = true;
    };
  }, []);

  // Fit when the set of shown sites changes, not on every traffic refresh (that would undo the user's panning).
  useEffect(() => {
    const bounds = boundsOf(sitePoints(shown));
    if (map && bounds) map.fitBounds(bounds, fitPadding);
  }, [map, shown, fitPadding]);

  // Legs: a light casing under each coloured line so it holds against any basemap; redraw on new data.
  // Hover shows the leg card. Where a click does not select (the site map), a click or tap pins it with a
  // close button (Escape or a click on the map closes it; see useMapPopup).
  useEffect(() => {
    if (!map || !libs || !showLegs) return;
    const cleanups: (() => void)[] = [];
    for (const site of shown) {
      for (const leg of site.legs) {
        const path = lineToPath(leg.expected_polyline);
        if (path.length < 2) continue;
        const row = latest.get(leg.selected_route_id);
        const model = buildLegPopup(site, leg, row);
        const { color } = legColor(row, legContext(site, leg.selected_route_id));
        const casing = new libs.maps.Polyline({ map, path, strokeColor: CHART_INK.surface, strokeOpacity: 0.95, strokeWeight: 10, clickable: false });
        const line = new libs.maps.Polyline({
          map,
          path,
          strokeColor: color,
          strokeOpacity: 1,
          strokeWeight: 6,
          clickable: true,
          // Arrow at the midpoint: the polyline runs in travel direction (approach towards the SPBU, departure away).
          icons: [
            {
              icon: { path: libs.core.SymbolPath.FORWARD_CLOSED_ARROW, scale: 2, strokeColor: CHART_INK.surface, fillColor: color, fillOpacity: 1 },
              offset: "50%",
            },
          ],
        });
        line.addListener("mouseover", (e: google.maps.PolyMouseEvent) => {
          line.setOptions({ strokeWeight: 9 });
          casing.setOptions({ strokeWeight: 13 });
          if (e.latLng) popup.hover(e.latLng.toJSON(), <LegPopup model={model} />);
        });
        line.addListener("mouseout", () => {
          line.setOptions({ strokeWeight: 6 });
          casing.setOptions({ strokeWeight: 10 });
          popup.hideSoon();
        });
        line.addListener("click", (e: google.maps.PolyMouseEvent) => {
          if (clickable) return select.current?.(site.site_id);
          if (e.latLng) popup.togglePin(line, e.latLng.toJSON(), (onClose) => <LegPopup model={model} onClose={onClose} />);
        });
        cleanups.push(() => {
          line.setMap(null);
          casing.setMap(null);
        });
      }
    }
    return () => {
      popup.hide();
      cleanups.forEach((fn) => fn());
    };
  }, [map, libs, shown, latest, clickable, showLegs, popup]);

  // Markers: one per site; on the overview, sites that would overlap at this zoom share one group marker that
  // zooms in on click. Live traffic shows each site's worst band and delay (a group: its worst member's band);
  // "Queue risk" shows each site's level (a group marker: its highest risk).
  useEffect(() => {
    if (!map || !libs || queueRisks === null) return;
    const ranked = rankSites(shown, latest);
    const ordered = queueRisks ? byRisk(ranked, queueRisks) : ranked;
    const byId = new Map(ordered.map((s) => [s.site.site_id, s]));
    const box = compact ? MARKER_BOX_COMPACT : queueRisks ? MARKER_BOX_WIDE : MARKER_BOX;
    const points = ordered.map((s) => ({ id: s.site.site_id, ...s.site.location }));
    clusterInput.current = { points, box };
    const groups = siteId ? ordered.map((s) => ({ ids: [s.site.site_id], ...s.site.location })) : clusterPoints(points, groupZoom, box);
    const cleanups: (() => void)[] = [];

    for (const group of groups) {
      const members = group.ids.map((id) => byId.get(id)!);
      const lead = members[0]; // ordered: the worst site (or highest risk) leads its group
      if (members.length === 1) {
        const { site, band, worstDelay } = lead;
        const selected = site.site_id === selectedId;
        if (queueRisks) {
          const r = queueRisks.get(site.site_id) ?? "low";
          const { marker, remove } = reactMarker(
            libs,
            map,
            site.location,
            `${site.name}: ${RISK_LABELS[r]}`,
            <QueueMarker risk={r} text={RISK_MARKER_TEXT[r]} compact={compact} selected={selected} />,
          );
          if (selected) marker.zIndex = SELECTED_Z;
          marker.addEventListener("gmp-click", () => select.current?.(site.site_id));
          cleanups.push(remove);
          continue;
        }
        const text = worstDelay === null ? BANDS.none.label : formatDelay(worstDelay);
        const { marker, remove } = reactMarker(
          libs,
          map,
          site.location,
          `${site.name}: ${BANDS[band].label}, ${text}`,
          <MapMarker band={band} text={text} compact={compact} selected={selected} />,
        );
        if (selected) marker.zIndex = SELECTED_Z;
        const model = buildSitePopup(site, latest);
        marker.addEventListener("pointerenter", hoverOnly(() => popup.hover(site.location, <SitePopup model={model} />, MARKER_CARD_LIFT_PX)));
        marker.addEventListener("pointerleave", popup.hideSoon);
        // Where a click does not select (the site map) a tap pins the card, as on the legs.
        marker.addEventListener("gmp-click", () =>
          clickable
            ? select.current?.(site.site_id)
            : popup.togglePin(marker, site.location, (onClose) => <SitePopup model={model} onClose={onClose} />, MARKER_CARD_LIFT_PX),
        );
        cleanups.push(remove);
      } else {
        const names = members.map((m) => m.site.name);
        const at = { lat: group.lat, lng: group.lng };
        const countText = compact ? String(members.length) : `${members.length} sites`;
        const leadRisk = queueRisks?.get(lead.site.site_id);
        const { marker, remove } = leadRisk
          ? reactMarker(libs, map, at, `${members.length} sites: ${names.join(", ")}`, <QueueMarker risk={leadRisk} text={countText} group compact={compact} />)
          : reactMarker(
              libs,
              map,
              at,
              `${members.length} sites, worst ${BANDS[lead.band].label}: ${names.join(", ")}`,
              <MapMarker band={lead.band} text={countText} group compact={compact} />,
            );
        if (!queueRisks) {
          const model = buildGroupPopup(members);
          marker.addEventListener("pointerenter", hoverOnly(() => popup.hover(at, <GroupPopup model={model} />, MARKER_CARD_LIFT_PX)));
          marker.addEventListener("pointerleave", popup.hideSoon);
        }
        marker.addEventListener("gmp-click", () => {
          const bounds = boundsOf(sitePoints(members.map((m) => m.site)));
          if (bounds) map.fitBounds(bounds, fitPadding);
        });
        cleanups.push(remove);
      }
    }
    return () => {
      popup.hide();
      cleanups.forEach((fn) => fn());
    };
  }, [map, libs, shown, latest, clickable, siteId, groupZoom, popup, compact, fitPadding, queueRisks, selectedId]);

  // Selection: pan to the site, zooming in first when its marker sits inside a group marker at this zoom.
  useEffect(() => {
    if (!map || !selectedId || siteId) return;
    const site = shownRef.current.find((s) => s.site_id === selectedId);
    if (!site) return;
    // The zoom the markers were grouped at (see the idle listener), so "already separate" matches what is drawn.
    const zoom = Math.floor((map.getZoom() ?? START.zoom) * 4) / 4;
    const input = clusterInput.current;
    const next = input ? zoomToSeparate(input.points, selectedId, zoom, input.box) : zoom;
    if (next > zoom || window.matchMedia("(prefers-reduced-motion: reduce)").matches) map.moveCamera({ center: site.location, zoom: next });
    else map.panTo(site.location);
  }, [map, selectedId, siteId]);

  return (
    <>
      {error && (
        <div className="map-error" role="alert">
          {error}
        </div>
      )}
      <div ref={el} className="map-canvas" />
      {legendEl &&
        createPortal(riskMode ? <QueueLegend /> : <Legend sites={shown} latest={latest} compact={!!siteId} />, legendEl)}
    </>
  );
}
