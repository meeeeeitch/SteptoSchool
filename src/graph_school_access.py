from typing import Dict
import numpy as np
import pandas as pd
import geopandas as gpd
import networkx as nx
import osmnx as ox
from shapely import geometry as sg

from .config import ACT_BBOX, WALK_SPEED_MPS
from .match_schools import match_school_names

# osmnx v1/v2: nearest_nodes location differs
try:
    _nearest_nodes = ox.distance.nearest_nodes  # v2+
except AttributeError:
    _nearest_nodes = ox.nearest_nodes           # v1.x


def _edge_length_m(G: nx.MultiDiGraph, u: int, v: int, data: Dict) -> float:
    """Best-effort edge length in meters."""
    val = data.get("length")
    if isinstance(val, (int, float)):
        return float(val)
    geom = data.get("geometry")
    if geom is not None and hasattr(geom, "coords"):
        coords = list(geom.coords)
        if len(coords) >= 2:
            dist = 0.0
            for (x1, y1), (x2, y2) in zip(coords[:-1], coords[1:]):
                dist += ox.distance.great_circle_vec(y1, x1, y2, x2)
            return dist
    n1, n2 = G.nodes[u], G.nodes[v]
    if {"x", "y"} <= set(n1.keys()) and {"x", "y"} <= set(n2.keys()):
        return ox.distance.great_circle_vec(n1["y"], n1["x"], n2["y"], n2["x"])
    return 0.0


def build_walk_graph(bbox=ACT_BBOX) -> nx.MultiDiGraph:
    """
    Build a pedestrian graph for the ACT bbox using a rectangle polygon.
    This works across OSMnx versions (avoids bbox arg signature changes).
    """
    west, south, east, north = bbox  # (minx, miny, maxx, maxy)
    poly = sg.box(west, south, east, north)
    G = ox.graph_from_polygon(poly, network_type="walk")

    # add travel_time (seconds)
    for u, v, k, data in G.edges(keys=True, data=True):
        L = _edge_length_m(G, u, v, data)
        data["length"] = L
        data["travel_time"] = (L / float(WALK_SPEED_MPS)) if L > 0 else 0.0
    return G


def _to_undirected_min_time(G: nx.MultiDiGraph) -> nx.Graph:
    """Undirected graph with the minimum travel_time per edge (faster Dijkstra)."""
    H = nx.Graph()
    for u, v, data in G.edges(data=True):
        t = float(data.get("travel_time", 0.0))
        if H.has_edge(u, v):
            if t < H[u][v]["travel_time"]:
                H[u][v]["travel_time"] = t
        else:
            H.add_edge(u, v, travel_time=t)
    return H


