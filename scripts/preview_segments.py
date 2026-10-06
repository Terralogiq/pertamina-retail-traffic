#!/usr/bin/env python3
"""Write the segment preview map: out/segments/preview.html.

Reads data/routes.csv and out/segments/polylines.json (both written by
propose_segments.py). Makes no API calls. The Maps JS key is spliced into the
HTML, so the file is git-ignored (out/) and written with mode 600.

Usage: python3 scripts/preview_segments.py [--routes CSV] [--polylines JSON] [--out HTML]
The key comes from $MAPS_API_KEY or Secret Manager; it is never printed.
"""
import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import segments_lib as lib  # noqa: E402
from propose_segments import (  # noqa: E402
    OUT_DIR, POLYLINES_JSON, ROUTES_CSV, SITES_CSV, get_api_key, read_csv)

LEG_NAMES = {"approach": "Approach (Entry → Front)", "departure": "Departure (Front → Exit)"}

TEMPLATE = r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SPBU segments preview</title>
<style>
:root{--bg:#fff;--fg:#1a1a1a;--mut:#666;--line:#e3e3e3;--red:#d62728}
@media (prefers-color-scheme:dark){:root{--bg:#141414;--fg:#eee;--mut:#9a9a9a;--line:#2c2c2c;--red:#ff6b6b}}
body{margin:0;font:14px/1.4 system-ui,sans-serif;background:var(--bg);color:var(--fg);display:grid;grid-template-columns:400px 1fr;height:100vh}
#side{overflow:auto;padding:12px 16px;border-right:1px solid var(--line)}#map{height:100vh}
select{width:100%;padding:6px;margin:6px 0 10px}
.leg{padding:8px;border:1px solid var(--line);border-radius:6px;margin:6px 0;cursor:pointer}
.leg b.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px}
.leg.needs{border-color:var(--red);border-width:2px}
.mut{color:var(--mut);font-size:12px}.bad{color:var(--red);font-weight:600}
@media (max-width:700px){body{grid-template-columns:1fr;grid-template-rows:auto 60vh}#map{height:60vh}}
</style></head><body>
<div id="side"><h3 style="margin:4px 0">Segment preview</h3>
<div class="mut">Geometry and timings from Routes API (TRAFFIC_AWARE) at generation time. Entry = start point, Front = main road in front of the SPBU, Exit = end point.</div>
<select id="site"></select>
<div class="mut" style="margin-bottom:6px"><span style="color:#0b6e4f">●</span> SPBU side &nbsp; <span style="color:#6b4fbb">●</span> Opposite side &nbsp; <span style="color:var(--red)">●</span> needs_link (no validated points)</div>
<div id="list"></div></div><div id="map"></div>
<script>
const LEGS=__LEGS__, PTS=__PTS__, SITES=__SITES__;
const COL={approach:"#1f77b4",departure:"#17becf"};
const SIDE={spbu_side:"SPBU side",opposite:"Opposite side"};
let map, drawn=[];
function render(){
  drawn.forEach(o=>o.setMap(null)); drawn=[];
  const site=document.getElementById('site').value;
  const b=new google.maps.LatLngBounds(), list=document.getElementById('list'); list.innerHTML='';
  const sideNotes={};
  LEGS.filter(l=>l.site===site).forEach(l=>{
    const opp=l.side==='opposite', needs=l.status!=='ok';
    sideNotes[l.side]=l.note;
    let pl=null;
    if(l.path.length){
      const c=needs?'#d62728':COL[l.leg];
      pl=new google.maps.Polyline({path:l.path,map,strokeColor:c,strokeWeight:7,strokeOpacity:opp?0.55:0.95,
        icons:[{icon:{path:google.maps.SymbolPath.FORWARD_OPEN_ARROW,scale:2.5,strokeColor:c},offset:'0',repeat:'90px'}]});
      drawn.push(pl); l.path.forEach(p=>b.extend(p));
    }
    const bad=l.man.some(m=>/UTURN|RAMP|TURN/.test(m));
    const d=document.createElement('div'); d.className='leg'+(needs?' needs':'');
    const ratio=(l.dur!=null&&l.static)?(l.dur/l.static).toFixed(2):'–';
    d.innerHTML=`<b class="sw" style="background:${needs?'#d62728':COL[l.leg]}"></b><strong>${SIDE[l.side]} · ${l.name}</strong> <span class="${needs?'bad':'mut'}">[${l.status}]</span><br>`
      +(l.m!=null?`${l.m} m · now ${l.dur} s · no-traffic ${l.static} s · ratio ${ratio}<br><span class="mut ${bad?'bad':''}">maneuvers: ${l.man.join(', ')||'none'} · roads: ${l.roads.join(', ')||'–'}</span>`:`<span class="bad">no validated route</span>`);
    if(pl){d.onmouseenter=()=>pl.setOptions({strokeWeight:11}); d.onmouseleave=()=>pl.setOptions({strokeWeight:7});}
    list.appendChild(d);
  });
  Object.entries(sideNotes).forEach(([side,note])=>{
    const n=document.createElement('div'); n.className='mut'; n.style.margin='2px 0 8px';
    const fp=(LEGS.find(l=>l.site===site&&l.side===side)||{}).front_from_pin;
    n.textContent=`${SIDE[side]}: ${fp!=null?'Front '+Math.round(fp)+' m from the Places pin. ':''}${note||''}`;
    list.appendChild(n);
  });
  PTS.filter(p=>p.site===site).forEach(p=>{
    const fill=p.status!=='ok'?'#d62728':(p.side==='opposite'?'#6b4fbb':'#0b6e4f');
    drawn.push(new google.maps.Marker({position:p,map,label:{text:p.label,color:'#fff',fontWeight:'700',fontSize:'11px'},icon:{path:google.maps.SymbolPath.CIRCLE,scale:22,fillColor:fill,fillOpacity:0.95,strokeColor:'#fff',strokeWeight:2},title:`${SIDE[p.side]} · ${p.label}: ${p.lat.toFixed(7)}, ${p.lng.toFixed(7)} · heading ${p.heading}`}));
    b.extend(p);
  });
  if(!b.isEmpty()) map.fitBounds(b,40);
}
function initMap(){
  map=new google.maps.Map(document.getElementById('map'),{mapTypeId:'hybrid',tilt:0,center:{lat:-2.5,lng:118},zoom:5});
  const sel=document.getElementById('site'); SITES.forEach(s=>sel.add(new Option(s.label,s.key)));
  sel.onchange=render; render();
}
</script>
<script async src="https://maps.googleapis.com/maps/api/js?key=__KEY__&callback=initMap"></script>
</body></html>
"""


def js(obj):
    """JSON safe to embed in a <script> block."""
    return json.dumps(obj).replace("</", "<\\/")


def build(rows, polylines, sites):
    """Return (legs, points, sites_for_select) for the template."""
    by_no = {s["site_no"]: s for s in sites}
    legs, points, site_list, seen = [], [], [], set()
    for r in rows:
        site = by_no.get(r["site_no"], {})
        key = f"{r['site_no']} · SPBU {r['site_id']}"
        if r["site_no"] not in seen:
            seen.add(r["site_no"])
            site_list.append({"key": key, "site_no": r["site_no"],
                              "label": f"{key} · {site.get('road', '')} ({site.get('city', '')})"})
        pl = polylines.get(r["selected_route_id"], {})
        path = [{"lat": a, "lng": b} for a, b in lib.decode_polyline(pl.get("polyline", ""))]
        legs.append({"site": key, "side": r["side"], "leg": r["leg"], "name": LEG_NAMES[r["leg"]],
                     "status": r["status"], "note": r["note"], "front_from_pin": pl.get("front_from_pin_m"),
                     "m": pl.get("distance_m"), "dur": pl.get("duration_s"), "static": pl.get("static_s"),
                     "man": pl.get("maneuvers") or [], "roads": pl.get("roads") or [], "path": path})
        if r["origin_lat"]:
            pts = ([("Entry", "origin")] if r["leg"] == "approach" else []) + [
                ("Front" if r["leg"] == "approach" else "Exit", "dest")]
            for label, k in pts:
                points.append({"site": key, "side": r["side"], "label": label, "status": r["status"],
                               "lat": float(r[k + "_lat"]), "lng": float(r[k + "_lng"]),
                               "heading": r[k + "_heading"]})
    # A site is flagged in the selector if any of its sides needs a link.
    flagged = {r["site_no"] for r in rows if r["status"] != "ok"}
    for s in site_list:
        s["label"] = ("⚠ " if s.pop("site_no") in flagged else "") + s["label"]
    return legs, points, site_list


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--routes", default=ROUTES_CSV)
    ap.add_argument("--polylines", default=POLYLINES_JSON)
    ap.add_argument("--out", default=os.path.join(OUT_DIR, "preview.html"))
    args = ap.parse_args()
    rows = read_csv(args.routes)
    if not rows or not os.path.exists(args.polylines):
        sys.exit("run scripts/propose_segments.py first (routes.csv or polylines.json missing)")
    with open(args.polylines) as f:
        polylines = json.load(f)
    legs, points, site_list = build(rows, polylines, read_csv(SITES_CSV))
    html = (TEMPLATE.replace("__LEGS__", js(legs)).replace("__PTS__", js(points))
            .replace("__SITES__", js(site_list)).replace("__KEY__", get_api_key()))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(html)
    os.chmod(args.out, 0o600)
    bad = sum(1 for r in rows if r["status"] != "ok") // 2
    print(f"{len(legs)} legs, {len(site_list)} sites, {bad} sides needing a link -> {args.out}")


if __name__ == "__main__":
    main()
