# %% [markdown]
# # 02 — Seed Remaining Star-Schema Tables
#
# **Purpose**: Build and persist all star-schema tables not created in notebook 01.
#
# **Outputs**:
# - `data/dim_contract.parquet` — contract scale definitions derived from LeagueConfig
# - dim_nfl_players
# - dim_position
# - dim_school
# - `data/dim_team.parquet` — 28-team placeholder seed (update owners/names before draft)
# - `data/fact_combine_metrics.parquet` — full athletic measurements from nflverse combine
# - `data/fact_team.parquet` — empty roster fact (schema seed, populated by draft notebook)
# - `data/fact_rookie_rankings.parquet` — empty rankings fact (schema seed, populated by rankings notebook)

# %% [markdown]
# ## Setup & Config

# %%
import pandas as pd
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


@dataclass
class LeagueConfig:
    """Central config — all league rules live here, nowhere else."""
    draft_year: int = 2026
    total_cap: int = 300_000_000
    num_teams: int = 28
    num_conferences: int = 2
    initial_contract_years: int = 3
    resign_eligible_year: int = 2          # can re-sign end of year 2
    resign_contract_years: int = 3         # new 3-year term on re-sign
    cap_hit_pct: dict = field(default_factory=lambda: {1: 0.50, 2: 0.40, 3: 0.00})
    dead_money_applies: bool = True        # dropped player cap still hits books
    data_dir: str = "data"
    fuzzy_auto_threshold: int = 90
    fuzzy_review_threshold: int = 70
    nflverse_combine_url: str = (
        "https://github.com/nflverse/nflverse-data/"
        "releases/download/combine/combine.csv"
    )


CFG = LeagueConfig()
DATA = Path(CFG.data_dir)
TODAY = date.today().isoformat()


def parse_height_to_inches(ht_value) -> float | None:
    """
    Convert any height format to total inches.
    Handles: numeric, "6'2\"", "6-2", "602" compact, None/NaN.
    Copied from 01_dim_nfl_players_seed so this notebook runs standalone.
    """
    if pd.isna(ht_value):
        return None
    if isinstance(ht_value, (int, float)):
        return float(ht_value) if ht_value > 12 else float(ht_value) * 12
    s = str(ht_value).strip().replace("\\", "").replace('"', "").replace(" ", " ")
    for sep in ["'", "’"]:
        if sep in s:
            parts = s.split(sep)
            try:
                return float(int(parts[0].strip()) * 12 + int(parts[1].strip() or 0))
            except ValueError:
                continue
    if "-" in s:
        parts = s.split("-")
        try:
            return float(int(parts[0].strip()) * 12 + int(parts[1].strip()))
        except ValueError:
            pass
    if s.isdigit() and len(s) == 3 and int(s[1:]) < 12:
        return float(int(s[0]) * 12 + int(s[1:]))
    try:
        val = float(s)
        return val if val > 12 else val * 12
    except ValueError:
        return None


# %% [markdown]
# ## 1 — dim_contract
#
# Two rows: one for initial rookie contracts, one for re-sign contracts.
# All percentages and terms come from LeagueConfig — never hardcoded below.

# %%
def build_dim_contract(cfg: LeagueConfig) -> pd.DataFrame:
    """Generate one row per contract type from LeagueConfig."""
    rows = []
    for contract_type, total_years in [
        ("initial", cfg.initial_contract_years),
        ("resign",  cfg.resign_contract_years),
    ]:
        rows.append({
            "contract_id":          f"{contract_type}_{cfg.draft_year}",
            "contract_type":        contract_type,
            "total_years":          total_years,
            "year_1_pct":           cfg.cap_hit_pct[1],
            "year_2_pct":           cfg.cap_hit_pct[2],
            "year_3_pct":           cfg.cap_hit_pct[3],
            "resign_eligible_year": cfg.resign_eligible_year,
            "dead_money_applies":   cfg.dead_money_applies,
            "effective_season":     cfg.draft_year,
        })
    df = pd.DataFrame(rows)
    df.to_parquet(DATA / "dim_contract.parquet", index=False)
    print(f"dim_contract: {len(df)} rows -> data/dim_contract.parquet")
    return df


dim_contract = build_dim_contract(CFG)
dim_contract

