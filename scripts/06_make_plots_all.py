"""
make_plots_all.py
Generate ALL visuals from CSVs in ./output and save PNGs to ./plots.

Examples:
  python scripts\06_make_plots_all.py --min-threshold 10 --max-threshold 15
  python scripts\06_make_plots_all.py --min-threshold 10 --max-threshold 15 --step 5 --per-school

Inputs expected in ./output:
  - pbi_sa1_points_per_school.csv
      Columns must include: sa1_code_2021, school, (walk_time_sec OR walk_time_min), lon, lat
  - pbi_stops.csv                      (optional but recommended)
      Columns: lon, lat (others ignored)
  - pbi_candidate_stops.csv            (optional)
      Columns: lon, lat (others ignored)

Outputs (written to ./plots):
  - hist_sa1_pct_within_{T}min.png
  - map_act_sa1_coverage_{T}min.png
  - (optional) bars_schools_best_{PICK}min.png
  - (optional) bars_schools_worst_{PICK}min.png
"""

import argparse
from pathlib import Path
import json
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from shapely.geometry import shape

# ---------- Safe GeoJSON reader (no GDAL needed) ----------
def read_geojson_light(path: Path) -> gpd.GeoDataFrame:
    """Read a FeatureCollection GeoJSON via stdlib json + shapely."""
    js = json.loads(path.read_text(encoding="utf-8"))
    feats = js.get("features", [])
    if not feats:
        return gpd.GeoDataFrame(columns=["geometry"], geometry=[], crs="EPSG:4326")
    props = []
    geoms = []
    for ft in feats:
        props.append((ft.get("properties") or {}))
        geom = ft.get("geometry")
        geoms.append(shape(geom) if geom else None)
    gdf = gpd.GeoDataFrame(props, geometry=geoms, crs="EPSG:4326")
    return gdf

# ---------- Helpers ----------
def thresholds_from_args(min_thr: int, max_thr: int, step: int) -> list[int]:
    if max_thr < min_thr:
        raise SystemExit("--max-threshold must be >= --min-threshold")
    if step <= 0:
        raise SystemExit("--step must be a positive integer")
    return list(range(min_thr, max_thr + 1, step))

def ensure_plots_dir() -> Path:
    p = Path("plots")
    p.mkdir(parents=True, exist_ok=True)
    return p

def load_per_pair(outdir: Path) -> pd.DataFrame:
    per_pair_path = outdir / "pbi_sa1_points_per_school.csv"
    if not per_pair_path.exists():
        raise SystemExit(f"Missing {per_pair_path}. Make sure your CSVs are in ./output")
    return pd.read_csv(per_pair_path)

def df_points_from_lonlat(df: pd.DataFrame, lon_col="lon", lat_col="lat") -> gpd.GeoDataFrame:
    if {lon_col, lat_col}.issubset(df.columns):
        return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df[lon_col], df[lat_col]), crs="EPSG:4326")
    return gpd.GeoDataFrame()

def load_stops_gdf(outdir: Path) -> gpd.GeoDataFrame:
    """Prefer full GeoJSON produced by 02_build_graph.py; fallback to pbi_stops.csv."""
    geojson_path = outdir / "stops_schoolspecials.geojson"
    csv_path = outdir / "pbi_stops.csv"
    if geojson_path.exists():
        gdf = read_geojson_light(geojson_path)
        # Some pipelines lowercase columns—keep common names if present
        return gdf
    if csv_path.exists():
        df = pd.read_csv(csv_path)
        return df_points_from_lonlat(df)
    return gpd.GeoDataFrame(columns=["geometry"], geometry=[], crs="EPSG:4326")

def load_candidate_gdf(outdir: Path) -> gpd.GeoDataFrame:
    """Prefer candidate_new_stops.geojson; fallback to pbi_candidate_stops.csv."""
    geojson_path = outdir / "candidate_new_stops.geojson"
    csv_path = outdir / "pbi_candidate_stops.csv"
    if geojson_path.exists():
        return read_geojson_light(geojson_path)
    if csv_path.exists():
        df = pd.read_csv(csv_path)
        return df_points_from_lonlat(df)
    return gpd.GeoDataFrame(columns=["geometry"], geometry=[], crs="EPSG:4326")

def load_routes_geojson() -> gpd.GeoDataFrame | None:
    routes_path = Path("data/raw/bus_routes_shapes.geojson")
    if not routes_path.exists():
        return None
    try:
        gdf = read_geojson_light(routes_path)
        if getattr(gdf, "geometry", None) is None or gdf.geometry.isna().all():
            return None
        return gdf.to_crs(4326)
    except Exception:
        return None

