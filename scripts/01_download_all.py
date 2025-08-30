"""
Download open datasets into data/raw using Socrata SODA.
"""
import os, sys
from pathlib import Path
import pandas as pd
from src import data_loaders
from src.geojson_io import gdf_to_geojson_bytes

RAW = Path("data/raw")
RAW.mkdir(parents=True, exist_ok=True)

def _has_geometry(gdf) -> bool:
    try:
        return gdf is not None and getattr(gdf, "geometry", None) is not None and gdf.geometry.notna().any()
    except Exception:
        return False

def main():
    print("Downloading daily journeys...")
    data_loaders.load_daily_journeys().to_csv(RAW/"daily_journeys.csv", index=False)

    print("Downloading school bus services...")
    gdf = data_loaders.load_school_bus_services()
    # If geometry present, save to GeoJSON; always write CSV
    if _has_geometry(gdf):
        open(RAW/"school_bus_services.geojson", "wb").write(
            gdf_to_geojson_bytes(gdf.to_crs(4326))
        )
    gdf.drop(columns=["geometry"], errors="ignore").to_csv(RAW/"school_bus_services.csv", index=False)

    print("Downloading bus routes shapes (optional)...")
    try:
        routes = data_loaders.load_bus_routes_shapes()
        if _has_geometry(routes):
            open(RAW/"bus_routes_shapes.geojson", "wb").write(
                gdf_to_geojson_bytes(routes.to_crs(4326))
            )
    except Exception as e:
        print("  Skipped bus routes shapes (optional):", e)

    print("Downloading Students Distance SA1...")
    data_loaders.load_students_distance_sa1().to_csv(RAW/"students_distance_sa1.csv", index=False)

    print("Downloading Park & Ride (optional)...")
    try:
        par = data_loaders.load_park_and_ride()
        if _has_geometry(par):
            open(RAW/"park_and_ride.geojson", "wb").write(
                gdf_to_geojson_bytes(par.to_crs(4326))
            )
    except Exception as e:
        print("  Skipped park-and-ride (optional):", e)

    print("Done.")

if __name__ == "__main__":
    main()