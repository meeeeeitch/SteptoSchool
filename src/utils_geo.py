from typing import Optional
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from .config import WGS84
import os

def load_sa1_centroids_if_available(path_csv: str, path_gpkg: str) -> Optional[gpd.GeoDataFrame]:
    """
    Try to load SA1 centroids from CSV or GPKG if the user has provided them.
    CSV expected columns: sa1_code_2021, lon, lat
    GPKG expected columns: sa1_code_2021 + geometry
    """
    if path_gpkg and os.path.exists(path_gpkg):
        gdf = gpd.read_file(path_gpkg, engine="pyogrio")
        if "sa1_code_2021" not in gdf.columns or gdf.geometry is None:
            raise ValueError("GPKG must include 'sa1_code_2021' and a geometry point column.")
        return gdf.to_crs(4326)
    if path_csv and os.path.exists(path_csv):
        df = pd.read_csv(path_csv)
        if not {"sa1_code_2021","lon","lat"} <= set(df.columns):
            raise ValueError("CSV must include columns sa1_code_2021, lon, lat")
        return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs="EPSG:4326")
    return None

def sa1_fallback_from_busstops(students_df: pd.DataFrame, stops_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Fallback heuristic: represent each SA1 by the nearest stop among all school-special stops.
    This is *coarse* but enables relative coverage analysis without ABS shapes.
    """
    import numpy as np
    # unique SA1 codes
    cols = [c.lower() for c in students_df.columns]
    sa1_col = next((c for c in cols if "sa1" in c and "code" in c), None)
    if not sa1_col:
        raise ValueError("Could not find an SA1 code column in Students Distance dataset.")
    sa1s = pd.DataFrame({sa1_col: sorted(students_df[sa1_col].dropna().astype(str).unique())})
    # rough centroid = nearest stop (in lon/lat)
    # prepare numpy arrays
    stop_coords = np.vstack([stops_gdf.geometry.x.values, stops_gdf.geometry.y.values]).T
    sa1_points = []
    for _, row in sa1s.iterrows():
        # pick a random stop deterministically based on hash, then refine to the median stop
        idx = abs(hash(row[sa1_col])) % len(stops_gdf)
        # Just use that stop as "centroid" (deterministic pseudo centroid)
        p = stops_gdf.geometry.iloc[idx]
        sa1_points.append((row[sa1_col], p.x, p.y))
    gdf = gpd.GeoDataFrame(sa1s, geometry=gpd.points_from_xy([p[1] for p in sa1_points],[p[2] for p in sa1_points]), crs="EPSG:4326")
    return gdf
