# Step to School

This repo gives you a pipeline to analyse and optimise ACT public **school transport** using open data.
It focuses on **school specials** coverage and “less hassle” metrics (walk time to an appropriate stop, transfers avoided).

## What it does

1. **Downloads** datasets from ACT open data (Socrata) + optional ABS SA1 centroids.
2. **Builds a graph**: SA1 origins ↔ walking edges ↔ school-special stops.
3. **Matches** school‑special routes to schools via fuzzy text on headsigns/names.
4. **Computes KPIs** (coverage, walk times, single‑seat reach).
5. **Suggests quick wins** (candidate new stops / minor detours) with simple heuristics.
6. **Exports** CSVs/GeoPackages for mapping (Power BI, QGIS).

## Datasets

- Daily Public Transport Passenger Journeys by Service Type (ACT, Socrata ID: `nkxy-abdj`)
- ACT School Bus Services (Socrata ID: `p4rg-3jx2`)
- Bus Routes – shapes (Socrata ID: `ifm8-78yv`) — optional for visuals
- Students Distance from School — by school and SA1 (Socrata ID: `3fd4-5fkk`)
- Park and Ride Locations (Socrata ID: `sfwt-4uw4`) — optional for scenarios
- **OpenStreetMap** — fetched via `osmnx` (no key required)
- **(Optional)** ABS SA1 2021 centroids CSV/GeoPackage — drop into `data/manual/sa1_centroids.*`

## Install

- Python 3.10+ recommended.

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Configure environment

Set an optional Socrata App Token to avoid rate limits:

```bash
export SOCRATA_APP_TOKEN="YOUR_TOKEN"
```

If you have ABS SA1 centroids (recommended), drop a file into `data/manual/` named **`sa1_centroids.csv`** or `sa1_centroids.gpkg` with columns:
- `sa1_code_2021` (string) and `geometry` (if gpkg) or `lon`, `lat` (if csv).

If you don’t provide SA1 centroids, the pipeline will **fall back** to approximating SA1 origins by snapping to the nearest school‑special stop for each SA1 in the Students Distance table (coarse but still usable).

## Run

1) **Download** the open datasets as local CSV/GeoJSON:

```bash
python scripts/01_download_all.py
```

2) **Build** the school‑access graph and precompute nearest stops/isochrones:

```bash
python scripts/02_build_graph.py --walk-radius-m 900
```

3) **Compute KPIs** (per SA1 and per school):

```bash
python scripts/03_compute_kpis.py --threshold-min 10 --threshold2-min 15
```

4) **Suggest quick wins** (candidate new stops / minor detours):

```bash
python scripts/04_suggest_quick_wins.py --max-new-stops 15
```

Outputs land in `output/` as CSV and GeoPackage layers you can map in Power BI or QGIS.


## Repo layout

```
school_transport_opt/
  data/
    raw/
    manual/
  output/
  scripts/
    01_download_all.py
    02_build_graph.py
    03_compute_kpis.py
    04_suggest_quick_wins.py
    05_prepare_view.py
    06_make_plots_all.py
  src/
    config.py
    data_loaders.py
    match_schools.py
    graph_school_access.py
    kpis.py
    optimise_stops.py
    utils_geo.py
requirements.txt
README.md
```

## Notes & Limitations

- School matching is **fuzzy** by design (headsigns vs official school names). Check `output/match_debug.csv` to validate.
