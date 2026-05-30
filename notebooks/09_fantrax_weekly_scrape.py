# %% [markdown]
# # 09_fantrax_weekly_scrape  (Playwright, weekly)
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
# - `data/fact_fantrax_adp.parquet` — parsed weekly board; grain = scorer_id x season x week
#
# **Identity:** rows key on Fantrax `scorer_id`; `gsis_id` / `player_key` are left
# null. A scorer_id -> player-registry crosswalk is a separate, later task.
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
    season_or_projection: str = "SEASON_23l_YEAR_TO_DATE"
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
    crosswalk_name: str = "dim_fantrax_crosswalk"   # scorer_id -> gsis_id/player_key (built by 09a)
    # --- Heuristics ---
    min_expected_rows: int = 50


CFG = LeagueConfig()


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
                 "data": {"seasonOrProjection": self.cfg.season_or_projection}},
                {"method": "getFantasyTeams", "data": {}},
            ],
            "uiv": self.cfg.ui_version,
            "refUrl": self.cfg.ref_url,
            "dt": 0, "at": 0,
            "tz": self.cfg.timezone,
            "v": self.cfg.api_version,
        }

    def _post_draftranks(self, ctx) -> dict:
        """POST getDraftRanks via the authenticated request context."""
        url = f"{self.cfg.endpoint}?leagueId={self.cfg.league_id}"
        resp = ctx.request.post(
            url, data=json.dumps(self._payload()),
            headers={"Content-Type": "application/json"},
        )
        if not resp.ok:
            raise RuntimeError(f"getDraftRanks HTTP {resp.status}")
        return resp.json()

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


_IDP_POS = {"DL", "LB", "DB", "EDGE", "CB", "S", "DT", "DE", "OLB", "ILB", "SS", "FS"}


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
    09a_fantrax_crosswalk is (re)run to resolve them.
    """
    path = f"{cfg.data_dir}/{cfg.crosswalk_name}.parquet"
    if not Path(path).exists():
        return {}
    xw = pd.read_parquet(path)
    return {r.scorer_id: (r.gsis_id, r.player_key) for r in xw.itertuples()}


def board_to_frame(raw: dict, cfg: LeagueConfig = CFG) -> pd.DataFrame:
    """
    Flatten the ranked ADP board into the fact_fantrax_adp shape.

    Grain: one row per scorer_id x season x week. FKs gsis_id / player_key are
    populated from dim_fantrax_crosswalk when present (null for any scorer_id not
    yet resolved — run 09a to extend the crosswalk).
    statsAll order: [bye, salary, score, fptsPerGame, adp, percentOwned].
    """
    week = derive_week_label(cfg)
    today = date.today().isoformat()
    xwalk = _load_crosswalk(cfg)
    recs = []
    for r in extract_ranked_board(raw):
        s = r["scorer"]
        gsis, pkey = xwalk.get(s["scorerId"], (None, None))
        recs.append({
            "scorer_id":       s["scorerId"],
            "season":          cfg.snapshot_season,
            "week":            week,
            "capture_date":    today,
            "player_name":     s.get("name"),
            "position_raw":    re.sub(r"<[^>]+>", "", s.get("posShortNames", "")).strip(),
            "nfl_team":        s.get("teamShortName"),
            "is_rookie":       bool(s.get("rookie")),
            "adp":             r["statsAll"][4],
            "salary":          r.get("salary"),
            "percent_drafted": r.get("percentDrafted"),
            "score":           r.get("score"),
            "gsis_id":         gsis,   # FK -> dim_nfl_players (via crosswalk)
            "player_key":      pkey,   # FK -> dim_rookie_prospect (via crosswalk)
        })
    return pd.DataFrame.from_records(recs)


def load_fact(df: pd.DataFrame, cfg: LeagueConfig = CFG) -> str:
    """
    Append this week's snapshot to the parquet fact and dedup on
    [scorer_id, season, week] keep='last' so re-running a week is idempotent.
    """
    path = f"{cfg.data_dir}/{cfg.fact_name}.parquet"
    if Path(path).exists():
        df = pd.concat([pd.read_parquet(path), df], ignore_index=True)
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