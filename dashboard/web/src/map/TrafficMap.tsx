import { ReactElement, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { createRoot } from "react-dom/client";
import { BANDS, CHART_INK } from "../theme/palette";
import { LatestLeg, Site } from "./api";
import { boundsOf, formatDelay, legColor, lineToPath, sitePoints } from "./bands";
import Legend from "./Legend";
import { GroupPopup, LegPopup, SitePopup, buildGroupPopup, buildLegPopup, buildSitePopup } from "./LegPopup";
import { loadMaps } from "./maps";
import { MapMarker } from "./MapMarker";
import { useMapPopup } from "./useMapPopup";
import { MARKER_BOX, MARKER_BOX_COMPACT, clusterPoints, rankSites } from "./severity";

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

/** Pointer-enter handler for hover cards: a touch tap fires it too, but there a tap acts (navigate, zoom, pin) and has no hover. */
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
  /** Overview shows every site (grouped when they overlap) and navigates on click; the site map passes one site's id. */
  siteId?: string;
  onSelectSite?: (siteId: string) => void;
}

export default function TrafficMap({ sites, latest, siteId, onSelectSite }: Props) {
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
  const clickable = !!onSelectSite;
  const showLegs = !!siteId || zoom >= LEGS_MIN_ZOOM;
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
  // Hover shows the leg card. Where a click does not navigate (the site map), a click or tap pins it with a
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
        const { color } = legColor(row);
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

  // Markers: one per site showing its worst band and delay; on the overview, sites that would overlap at
  // this zoom share one group marker (its worst member's band) that zooms in on click.
  useEffect(() => {
    if (!map || !libs) return;
    const ranked = rankSites(shown, latest);
    const byId = new Map(ranked.map((s) => [s.site.site_id, s]));
    const groups = siteId
      ? ranked.map((s) => ({ ids: [s.site.site_id], ...s.site.location }))
      : clusterPoints(ranked.map((s) => ({ id: s.site.site_id, ...s.site.location })), groupZoom, compact ? MARKER_BOX_COMPACT : MARKER_BOX);
    const cleanups: (() => void)[] = [];

    for (const group of groups) {
      const members = group.ids.map((id) => byId.get(id)!);
      const lead = members[0]; // ranked order: the worst site leads its group
      if (members.length === 1) {
        const { site, band, worstDelay } = lead;
        const text = worstDelay === null ? BANDS.none.label : formatDelay(worstDelay);
        const { marker, remove } = reactMarker(libs, map, site.location, `${site.name}: ${BANDS[band].label}, ${text}`, <MapMarker band={band} text={text} compact={compact} />);
        const model = buildSitePopup(site, latest);
        marker.addEventListener("pointerenter", hoverOnly(() => popup.hover(site.location, <SitePopup model={model} />, MARKER_CARD_LIFT_PX)));
        marker.addEventListener("pointerleave", popup.hideSoon);
        // Where a click does not navigate (the site map) a tap pins the card, as on the legs.
        marker.addEventListener("gmp-click", () =>
          clickable
            ? select.current?.(site.site_id)
            : popup.togglePin(marker, site.location, (onClose) => <SitePopup model={model} onClose={onClose} />, MARKER_CARD_LIFT_PX),
        );
        cleanups.push(remove);
      } else {
        const names = members.map((m) => m.site.name);
        const title = `${members.length} sites, worst ${BANDS[lead.band].label}: ${names.join(", ")}`;
        const { marker, remove } = reactMarker(
          libs,
          map,
          { lat: group.lat, lng: group.lng },
          title,
          <MapMarker band={lead.band} text={compact ? String(members.length) : `${members.length} sites`} group compact={compact} />,
        );
        const model = buildGroupPopup(members);
        const at = { lat: group.lat, lng: group.lng };
        marker.addEventListener("pointerenter", hoverOnly(() => popup.hover(at, <GroupPopup model={model} />, MARKER_CARD_LIFT_PX)));
        marker.addEventListener("pointerleave", popup.hideSoon);
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
  }, [map, libs, shown, latest, clickable, siteId, groupZoom, popup, compact, fitPadding]);

  return (
    <>
      {error && (
        <div className="map-error" role="alert">
          {error}
        </div>
      )}
      <div ref={el} className="map-canvas" />
      {legendEl && createPortal(<Legend sites={shown} latest={latest} compact={!!siteId} />, legendEl)}
    </>
  );
}
