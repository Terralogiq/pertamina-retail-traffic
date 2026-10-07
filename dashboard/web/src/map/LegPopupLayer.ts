import type { ReactElement } from "react";
import { flushSync } from "react-dom";
import { createRoot } from "react-dom/client";

/** Gap between the hovered point and the card, and the margin kept to the map edge. They mirror --space-3 and --space-2. */
const GAP_PX = 12;
const EDGE_PX = 8;

export interface ShowOptions {
  /** Extra room above the point for a marker pill. When the card flips below the point it is not needed: the pill is above. */
  liftPx?: number;
  /** Announce the card to screen readers (a pinned card; hover cards stay silent). */
  live?: boolean;
}

/**
 * Offset of the card from its anchor point, in px, given the point's position in the map container, the card size
 * and the container width. Above the point (and above a marker pill of `lift` px) when it fits; else just below
 * the point, which clears the pill because the pill sits above it. Horizontally centred, then clamped inside the
 * map with the left edge winning when the card is wider than the map.
 */
export function placeCard(box: { x: number; y: number }, w: number, h: number, lift: number, mapWidth: number): { dx: number; dy: number } {
  const above = box.y - h - GAP_PX - lift >= EDGE_PX;
  return {
    dx: Math.max(EDGE_PX - box.x, Math.min(-w / 2, mapWidth - EDGE_PX - w - box.x)),
    dy: above ? -(h + GAP_PX + lift) : GAP_PX,
  };
}

export interface LegPopupLayer {
  show(at: google.maps.LatLngLiteral, body: ReactElement, options?: ShowOptions): void;
  hide(): void;
  destroy(): void;
}

/**
 * One React-rendered card on the map's float pane, anchored at a lat/lng. Chosen over InfoWindow because
 * the default InfoWindow always draws its own header row, close button and tail, which cannot be removed
 * cleanly; an overlay is plain DOM under our CSS. It sits above the point, flips below near the top edge
 * and is clamped inside the map horizontally (a 360 px map is narrower than a long site name).
 */
export function createLegPopupLayer(maps: google.maps.MapsLibrary, map: google.maps.Map): LegPopupLayer {
  const el = document.createElement("div");
  el.className = "leg-popup-anchor";
  el.hidden = true;
  const root = createRoot(el);
  let at: google.maps.LatLngLiteral | null = null;
  let lift = 0;

  class Overlay extends maps.OverlayView {
    onAdd() {
      this.getPanes()!.floatPane.appendChild(el);
      // A pinned card is clickable: keep its clicks and drags from reaching the map (which would close it or pan).
      maps.OverlayView.preventMapHitsAndGesturesFrom(el);
    }
    onRemove() {
      el.remove();
    }
    draw() {
      const projection = this.getProjection();
      const card = el.firstElementChild as HTMLElement | null;
      if (!projection || !at || !card) return;
      const point = new google.maps.LatLng(at);
      const div = projection.fromLatLngToDivPixel(point)!;
      const box = projection.fromLatLngToContainerPixel(point)!;
      el.style.left = `${div.x}px`;
      el.style.top = `${div.y}px`;
      const { offsetWidth: w, offsetHeight: h } = card;
      const { dx, dy } = placeCard(box, w, h, lift, map.getDiv().clientWidth);
      card.style.transform = `translate(${dx}px, ${dy}px)`;
    }
  }
  const overlay = new Overlay();
  overlay.setMap(map);

  return {
    show(position, body, { liftPx = 0, live = false } = {}) {
      at = position;
      lift = liftPx;
      if (live) el.setAttribute("aria-live", "polite");
      else el.removeAttribute("aria-live");
      flushSync(() => root.render(body));
      el.hidden = false;
      overlay.draw();
    },
    hide() {
      at = null;
      el.hidden = true;
      el.removeAttribute("aria-live");
      root.render(null);
    },
    destroy() {
      overlay.setMap(null);
      // Unmount after the current render pass; unmounting a root synchronously inside an effect cleanup warns.
      setTimeout(() => root.unmount());
    },
  };
}
