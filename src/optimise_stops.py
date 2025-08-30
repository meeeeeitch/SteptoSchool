from typing import Tuple
import pandas as pd
import geopandas as gpd
from shapely.ops import unary_union
from shapely.geometry import Point
from .config import WGS84, TARGET_CRS

def greedy_new_stop_candidates(sa1_kpis: pd.DataFrame, sa1_points: gpd.GeoDataFrame, stops_gdf: gpd.GeoDataFrame, threshold_min: int = 10, max_new_stops: int = 10) -> gpd.GeoDataFrame:
    """
    Very simple set-cover style heuristic:
    - Find SA1s that are NOT within threshold.
    - Iteratively place a candidate stop at the centroid of the highest-need cluster (here, the densest group by proximity).
    - Stop after max_new_stops or full coverage.
    """
    # Merge to get coords
    gdf = sa1_points.merge(sa1_kpis[["sa1_code_2021", f"pct_within_{threshold_min}_min"]], on="sa1_code_2021", how="left")
    gdf = gdf.fillna({f"pct_within_{threshold_min}_min":0.0})
    need = gdf[gdf[f"pct_within_{threshold_min}_min"] < 1.0].copy()
    if need.empty:
        return gpd.GeoDataFrame(columns=["geometry","reason"], crs=WGS84)

    # naive clustering via buffer-overlap, pick densest center repeatedly
    candidates = []
    remaining = need.copy()
    radius_m = threshold_min * 60 * 1.25  # meters ~ walk distance
    remaining = remaining.to_crs(3857)
    for _ in range(max_new_stops):
        # find densest area: pick point with most neighbors in radius
        idx_max = None
        best_count = -1
        for idx, row in remaining.iterrows():
            nb = remaining[remaining.geometry.distance(row.geometry) <= radius_m]
            if len(nb) > best_count:
                best_count = len(nb)
                idx_max = idx
        if idx_max is None or best_count <= 0:
            break
        chosen = remaining.loc[[idx_max]].to_crs(4326)
        candidates.append(chosen.geometry.iloc[0])
        # remove covered SA1s
        disk = chosen.to_crs(3857).buffer(radius_m).iloc[0]
        remaining = remaining[~remaining.geometry.within(disk)]

        if remaining.empty:
            break
    cand_gdf = gpd.GeoDataFrame(geometry=gpd.GeoSeries(candidates, crs=WGS84))
    cand_gdf["reason"] = f"Improve <= {threshold_min} min walk coverage"
    return cand_gdf
