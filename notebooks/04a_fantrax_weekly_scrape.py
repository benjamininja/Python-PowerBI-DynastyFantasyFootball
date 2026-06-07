# %% [markdown]
# # 04a_fantrax_weekly_scrape  (Playwright, weekly)
#
# **Purpose:** Authenticate to Fantrax via a headless browser and pull the full
# draft-ranking board (`getDraftRanks`) as a weekly snapshot for league
# `v744203wmmvjqzv6`. Replaces the dead UI export (disabled for duplicate-player
# leagues) and the brittle pasted-cookie approach.
#
# **Auth model:** Playwright persistent context. Log in ONCE (headful first run,
# to clear any Cloudflare/captcha); the session is stored in a user-data dir and
# reused on every scheduled run. If the stored session is dead, it re-logs in
# from creds in a gitignored `.env`. The authenticated `context.request.post`
# carries the session cookies, so we call the JSON API directly — no DOM scrape.
#
# **Schedule:** Windows Task Scheduler, Thursday ~06:00 CT. The run date maps to
# the just-completed NFL week (override with CFG.snapshot_week if needed).
#
# **Outputs:**
# - `data/raw/fantrax_draftranks_{season}_wk{NN}.json` — verbatim API response (audit/replay)
# - `data/fact_fantrax_adp.parquet` — parsed weekly board; grain = scorer_id x season x week.
#   Columns include overall_rank (Fantrax "Rk"), adp, salary, fpts, fpts_per_game,
#   age, percent_drafted. fpts/fpts_per_game are PHASE-AWARE: season projections
#   preseason, YTD actuals once the season starts (resolve_season_or_projection).
#
# **Stats not on this board:** games-played and the per-stat splits live only on the
# Players grid (method `getPlayerStats`, miscDisplayType=1, paged maxResultsPerPage
# up to 500). Validated for a future in-season GP/splits pull; not wired in yet.
#
# **Identity:** rows key on Fantrax `scorer_id`; `gsis_id` / `player_key` are joined
# from dim_fantrax_crosswalk (built by 04z). `age` is derived from dim_nfl_players
# via the crosswalk gsis_id — it's a registry attribute, not a board field.
#
# **Pipeline (one notebook, E+T+L):** scrape -> write raw JSON -> parse the ADP'd
# board (~280 of ~8600) -> append to the parquet fact, dedup on [scorer_id, season, week].
#
# **Setup:**
#   pip install playwright python-dotenv && playwright install chromium
#   .env  ->  FANTRAX_EMAIL=...   FANTRAX_PASSWORD=...      (gitignore .env)

# %%
# ---- Setup & Config ---------------------------------------------------------
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
import json
import os
import re

import pandas as pd


@dataclass
class LeagueConfig:
    """Central config — Fantrax API, auth, scheduling. Edit here only."""
    # --- Fantrax API (recovered from HAR) ---
    league_id: str = "v744203wmmvjqzv6"
    endpoint: str = "https://www.fantrax.com/fxpa/req"
    login_url: str = "https://www.fantrax.com/login"
    # Stat timeframe is phase-aware (see resolve_season_or_projection):
    # preseason runs capture the season projection; once Week 1 completes,
    # in-season runs capture year-to-date actuals (real FPts + games played).
    projection_code: str = "PROJECTION_0_23l_SEASON"   # "Projected - Season"
    ytd_code: str = "SEASON_23l_YEAR_TO_DATE"          # "Reg Season - YTD"
    ui_version: int = 3
    api_version: str = "182.4.8"          # 'v' field; bump when Fantrax updates UI
    timezone: str = "America/Chicago"
    ref_url: str = (
        "https://www.fantrax.com/fantasy/league/v744203wmmvjqzv6/draft-ranking;"
        "seasonOrProjection=SEASON_23l_YEAR_TO_DATE?sortKey=ADP&sortDir=-1"
        "&rookie=false&view=RANKING&groupId=1010&posId="
    )
    # --- Playwright / auth ---
    user_data_dir: str = "data/.pw_profile"   # persistent session lives here (gitignore)
    headless: bool = True                     # set False on first run to clear captcha
    nav_timeout_ms: int = 30_000
    # --- Scheduling / week derivation ---
    snapshot_season: int = 2026
    week1_thursday: str = "2026-09-10"        # TODO verify 2026 NFL Week-1 Thursday
    snapshot_week: int | str | None = None    # None=auto; int 1-18; or "PRE"
    preseason_label: str = "PRE"              # any run before Week-1 completes
    # --- Local paths ---
    data_dir: str = "data"
    raw_dir: str = "data/raw"
    fact_name: str = "fact_fantrax_adp"   # parquet fact: weekly ADP/salary snapshots
    crosswalk_name: str = "dim_fantrax_crosswalk"   # scorer_id -> gsis_id/player_key (built by 04z)
    # --- Players-grid backfill (getPlayerStats): real season actuals incl. GP ---
    # getDraftRanks lacks games-played and per-stat splits; the Players grid has
    # them but is paginated and position-group-scoped (the "ALL" group drops GP).
    # Used to backfill completed-season YTD actuals as a counterpoint to the
    # projection board (e.g. season=2025, week="YTD").
    players_page_size: int = 500
    players_misc_display: str = "1"                          # detailed view -> splits + GP
    players_pos_groups: tuple = ("FOOTBALL_OFFENSE", "FOOTBALL_DEFENSE")
    # --- Heuristics ---
    min_expected_rows: int = 50


