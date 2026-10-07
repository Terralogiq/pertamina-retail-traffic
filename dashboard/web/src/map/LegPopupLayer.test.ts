import { describe, expect, it } from "vitest";
import { placeCard } from "./LegPopupLayer";

// Mirrors of the layer's GAP_PX (12) and EDGE_PX (8).
const GAP = 12;
const EDGE = 8;
const W = 200;
const H = 100;
const MAP_W = 400;

describe("placeCard", () => {
  it("centres the card above the point when it fits", () => {
    expect(placeCard({ x: 200, y: 300 }, W, H, 0, MAP_W)).toEqual({ dx: -100, dy: -(H + GAP) });
  });

  it("raises the card by the marker lift", () => {
    expect(placeCard({ x: 200, y: 300 }, W, H, 48, MAP_W).dy).toBe(-(H + GAP + 48));
  });

  it("flips below the point when there is no room above, clear of the pill that sits above the point", () => {
    const lift = 48;
    // 150 - 100 - 12 - 48 < 8: fits only without the lift, so it must flip.
    const { dy } = placeCard({ x: 200, y: 150 }, W, H, lift, MAP_W);
    expect(dy).toBe(GAP);
    expect(dy).toBeGreaterThanOrEqual(0); // card top is at or below the point; the pill occupies [y - lift, y]
    expect(placeCard({ x: 200, y: 50 }, W, H, 0, MAP_W).dy).toBe(GAP);
  });

  it("keeps the card above at exactly the edge margin", () => {
    expect(placeCard({ x: 200, y: H + GAP + EDGE }, W, H, 0, MAP_W).dy).toBe(-(H + GAP));
    expect(placeCard({ x: 200, y: H + GAP + EDGE - 1 }, W, H, 0, MAP_W).dy).toBe(GAP);
  });

  it("clamps to the left edge", () => {
    const { dx } = placeCard({ x: 20, y: 300 }, W, H, 0, MAP_W);
    expect(20 + dx).toBe(EDGE);
  });

  it("clamps to the right edge", () => {
    const { dx } = placeCard({ x: 380, y: 300 }, W, H, 0, MAP_W);
    expect(380 + dx + W).toBe(MAP_W - EDGE);
  });

  it("keeps the left edge visible when the card is wider than the map", () => {
    const { dx } = placeCard({ x: 180, y: 300 }, 500, H, 0, 360);
    expect(180 + dx).toBe(EDGE);
  });
});
