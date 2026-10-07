import { useEffect, useMemo, useRef, useState } from "react";
import { LatestLeg, Site } from "./api";
import { boundsOf, formatDelay, formatSpeed, legColor, legLabel, lineToPath, sitePoints } from "./bands";
import { loadMaps } from "./maps";

type Libs = Awaited<ReturnType<typeof loadMaps>>;

// AdvancedMarkerElement needs a mapId; DEMO_MAP_ID is Google's placeholder for development and demos.
const DEMO_MAP_ID = "DEMO_MAP_ID";

function infoContent(title: string, lines: string[]): HTMLElement {
  const root = document.createElement("div");
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

interface Props {
  sites: Site[];
  latest: Map<string, LatestLeg>;
  /** Overview shows every site and navigates on click; the site map passes one site's id and does not navigate. */
  siteId?: string;
  onSelectSite?: (siteId: string) => void;
}

export default function TrafficMap({ sites, latest, siteId, onSelectSite }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const [libs, setLibs] = useState<Libs | null>(null);
  const [map, setMap] = useState<google.maps.Map | null>(null);
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
        setLibs(l);
        // Centre of Indonesia until the fit below runs.
        setMap(
          new l.maps.Map(el.current!, {
            center: { lat: -2.5, lng: 118 },
            zoom: 5,
            mapId: DEMO_MAP_ID,
            mapTypeControl: false,
            streetViewControl: false,
          }),
        );
      })
      .catch((e) => !cancelled && setError(String(e)));
    return () => {
      cancelled = true;
    };
  }, []);

  // Fit when the set of shown sites changes, not on every traffic refresh (that would undo the user's panning).
  useEffect(() => {
    const bounds = boundsOf(sitePoints(shown));
    if (map && bounds) map.fitBounds(bounds, 48);
  }, [map, shown]);

  // Draw markers and legs; redraw on new data.
  useEffect(() => {
    if (!map || !libs) return;
    const info = new libs.maps.InfoWindow();
    const cleanups: (() => void)[] = [];

    for (const site of shown) {
      const pin = new libs.marker.PinElement({ background: "#1565c0", borderColor: "#0d47a1", glyphColor: "#fff" });
      const marker = new libs.marker.AdvancedMarkerElement({
        map,
        position: site.location,
        title: site.name,
        content: pin,
        gmpClickable: clickable,
      });
      const showSite = () => {
        info.setContent(infoContent(site.name, [site.city ?? "", ...legLines(site, latest)].filter(Boolean)));
        info.open({ map, anchor: marker });
      };
      marker.addEventListener("pointerenter", showSite);
      marker.addEventListener("pointerleave", () => info.close());
      if (clickable) marker.addEventListener("gmp-click", () => select.current?.(site.site_id));
      cleanups.push(() => (marker.map = null));

      for (const leg of site.legs) {
        const path = lineToPath(leg.expected_polyline);
        if (path.length < 2) continue;
        const row = latest.get(leg.selected_route_id);
        const { color } = legColor(row);
        const line = new libs.maps.Polyline({
          map,
          path,
          strokeColor: color,
          strokeOpacity: 0.9,
          strokeWeight: 6,
          clickable: true,
          // Arrow at the midpoint: the polyline runs in travel direction (approach towards the SPBU, departure away).
          icons: [
            {
              icon: { path: libs.core.SymbolPath.FORWARD_CLOSED_ARROW, scale: 2, strokeColor: "#fff", fillColor: color, fillOpacity: 1 },
              offset: "50%",
            },
          ],
        });
        line.addListener("mouseover", (e: google.maps.PolyMouseEvent) => {
          line.setOptions({ strokeWeight: 9 });
          info.setContent(
            infoContent(`${site.name} · ${legLabel(leg.leg)}`, [
              `Delay: ${formatDelay(row?.delay_s)}`,
              `Speed: ${formatSpeed(row?.speed_kmh)}`,
            ]),
          );
          if (e.latLng) info.setPosition(e.latLng);
          info.open({ map });
        });
        line.addListener("mouseout", () => {
          line.setOptions({ strokeWeight: 6 });
          info.close();
        });
        if (clickable) line.addListener("click", () => select.current?.(site.site_id));
        cleanups.push(() => line.setMap(null));
      }
    }

    return () => {
      info.close();
      cleanups.forEach((fn) => fn());
    };
  }, [map, libs, shown, latest, clickable]);

  return (
    <>
      {error && <div role="alert">{error}</div>}
      <div ref={el} style={{ width: "100%", height: "100%", minHeight: 240 }} />
    </>
  );
}