CFG = LeagueConfig()

# Completed-season YTD `seasonOrProjection` codes (from the response's
# seasonOrProjections list). Used by backfill_player_stats to pull actuals.
YTD_SEASON_CODES = {
    2025: "SEASON_23j_YEAR_TO_DATE",   # 2025-26 Reg Season - YTD
    2024: "SEASON_23h_YEAR_TO_DATE",   # 2024-25 Reg Season - YTD
}


# %%
# ---- Week derivation --------------------------------------------------------
def derive_week_label(cfg: LeagueConfig, run_dt: date | None = None) -> str:
    """
    Map a run date to a week LABEL: cfg.preseason_label ("PRE") for any run
    before Week 1 completes, else zero-padded "01".."18".

    A regular week is 'complete' once its Monday-night slate is done. Week 1's
    Monday is (week1_thursday + 4 days). Before that first Monday the league is
    in preseason -> "PRE". Override with cfg.snapshot_week ("PRE" or an int).
    """
    if cfg.snapshot_week is not None:
        wk = cfg.snapshot_week
        return wk if isinstance(wk, str) else f"{wk:02d}"
    run_dt = run_dt or date.today()
    week1_monday = datetime.strptime(cfg.week1_thursday, "%Y-%m-%d").date() + timedelta(days=4)
    if run_dt < week1_monday:
        return cfg.preseason_label
    weeks = (run_dt - week1_monday).days // 7 + 1
    return f"{max(1, min(18, weeks)):02d}"


def resolve_season_or_projection(cfg: LeagueConfig, run_dt: date | None = None) -> str:
    """
    Phase-aware stat timeframe. Preseason (week label == preseason_label) ->
    season projection (projected FPts/FP-G/GP); in-season -> year-to-date
    actuals. This drives what getDraftRanks returns in statsAll[2]/[3].
    """
    week = derive_week_label(cfg, run_dt)
    return cfg.projection_code if week == cfg.preseason_label else cfg.ytd_code


