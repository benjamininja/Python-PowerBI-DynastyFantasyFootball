"""
etl_helpers.py — shared helpers for the dynasty fantasy football ETL pipeline.

Single source of truth for league config, name normalization, the player-key
hash, the HTTP session factory, and the rookie-ranking matcher/ingester. The
03x ranking notebooks, 03y/03z (alias + review apply), and the dimension seeds
import from here so the logic exists once.

Import pattern (notebooks run with CWD = repo root):

    import sys
    from pathlib import Path
    for _p in (Path.cwd() / "notebooks", Path.cwd()):
        if (_p / "etl_helpers.py").exists():
            sys.path.insert(0, str(_p)); break
    import etl_helpers as etl
    from etl_helpers import CFG, DATA, REVIEW, TODAY, ALIAS, clean_player_name, ...

Paths (DATA, REVIEW, ALIAS) are relative to CWD, so always run with CWD = repo root.
"""
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from thefuzz import fuzz, process


@dataclass
class LeagueConfig:
    """Central config — all league rules live here, nowhere else."""
    draft_year: int = 2026
    total_cap: int = 500_000_000
    num_teams: int = 28
    num_conferences: int = 2
    initial_contract_years: int = 3
    extension_contract_years: int = 3
    fa_minimum_salary: int = 2_000_000
    data_dir: str = "data"
    review_dir: str = "data/review"
    fuzzy_auto_threshold: int = 90
    fuzzy_review_threshold: int = 70
    # Optional extras used by specific notebooks:
    team_sheet_id: str = "1Fiz_KHH5bexSAHIfL0uVIqgHU6jTgnOmDs86kjR8TZc"
    team_sheet_gid: str = "178660131"


CFG    = LeagueConfig()
DATA   = Path(CFG.data_dir)
REVIEW = Path(CFG.review_dir)
TODAY  = date.today().isoformat()
ALIAS  = DATA / "dim_player_alias.parquet"   # persistent name->player_key decisions (03y/03z)
DATA.mkdir(exist_ok=True)
REVIEW.mkdir(parents=True, exist_ok=True)

# Default browser-like headers for scrapers (Chrome UA).
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# ── Name / key helpers ───────────────────────────────────────────────
def clean_player_name(name: str) -> str:
    # Normalize for matching: remove periods, collapse whitespace, lowercase.
    if pd.isna(name):
        return ""
    s = str(name).strip()
    s = s.replace(".", "").replace("\u00a0", " ")
    s = s.replace("\u2018", "'").replace("\u2019", "'").replace("`", "'")
    return " ".join(s.split()).lower()

def generate_player_key(name: str, position: str, school: str) -> str:
    # Deterministic 12-char MD5 hash -- matches keys generated in 01.
    raw = f"{clean_player_name(name)}|{str(position).upper().strip()}|{str(school).strip().lower()}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]

def parse_height_to_inches(ht_value) -> float | None:
    """
    Convert any height format to total inches.

    Handles:
      - Already numeric (assume inches if > 12, else feet)
      - "6'2\"" or "6'2" or "6'2"  ->  74
      - '6-2' or '6-02'            ->  74
      - '602' or '510' (NFL compact) ->  72 or 70
      - '6\' 2"' (space after foot) ->  74
      - None / NaN                  ->  None
    """
    if pd.isna(ht_value):
        return None

    # Already a number
    if isinstance(ht_value, (int, float)):
        if ht_value > 12:
            return float(ht_value)  # already inches
        else:
            return float(ht_value) * 12  # feet only

    s = str(ht_value).strip().replace("\\", "").replace('"', '').replace('\u00a0', ' ')

    # Try feet'inches pattern: 6'2, 6' 2
    for sep in ["'", "\u2019"]:
        if sep in s:
            parts = s.split(sep)
            try:
                feet = int(parts[0].strip())
                inches = int(parts[1].strip()) if parts[1].strip() else 0
                return float(feet * 12 + inches)
            except ValueError:
                continue

    # Try feet-inches: 6-2, 6-02
    if "-" in s:
        parts = s.split("-")
        try:
            feet = int(parts[0].strip())
            inches = int(parts[1].strip())
            return float(feet * 12 + inches)
        except ValueError:
            pass

    # Try NFL compact: '602' = 6ft 02in, '510' = 5ft 10in
    if s.isdigit() and len(s) == 3:
        feet = int(s[0])
        inches = int(s[1:])
        if inches < 12:
            return float(feet * 12 + inches)

    # Last resort: try direct numeric
    try:
        val = float(s)
        return val if val > 12 else val * 12
    except ValueError:
        return None

