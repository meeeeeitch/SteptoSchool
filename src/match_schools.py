import re
import pandas as pd
from rapidfuzz import fuzz, process

def normalize_name(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9\s&'-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def extract_candidate_school_from_headsign(headsign: str) -> str:
    if not headsign:
        return ""
    s = normalize_name(headsign)
    words = s.split()
    keep = [w for w in words if w not in {"to","via","am","pm","from","service","route"}]
    return " ".join(keep)

def match_school_names(bus_df: pd.DataFrame, student_df: pd.DataFrame, score_cutoff: int = 80) -> pd.DataFrame:
    bus_df = bus_df.copy()
    bus_df.columns = [c.lower() for c in bus_df.columns]

    student_cols = [c.lower() for c in student_df.columns]
    school_col = next((c for c in student_cols if "school" in c and "code" not in c), None) or \
                 ("school_name" if "school_name" in student_cols else None)
    if not school_col:
        raise ValueError("Could not find a 'school' column in Students Distance dataset.")

    school_names = sorted(set(student_df[school_col].dropna().astype(str)))
    normalized_targets = {name: normalize_name(name) for name in school_names}
    choices = list(normalized_targets.values())
    name_by_norm = {v: k for k, v in normalized_targets.items()}

    candidate_cols = [
        "trip_headsign","headsign","destination",
        "route_long_name","route_short_name","route_name","trip_short_name",
        "school","school_name","stop_name"
    ]
    present = [c for c in candidate_cols if c in bus_df.columns]
    if present:
        text_raw = bus_df[present].astype(str).fillna("").agg(" ".join, axis=1)
    else:
        text_raw = pd.Series([""] * len(bus_df), index=bus_df.index)

    bus_df["text_norm"] = text_raw.map(extract_candidate_school_from_headsign)

    stop_id_col = None
    for c in ["stop_id","stop_code","stopid","stopcode"]:
        if c in bus_df.columns:
            stop_id_col = c
            break

    matches = []
    for idx, row in bus_df.iterrows():
        q = row.get("text_norm", "")
        if not isinstance(q, str) or not q.strip():
            continue
        best = process.extractOne(q, choices, scorer=fuzz.WRatio)
        if not best:
            continue
        matched_norm, score = best[0], int(best[1])
        if score < score_cutoff:
            continue
        matched_school = name_by_norm[matched_norm]
        stop_id = row[stop_id_col] if stop_id_col else idx
        stop_name = row.get("stop_name", None)
        matches.append({"stop_id": str(stop_id), "stop_name": stop_name,
                        "matched_school": matched_school, "confidence": score})

    return pd.DataFrame(matches).drop_duplicates(subset=["stop_id","matched_school"])