# %%
# ---- Scraper ----------------------------------------------------------------
# Playwright imported lazily inside methods so this file still parses/imports
# in environments where Playwright isn't installed (e.g. the fact notebook).
class FantraxScraper:
    """
    Headless-browser scraper for the Fantrax draft-ranking board.

    Persistent context => log in once, reuse the session on scheduled runs.
    Credentials come from env (.env): FANTRAX_EMAIL / FANTRAX_PASSWORD.
    """

    def __init__(self, cfg: LeagueConfig = CFG):
        self.cfg = cfg
        Path(cfg.raw_dir).mkdir(parents=True, exist_ok=True)
        Path(cfg.user_data_dir).mkdir(parents=True, exist_ok=True)

    # --- auth -----------------------------------------------------------------
    def _creds(self) -> tuple[str, str]:
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ModuleNotFoundError:
            pass  # env vars may already be set by the OS/scheduler
        email = os.getenv("FANTRAX_EMAIL")
        pwd = os.getenv("FANTRAX_PASSWORD")
        if not email or not pwd:
            raise RuntimeError(
                "Set FANTRAX_EMAIL and FANTRAX_PASSWORD (in a gitignored .env "
                "or as scheduler env vars)."
            )
        return email, pwd

    @staticmethod
    def _session_dead(raw: dict) -> bool:
        """
        True if Fantrax rejected the call for auth reasons. Trust the server's
        verdict (WARNING_NOT_LOGGED_IN anywhere in the response) instead of
        guessing from the DOM — the draft-ranking page has no password field
        whether or not you're logged in, so a DOM check gives false positives.
        """
        def walk(node) -> bool:
            if isinstance(node, dict):
                if node.get("code") == "WARNING_NOT_LOGGED_IN":
                    return True
                return any(walk(v) for v in node.values())
            if isinstance(node, list):
                return any(walk(it) for it in node)
            return False
        return walk(raw)

    def _login(self, page) -> None:
        """
        Fill and submit the Fantrax login form. Selectors are resilient
        (type/placeholder fallbacks); a failure screenshot is saved for fast
        fixing if Fantrax changes the form.
        """
        email, pwd = self._creds()
        page.goto(self.cfg.login_url, wait_until="domcontentloaded",
                  timeout=self.cfg.nav_timeout_ms)
        try:
            # Angular Material form: target the reactive-form control names.
            # Submit via Enter to avoid the page's several icon submit-buttons.
            page.locator("input[formcontrolname='email']").fill(email)
            pw = page.locator("input[formcontrolname='password']")
            pw.fill(pwd)
            pw.press("Enter")
        except Exception:
            page.screenshot(path=f"{self.cfg.raw_dir}/login_debug.png")
            raise RuntimeError(
                "Login form interaction failed — see data/raw/login_debug.png "
                "and adjust selectors in _login()."
            )
        # SPA keeps connections open, so 'networkidle' never fires. Wait for the
        # login form to go away (navigation off /login); fall back to a short
        # settle. Auth is verified for real by the retry-probe in fetch().
        try:
            page.wait_for_url(lambda u: "/login" not in u,
                              timeout=self.cfg.nav_timeout_ms)
        except Exception:
            page.wait_for_timeout(3000)

    # --- payload --------------------------------------------------------------
    def _payload(self) -> dict:
        """Exact getDraftRanks request body (from HAR capture)."""
        return {
            "msgs": [
                {"method": "getDraftRanks",
                 "data": {"seasonOrProjection": resolve_season_or_projection(self.cfg)}},
                {"method": "getFantasyTeams", "data": {}},
            ],
            "uiv": self.cfg.ui_version,
            "refUrl": self.cfg.ref_url,
            "dt": 0, "at": 0,
            "tz": self.cfg.timezone,
            "v": self.cfg.api_version,
        }

    def _post_json(self, ctx, payload: dict, what: str = "request") -> dict:
        """POST an fxpa payload via the authenticated request context."""
        url = f"{self.cfg.endpoint}?leagueId={self.cfg.league_id}"
        resp = ctx.request.post(
            url, data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        if not resp.ok:
            raise RuntimeError(f"{what} HTTP {resp.status}")
        return resp.json()

    def _post_draftranks(self, ctx) -> dict:
        """POST getDraftRanks via the authenticated request context."""
        return self._post_json(ctx, self._payload(), "getDraftRanks")

    # --- players-grid (getPlayerStats) backfill ------------------------------
    def _player_stats_payload(self, season_code: str, timeframe: str,
                              pos_group: str, page_no: int) -> dict:
        """getPlayerStats request body for one position group + page."""
        return {
            "msgs": [{"method": "getPlayerStats", "data": {
                "statusOrTeamFilter": "ALL",
                "pageNumber": str(page_no),
                "maxResultsPerPage": str(self.cfg.players_page_size),
                "miscDisplayType": self.cfg.players_misc_display,
                "positionOrGroup": pos_group,
                "seasonOrProjection": season_code,
                "timeframeTypeCode": timeframe,
            }}],
            "uiv": self.cfg.ui_version, "refUrl": self.cfg.ref_url,
            "dt": 0, "at": 0, "tz": self.cfg.timezone, "v": self.cfg.api_version,
        }

    def fetch_player_stats(self, season_code: str, timeframe: str,
                           label: str) -> list:
        """
        Paginate getPlayerStats across position groups (the 'ALL' group omits GP,
        so we pull FOOTBALL_OFFENSE + FOOTBALL_DEFENSE and union). Returns every
        raw page response — each carries its own tableHeader for the parser — and
        writes a combined raw audit file. Self-heals auth like fetch().
        """
        from playwright.sync_api import sync_playwright
        responses = []
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                self.cfg.user_data_dir, headless=self.cfg.headless,
            )
            page = ctx.new_page()
            page.set_default_timeout(self.cfg.nav_timeout_ms)
            for pos_group in self.cfg.players_pos_groups:
                page_no = 1
                while True:
                    payload = self._player_stats_payload(
                        season_code, timeframe, pos_group, page_no)
                    raw = self._post_json(ctx, payload, "getPlayerStats")
                    if self._session_dead(raw):
                        self._login(page)
                        raw = self._post_json(ctx, payload, "getPlayerStats")
                    responses.append(raw)
                    prs = raw["responses"][0]["data"].get("paginatedResultSet", {})
                    total_pages = prs.get("totalNumPages", 1)
                    print(f"[info] {pos_group} page {page_no}/{total_pages}")
                    if page_no >= total_pages:
                        break
                    page_no += 1
            ctx.close()
        out = f"{self.cfg.raw_dir}/fantrax_playerstats_{label}.json"
        Path(out).write_text(json.dumps(responses, indent=2), encoding="utf-8")
        print(f"[ok] getPlayerStats {label}: {len(responses)} pages -> {out}")
        return responses

    # --- main entry -----------------------------------------------------------
    def fetch(self) -> dict:
        """
        Launch persistent context, POST getDraftRanks, and let the SERVER decide
        if auth is needed: if the response carries WARNING_NOT_LOGGED_IN, log in
        from .env creds and retry once. Persist week-stamped raw JSON, return it.
        """
        from playwright.sync_api import sync_playwright

        week = derive_week_label(self.cfg)
        out_path = (f"{self.cfg.raw_dir}/fantrax_draftranks_"
                    f"{self.cfg.snapshot_season}_wk{week}.json")

        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                self.cfg.user_data_dir, headless=self.cfg.headless,
            )
            page = ctx.new_page()
            page.set_default_timeout(self.cfg.nav_timeout_ms)

            raw = self._post_draftranks(ctx)
            if self._session_dead(raw):
                self._login(page)
                raw = self._post_draftranks(ctx)
                if self._session_dead(raw):
                    ctx.close()
                    raise RuntimeError(
                        "Still WARNING_NOT_LOGGED_IN after login. Check .env "
                        "creds, or run once with CFG.headless=False to clear a "
                        "Cloudflare/captcha gate (see data/raw/login_debug.png)."
                    )
            ctx.close()

        Path(out_path).write_text(json.dumps(raw, indent=2), encoding="utf-8")
        print(f"[ok] season={self.cfg.snapshot_season} week={week} -> {out_path}")
        return raw