def stops_to_nodes(G: nx.MultiDiGraph, stops_gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    stop_ids = stops_gdf.get("stop_id", stops_gdf.index.astype(str)).astype(str)
    nodes = _nearest_nodes(G, X=stops_gdf.geometry.x.values, Y=stops_gdf.geometry.y.values)
    out = pd.DataFrame({"stop_id": stop_ids.values, "graph_node": nodes})
    out["graph_node"] = out["graph_node"].astype(int)
    return out


def sa1_to_nodes(G: nx.MultiDiGraph, sa1_gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    sa1_codes = sa1_gdf.get("sa1_code_2021", sa1_gdf.index.astype(str)).astype(str)
    nodes = _nearest_nodes(G, X=sa1_gdf.geometry.x.values, Y=sa1_gdf.geometry.y.values)
    out = pd.DataFrame({"sa1_code_2021": sa1_codes.values, "graph_node": nodes})
    out["graph_node"] = out["graph_node"].astype(int)
    return out


def _find_student_cols(students_df: pd.DataFrame):
    """
    Find the SA1 and school columns in the Students Distance table, handling common variants:
    e.g. 'sa1_code_2021', 'sa1_code', 'sa1', and 'school'/'school_name'.
    Returns the ORIGINAL column names (not lowercased) for downstream merges.
    """
    # map lower->original
    lower_to_orig = {c.lower(): c for c in students_df.columns}

    # SA1 candidates (ordered by preference)
    sa1_candidates = ["sa1_code_2021", "sa1_code", "sa1", "sa1id", "sa1_code_2016"]
    sa1_col = next((lower_to_orig[c] for c in sa1_candidates if c in lower_to_orig), None)

    # School candidates
    school_candidates = ["school", "school_name", "schoolname", "school_label"]
    school_col = next((lower_to_orig[c] for c in school_candidates if c in lower_to_orig), None)

    if not sa1_col or not school_col:
        raise ValueError(
            "Could not find SA1 and School columns in Students Distance dataset. "
            f"Columns seen: {list(students_df.columns)}"
        )
    return sa1_col, school_col


def prepare_school_stop_mapping(
    bus_gdf: gpd.GeoDataFrame,
    students_df: pd.DataFrame,
    score_cutoff: int = 82
) -> pd.DataFrame:
    if "geometry" not in bus_gdf.columns or bus_gdf.geometry.isna().all():
        raise ValueError("School bus services dataset lacks geometry; cannot map stops to the walk graph.")

    matches = match_school_names(bus_gdf, students_df, score_cutoff=score_cutoff).copy()
    if matches.empty:
        raise ValueError("No stop↔school matches found. Lower the cutoff or inspect text columns.")

    if "stop_id" not in matches.columns:
        matches["stop_id"] = matches.index.astype(str)
    matches["stop_id"] = matches["stop_id"].astype(str)
    return matches[["stop_id", "matched_school", "confidence"]]


def compute_min_walk_to_schoolstop(
    G: nx.MultiDiGraph,
    sa1_nodes_df: pd.DataFrame,
    stop_nodes_df: pd.DataFrame,
    mapping_school_stops: pd.DataFrame,
    students_df: pd.DataFrame
) -> pd.DataFrame:
    for col in ["stop_id", "matched_school"]:
        if col not in mapping_school_stops.columns:
            raise ValueError(f"mapping_school_stops missing required column: {col}")

    stop_nodes_df = stop_nodes_df.copy()
    stop_nodes_df["stop_id"] = stop_nodes_df["stop_id"].astype(str)
    map_nodes = mapping_school_stops.merge(stop_nodes_df, on="stop_id", how="inner").dropna(subset=["graph_node"])
    if map_nodes.empty:
        raise ValueError("No school-serving stops could be snapped to the graph.")

    sa1_col, school_col = _find_student_cols(students_df)
    pairs = students_df[[sa1_col, school_col]].drop_duplicates().rename(
        columns={sa1_col: "sa1_code_2021", school_col: "school"}
    )
    pairs["sa1_code_2021"] = pairs["sa1_code_2021"].astype(str)

    sa1_nodes_df = sa1_nodes_df.copy()
    sa1_nodes_df["sa1_code_2021"] = sa1_nodes_df["sa1_code_2021"].astype(str)
    pairs = pairs.merge(sa1_nodes_df, on="sa1_code_2021", how="left").dropna(subset=["graph_node"])
    if pairs.empty:
        raise ValueError("No SA1 centroids could be snapped to the graph.")

    H = _to_undirected_min_time(G)

    results = []
    for school, df_s in map_nodes.groupby("matched_school"):
        targets = df_s["graph_node"].astype(int).unique().tolist()
        if not targets:
            continue
        dist_map = nx.multi_source_dijkstra_path_length(H, sources=targets, weight="travel_time")
        sub = pairs.loc[pairs["school"] == school, ["sa1_code_2021", "graph_node"]]
        for _, row in sub.iterrows():
            node = int(row["graph_node"])
            tt = dist_map.get(node)
            if tt is not None:
                results.append({"sa1_code_2021": row["sa1_code_2021"], "school": school, "walk_time_sec": float(tt)})

    if not results:
        return pd.DataFrame(columns=["sa1_code_2021", "school", "walk_time_sec"])

    out = pd.DataFrame(results).groupby(["sa1_code_2021", "school"], as_index=False)["walk_time_sec"].min()
    return out