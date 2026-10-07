import { LatestLeg, Site } from "./api";
import { Basis, CONGESTION_BANDS, GREY, SPEED_BANDS, legColor } from "./bands";

function Bands({ title, bands }: { title: string; bands: { color: string; label: string }[] }) {
  return (
    <span style={{ marginRight: 16 }}>
      <strong>{title}</strong>{" "}
      {bands.map((b) => (
        <span key={b.label} style={{ marginRight: 8 }}>
          <span style={{ display: "inline-block", width: 12, height: 12, background: b.color, verticalAlign: "middle" }} /> {b.label}
        </span>
      ))}
    </span>
  );
}

/** Shows the bands in use: congestion index where the baseline is full, speed where it is still building, grey for no data. */
export default function Legend({ sites, latest }: { sites: Site[]; latest: Map<string, LatestLeg> }) {
  const bases = new Set<Basis>(sites.flatMap((s) => s.legs.map((l) => legColor(latest.get(l.selected_route_id)).basis)));
  return (
    <div style={{ padding: "6px 16px", fontSize: 13 }}>
      {bases.has("congestion") && <Bands title="Congestion index" bands={CONGESTION_BANDS} />}
      {bases.has("speed") && <Bands title="Speed (baseline building)" bands={SPEED_BANDS} />}
      {bases.has("none") && <Bands title="No data" bands={[{ color: GREY, label: "grey" }]} />}
    </div>
  );
}
