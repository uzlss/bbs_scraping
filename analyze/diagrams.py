# analyze/diagrams.py
import os
import re
import ast
import logging
import unicodedata
from typing import Dict, Optional

import pandas as pd
import matplotlib
matplotlib.use("Agg")           # headless backend (no Tk needed)
import matplotlib.pyplot as plt
import geopandas as gpd
from pandas.api.types import is_scalar

logger = logging.getLogger(__name__)


# ==================== Text Normalization ====================
def _normalize_text(s: str) -> str:
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


# ==================== World Geometry (no deprecated datasets) ====================
def read_world_countries() -> gpd.GeoDataFrame:
    url = "https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson"
    return gpd.read_file(url)


def pick_country_name_column(world: gpd.GeoDataFrame) -> str:
    for c in ["ADMIN", "NAME_EN", "NAME", "name", "formal_en"]:
        if c in world.columns:
            return c
    for c in world.columns:
        if world[c].dtype == object:
            return c
    raise ValueError("Could not find a country name column in world dataset.")


def build_country_lookup(world: gpd.GeoDataFrame) -> Dict[str, str]:
    name_col = pick_country_name_column(world)
    candidate_cols = [name_col] + [
        c for c in world.columns if c != name_col and world[c].dtype == object
    ]

    lookup: Dict[str, str] = {}
    for _, row in world[candidate_cols].iterrows():
        canonical = str(row[name_col]).strip()
        if not canonical:
            continue

        for c in candidate_cols:
            val = row[c]
            if not is_scalar(val):
                continue
            s = str(val).strip()
            if not s or s.lower() in {"nan", "none"}:
                continue
            key = _normalize_text(s)
            if key:
                lookup[key] = canonical

        key_canon = _normalize_text(canonical)
        if key_canon:
            lookup[key_canon] = canonical

    return lookup


# ==================== CSV Loading ====================
def _parse_skills_cell(x) -> str:
    """
    Accepts:
      - a list -> join with commas
      - a string list repr, e.g. "['Python','Django']" -> parse with ast.literal_eval
      - a plain comma-separated string
    Returns a clean comma-separated string (may be empty).
    """
    if isinstance(x, list):
        return ", ".join(map(str, x))
    if isinstance(x, str):
        s = x.strip()
        if s.startswith("[") and s.endswith("]"):
            try:
                lst = ast.literal_eval(s)
                if isinstance(lst, list):
                    return ", ".join(map(str, lst))
            except Exception:
                pass
        return s
    return ""


def load_jobs_csv(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    expected = {"skills", "years_of_experience", "location"}
    missing = expected - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df["skills"] = df["skills"].apply(_parse_skills_cell).fillna("")
    df["location"] = df["location"].fillna("").astype(str)
    return df


# ==================== Country Inference ====================
def infer_country_from_location(
    location: str, country_lookup: Dict[str, str], *, allow_us_state_guess: bool = False
) -> Optional[str]:
    if not location:
        return None

    full_key = _normalize_text(location)
    if full_key in country_lookup:
        return country_lookup[full_key]

    tokens = [t.strip() for t in str(location).split(",") if t.strip()]
    for token in reversed(tokens):
        key = _normalize_text(token)
        if key in country_lookup:
            return country_lookup[key]
        if allow_us_state_guess and re.fullmatch(r"[A-Z]{2}", token):
            us_key = _normalize_text("United States")
            return country_lookup.get(us_key, "United States")

    return None


# ==================== Plots ====================
def plot_top_skills(df: pd.DataFrame, out_path: str, top_n: int = 10) -> str:
    all_skills = (
        df["skills"]
        .str.split(",")
        .explode()
        .astype(str)
        .str.strip()
        .replace("", pd.NA)
        .dropna()
    )
    top_skills = all_skills.value_counts().head(top_n)
    if top_skills.empty:
        raise ValueError("No skills found to plot.")

    plt.figure(figsize=(10, 6))
    top_skills.plot(kind="bar")
    plt.title(f"Top {top_n} Most In-Demand Skills")
    plt.xlabel("Skill")
    plt.ylabel("Number of Job Listings")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()
    return out_path


def plot_experience_levels(df: pd.DataFrame, out_path: str) -> str:
    exp = pd.to_numeric(df["years_of_experience"], errors="coerce").dropna().astype(int)
    exp_counts = exp.value_counts().sort_index()
    if exp_counts.empty:
        raise ValueError("No parsable 'years_of_experience' values to plot.")

    plt.figure(figsize=(8, 6))
    exp_counts.plot(kind="bar")
    plt.title("Years of Experience Required")
    plt.xlabel("Years")
    plt.ylabel("Number of Job Listings")
    plt.xticks(rotation=0)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()
    return out_path


def plot_country_heatmap(
    df: pd.DataFrame, out_path: str, *, allow_us_state_guess: bool = False
) -> str:
    world = read_world_countries()
    country_lookup = build_country_lookup(world)
    name_col = pick_country_name_column(world)

    countries = df["location"].apply(
        lambda loc: infer_country_from_location(
            loc, country_lookup, allow_us_state_guess=allow_us_state_guess
        )
    )
    df_countries = countries.dropna()
    if df_countries.empty:
        raise ValueError("No resolvable countries from 'location' values to plot.")

    country_counts = df_countries.value_counts()

    world["_join_name"] = world[name_col].astype(str).str.strip().str.lower()
    cc = country_counts.rename_axis("country").reset_index(name="job_count")
    cc["_join_name"] = cc["country"].str.strip().str.lower()

    world = world.merge(cc[["_join_name", "job_count"]], on="_join_name", how="left")

    ax = world.plot(
        column="job_count",
        cmap="OrRd",
        legend=True,
        figsize=(12, 8),
        missing_kwds={"color": "lightgrey", "label": "No data"},
        linewidth=0.2,
        edgecolor="black",
    )
    ax.set_axis_off()
    ax.set_title("Job Listings by Country", pad=12)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    return out_path


# ==================== Orchestrator ====================
def make_all_charts(
    csv_path: str, out_dir: str, *, allow_us_state_guess: bool = False
) -> None:
    """
    Save all outputs directly in out_dir (no subfolders).
    """
    os.makedirs(out_dir, exist_ok=True)
    df = load_jobs_csv(csv_path)

    logger.info("→ Building Top Skills…")
    logger.info(
        "   saved: %s", plot_top_skills(df, os.path.join(out_dir, "top_skills.png"))
    )

    logger.info("→ Building Experience Levels…")
    logger.info(
        "   saved: %s",
        plot_experience_levels(df, os.path.join(out_dir, "experience_levels.png")),
    )

    logger.info("→ Building Country Heatmap…")
    logger.info(
        "   saved: %s",
        plot_country_heatmap(
            df,
            os.path.join(out_dir, "location_heatmap.png"),
            allow_us_state_guess=allow_us_state_guess,
        ),
    )


if __name__ == "__main__":
    # Standalone run: show logs in console
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )
    # Example: put results in data/Developer/2025-08-07/
    make_all_charts(
        "../data/vibe_coder/2025-08-07/jobs.csv",
        out_dir="../data/vibe_coder/2025-08-07",
        allow_us_state_guess=False,
    )