# %%
# ---- Schema discovery (finalize field map from first real response) ---------
def summarize_schema(node, depth: int = 0, max_depth: int = 3):
    pad = "  " * depth
    if depth > max_depth:
        return
    if isinstance(node, dict):
        for k, v in node.items():
            extra = f" (len={len(v)})" if isinstance(v, (list, dict)) else ""
            print(f"{pad}{k}: {type(v).__name__}{extra}")
            summarize_schema(v, depth + 1, max_depth)
    elif isinstance(node, list) and node:
        print(f"{pad}[0] sample of {len(node)}:")
        summarize_schema(node[0], depth + 1, max_depth)


# Fallback defensive codes if dim_position isn't seeded yet (fresh clone /
# scheduled run before the dimension exists).
_IDP_POS_FALLBACK = {"DL", "LB", "DB", "EDGE", "CB", "S", "DT", "DE", "OLB", "ILB", "SS", "FS"}


def _idp_positions(cfg: LeagueConfig) -> set:
    """
    Defensive position codes, sourced from dim_position (single source of truth)
    so a new defensive code added there is picked up automatically. The hardcoded
    fallback is a strict subset, used only when dim_position.parquet is absent.
    """
    path = Path(cfg.data_dir) / "dim_position.parquet"
    if path.exists():
        try:
            dp = pd.read_parquet(path)
            codes = set(dp.loc[dp["side_of_ball"] == "Defense", "position_raw"].str.upper())
            if codes:
                return codes
        except Exception as e:
            print(f"[warn] could not read dim_position ({e}); using IDP fallback set")
    return set(_IDP_POS_FALLBACK)


