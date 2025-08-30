"""
Build walking graph and compute min walk times from SA1 to nearest stop serving the student's school.
"""
import sys, os, argparse
from pathlib import Path
import pandas as pd
import geopandas as gpd

# make src importable no matter where you run from
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config import DEFAULT_WALK_RADIUS_M  # (kept for CLI consistency; radius currently unused here)
from src.graph_school_access import (
    build_walk_graph, stops_to_nodes, sa1_to_nodes,
    compute_min_walk_to_schoolstop, prepare_school_stop_mapping
)
from src.utils_geo import load_sa1_centroids_if_available, sa1_fallback_from_busstops
from src.geojson_io import gdf_from_geojson_bytes, gdf_to_geojson_bytes

RAW = Path("data/raw")
OUT = Path("output")
OUT.mkdir(parents=True, exist_ok=True)

def _read_geojson(path: Path) -> gpd.GeoDataFrame:
    data = path.read_bytes()
    gdf = gdf_from_geojson_bytes(data)
    return gdf

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--walk-radius-m", type=int, default=DEFAULT_WALK_RADIUS_M)
    ap.add_argument("--sa1-centroids-csv", default="data/manual/sa1_centroids.csv")
    ap.add_argument("--sa1-centroids-gpkg", default="data/manual/sa1_centroids.gpkg")
    args = ap.parse_args()

    students = pd.read_csv(RAW / "students_distance_sa1.csv")

    sb_path = RAW / "school_bus_services.geojson"
    if not sb_path.exists():
        raise SystemExit("Missing data/raw/school_bus_services.geojson. Run scripts/01_download_all.py first.")
    busstops = _read_geojson(sb_path)

    print("Matching school specials to schools (fuzzy)...")
    mapping = prepare_school_stop_mapping(busstops, students, score_cutoff=82)
    (OUT / "match_debug.csv").write_text(mapping.to_csv(index=False))

    print("Loading/deriving SA1 centroids...")
    sa1_gdf = load_sa1_centroids_if_available(args.sa1_centroids_csv, args.sa1_centroids_gpkg)
    if sa1_gdf is None:
        print("  No SA1 centroids provided — falling back to nearest stop heuristic (coarse).")
        sa1_gdf = sa1_fallback_from_busstops(students, busstops)
    sa1_gdf = sa1_gdf.to_crs(4326)

    print("Building pedestrian graph from OSM... (this may take a few minutes)")
    G = build_walk_graph()

    print("Snapping stops and SA1s to graph nodes...")
    stop_nodes = stops_to_nodes(G, busstops)
    sa1_nodes = sa1_to_nodes(G, sa1_gdf)

    print("Computing min walk time SA1 -> nearest stop serving that school...")
    walk_df = compute_min_walk_to_schoolstop(G, sa1_nodes, stop_nodes, mapping, students)
    walk_df.to_csv(OUT / "sa1_school_walktimes.csv", index=False)
    print("Saved to output/sa1_school_walktimes.csv")

    # Also output the stops as GeoJSON for mapping (no GDAL/fiona)
    open(OUT / "stops_schoolspecials.geojson", "wb").write(
        gdf_to_geojson_bytes(busstops.to_crs(4326))
    )

if __name__ == "__main__":
    main()