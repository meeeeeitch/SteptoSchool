import os
import io, os
import json
from typing import Optional, Dict
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, LineString
import requests
from .config import SOCRATA_DOMAIN, DATASETS
from .geojson_io import gdf_from_geojson_bytes

APP_TOKEN = os.getenv("SOCRATA_APP_TOKEN", None)

def _socrata_csv(dataset_id: str, limit: int = 500000, where: Optional[str] = None, select: Optional[str] = None) -> pd.DataFrame:
    """
    Fetch a Socrata dataset as CSV using the SODA API.
    """
    params = {"$limit": limit}
    if where: params["$where"] = where
    if select: params["$select"] = select
    url = f"https://{SOCRATA_DOMAIN}/resource/{dataset_id}.csv"
    headers = {}
    if APP_TOKEN:
        headers["X-App-Token"] = APP_TOKEN
    resp = requests.get(url, headers=headers, params=params, timeout=60)
    resp.raise_for_status()
    return pd.read_csv(io.BytesIO(resp.content))

def load_daily_journeys() -> pd.DataFrame:
    return _socrata_csv(DATASETS["daily_journeys"])

def load_school_bus_services() -> gpd.GeoDataFrame:
    df = _socrata_csv(DATASETS["school_bus_services"])
    df.columns = [c.lower() for c in df.columns]

    # 1) Try explicit lat/lon column names
    lat_col = next((c for c in df.columns if c in ["stop_lat","lat","latitude"]), None)
    lon_col = next((c for c in df.columns if c in ["stop_lon","lon","longitude"]), None)
    if lat_col and lon_col:
        return gpd.GeoDataFrame(
            df,
            geometry=gpd.points_from_xy(df[lon_col], df[lat_col], crs="EPSG:4326")
        )

    # 2) Try a WKT point column like "location" / "point" / anything that starts with 'POINT ('
    from shapely import wkt as _wkt
    cand_cols = ["location","point","the_geom","geom"] + list(df.columns)
    wkt_col = None
    for c in cand_cols:
        if c in df.columns:
            s = df[c].astype(str)
            if s.str.startswith("POINT").any():
                wkt_col = c
                break
    if wkt_col:
        geom = df[wkt_col].astype(str).apply(_wkt.loads)
        return gpd.GeoDataFrame(df, geometry=geom, crs="EPSG:4326")

    # 3) If nothing found, return a *regular* DataFrame and let callers handle it
    # (01_download_all.py will still write CSV; 02_build_graph will error with a clear message)
    return gpd.GeoDataFrame(df)  # no geometry/CRS set

def load_bus_routes_shapes() -> gpd.GeoDataFrame:
    url = f"https://{SOCRATA_DOMAIN}/resource/{DATASETS['bus_routes_shapes']}.geojson?$limit=500000"
    headers = {"Accept": "application/json"}
    if APP_TOKEN:
        headers["X-App-Token"] = APP_TOKEN
    resp = requests.get(url, headers=headers, timeout=120)
    resp.raise_for_status()
    return gdf_from_geojson_bytes(resp.content)

def load_students_distance_sa1() -> pd.DataFrame:
    return _socrata_csv(DATASETS["students_distance_sa1"], limit=500000)

def load_park_and_ride() -> gpd.GeoDataFrame:
    url = f"https://{SOCRATA_DOMAIN}/resource/{DATASETS['park_and_ride']}.geojson?$limit=50000"
    headers = {"Accept": "application/json"}
    if APP_TOKEN:
        headers["X-App-Token"] = APP_TOKEN
    resp = requests.get(url, headers=headers, timeout=120)
    resp.raise_for_status()
    return gdf_from_geojson_bytes(resp.content)