# Resolved once at import; offense/IDP split in extract_ranked_board uses it.
_IDP_POS = _idp_positions(CFG)


def _is_idp(scorer: dict) -> bool:
    """True if all eligible positions are defensive (IDP)."""
    raw_pos = re.sub(r"<[^>]+>", "", scorer.get("posShortNames", ""))
    return bool(raw_pos) and all(p.strip() in _IDP_POS for p in raw_pos.split(","))


def extract_ranked_board(raw: dict) -> list[dict]:
    """
    Return the full board for this league: offense players with non-null ADP
    (Fantrax global ADP is offense-only) PLUS IDP players on real NFL rosters.

    IDP players have null ADP/percentOwned — Fantrax's global ADP reflects
    offense-only leagues. We still need them for salary, bye, Rk, and in-season
    FPts/FP/G. Filter: teamShortName != '(N/A)' identifies active-roster IDP
    players; '(N/A)' = cut/retired/unsigned.

    statsAll order: [bye, salary, score, fptsPerGame, adp, percentOwned].
    Offense rows sorted by ADP ascending; IDP rows appended (ADP null, no sort).
    """
    rows = raw["responses"][0]["data"]["fullStats"]

    offense = [r for r in rows
               if r.get("statsAll") and r["statsAll"][4] is not None
               and not _is_idp(r["scorer"])]
    offense.sort(key=lambda r: r["statsAll"][4])

    idp = [r for r in rows
           if _is_idp(r["scorer"])
           and r["scorer"].get("teamShortName", "(N/A)") != "(N/A)"]

    return offense + idp


# %%
# ---- Parse + load (board -> weekly parquet fact) ----------------------------
def _load_crosswalk(cfg: LeagueConfig) -> dict:
    """
    scorer_id -> (gsis_id, player_key) from dim_fantrax_crosswalk, if built.
    Missing file (first ever run) -> empty map; new scorer_ids stay null until
    04z_fantrax_crosswalk is (re)run to resolve them.
    """
    path = f"{cfg.data_dir}/{cfg.crosswalk_name}.parquet"
    if not Path(path).exists():
        return {}
    xw = pd.read_parquet(path)
    return {r.scorer_id: (r.gsis_id, r.player_key) for r in xw.itertuples()}


def _overall_rank_map(raw: dict) -> dict:
    """
    Reproduce Fantrax's "Rk" (ranking based on fantasy points among all players):
    rank the entire scorer pool by FPts (statsAll[2]) descending, 1-based.
    Players with no FPts are unranked (absent from the map -> null Rk). Ties keep
    response order. In-season this is YTD-actual rank; preseason it's projected.
    """
    rows = raw["responses"][0]["data"]["fullStats"]
    scored = [(r["scorer"]["scorerId"], r["statsAll"][2])
              for r in rows
              if r.get("statsAll") and r["statsAll"][2] is not None and r["statsAll"][2] > 0]
    scored.sort(key=lambda x: x[1], reverse=True)
    return {sid: i + 1 for i, (sid, _) in enumerate(scored)}


def _age_map(cfg: LeagueConfig, gsis_ids: set, as_of: date) -> dict:
    """
    gsis_id -> integer age (whole years) as of `as_of`, from
    dim_nfl_players.birth_date. Age is a player attribute (lives in the registry),
    not a Fantrax-board field — so we derive it via the crosswalk gsis_id rather
    than scraping a second endpoint. Missing registry/birth_date -> no entry.
    """
    path = f"{cfg.data_dir}/dim_nfl_players.parquet"
    if not Path(path).exists():
        return {}
    dp = pd.read_parquet(path, columns=["gsis_id", "birth_date"])
    dp = dp[dp["gsis_id"].isin(gsis_ids) & dp["birth_date"].notna()]
    bd = pd.to_datetime(dp["birth_date"], errors="coerce")
    out = {}
    for gid, b in zip(dp["gsis_id"], bd):
        if pd.isna(b):
            continue
        out[gid] = as_of.year - b.year - ((as_of.month, as_of.day) < (b.month, b.day))
    return out


