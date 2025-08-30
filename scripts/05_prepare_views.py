"""
Prepare flat CSVs for Power BI (no GDAL).
Creates:
  - output/pbi_sa1_points_per_school.csv   (SA1 centroids + school + walk_time + flags)
  - output/pbi_sa1_points_kpis.csv         (SA1-level coverage % across schools)
  - output/pbi_stops.csv                   (all school-special stops as points)
  - output/pbi_candidate_stops.csv         (optional; only if quick-wins run)
"""
import sys, os
from pathlib import Path
import pandas as pd
import geopandas as gpd

# allow "from src..." imports when run directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.geojson_io import gdf_from_geojson_bytes

ROOT = Path(".")
OUT = ROOT / "output"
MAN = ROOT / "data" / "manual"
RAW = ROOT / "data" / "raw"
OUT.mkdir(parents=True, exist_ok=True)

# Inputs
sa1_centroids_csv = MAN / "sa1_centroids.csv"
walk_csv = OUT / "sa1_school_walktimes.csv"
kpi_sa1_csv = OUT / "sa1_school_kpis.csv"
stops_geojson = OUT / "stops_schoolspecials.geojson"
cand_geojson = OUT / "candidate_new_stops.geojson"

def main():
    if not sa1_centroids_csv.exists():
        raise SystemExit("Missing data/manual/sa1_centroids.csv (run 00_fetch_act_sa1_centroids.py).")
    if not walk_csv.exists():
        raise SystemExit("Missing output/sa1_school_walktimes.csv (run 02_build_graph.py).")
    if not kpi_sa1_csv.exists():
        raise SystemExit("Missing output/sa1_school_kpis.csv (run 03_compute_kpis.py).")
    if not stops_geojson.exists():
        raise SystemExit("Missing output/stops_schoolspecials.geojson (run 02_build_graph.py).")

    # SA1 centroids
    c = pd.read_csv(sa1_centroids_csv)  # sa1_code_2021, lon, lat
    if not {"sa1_code_2021","lon","lat"}.issubset(c.columns):
        raise SystemExit("Centroids CSV must have columns: sa1_code_2021, lon, lat")

    # Per-pair walk times -> per-school points
    w = pd.read_csv(walk_csv)  # sa1_code_2021, school, walk_time_sec
    w["walk_time_min"] = w["walk_time_sec"] / 60.0
    for thr in (10, 15, 20):
        w[f"within_{thr}_min"] = (w["walk_time_min"] <= thr).astype(int)
    pbi_sa1_school = w.merge(c, on="sa1_code_2021", how="left")
    pbi_sa1_school.to_csv(OUT / "pbi_sa1_points_per_school.csv", index=False)

    # SA1-level KPIs (already aggregated)
    k = pd.read_csv(kpi_sa1_csv)  # includes pct_within_10_min etc.
    k = k.merge(c, on="sa1_code_2021", how="left")
    k.to_csv(OUT / "pbi_sa1_points_kpis.csv", index=False)

    # Stops as points
    g_stops = gdf_from_geojson_bytes(stops_geojson.read_bytes())
    g_stops["lon"] = g_stops.geometry.x
    g_stops["lat"]  = g_stops.geometry.y
    keep_cols = [c for c in ["stop_id","stop_name","matched_school","confidence"] if c in g_stops.columns]
    pd.DataFrame(g_stops[keep_cols + ["lon","lat"]]).to_csv(OUT / "pbi_stops.csv", index=False)

    # Candidate stops (if available)
    if cand_geojson.exists():
        g_cand = gdf_from_geojson_bytes(cand_geojson.read_bytes())
        g_cand["lon"] = g_cand.geometry.x
        g_cand["lat"]  = g_cand.geometry.y
        cols = [c for c in ["reason"] if c in g_cand.columns]
        pd.DataFrame(g_cand[cols + ["lon","lat"]]).to_csv(OUT / "pbi_candidate_stops.csv", index=False)

    print("Wrote:")
    for f in ["pbi_sa1_points_per_school.csv","pbi_sa1_points_kpis.csv","pbi_stops.csv","pbi_candidate_stops.csv"]:
        p = OUT / f
        if p.exists():
            print("  -", p)

if __name__ == "__main__":
    main()