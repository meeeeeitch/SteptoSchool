# scripts/00_fetch_act_sa1_centroids.py
"""
Fetch ACT-only SA1 (ASGS 2021) centroids from ABS ArcGIS REST and save CSV.
Robust to MultiPoint geometry and server pagination. No GeoPandas/GDAL required.
"""
from pathlib import Path
import requests, json, csv, sys, time

MAN = Path("data/manual")
MAN.mkdir(parents=True, exist_ok=True)

BASE = "https://geo.abs.gov.au/arcgis/rest/services/ASGS2021/SA1/MapServer/2/query"
PARAMS = {
    "where": "state_code_2021='8'",         # ACT
    "outFields": "sa1_code_2021,state_code_2021",
    "returnGeometry": "true",
    "outSR": "4326",
    "f": "geojson",
    "resultRecordCount": "2000",            # server max
    # we'll add resultOffset incrementally
}

def fetch_chunk(offset: int):
    params = PARAMS.copy()
    params["resultOffset"] = str(offset)
    r = requests.get(BASE, params=params, headers={"Accept":"application/json"}, timeout=120)
    r.raise_for_status()
    try:
        return r.json()
    except Exception:
        # Show some of the response for debugging
        txt = r.text[:300]
        raise RuntimeError(f"ABS returned non-JSON. First 300 chars:\n{txt}")

def main():
    out_geojson = MAN / "sa1_centroids_act.geojson"
    out_csv     = MAN / "sa1_centroids.csv"

    print("Downloading ACT SA1 centroids (ABS, layer 2 SA1_PT)...")
    all_feats = []
    offset = 0
    while True:
        js = fetch_chunk(offset)
        feats = js.get("features") or []
        if not feats:
            break
        all_feats.extend(feats)
        if len(feats) < int(PARAMS["resultRecordCount"]):
            break
        offset += len(feats)
        time.sleep(0.2)  # be polite

    if not all_feats:
        print("No features returned. Check the service or try again later.")
        sys.exit(1)

    # Save raw GeoJSON for reference
    out_geojson.write_text(json.dumps({"type":"FeatureCollection","features":all_feats}), encoding="utf-8")

    print("Converting to CSV (handles MultiPoint/Point)...")
    kept, skipped = 0, 0
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sa1_code_2021","lon","lat"])
        for ft in all_feats:
            props = (ft.get("properties") or {})
            geom  = (ft.get("geometry") or {})
            code  = props.get("sa1_code_2021")

            x = y = None
            coords = geom.get("coordinates")
            # GeoJSON Point: [x, y]
            if isinstance(coords, list) and len(coords) >= 2 and isinstance(coords[0], (int, float)):
                x, y = coords[0], coords[1]
            # GeoJSON MultiPoint: [[x, y], [x, y], ...]
            elif isinstance(coords, list) and coords and isinstance(coords[0], list) and len(coords[0]) >= 2:
                x, y = coords[0][0], coords[0][1]
            # ArcGIS JSON fallback (rare): {"x": .., "y": ..}
            elif isinstance(geom, dict) and "x" in geom and "y" in geom:
                x, y = geom["x"], geom["y"]

            if code and isinstance(x, (int, float)) and isinstance(y, (int, float)):
                w.writerow([code, x, y])
                kept += 1
            else:
                skipped += 1

    print(f"Wrote {out_csv}  (kept {kept}, skipped {skipped})")

if __name__ == "__main__":
    main()