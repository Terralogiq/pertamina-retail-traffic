// Shim for `legBand` until .9.4's version lands in src/map/bands.ts (contract item 4); after the merge, import it
// from there and delete this file. Same signature, built on the existing legColor so the two can't disagree.
import type { LatestLeg } from "../map/api";
import { Basis, legColor } from "../map/bands";
import { BANDS, BandId } from "../theme/palette";

export function legBand(latest: LatestLeg | undefined): { band: BandId; basis: Basis } {
  const { color, basis } = legColor(latest);
  const band = (Object.keys(BANDS) as BandId[]).find((id) => BANDS[id].color === color) ?? "none";
  return { band, basis };
}
