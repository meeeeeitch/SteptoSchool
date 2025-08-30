import pandas as pd

def coverage_kpis(walk_df: pd.DataFrame, thresholds_min=(10,15,20)) -> pd.DataFrame:
    """
    Compute coverage by SA1 and by school for given walk-time thresholds.
    Assumes walk_df has rows (sa1_code_2021, school, walk_time_sec).
    """
    walk_df = walk_df.copy()
    for thr in thresholds_min:
        walk_df[f"within_{thr}_min"] = (walk_df["walk_time_sec"] <= thr*60).astype(int)

    # aggregate per SA1
    sa1 = walk_df.groupby("sa1_code_2021").agg(
        pairs=("school","count"),
        **{f"pairs_within_{thr}_min": (f"within_{thr}_min","sum") for thr in thresholds_min}
    ).reset_index()
    for thr in thresholds_min:
        sa1[f"pct_within_{thr}_min"] = sa1[f"pairs_within_{thr}_min"] / sa1["pairs"]

    # aggregate per school
    school = walk_df.groupby("school").agg(
        sa1_pairs=("sa1_code_2021","count"),
        **{f"sa1_pairs_within_{thr}_min": (f"within_{thr}_min","sum") for thr in thresholds_min}
    ).reset_index()
    for thr in thresholds_min:
        school[f"pct_within_{thr}_min"] = school[f"sa1_pairs_within_{thr}_min"] / school["sa1_pairs"]

    return sa1, school
