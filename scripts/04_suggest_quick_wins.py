import sys, os, argparse
from pathlib import Path
import pandas as pd
import geopandas as gpd

# make src importable no matter where you run from
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.optimise_stops import greedy_new_stop_candidates
from src.geojson_io import gdf_from_geojson_bytes, gdf_to_geojson_bytes

OUT = Path("output")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold-min", type=int, default=10)
    ap.add_argument("--max-new-stops", type=int, default=10)
    ap.add_argument("--sa1-centroids-csv", default="data/manual/sa1_centroids.csv")
    args = ap.parse_args()

    # 1) KPIs
    sa1_kpis_path = OUT / "sa1_school_kpis.csv"
    if not sa1_kpis_path.exists():
        raise SystemExit("Missing output/sa1_school_kpis.csv — run scripts/03_compute_kpis.py first.")
    sa1_kpis = pd.read_csv(sa1_kpis_path)

    # 2) SA1 centroids (CSV expected: sa1_code_2021, lon, lat)
    if not Path(args.sa1_centroids_csv).exists():
        raise SystemExit("This step requires SA1 centroids CSV. Provide data/manual/sa1_centroids.csv "
                         "with columns: sa1_code_2021, lon, lat.")
    c = pd.read_csv(args.sa1_centroids_csv)
    required = {"sa1_code_2021", "lon", "lat"}
    if not required.issubset(c.columns):
        raise SystemExit(f"Centroids CSV missing columns {required}. Found: {list(c.columns)}")
    sa1_points = gpd.GeoDataFrame(
        c, geometry=gpd.points_from_xy(c["lon"], c["lat"]), crs="EPSG:4326"
    )

    # 3) Stops (produced by 02_build_graph.py)
    stops_path = OUT / "stops_schoolspecials.geojson"
    if not stops_path.exists():
        raise SystemExit("Missing output/stops_schoolspecials.geojson — run scripts/02_build_graph.py first.")
    stops = gdf_from_geojson_bytes(stops_path.read_bytes())  # GeoDataFrame, EPSG:4326

    # 4) Heuristic placement
    cand = greedy_new_stop_candidates(
        sa1_kpis, sa1_points, stops,
        threshold_min=args.threshold_min,
        max_new_stops=args.max_new_stops
    )

    # 5) Save GeoJSON (pure writer)
    out_path = OUT / "candidate_new_stops.geojson"
    out_path.write_bytes(gdf_to_geojson_bytes(cand.to_crs(4326)))
    print(f"Wrote {out_path}  (n={len(cand)})")

if __name__ == "__main__":
    main()