def add_threshold_columns(df: pd.DataFrame, thresholds: list[int]) -> pd.DataFrame:
    out = df.copy()
    if "walk_time_min" not in out.columns:
        if "walk_time_sec" in out.columns:
            out["walk_time_min"] = out["walk_time_sec"] / 60.0
        else:
            raise SystemExit("Need walk_time_min or walk_time_sec in pbi_sa1_points_per_school.csv")
    for t in thresholds:
        out[f"within_{t}_min"] = (out["walk_time_min"] <= t).astype(int)
    return out

def aggregate_sa1_kpis(df: pd.DataFrame, thresholds: list[int]) -> pd.DataFrame:
    required = {"sa1_code_2021", "lon", "lat"}
    if not required.issubset(df.columns):
        raise SystemExit(f"Expected columns {required} in pbi_sa1_points_per_school.csv")
    keep_cols = ["sa1_code_2021", "lon", "lat"] + [c for c in df.columns if c.startswith("within_")]
    d = df[keep_cols].copy()
    agg = d.groupby("sa1_code_2021").agg(
        pairs=("lon", "count"),
        lon=("lon", "first"),
        lat=("lat", "first")
    ).reset_index()
    for t in thresholds:
        col = f"within_{t}_min"
        if col in d.columns:
            cnt = d.groupby("sa1_code_2021")[col].sum().reset_index(name=f"pairs_within_{t}_min")
            agg = agg.merge(cnt, on="sa1_code_2021", how="left")
            agg[f"pct_within_{t}_min"] = agg[f"pairs_within_{t}_min"] / agg["pairs"]
    return agg

def compute_breakdown(sa1_kpis: pd.DataFrame, thresholds: list[int]) -> pd.DataFrame:
    rows = []
    total_sa1 = len(sa1_kpis)
    for t in thresholds:
        col = f"pct_within_{t}_min"
        if col not in sa1_kpis.columns:
            continue
        s = sa1_kpis[col].fillna(0)
        full = int((s == 1).sum())
        none = int((s == 0).sum())
        partial = int(((s > 0) & (s < 1)).sum())
        rows.append({
            "threshold_min": t,
            "sa1_total": total_sa1,
            "sa1_full": full,
            "sa1_partial": partial,
            "sa1_none": none,
            "pct_full": full / total_sa1 if total_sa1 else 0.0,
            "pct_partial": partial / total_sa1 if total_sa1 else 0.0,
            "pct_none": none / total_sa1 if total_sa1 else 0.0,
        })
    return pd.DataFrame(rows)

# ---------- Plotters ----------
def plot_histograms(sa1_kpis: pd.DataFrame, thresholds: list[int], outdir: Path):
    for t in thresholds:
        col = f"pct_within_{t}_min"
        if col not in sa1_kpis.columns:
            continue
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.hist(sa1_kpis[col].fillna(0), bins=10, range=(0, 1), edgecolor="black")
        ax.set_title(f"Distribution of SA1 Coverage ≤ {t} minutes")
        ax.set_xlabel("% of school pairings within threshold")
        ax.set_ylabel("Number of SA1s")
        fig.tight_layout()
        fig.savefig(outdir / f"hist_sa1_pct_within_{t}min.png", dpi=200)
        plt.close(fig)