# %% [markdown]
# ## 2 — dim_team
#
# Placeholder seed for all 28 teams (14 per conference).
# **Edit `team_name` and `owner` before the draft.** The parquet file is the
# source of truth — update it directly or add a CSV-import cell pointing to
# a sheet your league managers fill out.

# %%
def build_dim_team(cfg: LeagueConfig) -> pd.DataFrame:
    """
    Generate placeholder team rows, one per team.
    teams_per_conf derived from cfg so the count stays consistent with LeagueConfig.
    """
    teams_per_conf = cfg.num_teams // cfg.num_conferences
    rows = [
        {
            "team_key":   f"{conf}{i:02d}",
            "team_name":  f"Team {conf}{i:02d}",
            "conference": conf,
            "owner":      "TBD",
            "total_cap":  cfg.total_cap,
        }
        for conf in ["A", "B"]
        for i in range(1, teams_per_conf + 1)
    ]
    df = pd.DataFrame(rows)
    df.to_parquet(DATA / "dim_team.parquet", index=False)
    print(f"dim_team: {len(df)} rows -> data/dim_team.parquet")
    return df


dim_team = build_dim_team(CFG)
dim_team

# %% [markdown]
# ## 3 — fact_combine_metrics
#
# Full athletic measurements from the nflverse combine CSV.
# Joins to `dim_nfl_players` via `pfr_id` to attach `player_key`.
#
# **Columns not in nflverse** (`ten_split`, `hand_size`, `arm_length`, `wingspan`)
# are kept as NA — populate from pro-day scraping notebooks when available.
#
# **Coverage note**: 54 of 319 2026 invitees have no pfr_id in nflverse and will
# not appear here. They can be added via the pro-day source path.

# %%
# nflverse combine.csv column -> fact_combine_metrics schema column
_NFLVERSE_COL_MAP = {
    "ht":         "_ht_raw",      # parsed via parse_height_to_inches
    "wt":         "weight",
    "forty":      "forty_yard",
    "bench":      "bench_press",
    "vertical":   "vertical_jump",
    "broad_jump": "broad_jump",
    "cone":       "three_cone",
    "shuttle":    "shuttle",
}

# Columns that may exist in future nflverse builds but aren't present today
_OPTIONAL_NFLVERSE_COLS = {
    "ten_split":  "ten_split",
    "hand_size":  "hand_size",
    "arm_length": "arm_length",
    "wingspan":   "wingspan",
}

_FACT_COMBINE_SCHEMA = [
    "player_key", "draft_year", "metric_source",
    "height_inches", "weight",
    "forty_yard", "ten_split",
    "bench_press", "vertical_jump", "broad_jump",
    "three_cone", "shuttle",
    "hand_size", "arm_length", "wingspan",
]


def build_fact_combine_metrics(cfg: LeagueConfig) -> pd.DataFrame:
    """
    Pull nflverse combine CSV, filter to draft_year season, map column names,
    and join player_key from dim_nfl_players via pfr_id.
    Players without a pfr_id in both sources are excluded and noted in output.
    """
    print(f"Fetching nflverse combine data for {cfg.draft_year}...")
    raw = pd.read_csv(cfg.nflverse_combine_url)
    year_raw = raw[raw["season"] == cfg.draft_year].copy()
    print(f"  nflverse records: {len(year_raw)}")

    # Rename known columns; include any optional columns present in this build
    col_map = {
        **_NFLVERSE_COL_MAP,
        **{k: v for k, v in _OPTIONAL_NFLVERSE_COLS.items() if k in year_raw.columns},
    }
    src_cols = ["pfr_id"] + [c for c in col_map if c in year_raw.columns]
    metrics = year_raw[src_cols].rename(columns=col_map).copy()

    # Parse height from its raw string format ("6-5" -> 77.0)
    if "_ht_raw" in metrics.columns:
        metrics["height_inches"] = metrics["_ht_raw"].apply(parse_height_to_inches)
        metrics.drop(columns=["_ht_raw"], inplace=True)

    # Join player_key from dim_nfl_players via pfr_id
    dim_nfl_players = pd.read_parquet(DATA / "dim_nfl_players.parquet")
    key_lookup = (
        dim_nfl_players[["player_key", "pfr_id", "draft_year"]]
        .dropna(subset=["pfr_id"])
        .drop_duplicates(subset=["pfr_id"])
    )
    metrics = metrics.merge(key_lookup, on="pfr_id", how="inner")
    metrics["metric_source"] = "combine"

    # Ensure all schema columns exist (NA for columns not in nflverse yet)
    for col in _FACT_COMBINE_SCHEMA:
        if col not in metrics.columns:
            metrics[col] = pd.NA

    result = metrics[_FACT_COMBINE_SCHEMA].copy()
    result.to_parquet(DATA / "fact_combine_metrics.parquet", index=False)

    unmatched = len(year_raw) - len(result)
    print(f"  Matched to dim_nfl_players: {len(result)}")
    print(f"  Unmatched (no shared pfr_id): {unmatched}")
    print(f"fact_combine_metrics: {len(result)} rows -> data/fact_combine_metrics.parquet")
    return result


