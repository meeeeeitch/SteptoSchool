"""
Central config — dataset IDs and parameters.
Update IDs if portals change.
"""
from dataclasses import dataclass

# Socrata domain for ACT Open Data
SOCRATA_DOMAIN = "www.data.act.gov.au"

# Dataset IDs (Socrata 4-4)
DATASETS = {
    "daily_journeys": "nkxy-abdj",
    "school_bus_services": "p4rg-3jx2",
    "bus_routes_shapes": "ifm8-78yv",     # optional for visuals
    "students_distance_sa1": "3fd4-5fkk",
    "park_and_ride": "sfwt-4uw4",         # optional for scenarios
}

# AOI bounding box for ACT (approx), used for OSM extracts
ACT_BBOX = (148.76, -35.92, 149.44, -35.05)  # (minx, miny, maxx, maxy)

# Walking speed (m/s) and max walking radius to search
WALK_SPEED_MPS = 1.25
DEFAULT_WALK_RADIUS_M = 900

# Output CRS for Geo work
TARGET_CRS = "EPSG:3857"  # metric, web-mercator
WGS84 = "EPSG:4326"
