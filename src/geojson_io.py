import json
from typing import Iterable
import geopandas as gpd
from shapely.geometry import shape, mapping

def gdf_from_geojson_bytes(data: bytes) -> gpd.GeoDataFrame:
    js = json.loads(data.decode("utf-8"))
    feats = js["features"]
    records = []
    geoms = []
    for ft in feats:
        props = ft.get("properties", {}) or {}
        records.append(props)
        geoms.append(shape(ft["geometry"]))
    return gpd.GeoDataFrame(records, geometry=geoms, crs="EPSG:4326")

def gdf_to_geojson_bytes(gdf: gpd.GeoDataFrame) -> bytes:
    feats = []
    for _, row in gdf.iterrows():
        props = {k: v for k, v in row.items() if k != "geometry"}
        geom = mapping(row.geometry) if row.geometry is not None else None
        feats.append({"type":"Feature","properties":props,"geometry":geom})
    fc = {"type":"FeatureCollection","features":feats,"crs":{"type":"name","properties":{"name":"EPSG:4326"}}}
    return json.dumps(fc).encode("utf-8")