fact_combine_metrics = build_fact_combine_metrics(CFG)
fact_combine_metrics.head()

# %% [markdown]
# ## 4 — fact_team (empty schema seed)
#
# Schema-only file. The draft notebook populates this once picks are made.
# Nullable integer columns use pandas `Int64` (capital I) to support NA.

# %%
fact_team = pd.DataFrame({
    "team_key":        pd.Series(dtype="str"),
    "player_key":      pd.Series(dtype="str"),
    "conference":      pd.Series(dtype="str"),
    "contract_id":     pd.Series(dtype="str"),
    "contract_value":  pd.Series(dtype="Int64"),
    "contract_year":   pd.Series(dtype="Int64"),
    "cap_hit":         pd.Series(dtype="Int64"),
    "dead_money":      pd.Series(dtype="Int64"),
    "status":          pd.Series(dtype="str"),
    "acquired_method": pd.Series(dtype="str"),
    "season":          pd.Series(dtype="Int64"),
})
fact_team.to_parquet(DATA / "fact_team.parquet", index=False)
print("fact_team: empty schema seed -> data/fact_team.parquet")
fact_team.dtypes

# %% [markdown]
# ## 5 — fact_rookie_rankings (empty schema seed)
#
# Schema-only file. Expert ranking notebooks populate this in long/narrow format:
# one row per player × source × phase.

# %%
fact_rookie_rankings = pd.DataFrame({
    "player_key":      pd.Series(dtype="str"),
    "source":          pd.Series(dtype="str"),
    "phase":           pd.Series(dtype="str"),
    "draft_year":      pd.Series(dtype="Int64"),
    "global_rank":     pd.Series(dtype="Int64"),
    "positional_rank": pd.Series(dtype="Int64"),
    "grade":           pd.Series(dtype="float64"),
    "capture_date":    pd.Series(dtype="str"),
})
fact_rookie_rankings.to_parquet(DATA / "fact_rookie_rankings.parquet", index=False)
print("fact_rookie_rankings: empty schema seed -> data/fact_rookie_rankings.parquet")
fact_rookie_rankings.dtypes

# %% [markdown]
# ## 6 — Validation

# %%
_ALL_TABLES = {
    "dim_nfl_players":           DATA / "dim_nfl_players.parquet",
    "dim_position":         DATA / "dim_position.parquet",
    "dim_school":           DATA / "dim_school.parquet",
    "dim_contract":         DATA / "dim_contract.parquet",
    "dim_team":             DATA / "dim_team.parquet",
    "fact_combine_metrics": DATA / "fact_combine_metrics.parquet",
    "fact_team":            DATA / "fact_team.parquet",
    "fact_rookie_rankings":        DATA / "fact_rookie_rankings.parquet",
}

print(f"{'Table':<25} {'Rows':>6}  {'Cols':>4}  {'File size':>10}")
print("-" * 52)
for name, path in _ALL_TABLES.items():
    df = pd.read_parquet(path)
    size_kb = path.stat().st_size / 1024
    print(f"{name:<25} {len(df):>6}  {len(df.columns):>4}  {size_kb:>8.1f} KB")

# Referential integrity: every fact_combine_metrics player_key must be in dim_nfl_players
print()
dim_pk = set(pd.read_parquet(DATA / "dim_nfl_players.parquet")["player_key"])
fcm_pk = set(pd.read_parquet(DATA / "fact_combine_metrics.parquet")["player_key"])
orphans = fcm_pk - dim_pk
if orphans:
    print(f"WARN: {len(orphans)} orphaned player_keys in fact_combine_metrics")
else:
    print("OK: All fact_combine_metrics player_keys resolve to dim_nfl_players")