def plot_citywide_maps(sa1_kpis: pd.DataFrame,
                       stops_gdf: gpd.GeoDataFrame,
                       cand_gdf: gpd.GeoDataFrame,
                       thresholds: list[int],
                       routes_gdf: gpd.GeoDataFrame | None,
                       outdir: Path):
    sa1_gdf = gpd.GeoDataFrame(
        sa1_kpis, geometry=gpd.points_from_xy(sa1_kpis["lon"], sa1_kpis["lat"]), crs="EPSG:4326"
    )
    for t in thresholds:
        col = f"pct_within_{t}_min"
        if col not in sa1_gdf.columns:
            continue
        fig, ax = plt.subplots(figsize=(9, 10))

        # Routes underlay (if available)
        if routes_gdf is not None and not routes_gdf.empty:
            try:
                routes_gdf.plot(ax=ax, linewidth=0.6, alpha=0.35, color="grey")
            except Exception:
                pass

        # SA1 choropleth (points, but colored by coverage)
        sa1_gdf.plot(ax=ax, column=col, cmap="RdYlGn", legend=True,
                     legend_kwds={"label": f"% of schools ≤ {t} min"})

        # Existing stops (authoritative GeoJSON -> all should render)
        if stops_gdf is not None and not stops_gdf.empty:
            try:
                stops_gdf.plot(ax=ax, color="blue", markersize=10, alpha=0.8,
                               label=f"Existing stops (n={len(stops_gdf)})")
            except Exception:
                # If geometry missing for some reason, try fallback from lon/lat
                if {"lon", "lat"}.issubset(stops_gdf.columns):
                    df_points_from_lonlat(stops_gdf).plot(ax=ax, color="blue", markersize=10, alpha=0.8,
                                                          label=f"Existing stops (n={len(stops_gdf)})")

        # Candidate stops
        if cand_gdf is not None and not cand_gdf.empty:
            try:
                cand_gdf.plot(ax=ax, color="red", markersize=60, marker="*", label=f"Candidate stops (n={len(cand_gdf)})")
            except Exception:
                if {"lon", "lat"}.issubset(cand_gdf.columns):
                    df_points_from_lonlat(cand_gdf).plot(ax=ax, color="red", markersize=60, marker="*",
                                                         label=f"Candidate stops (n={len(cand_gdf)})")

        ax.set_title(f"ACT SA1 Coverage ≤ {t} minutes (with existing + candidate stops{' + routes' if routes_gdf is not None else ''})")
        ax.legend()
        fig.tight_layout()
        fig.savefig(outdir / f"map_act_sa1_coverage_{t}min.png", dpi=220)
        plt.close(fig)

def plot_routes_overview(routes_gdf: gpd.GeoDataFrame | None,
                         stops_gdf: gpd.GeoDataFrame,
                         cand_gdf: gpd.GeoDataFrame,
                         outdir: Path):
    if routes_gdf is None or routes_gdf.empty:
        return
    fig, ax = plt.subplots(figsize=(10, 10))
    routes_gdf.plot(ax=ax, linewidth=0.7, alpha=0.55, color="grey", label="Bus routes")
    if stops_gdf is not None and not stops_gdf.empty:
        stops_gdf.plot(ax=ax, color="blue", markersize=8, alpha=0.8, label=f"Existing stops (n={len(stops_gdf)})")
    if cand_gdf is not None and not cand_gdf.empty:
        cand_gdf.plot(ax=ax, color="red", markersize=60, marker="*", label=f"Candidate stops (n={len(cand_gdf)})")
    ax.set_title("Transport Canberra Bus Routes with Stops & Candidate New Stops")
    ax.legend()
    fig.tight_layout()
    fig.savefig(outdir / "routes_overview.png", dpi=220)
    plt.close(fig)

def plot_per_school_bars(per_pair_df: pd.DataFrame, thresholds: list[int], outdir: Path, top_n: int = 20):
    df = per_pair_df.copy()
    school_col = "school" if "school" in df.columns else df.columns[1]
    within_cols = [f"within_{t}_min" for t in thresholds if f"within_{t}_min" in df.columns]
    if not within_cols:
        return
    agg = df.groupby(school_col).agg(sa1_pairs=("sa1_code_2021", "count")).reset_index()
    for t in thresholds:
        col = f"within_{t}_min"
        if col in df.columns:
            pct = df.groupby(school_col)[col].mean().reset_index(name=f"pct_within_{t}_min")
            agg = agg.merge(pct, on=school_col, how="left")
    pick = 15 if f"pct_within_15_min" in agg.columns else max(thresholds)
    sortcol = f"pct_within_{pick}_min"
    if sortcol not in agg.columns:
        return
    best = agg.sort_values(sortcol, ascending=False).head(top_n)
    worst = agg.sort_values(sortcol, ascending=True).head(top_n)
    for name, sub in [("best", best), ("worst", worst)]:
        fig, ax = plt.subplots(figsize=(10, 8))
        ax.barh(sub[school_col], sub[sortcol])
        ax.set_xlim(0, 1)
        ax.invert_yaxis()
        ax.set_xlabel(f"% of SA1s ≤ {pick} min")
        ax.set_title(f"{name.title()} {top_n} schools by {pick}-minute coverage")
        fig.tight_layout()
        fig.savefig(outdir / f"bars_schools_{name}_{pick}min.png", dpi=220)
        plt.close(fig)