def board_to_frame(raw: dict, cfg: LeagueConfig = CFG) -> pd.DataFrame:
    """
    Flatten the ranked board into the fact_fantrax_adp shape.

    Grain: one row per scorer_id x season x week. FKs gsis_id / player_key come
    from dim_fantrax_crosswalk when present (null for unresolved scorer_ids — run
    04z to extend the crosswalk).

    statsAll order: [bye, salary, fpts, fpts_per_game, adp, percent_owned].
    Phase-aware: fpts/fpts_per_game are season projections preseason, YTD actuals
    in-season (see resolve_season_or_projection). overall_rank reproduces Fantrax's
    "Rk"; age is derived from dim_nfl_players via the crosswalk gsis_id.
    """
    week = derive_week_label(cfg)
    today = date.today()
    today_iso = today.isoformat()
    xwalk = _load_crosswalk(cfg)
    rank_map = _overall_rank_map(raw)
    board = extract_ranked_board(raw)

    gsis_ids = {g for g, _ in (xwalk.get(r["scorer"]["scorerId"], (None, None)) for r in board) if g}
    age_map = _age_map(cfg, gsis_ids, today)

    recs = []
    for r in board:
        s = r["scorer"]
        sid = s["scorerId"]
        gsis, pkey = xwalk.get(sid, (None, None))
        stats = r["statsAll"]
        recs.append({
            "scorer_id":       sid,
            "season":          cfg.snapshot_season,
            "week":            week,
            "capture_date":    today_iso,
            "player_name":     s.get("name"),
            "position_raw":    re.sub(r"<[^>]+>", "", s.get("posShortNames", "")).strip(),
            "nfl_team":        s.get("teamShortName"),
            "is_rookie":       bool(s.get("rookie")),
            "overall_rank":    rank_map.get(sid),         # Fantrax "Rk" (by FPts, all players)
            "adp":             stats[4],
            "salary":          r.get("salary"),
            "percent_drafted": r.get("percentDrafted"),
            "fpts":            stats[2],                  # total fantasy points
            "fpts_per_game":   stats[3],                  # FP/G
            "games_played":    None,                      # not on the draft-ranks board (see backfill)
            "age":             age_map.get(gsis),         # from dim_nfl_players (via crosswalk)
            "gsis_id":         gsis,   # FK -> dim_nfl_players (via crosswalk)
            "player_key":      pkey,   # FK -> dim_rookie_prospect (via crosswalk)
        })
    return pd.DataFrame.from_records(recs)


def _cell_num(x):
    """Fantrax cell content -> float | None. Handles '1,234', '27.31', '78%', '-'."""
    if x is None:
        return None
    x = str(x).replace(",", "").replace("%", "").strip()
    if x in ("", "-"):
        return None
    try:
        return float(x)
    except ValueError:
        return None


def player_stats_to_frame(responses: list, cfg: LeagueConfig,
                          season: int, week: str) -> pd.DataFrame:
    """
    Flatten paginated getPlayerStats pages into the fact_fantrax_adp shape (same
    columns as board_to_frame, with games_played populated). Columns are read by
    header shortName (not fixed index) since splits differ by position group.

    Filter: active NFL roster only (teamShortName != '(N/A)'). Dual-eligible
    players appear in both position-group pulls -> first occurrence wins.
    overall_rank uses Fantrax's global scorer.rank; age comes straight from the
    grid's Age column (always present here, unlike the draft-ranks board).
    """
    today = date.today().isoformat()
    xwalk = _load_crosswalk(cfg)
    recs, seen = [], set()
    for resp in responses:
        d = resp["responses"][0]["data"]
        hdr = {c.get("shortName"): i for i, c in enumerate(d["tableHeader"]["cells"])}
        for r in d.get("statsTable", []):
            s = r["scorer"]
            if s.get("teamShortName", "(N/A)") == "(N/A)":
                continue
            sid = s["scorerId"]
            if sid in seen:
                continue
            seen.add(sid)
            cells = r["cells"]

            def col(name):
                i = hdr.get(name)
                return cells[i].get("content") if (i is not None and i < len(cells)) else None

            gsis, pkey = xwalk.get(sid, (None, None))
            age = _cell_num(col("Age"))
            gp = _cell_num(col("GP"))
            recs.append({
                "scorer_id":       sid,
                "season":          season,
                "week":            week,
                "capture_date":    today,
                "player_name":     s.get("name"),
                "position_raw":    re.sub(r"<[^>]+>", "", s.get("posShortNames", "")).strip(),
                "nfl_team":        s.get("teamShortName"),
                "is_rookie":       bool(s.get("rookie")),
                "overall_rank":    s.get("rank"),
                "adp":             _cell_num(col("ADP")),
                "salary":          _cell_num(col("Sal")),
                "percent_drafted": _cell_num(col("%D")),
                "fpts":            _cell_num(col("FPts")),
                "fpts_per_game":   _cell_num(col("FP/G")),
                "games_played":    int(gp) if gp is not None else None,
                "age":             int(age) if age is not None else None,
                "gsis_id":         gsis,
                "player_key":      pkey,
            })
    return pd.DataFrame.from_records(recs)


