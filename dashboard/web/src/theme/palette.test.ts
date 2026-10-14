import { describe, expect, it, vi } from "vitest";
import { BANDS, SEQUENTIAL, SERIES, applyDataPalette } from "./palette";

describe("band colours", () => {
  it("uses the signed-off Google-familiar colours", () => {
    expect(BANDS.free.color).toBe("#1e8e3e");
    expect(BANDS.moderate.color).toBe("#f29900");
    expect(BANDS.heavy.color).toBe("#e8452c");
    expect(BANDS.jam.color).toBe("#9a1a1a");
  });
});

describe("applyDataPalette", () => {
  it("mirrors every band, series and sequential colour into a custom property", () => {
    const setProperty = vi.fn();
    applyDataPalette({ style: { setProperty } } as unknown as HTMLElement);
    const props = new Map<string, string>(setProperty.mock.calls.map(([k, v]) => [k, v]));
    for (const [id, band] of Object.entries(BANDS)) expect(props.get(`--band-${id}`), id).toBe(band.color);
    for (const [id, color] of Object.entries(SERIES)) expect(props.get(`--series-${id}`), id).toBe(color);
    SEQUENTIAL.forEach((color, i) => expect(props.get(`--seq-${i + 1}`)).toBe(color));
  });
});
