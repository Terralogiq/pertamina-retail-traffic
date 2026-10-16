import type { ReactElement } from "react";
import { useEffect, useRef } from "react";
import { createLegPopupLayer, LegPopupLayer } from "./LegPopupLayer";

/** How long a card stays after the pointer leaves what opened it, so crossing a gap between two legs does not flicker. */
export const HIDE_DELAY_MS = 150;

export interface MapPopup {
  /** Hover card. `liftPx` raises it above a marker pill that sits over the point. Ignored while a card is pinned. */
  hover(at: google.maps.LatLngLiteral, body: ReactElement, liftPx?: number): void;
  /** Hide shortly, unless a card is pinned. */
  hideSoon(): void;
  hide(): void;
  /** Pin the card for `owner` (touch, or a click where a click does not select a site); a second call for the same owner closes it. */
  togglePin(owner: unknown, at: google.maps.LatLngLiteral, body: (onClose: () => void) => ReactElement, liftPx?: number): void;
  /**
   * Close on Escape and on a click on the map. The returned cleanup clears the timer and the pin, removes the
   * listeners and calls `destroy`.
   */
  bind(doc: Pick<Document, "addEventListener" | "removeEventListener">, map: Pick<google.maps.Map, "addListener">, destroy: () => void): () => void;
}

/** The popup's behaviour, apart from React and Google Maps: `getLayer` is null until the layer exists. */
export function createMapPopup(getLayer: () => LegPopupLayer | null): MapPopup {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let pinned: unknown = null;
  const popup: MapPopup = {
    hover(at, body, liftPx) {
      clearTimeout(timer);
      if (!pinned) getLayer()?.show(at, body, { liftPx });
    },
    hideSoon() {
      clearTimeout(timer);
      if (!pinned) timer = setTimeout(popup.hide, HIDE_DELAY_MS);
    },
    hide() {
      clearTimeout(timer);
      pinned = null;
      getLayer()?.hide();
    },
    togglePin(owner, at, body, liftPx) {
      clearTimeout(timer);
      if (pinned === owner) return popup.hide();
      pinned = owner;
      getLayer()?.show(at, body(popup.hide), { liftPx, live: true });
    },
    bind(doc, map, destroy) {
      const onKey = (e: Event) => (e as KeyboardEvent).key === "Escape" && popup.hide();
      doc.addEventListener("keydown", onKey);
      const mapClick = map.addListener("click", popup.hide);
      return () => {
        clearTimeout(timer);
        pinned = null;
        doc.removeEventListener("keydown", onKey);
        mapClick.remove();
        destroy();
      };
    },
  };
  return popup;
}

/**
 * The map's single card (one overlay layer), shared by legs and markers so two cards never stack.
 * The returned object is stable across renders.
 */
export function useMapPopup(map: google.maps.Map | null, libs: { maps: google.maps.MapsLibrary } | null): MapPopup {
  const layer = useRef<LegPopupLayer | null>(null);
  const popup = useRef<MapPopup>(null as unknown as MapPopup);
  popup.current ??= createMapPopup(() => layer.current);

  useEffect(() => {
    if (!map || !libs) return;
    const created = createLegPopupLayer(libs.maps, map);
    layer.current = created;
    return popup.current.bind(document, map, () => {
      layer.current = null;
      created.destroy();
    });
  }, [map, libs]);

  return popup.current;
}