def backfill_player_stats(cfg: LeagueConfig, season: int, week: str = "YTD",
                          season_code: str | None = None,
                          timeframe: str = "YEAR_TO_DATE") -> pd.DataFrame:
    """
    Scrape getPlayerStats for a completed season and append its actuals (incl. GP)
    to fact_fantrax_adp as season=<season>, week=<week>. A real-data counterpoint
    to the projection board. season_code defaults to YTD_SEASON_CODES[season].
    """
    season_code = season_code or YTD_SEASON_CODES[season]
    label = f"{season}_{week}"
    responses = FantraxScraper(cfg).fetch_player_stats(season_code, timeframe, label)
    df = player_stats_to_frame(responses, cfg, season, week)
    path = load_fact(df, cfg)
    print(f"[ok] backfill season={season} week={week}: {len(df)} rows -> {path}")
    return df


def load_fact(df: pd.DataFrame, cfg: LeagueConfig = CFG) -> str:
    """
    Write this week's snapshot to the parquet fact with replace-by-(season, week):
    each run scrapes the whole board for the current week, so we drop any existing
    rows for the (season, week) pairs in `df` and append the fresh ones. This is
    truly idempotent (no orphan rows left behind when the board composition shifts
    between runs), unlike a plain key-level drop_duplicates.
    """
    path = f"{cfg.data_dir}/{cfg.fact_name}.parquet"
    if Path(path).exists():
        old = pd.read_parquet(path)
        # Migrate the pre-2026-06 schema: `score` was renamed to `fpts`.
        if "score" in old.columns and "fpts" not in old.columns:
            old = old.rename(columns={"score": "fpts"})
        keys = set(map(tuple, df[["season", "week"]].drop_duplicates().to_numpy()))
        mask = old[["season", "week"]].apply(tuple, axis=1).isin(keys)
        df = pd.concat([old[~mask], df], ignore_index=True)
    # Safety net for an identical re-run within the same partition.
    df = df.drop_duplicates(subset=["scorer_id", "season", "week"], keep="last")
    df.to_parquet(path, index=False)
    return path


# %%
# ---- Main -------------------------------------------------------------------
if __name__ == "__main__":
    raw = FantraxScraper(CFG).fetch()
    print("\n=== RESPONSE SCHEMA ===")
    summarize_schema(raw)
    board = extract_ranked_board(raw)
    total = len(raw["responses"][0]["data"]["fullStats"])
    n_off = sum(1 for r in board if r.get("statsAll") and r["statsAll"][4] is not None)
    n_idp = len(board) - n_off
    print(f"\n[info] {len(board)} players in board (offense ADP: {n_off}, IDP roster: {n_idp}) "
          f"out of {total} in pool")
    if n_off < CFG.min_expected_rows:
        print("[warn] few offense-ADP players — check seasonOrProjection / ADP "
              "availability in the Fantrax UI.")

    df = board_to_frame(raw)
    fact_path = load_fact(df)
    total_fact = len(pd.read_parquet(fact_path))
    print(f"[ok] snapshot {len(df)} rows -> {fact_path} ({total_fact} total in fact)")