def plot_breakdown_stacked(breakdown_df: pd.DataFrame, outdir: Path):
    if breakdown_df.empty:
        return
    df = breakdown_df.sort_values("threshold_min")
    labels = df["threshold_min"].astype(str).tolist()
    none = df["pct_none"].values
    partial = df["pct_partial"].values
    full = df["pct_full"].values
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(labels, none, label="None", edgecolor="black")
    ax.bar(labels, partial, bottom=none, label="Partial", edgecolor="black")
    ax.bar(labels, full, bottom=none+partial, label="Full", edgecolor="black")
    ax.set_ylim(0, 1)
    ax.set_ylabel("Share of SA1s")
    ax.set_xlabel("Walk-time threshold (minutes)")
    ax.set_title("SA1 Coverage Breakdown by Threshold")
    ax.legend()
    for i, _ in enumerate(labels):
        ax.text(i, none[i]/2, f"{none[i]*100:.0f}%", ha="center", va="center", fontsize=9, color="white")
        ax.text(i, none[i] + partial[i]/2, f"{partial[i]*100:.0f}%", ha="center", va="center", fontsize=9, color="black")
        ax.text(i, none[i] + partial[i] + full[i]/2, f"{full[i]*100:.0f}%", ha="center", va="center", fontsize=9, color="white")
    fig.tight_layout()
    fig.savefig(outdir / "bars_coverage_breakdown_by_threshold.png", dpi=220)
    plt.close(fig)

# ---------- Main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-threshold", type=int, required=True, help="Minimum walk-time threshold in minutes (e.g., 10)")
    ap.add_argument("--max-threshold", type=int, required=True, help="Maximum walk-time threshold in minutes (e.g., 30)")
    ap.add_argument("--step", type=int, default=5, help="Step size between thresholds (default: 5)")
    ap.add_argument("--per-school", action="store_true", help="Also generate per-school top/bottom bar charts")
    ap.add_argument("--top-n", type=int, default=20, help="How many schools to show in best/worst charts (default: 20)")
    args = ap.parse_args()

    thresholds = thresholds_from_args(args.min_threshold, args.max_threshold, args.step)

    outdir = Path("output")
    plots_dir = ensure_plots_dir()

    # Load core tabular + thresholds
    per_pair = load_per_pair(outdir)
    per_pair = add_threshold_columns(per_pair, thresholds)
    sa1_kpis = aggregate_sa1_kpis(per_pair, thresholds)

    # Load geometries (authoritative sources preferred)
    stops_gdf = load_stops_gdf(outdir)
    cand_gdf  = load_candidate_gdf(outdir)
    routes_gdf = load_routes_geojson()

    # High-level counts
    n_sa1 = sa1_kpis["sa1_code_2021"].nunique()
    n_schools = per_pair["school"].nunique() if "school" in per_pair.columns else per_pair.iloc[:,1].nunique()
    n_stops = 0 if stops_gdf is None or stops_gdf.empty else len(stops_gdf)
    n_cand = 0 if cand_gdf is None or cand_gdf.empty else len(cand_gdf)
    n_routes = 0 if (routes_gdf is None or routes_gdf.empty) else len(routes_gdf)

    print("\n=== DATA COUNTS ===")
    print(f"SA1s:            {n_sa1}")
    print(f"Schools:         {n_schools}")
    print(f"Existing stops:  {n_stops}")
    print(f"Candidate stops: {n_cand}")
    print(f"Route features:  {n_routes} (from data/raw/bus_routes_shapes.geojson)")

    # Coverage breakdown + CSV
    breakdown = compute_breakdown(sa1_kpis, thresholds)
    breakdown.to_csv(plots_dir / "coverage_summary.csv", index=False)
    print("\n=== COVERAGE SUMMARY (per threshold) ===")
    print(breakdown.to_string(index=False) if not breakdown.empty else "No coverage columns found.")

    # Plots
    plot_histograms(sa1_kpis, thresholds, plots_dir)
    plot_citywide_maps(sa1_kpis, stops_gdf, cand_gdf, thresholds, routes_gdf, plots_dir)
    plot_breakdown_stacked(breakdown, plots_dir)
    plot_routes_overview(routes_gdf, stops_gdf, cand_gdf, plots_dir)

    if args.per_school:
        plot_per_school_bars(per_pair, thresholds, plots_dir, top_n=args.top_n)

    print(f"\nAll figures written to: {plots_dir.resolve()}")
    print(f"Thresholds used: {thresholds}")

if __name__ == "__main__":
    main()