import { ReactElement, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { BANDS, CHART_INK } from "../theme/palette";
import { LatestLeg, Site } from "./api";
import { boundsOf, formatDelay, formatSpeed, legColor, legLabel, lineToPath, sitePoints } from "./bands";
import { loadMaps } from "./maps";
import { MapMarker } from "./MapMarker";
import { clusterPoints, rankSites } from "./severity";

type Libs = Awaited<ReturnType<typeof loadMaps>>;

/** Initial zoom (Indonesia) until the fit below runs. */
const START = { center: { lat: -2.5, lng: 118 }, zoom: 5 };

function infoContent(title: string, lines: string[]): HTMLElement {
  const root = document.createElement("div");
  root.className = "map-info";
  const strong = document.createElement("strong");
  strong.textContent = title;
  root.append(strong);
  for (const line of lines) {
    const div = document.createElement("div");
    div.textContent = line;
    root.append(div);
  }
  return root;
}

function legLines(site: Site, latest: Map<string, LatestLeg>): string[] {
  return site.legs.map((leg) => {
    const row = latest.get(leg.selected_route_id);
    return `${legLabel(leg.leg)}: delay ${formatDelay(row?.delay_s)}, speed ${formatSpeed(row?.speed_kmh)}`;
  });
}

/** A marker whose content is a small React tree; returns its cleanup. */
function reactMarker(
  libs: Libs,
  map: google.maps.Map,
  position: google.maps.LatLngLiteral,
  title: string,
  body: ReactElement,
  clickable: boolean,
): { marker: google.maps.marker.AdvancedMarkerElement; remove: () => void } {
  const el = document.createElement("div");
  const root = createRoot(el);
  root.render(body);
  const marker = new libs.marker.AdvancedMarkerElement({ map, position, title, content: el, gmpClickable: clickable });
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
  const [zoom, setZoom] = useState(START.zoom);
  const [error, setError] = useState("");

  const shown = useMemo(() => (siteId ? sites.filter((s) => s.site_id === siteId) : sites), [sites, siteId]);
  // Handlers read the callback through a ref so a new function identity does not redraw the overlays.
  const select = useRef(onSelectSite);
  select.current = onSelectSite;
  const clickable = !!onSelectSite;

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
        });
        m.addListener("zoom_changed", () => setZoom(Math.round(m.getZoom() ?? START.zoom)));
        setLibs(l);
        setMap(m);
      })
      .catch((e) => !cancelled && setError(`The map could not load: ${String(e)}`));
    return () => {
      cancelled = true;
    };
  }, []);

  // Fit when the set of shown sites changes, not on every traffic refresh (that would undo the user's panning).
  useEffect(() => {
    const bounds = boundsOf(sitePoints(shown));
    if (map && bounds) map.fitBounds(bounds, 48);
  }, [map, shown]);

  // Legs: a light casing under each coloured line so it holds against any basemap; redraw on new data.
  useEffect(() => {
    if (!map || !libs) return;
    const info = new libs.maps.InfoWindow();
    const cleanups: (() => void)[] = [];
    for (const site of shown) {
      for (const leg of site.legs) {
        const path = lineToPath(leg.expected_polyline);
        if (path.length < 2) continue;
        const row = latest.get(leg.selected_route_id);
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
          info.setContent(
            infoContent(`${site.name} · ${legLabel(leg.leg)}`, [`Delay: ${formatDelay(row?.delay_s)}`, `Speed: ${formatSpeed(row?.speed_kmh)}`]),
          );
          if (e.latLng) info.setPosition(e.latLng);
          info.open({ map });
        });
        line.addListener("mouseout", () => {
          line.setOptions({ strokeWeight: 6 });
          casing.setOptions({ strokeWeight: 10 });
          info.close();
        });
        if (clickable) line.addListener("click", () => select.current?.(site.site_id));
        cleanups.push(() => {
          line.setMap(null);
          casing.setMap(null);
        });
      }
    }
    return () => {
      info.close();
      cleanups.forEach((fn) => fn());
    };
  }, [map, libs, shown, latest, clickable]);

  // Markers: one per site showing its worst band and delay; on the overview, sites that would overlap at
  // this zoom share one group marker (its worst member's band) that zooms in on click.
  useEffect(() => {
    if (!map || !libs) return;
    const info = new libs.maps.InfoWindow();
    const ranked = rankSites(shown, latest);
    const byId = new Map(ranked.map((s) => [s.site.site_id, s]));
    const groups = siteId
      ? ranked.map((s) => ({ ids: [s.site.site_id], ...s.site.location }))
      : clusterPoints(ranked.map((s) => ({ id: s.site.site_id, ...s.site.location })), zoom);
    const cleanups: (() => void)[] = [];

    for (const group of groups) {
      const members = group.ids.map((id) => byId.get(id)!);
      const lead = members[0]; // ranked order: the worst site leads its group
      if (members.length === 1) {
        const { site, band, worstDelay } = lead;
        const text = worstDelay === null ? BANDS.none.label : formatDelay(worstDelay);
        const { marker, remove } = reactMarker(libs, map, site.location, `${site.name}: ${BANDS[band].label}, ${text}`, <MapMarker band={band} text={text} />, clickable);
        marker.addEventListener("pointerenter", () => {
          info.setContent(infoContent(site.name, [site.city ?? "", ...legLines(site, latest)].filter(Boolean)));
          info.open({ map, anchor: marker });
        });
        marker.addEventListener("pointerleave", () => info.close());
        if (clickable) marker.addEventListener("gmp-click", () => select.current?.(site.site_id));
        cleanups.push(remove);
      } else {
        const names = members.map((m) => m.site.name);
        const title = `${members.length} sites, worst ${BANDS[lead.band].label}: ${names.join(", ")}`;
        const { marker, remove } = reactMarker(
          libs,
          map,
          { lat: group.lat, lng: group.lng },
          title,
          <MapMarker band={lead.band} text={`${members.length} sites`} group />,
          true,
        );
        marker.addEventListener("pointerenter", () => {
          info.setContent(infoContent(`${members.length} sites`, members.map((m) => `${m.site.name}: ${m.worstDelay === null ? BANDS.none.label : formatDelay(m.worstDelay)}`)));
          info.open({ map, anchor: marker });
        });
        marker.addEventListener("pointerleave", () => info.close());
        marker.addEventListener("gmp-click", () => {
          const bounds = boundsOf(sitePoints(members.map((m) => m.site)));
          if (bounds) map.fitBounds(bounds, 64);
        });
        cleanups.push(remove);
      }
    }
    return () => {
      info.close();
      cleanups.forEach((fn) => fn());
    };
  }, [map, libs, shown, latest, clickable, siteId, zoom]);

  return (
    <>
      {error && (
        <div className="map-error" role="alert">
          {error}
        </div>
      )}
      <div ref={el} className="map-canvas" />
    </>
  );
}
