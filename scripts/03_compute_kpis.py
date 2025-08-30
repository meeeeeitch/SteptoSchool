"""
Compute coverage KPIs from precomputed walk times.
"""
import argparse
from pathlib import Path
import pandas as pd
from src.kpis import coverage_kpis

OUT = Path("output")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold-min", type=int, default=10)
    ap.add_argument("--threshold2-min", type=int, default=15)
    args = ap.parse_args()

    walk_df = pd.read_csv(OUT/"sa1_school_walktimes.csv")
    sa1, school = coverage_kpis(walk_df, thresholds_min=(args.threshold_min, args.threshold2_min))
    sa1.to_csv(OUT/"sa1_school_kpis.csv", index=False)
    school.to_csv(OUT/"school_kpis.csv", index=False)
    print("Wrote output/sa1_school_kpis.csv and output/school_kpis.csv")

if __name__ == "__main__":
    main()