# ── Network ──────────────────────────────────────────────────────────
def _make_session(timeout_sec: int = 30, retries: int = 3, backoff: float = 2.0) -> requests.Session:
    # Shared session factory: retry on timeout/5xx with exponential backoff.
    # backoff waits: 2s, 4s, 8s between attempts.
    session = requests.Session()
    retry = Retry(
        total=retries,
        backoff_factor=backoff,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://",  adapter)
    return session

def _parse_rank_date(raw: str | None) -> str | None:
    # Parse the source-published "last updated" date into ISO format.
    # Returns None if raw is empty or unparseable (caller stores NULL).
    if not raw:
        return None
    raw = str(raw).strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return raw  # store as-is if no format matched

# ── Rookie-ranking matcher + ingester (canonical, alias-aware) ───────
def add_players_from_source(
    new_players_df: pd.DataFrame,
    source_name: str,
    draft_year: int = CFG.draft_year,
    auto_threshold: int = CFG.fuzzy_auto_threshold,
    review_threshold: int = CFG.fuzzy_review_threshold,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    # Fuzzy-match new player names against dim_rookie_prospect.
    # Returns (updated_dim_rookie_prospect, review_df).
    # new_players_df must have: player_name; optionally position_raw, school_raw.
    # NOTE: review_df is returned to caller -- file write is the caller's responsibility.
    dim_rp     = pd.read_parquet(DATA / "dim_rookie_prospect.parquet")
    pos_map    = pd.read_parquet(DATA / "dim_position.parquet")
    school_map = pd.read_parquet(DATA / "dim_school.parquet")

    existing_names  = dim_rp["player_name_clean"].tolist()
    existing_lookup = dict(zip(dim_rp["player_name_clean"], dim_rp["player_key"]))

    # Persistent decisions: (name_clean, position_raw) already resolved in a prior
    # review -> never ask again (dim_player_alias, built by 03y, appended by 03z).
    alias_keys = set()
    if ALIAS.exists():
        _al = pd.read_parquet(ALIAS)
        alias_keys = set(zip(_al["name_clean"], _al["position_raw"]))

    new_rows, review_rows, auto_alias_rows = [], [], []
    auto_matched = already_exists = alias_resolved = 0

    for _, row in new_players_df.iterrows():
        name_clean = clean_player_name(row["player_name"])
        pos_key    = str(row.get("position_raw", "")).upper().strip()

        if name_clean in existing_lookup:
            already_exists += 1
            continue

        # Already decided in a past review -> skip silently (no repeat review).
        if (name_clean, pos_key) in alias_keys:
            alias_resolved += 1
            continue

        best_match, score = ("", 0)
        if existing_names:
            best_match, score = process.extractOne(
                name_clean, existing_names, scorer=fuzz.token_sort_ratio
            )

        if score >= auto_threshold:
            # High-confidence auto-link. Record the alias so (a) ingest can attribute
            # this variant's ranking to the matched player_key instead of dropping it,
            # and (b) future runs skip it. Same fix as a manual "match" decision.
            auto_matched += 1
            mkey = existing_lookup.get(best_match, "")
            if mkey:
                auto_alias_rows.append({
                    "name_clean": name_clean, "position_raw": pos_key,
                    "player_key": mkey, "decision": "auto",
                    "source_example": source_name, "decided_date": TODAY,
                })
        elif score >= review_threshold:
            review_rows.append({
                "new_name":        row["player_name"],
                "new_name_clean":  name_clean,
                "new_position":    row.get("position_raw", ""),
                "new_school":      row.get("school_raw", ""),
                "best_match_name": best_match,
                "best_match_key":  existing_lookup.get(best_match, ""),
                "fuzzy_score":     score,
                "action":          "",  # fill: "match" or "new"
                "source":          source_name,
            })
        else:
            # New prospect -- add to dim_rookie_prospect
            pos_raw    = str(row.get("position_raw", "")).upper().strip()
            school_raw = str(row.get("school_raw", "")).strip()
            pos_match  = pos_map[pos_map["position_raw"] == pos_raw]
            sch_match  = school_map[school_map["school_raw"] == school_raw]
            pkey       = generate_player_key(row["player_name"], pos_raw, school_raw)
            new_rows.append({
                "player_key":        pkey,
                "player_name":       row["player_name"],
                "player_name_clean": name_clean,
                "position_raw":      pos_raw,
                "position_detail":   pos_match["position_detail"].iloc[0] if len(pos_match) else None,
                "position_group":    pos_match["position_group"].iloc[0]  if len(pos_match) else None,
                "side_of_ball":      pos_match["side_of_ball"].iloc[0]    if len(pos_match) else None,
                "fantasy_relevant":  pos_match["fantasy_relevant"].iloc[0] if len(pos_match) else False,
                "school_raw":        school_raw,
                "school_canonical":  sch_match["school_canonical"].iloc[0] if len(sch_match) else school_raw,
                "conference":        sch_match["conference"].iloc[0]       if len(sch_match) else "Unknown",
                "height_inches":     None,
                "weight":            None,
                "pfr_id":            None,
                "cfb_id":            None,
                "gsis_id":           pd.NA,
                "draft_year":        draft_year,
                "source":            source_name,
                "added_date":        TODAY,
            })
            existing_names.append(name_clean)
            existing_lookup[name_clean] = pkey

    if new_rows:
        dim_rp = pd.concat([dim_rp, pd.DataFrame(new_rows)], ignore_index=True)
        dim_rp.drop_duplicates(subset=["player_key"], inplace=True)
        dim_rp.to_parquet(DATA / "dim_rookie_prospect.parquet", index=False)

    # Persist auto-matches to the alias (append + dedup on the (name_clean, pos) key).
    if auto_alias_rows:
        aa = pd.DataFrame(auto_alias_rows)
        if ALIAS.exists():
            aa = pd.concat([pd.read_parquet(ALIAS), aa], ignore_index=True)
        aa.drop_duplicates(subset=["name_clean", "position_raw"], keep="last", inplace=True)
        aa.to_parquet(ALIAS, index=False)

    review_df = pd.DataFrame(review_rows) if review_rows else pd.DataFrame()

    print(f"Source: {source_name}")
    print(f"  Already in dim_rookie_prospect : {already_exists}")
    print(f"  Resolved via alias (no re-ask)  : {alias_resolved}")
    print(f"  Auto-matched (>={auto_threshold}) + aliased  : {auto_matched}")
    print(f"  New prospects added             : {len(new_rows)}")
    print(f"  Needs manual review             : {len(review_rows)}")

    return dim_rp, review_df

def ingest_ranking_source(
    rankings_df: pd.DataFrame,
    source_name: str,
    source_site: str,
    phase: str,
    draft_year: int = CFG.draft_year,
    capture_date: str = TODAY,
    rank_date: str | None = None,
) -> pd.DataFrame:
    # Append one row per player to fact_rookie_rankings for a given source + phase.
    # Call add_players_from_source() first to ensure all players are in dim_rookie_prospect.
    # Players pending review (not yet in dim_rookie_prospect) are logged as unmatched and skipped.
    #
    # rankings_df required columns: player_name, global_rank
    # rankings_df optional columns: positional_rank, grade

    valid_phases = {"pre_combine", "post_combine", "post_draft"}
    if phase not in valid_phases:
        raise ValueError(f"phase must be one of {valid_phases}")

    dim_rp = pd.read_parquet(DATA / "dim_rookie_prospect.parquet")
    name_to_key = dict(zip(dim_rp["player_name_clean"], dim_rp["player_key"]))
    key_to_pfr  = dict(zip(dim_rp["player_key"],        dim_rp["pfr_id"]))

    # Fold in alias decisions so a matched name-variant (X resolved to prospect Y)
    # attributes its ranking to Y's player_key instead of being dropped as unmatched.
    # setdefault: real dim_rookie_prospect names always win over an alias.
    if ALIAS.exists():
        _al = pd.read_parquet(ALIAS)
        for _nc, _pk in zip(_al["name_clean"], _al["player_key"]):
            name_to_key.setdefault(_nc, _pk)

    dim_nfl = pd.read_parquet(DATA / "dim_nfl_players.parquet")
    pfr_to_gsis = dict(zip(dim_nfl["pfr_id"].dropna(), dim_nfl["gsis_id"].dropna()))

    rows, unmatched = [], []
    for _, row in rankings_df.iterrows():
        name_clean = clean_player_name(row["player_name"])
        pkey = name_to_key.get(name_clean)

        if pkey is None:
            unmatched.append(row["player_name"])
            continue

        pfr_id  = key_to_pfr.get(pkey)
        gsis_id = pfr_to_gsis.get(pfr_id) if pfr_id else None

        rows.append({
            "player_key":      pkey,
            "gsis_id":         gsis_id,
            "source_name":     source_name,
            "source_site":     source_site,
            "phase":           phase,
            "draft_year":      draft_year,
            "global_rank":     row.get("global_rank"),
            "positional_rank": row.get("positional_rank"),
            "grade":           row.get("grade"),
            "capture_date":    capture_date,
            "rank_date":       rank_date,
        })

    if unmatched:
        print(f"  WARN: {len(unmatched)} players pending review -- re-run after apply_review_decisions():")
        for name in unmatched[:10]:
            print(f"    {name}")
        if len(unmatched) > 10:
            print(f"    ... and {len(unmatched) - 10} more")

    new_df = pd.DataFrame(rows)
    if new_df.empty:
        print("  No rows to append.")
        return new_df

    new_df["global_rank"]     = new_df["global_rank"].astype("Int64")
    new_df["positional_rank"] = new_df["positional_rank"].astype("Int64")
    new_df["draft_year"]      = new_df["draft_year"].astype("Int64")
    new_df["rank_date"]       = new_df["rank_date"].where(new_df["rank_date"].notna(), other=None)

    existing = pd.read_parquet(DATA / "fact_rookie_rankings.parquet")
    combined = pd.concat([existing, new_df], ignore_index=True)
    _DEDUP   = ["player_key", "source_name", "phase", "draft_year"]
    # rank_date: preserve the first non-null value ever captured — never overwrite with a later scrape.
    combined["rank_date"] = (
        combined.groupby(_DEDUP, sort=False)["rank_date"]
        .transform(lambda s: s.dropna().iloc[0] if s.notna().any() else None)
    )
    combined.drop_duplicates(subset=_DEDUP, keep="last", inplace=True)
    combined.to_parquet(DATA / "fact_rookie_rankings.parquet", index=False)

    print(f"  Ingested: {len(rows)} rows | source={source_name} | site={source_site} | phase={phase}")
    print(f"  fact_rookie_rankings total: {len(combined)}")
    return new_df

# ── Review file writer ───────────────────────────────────────────────

def append_review(reviews: list, path: Path | None = None) -> None:
    """Merge per-source review frames into the review CSV, preserving any
    already-filled `action` values (keep='first' on [new_name, source])."""
    if path is None:
        path = REVIEW / "review_fuzzy_matches.csv"
    path = Path(path)
    if not reviews:
        print("No fuzzy review items — all players matched cleanly.")
        return
    new = pd.concat(reviews, ignore_index=True)
    if path.exists():
        existing = pd.read_csv(path)
        new = pd.concat([existing, new], ignore_index=True)
        new.drop_duplicates(subset=["new_name", "source"], keep="first", inplace=True)
        new.to_csv(path, index=False)
        print(f"Review file updated: {len(new)} total rows -> {path}")
    else:
        new.to_csv(path, index=False)
        print(f"Review file created: {path} ({len(new)} rows)")


def resolve_dynasty_crosswalk(identities, data_dir="data", overrides=None,
                              auto_threshold=90, review_threshold=70, today=None):
    """Resolve dynasty-source player identities to registry keys for
    `dim_dynasty_crosswalk`. Single matcher shared by every section-04 dynasty
    source notebook (KTC 04b, manual 04x, ...) — do not re-implement per notebook.

    identities: DataFrame with columns source, source_player_id, player_name,
        position_raw, nfl_team.
    overrides:  optional {source_player_id: gsis_id} manual fixes (nickname vets,
        e.g. KTC 'Gabriel Davis' -> Gabe Davis). source_player_id compared as str.

    Returns a crosswalk DataFrame keyed (source, source_player_id):
        source, source_player_id, source_player_name, source_position, source_team,
        gsis_id, player_key, match_method, match_score, resolved_date.

    Matching mirrors the Fantrax crosswalk (04z): exact cleaned-name vs
    dim_nfl_players.display_name -> disambiguate by position / ACT / recency ->
    fuzzy >= auto_threshold (review_threshold..auto -> 'review', else 'unmatched').
    player_key from dim_rookie_prospect (rookie fallback); if no gsis but a
    player_key matches, method='rookie' (resolved, not a review item).
    """
    overrides = {str(k): v for k, v in (overrides or {}).items()}
    today = today or date.today().isoformat()
    _suffix = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")

    def _clean(name):
        if not isinstance(name, str):
            return ""
        n = name.lower().replace(".", "").replace("'", "").replace("’", "")
        n = _suffix.sub("", n)
        return re.sub(r"\s+", " ", n).strip()

    npl = pd.read_parquet(f"{data_dir}/dim_nfl_players.parquet").copy()
    rp = pd.read_parquet(f"{data_dir}/dim_rookie_prospect.parquet").copy()
    npl["name_clean"] = npl["display_name"].map(_clean)
    rp["name_clean"] = rp["player_name"].map(_clean)
    rp_lookup = (rp.dropna(subset=["name_clean"]).drop_duplicates("name_clean")
                   .set_index("name_clean")["player_key"].to_dict())
    npl_by_name = {n: g for n, g in npl.groupby("name_clean")}
    npl_names = list(npl_by_name.keys())

    def _disambig(cands, pos):
        df = cands
        if pos:
            m = (df["position"].str.upper() == pos) | (df["position_group"].str.upper() == pos)
            if m.any():
                df = df[m]
        if (df["status"] == "ACT").any():
            df = df[df["status"] == "ACT"]
        if "entry_year" in df and df["entry_year"].notna().any():
            df = df.sort_values("entry_year", ascending=False)
        return df.iloc[0]

    recs = []
    for r in identities.itertuples(index=False):
        spid = str(r.source_player_id)
        cn = _clean(r.player_name)
        pos = re.sub(r"\d+", "", str(r.position_raw)).upper().strip()  # 'QB1' -> 'QB'
        gsis, method, score = None, "unmatched", 0
        if spid in overrides:
            gsis, method, score = overrides[spid], "manual", 100
        elif cn in npl_by_name:
            cands = npl_by_name[cn]
            pick = cands.iloc[0] if len(cands) == 1 else _disambig(cands, pos)
            gsis = pick["gsis_id"]
            method, score = ("exact" if len(cands) == 1 else "exact+disambig"), 100
        elif npl_names:
            best_name, sc = process.extractOne(cn, npl_names, scorer=fuzz.token_sort_ratio)
            score = int(sc)
            if sc >= auto_threshold:
                gsis, method = _disambig(npl_by_name[best_name], pos)["gsis_id"], "fuzzy"
            elif sc >= review_threshold:
                method = "review"
        pkey = rp_lookup.get(cn)
        if gsis is None and pkey is not None and method in ("review", "unmatched"):
            method = "rookie"   # resolved via rookie registry — not a review item
        recs.append({
            # source_uid = single-column surrogate (source_player_id is NOT unique
            # across sources — slugs collide DS/FP). Use this for PBI relationships.
            "source_uid": f"{r.source}|{spid}",
            "source": r.source, "source_player_id": spid,
            "source_player_name": r.player_name, "source_position": r.position_raw,
            "source_team": getattr(r, "nfl_team", None),
            "gsis_id": gsis, "player_key": pkey,
            "match_method": method, "match_score": score, "resolved_date": today,
        })
    return pd.DataFrame.from_records(recs)
