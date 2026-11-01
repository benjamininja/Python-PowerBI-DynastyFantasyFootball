-- registry_state sha256: 1983a988a002a2f946f3db60549b8f4ca975198bbcf954026d86d371de4845de

CREATE SCHEMA football;

CREATE SCHEMA shared;

CREATE SCHEMA ops;

DO $do$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'etl_writer') THEN
        CREATE ROLE etl_writer LOGIN NOBYPASSRLS;
    END IF;
END
$do$;

DO $do$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'etl_reader') THEN
        CREATE ROLE etl_reader LOGIN NOBYPASSRLS;
    END IF;
END
$do$;

CREATE TABLE football.dim_contract (
    contract_id text NOT NULL,
    contract_type text,
    contract_label text,
    salary_type text,
    contract_year integer,
    total_years integer,
    cap_hit_pct double precision,
    guaranteed boolean,
    cap_exempt boolean,
    min_salary double precision,
    notes text,
    CONSTRAINT dim_contract_pkey PRIMARY KEY (contract_id)
);

CREATE TABLE football.dim_division (
    season_id text NOT NULL,
    conference text NOT NULL,
    division_name text NOT NULL,
    CONSTRAINT dim_division_pkey PRIMARY KEY (season_id, conference)
);

CREATE TABLE football.dim_dynasty_crosswalk (
    source text,
    source_player_id text,
    source_player_name text,
    source_position text,
    source_team text,
    gsis_id text,
    player_key text,
    match_method text,
    match_score integer,
    resolved_date date,
    source_uid text NOT NULL,
    CONSTRAINT dim_dynasty_crosswalk_pkey PRIMARY KEY (source_uid)
);

CREATE TABLE football.dim_dynasty_metric (
    metric_key text NOT NULL,
    metric_label text,
    metric_group text,
    metric_order integer,
    value_type text,
    direction text,
    source_name text,
    CONSTRAINT dim_dynasty_metric_pkey PRIMARY KEY (metric_key)
);

CREATE TABLE football.dim_fantasy_teams (
    team_key text NOT NULL,
    team_name text,
    team_abbr text,
    fantrax_team_id text,
    conference text,
    division text,
    original_cap integer,
    reinvestment_cap integer,
    CONSTRAINT dim_fantasy_teams_pkey PRIMARY KEY (team_key)
);

CREATE TABLE football.dim_fantrax_crosswalk (
    scorer_id text NOT NULL,
    player_name text,
    position_raw text,
    nfl_team text,
    is_rookie boolean,
    gsis_id text,
    player_key text,
    match_method text,
    match_score integer,
    resolved_date date,
    CONSTRAINT dim_fantrax_crosswalk_pkey PRIMARY KEY (scorer_id)
);

CREATE TABLE football.dim_nfl_players (
    gsis_id text NOT NULL,
    display_name text,
    first_name text,
    last_name text,
    birth_date date,
    status text,
    team_abbr text,
    position text,
    position_group text,
    jersey_number text,
    years_of_experience integer,
    college_name text,
    college_conference text,
    entry_year integer,
    last_season integer,
    draft_year integer,
    draft_club text,
    draft_round integer,
    draft_number integer,
    height double precision,
    weight integer,
    pfr_id text,
    pff_id text,
    espn_id text,
    esb_id text,
    nfl_id text,
    otc_id text,
    smart_id text,
    CONSTRAINT dim_nfl_players_pkey PRIMARY KEY (gsis_id)
);

CREATE TABLE football.dim_nfl_teams (
    team_abbr text NOT NULL,
    team_name text,
    team_id_pfr text,
    team_conf text,
    team_division text,
    team_color text,
    team_color2 text,
    team_logo_wikipedia text,
    team_logo_espn text,
    team_wordmark text,
    team_stadium text,
    CONSTRAINT dim_nfl_teams_pkey PRIMARY KEY (team_abbr)
);

CREATE TABLE football.dim_pick_value_curve (
    snapshot_date timestamp NOT NULL,
    source_name text NOT NULL,
    draft_year integer NOT NULL,
    round integer NOT NULL,
    tier text NOT NULL,
    value double precision,
    CONSTRAINT dim_pick_value_curve_pkey PRIMARY KEY (snapshot_date, source_name, draft_year, round, tier)
);

CREATE TABLE football.dim_player_alias (
    name_clean text NOT NULL,
    position_raw text NOT NULL,
    player_key text,
    decision text,
    source_example text,
    decided_date date,
    CONSTRAINT dim_player_alias_pkey PRIMARY KEY (name_clean, position_raw)
);

CREATE TABLE football.dim_position (
    position_raw text NOT NULL,
    position_detail text,
    position_group text,
    position_sort_order integer,
    side_of_ball text,
    side_of_ball_sort_order integer,
    fantasy_relevant boolean,
    CONSTRAINT dim_position_pkey PRIMARY KEY (position_raw)
);

CREATE TABLE football.dim_position_ceiling (
    snapshot_date timestamp NOT NULL,
    conference text NOT NULL,
    position_group text NOT NULL,
    pool_size integer,
    n_rostered double precision,
    n_free_agents double precision,
    max_fpts double precision,
    replacement_fpts double precision,
    best_free_agent text,
    vor double precision,
    ceiling double precision,
    source_season integer,
    source_week text,
    CONSTRAINT dim_position_ceiling_pkey PRIMARY KEY (snapshot_date, conference, position_group)
);

CREATE TABLE football.dim_rookie_prospect (
    player_key text NOT NULL,
    player_name text,
    player_name_clean text,
    position_raw text,
    position_detail text,
    position_group text,
    side_of_ball text,
    fantasy_relevant boolean,
    school_raw text,
    school_canonical text,
    conference text,
    height_inches double precision,
    weight integer,
    pfr_id text,
    cfb_id text,
    gsis_id text,
    draft_year integer,
    source text,
    added_date date,
    CONSTRAINT dim_rookie_prospect_pkey PRIMARY KEY (player_key)
);

CREATE TABLE football.dim_roster_asset (
    asset_id integer NOT NULL,
    asset_type text,
    scorer_id text,
    gsis_id text,
    player_key text,
    pick_ref text,
    CONSTRAINT dim_roster_asset_pkey PRIMARY KEY (asset_id)
);

CREATE TABLE football.dim_school (
    school_raw text NOT NULL,
    school_canonical text,
    school_abbr text,
    conference text,
    CONSTRAINT dim_school_pkey PRIMARY KEY (school_raw)
);

CREATE TABLE football.dim_scoring_period (
    season_id text NOT NULL,
    period integer NOT NULL,
    start_date timestamp NOT NULL,
    end_date timestamp NOT NULL,
    start_at timestamptz NOT NULL,
    end_at timestamptz NOT NULL,
    is_playoff boolean NOT NULL,
    update_set_state text,
    closed_at timestamptz,
    CONSTRAINT dim_scoring_period_pkey PRIMARY KEY (season_id, period)
);

CREATE TABLE football.dim_season (
    season_id text NOT NULL,
    season_start_year integer,
    season_end_year integer,
    season_fantasy_start_date timestamp,
    season_fantasy_end_date timestamp,
    season_nfl_start_date timestamp,
    season_nfl_end_date timestamp,
    theme text,
    relative_nfl_season_number integer,
    CONSTRAINT dim_season_pkey PRIMARY KEY (season_id)
);

CREATE TABLE football.fact_dead_money (
    transaction_id text NOT NULL,
    scorer_id text NOT NULL,
    team_key text NOT NULL,
    season_id text NOT NULL,
    drop_date timestamp NOT NULL,
    drop_period integer,
    gsis_id text,
    contract_id text NOT NULL,
    contract_value double precision NOT NULL,
    charge_contract_id text NOT NULL,
    cap_hit_pct double precision NOT NULL,
    dead_money double precision NOT NULL,
    contract_source text NOT NULL,
    CONSTRAINT fact_dead_money_pkey PRIMARY KEY (transaction_id, scorer_id, team_key, season_id)
);

CREATE TABLE football.fact_draft_pick (
    pick_ref text NOT NULL,
    draft_season text,
    round integer,
    pick_in_round integer,
    overall_slot integer,
    original_owner text,
    division_id text,
    current_owner text,
    is_made boolean,
    draft_type text,
    CONSTRAINT fact_draft_pick_pkey PRIMARY KEY (pick_ref)
);

CREATE TABLE football.fact_draft_pick_future (
    pick_ref text NOT NULL,
    draft_season text,
    round integer,
    pick_in_round integer,
    overall_slot integer,
    original_owner text,
    division_id text,
    current_owner text,
    is_made boolean,
    is_slotted boolean,
    draft_type text,
    CONSTRAINT fact_draft_pick_future_pkey PRIMARY KEY (pick_ref)
);

CREATE TABLE football.fact_dynasty_ranking_metrics (
    snapshot_date timestamp NOT NULL,
    source_name text NOT NULL,
    source_player_id text NOT NULL,
    format text NOT NULL,
    source_uid text,
    gsis_id text,
    metric_key text NOT NULL,
    metric_num double precision,
    metric_text text,
    CONSTRAINT fact_dynasty_ranking_metrics_pkey PRIMARY KEY (snapshot_date, source_name, source_player_id, format, metric_key),
    CONSTRAINT fact_dynasty_ranking_metrics_chk_b598208a CHECK (metric_num IS NOT NULL OR metric_text IS NOT NULL)
);

CREATE TABLE football.fact_fantasy_teams (
    team_key text NOT NULL,
    scorer_id text NOT NULL,
    gsis_id text,
    player_key text,
    contract_id text,
    contract_value double precision,
    contract_year integer,
    cap_hit double precision,
    cap_exempt boolean,
    acquired_method text,
    acquired_date timestamp,
    roster_slot text,
    season text,
    roster_captured_at timestamptz,
    ledger_captured_at timestamptz,
    CONSTRAINT fact_fantasy_teams_pkey PRIMARY KEY (team_key, scorer_id)
);

CREATE TABLE football.fact_fantrax_adp (
    scorer_id text NOT NULL,
    season integer NOT NULL,
    week text NOT NULL,
    capture_date date,
    player_name text,
    position_raw text,
    nfl_team text,
    is_rookie boolean,
    overall_rank double precision,
    adp double precision,
    salary double precision,
    percent_drafted double precision,
    fpts double precision,
    fpts_per_game double precision,
    games_played integer,
    age double precision,
    gsis_id text,
    player_key text,
    CONSTRAINT fact_fantrax_adp_pkey PRIMARY KEY (scorer_id, season, week)
);

CREATE TABLE football.fact_matchup (
    season_id text NOT NULL,
    period integer NOT NULL,
    team_key text NOT NULL,
    opponent_team_key text NOT NULL,
    is_home boolean NOT NULL,
    fpts_for double precision NOT NULL,
    fpts_against double precision NOT NULL,
    capture_date timestamp NOT NULL,
    CONSTRAINT fact_matchup_pkey PRIMARY KEY (season_id, period, team_key)
);

CREATE TABLE football.fact_minor_eligibility (
    scorer_id text NOT NULL,
    player_name text,
    position_raw text,
    nfl_team text,
    fa_status text,
    salary double precision,
    contract text,
    games_played integer,
    season integer NOT NULL,
    week text NOT NULL,
    capture_date date,
    CONSTRAINT fact_minor_eligibility_pkey PRIMARY KEY (scorer_id, season, week)
);

CREATE TABLE football.fact_nfl_combine_pro_day_metrics (
    pfr_id text NOT NULL,
    season integer NOT NULL,
    gsis_id text,
    player_key text,
    is_current_season boolean,
    cfb_id text,
    player_name text,
    pos text,
    school text,
    draft_team text,
    draft_round integer,
    draft_ovr integer,
    metric_source text,
    height_inches double precision,
    weight integer,
    forty_yard double precision,
    ten_split double precision,
    bench_press integer,
    vertical_jump double precision,
    broad_jump double precision,
    three_cone double precision,
    shuttle double precision,
    hand_size double precision,
    arm_length double precision,
    wingspan double precision,
    CONSTRAINT fact_nfl_combine_pro_day_metrics_pkey PRIMARY KEY (pfr_id, season)
);

CREATE TABLE football.fact_nfl_injuries (
    gsis_id text NOT NULL,
    season integer NOT NULL,
    week integer NOT NULL,
    game_type text,
    team text NOT NULL,
    report_status text,
    report_primary_injury text,
    practice_status text,
    period integer,
    CONSTRAINT fact_nfl_injuries_pkey PRIMARY KEY (gsis_id, season, week)
);

CREATE TABLE football.fact_nfl_snap_counts (
    gsis_id text NOT NULL,
    game_id text NOT NULL,
    season integer NOT NULL,
    week integer NOT NULL,
    team text NOT NULL,
    offense_snaps integer,
    offense_pct double precision,
    defense_snaps integer,
    defense_pct double precision,
    st_snaps integer,
    st_pct double precision,
    period integer,
    CONSTRAINT fact_nfl_snap_counts_pkey PRIMARY KEY (gsis_id, game_id)
);

CREATE TABLE football.fact_period_scoring (
    season_id text NOT NULL,
    period integer NOT NULL,
    team_key text NOT NULL,
    scorer_id text NOT NULL,
    is_starter boolean NOT NULL,
    fpts double precision NOT NULL,
    fpts_offense double precision NOT NULL,
    fpts_defense double precision NOT NULL,
    fpts_special_teams double precision NOT NULL,
    capture_date timestamp NOT NULL,
    CONSTRAINT fact_period_scoring_pkey PRIMARY KEY (season_id, period, team_key, scorer_id)
);

CREATE TABLE football.fact_preseason_salary (
    season_id text NOT NULL,
    team_key text NOT NULL,
    scorer_id text NOT NULL,
    salary double precision NOT NULL,
    contract_id text NOT NULL,
    capture_date timestamp NOT NULL,
    CONSTRAINT fact_preseason_salary_pkey PRIMARY KEY (season_id, team_key, scorer_id)
);

CREATE TABLE football.fact_rookie_rankings (
    player_key text NOT NULL,
    gsis_id text,
    source_name text NOT NULL,
    source_site text,
    phase text NOT NULL,
    draft_year integer NOT NULL,
    global_rank integer,
    positional_rank integer,
    grade double precision,
    capture_date date,
    rank_date date,
    CONSTRAINT fact_rookie_rankings_pkey PRIMARY KEY (player_key, source_name, phase, draft_year)
);

CREATE TABLE football.fact_roster_state (
    season_id text NOT NULL,
    period integer NOT NULL,
    team_key text NOT NULL,
    scorer_id text NOT NULL,
    roster_slot text NOT NULL,
    salary double precision NOT NULL,
    contract_id text NOT NULL,
    capture_date timestamp NOT NULL,
    CONSTRAINT fact_roster_state_pkey PRIMARY KEY (season_id, period, team_key, scorer_id)
);

CREATE TABLE football.fact_roster_transactions (
    transaction_id text NOT NULL,
    season_id text,
    event_type text NOT NULL,
    team_key text NOT NULL,
    asset_id integer,
    event_seq integer,
    event_date timestamp,
    period integer,
    contract_id text,
    contract_year integer,
    contract_value double precision,
    contract_source text,
    status text,
    scorer_id text NOT NULL,
    gsis_id text,
    draft_round integer,
    pick_in_round integer,
    pick_overall integer,
    source text,
    claim_method text,
    claim_bid double precision,
    CONSTRAINT fact_roster_transactions_pkey PRIMARY KEY (transaction_id, scorer_id, team_key, event_type)
);

CREATE TABLE football.fact_team_cap (
    season_id text NOT NULL,
    team_key text NOT NULL,
    is_current_season boolean NOT NULL,
    original_cap double precision NOT NULL,
    reinvestment_cap double precision NOT NULL,
    charged_salary double precision NOT NULL,
    ir_salary double precision NOT NULL,
    minors_salary double precision NOT NULL,
    dead_money double precision NOT NULL,
    cap_room double precision NOT NULL,
    roster_captured_at timestamptz,
    fantrax_salary_remaining double precision,
    fantrax_captured_at timestamptz,
    fantrax_period integer,
    CONSTRAINT fact_team_cap_pkey PRIMARY KEY (season_id, team_key)
);

CREATE TABLE football.fact_trade_log (
    transaction_id text NOT NULL,
    asset_id integer NOT NULL,
    asset_kind text,
    team_key_from text NOT NULL,
    team_key_to text NOT NULL,
    event_date timestamp,
    week text NOT NULL,
    scorer_id text,
    gsis_id text,
    pick_ref text,
    draft_year integer,
    draft_round integer,
    pick_in_round integer,
    source text,
    CONSTRAINT fact_trade_log_pkey PRIMARY KEY (transaction_id, asset_id)
);

CREATE TABLE ops.change_poll_state (
    team_key text NOT NULL,
    period integer,
    roster_hash text,
    last_polled_at timestamptz,
    hash_changed_at timestamptz,
    pending_since timestamptz,
    CONSTRAINT change_poll_state_pkey PRIMARY KEY (team_key)
);

CREATE TABLE ops.etl_run_log (
    run_id uuid NOT NULL,
    trigger text NOT NULL,
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    status text NOT NULL,
    git_sha text,
    snapshot_commit_sha text,
    rows_written jsonb,
    error text,
    CONSTRAINT etl_run_log_pkey PRIMARY KEY (run_id),
    CONSTRAINT etl_run_log_chk_8302bdbd CHECK (trigger IN ('daily', 'poll', 'weekly', 'manual')),
    CONSTRAINT etl_run_log_chk_37d80158 CHECK (status IN ('running', 'failed', 'committed', 'published'))
);

CREATE TABLE ops.review_check (
    check_name text NOT NULL,
    table_name text NOT NULL,
    row_key jsonb NOT NULL,
    detail jsonb,
    run_id text,
    created_at timestamptz NOT NULL,
    last_seen_at timestamptz,
    pending boolean,
    resolved_at timestamptz,
    resolution text,
    CONSTRAINT review_check_pkey PRIMARY KEY (check_name, table_name, row_key, created_at)
);

CREATE TABLE ops.review_dynasty_crosswalk (
    source text,
    source_player_id text,
    source_player_name text,
    source_position text,
    source_team text,
    gsis_id text,
    player_key text,
    match_method text,
    match_score integer,
    resolved_date date,
    source_uid text NOT NULL,
    action text,
    created_at timestamptz NOT NULL,
    resolved_at timestamptz,
    resolution text,
    CONSTRAINT review_dynasty_crosswalk_pkey PRIMARY KEY (source_uid, created_at)
);

CREATE TABLE ops.review_fantrax_crosswalk (
    scorer_id text NOT NULL,
    player_name text,
    position_raw text,
    nfl_team text,
    is_rookie boolean,
    gsis_id text,
    player_key text,
    match_method text,
    match_score integer,
    resolved_date date,
    action text,
    created_at timestamptz NOT NULL,
    resolved_at timestamptz,
    resolution text,
    CONSTRAINT review_fantrax_crosswalk_pkey PRIMARY KEY (scorer_id, created_at)
);

CREATE TABLE ops.review_fuzzy_matches (
    new_name text NOT NULL,
    new_name_clean text,
    new_position text,
    new_school text,
    best_match_name text,
    best_match_key text,
    fuzzy_score integer,
    action text,
    source text NOT NULL,
    created_at timestamptz NOT NULL,
    resolved_at timestamptz,
    resolution text,
    CONSTRAINT review_fuzzy_matches_pkey PRIMARY KEY (new_name, source, created_at)
);

CREATE TABLE shared.owner (
    owner_id text NOT NULL,
    team_key text,
    human_name text,
    email text,
    fantrax_username text,
    CONSTRAINT owner_pkey PRIMARY KEY (owner_id)
);

ALTER TABLE football.dim_division ADD CONSTRAINT dim_division_season_id_fkey FOREIGN KEY (season_id) REFERENCES football.dim_season (season_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.dim_dynasty_crosswalk ADD CONSTRAINT dim_dynasty_crosswalk_gsis_id_fkey FOREIGN KEY (gsis_id) REFERENCES football.dim_nfl_players (gsis_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.dim_fantrax_crosswalk ADD CONSTRAINT dim_fantrax_crosswalk_gsis_id_fkey FOREIGN KEY (gsis_id) REFERENCES football.dim_nfl_players (gsis_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.dim_rookie_prospect ADD CONSTRAINT dim_rookie_prospect_gsis_id_fkey FOREIGN KEY (gsis_id) REFERENCES football.dim_nfl_players (gsis_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.dim_roster_asset ADD CONSTRAINT dim_roster_asset_gsis_id_fkey FOREIGN KEY (gsis_id) REFERENCES football.dim_nfl_players (gsis_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.dim_scoring_period ADD CONSTRAINT dim_scoring_period_season_id_fkey FOREIGN KEY (season_id) REFERENCES football.dim_season (season_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_dead_money ADD CONSTRAINT fact_dead_money_gsis_id_fkey FOREIGN KEY (gsis_id) REFERENCES football.dim_nfl_players (gsis_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_dead_money ADD CONSTRAINT fact_dead_money_team_key_fkey FOREIGN KEY (team_key) REFERENCES football.dim_fantasy_teams (team_key) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_dead_money ADD CONSTRAINT fact_dead_money_contract_id_fkey FOREIGN KEY (contract_id) REFERENCES football.dim_contract (contract_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_dead_money ADD CONSTRAINT fact_dead_money_charge_contract_id_fkey FOREIGN KEY (charge_contract_id) REFERENCES football.dim_contract (contract_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_dead_money ADD CONSTRAINT fact_dead_money_season_id_fkey FOREIGN KEY (season_id) REFERENCES football.dim_season (season_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_draft_pick ADD CONSTRAINT fact_draft_pick_current_owner_fkey FOREIGN KEY (current_owner) REFERENCES football.dim_fantasy_teams (team_key) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_draft_pick ADD CONSTRAINT fact_draft_pick_draft_season_fkey FOREIGN KEY (draft_season) REFERENCES football.dim_season (season_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_draft_pick_future ADD CONSTRAINT fact_draft_pick_future_current_owner_fkey FOREIGN KEY (current_owner) REFERENCES football.dim_fantasy_teams (team_key) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_draft_pick_future ADD CONSTRAINT fact_draft_pick_future_draft_season_fkey FOREIGN KEY (draft_season) REFERENCES football.dim_season (season_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_dynasty_ranking_metrics ADD CONSTRAINT fact_dynasty_ranking_metrics_gsis_id_fkey FOREIGN KEY (gsis_id) REFERENCES football.dim_nfl_players (gsis_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_dynasty_ranking_metrics ADD CONSTRAINT fact_dynasty_ranking_metrics_metric_key_fkey FOREIGN KEY (metric_key) REFERENCES football.dim_dynasty_metric (metric_key) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_fantasy_teams ADD CONSTRAINT fact_fantasy_teams_gsis_id_fkey FOREIGN KEY (gsis_id) REFERENCES football.dim_nfl_players (gsis_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_fantasy_teams ADD CONSTRAINT fact_fantasy_teams_team_key_fkey FOREIGN KEY (team_key) REFERENCES football.dim_fantasy_teams (team_key) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_fantasy_teams ADD CONSTRAINT fact_fantasy_teams_contract_id_fkey FOREIGN KEY (contract_id) REFERENCES football.dim_contract (contract_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_fantrax_adp ADD CONSTRAINT fact_fantrax_adp_gsis_id_fkey FOREIGN KEY (gsis_id) REFERENCES football.dim_nfl_players (gsis_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_matchup ADD CONSTRAINT fact_matchup_team_key_fkey FOREIGN KEY (team_key) REFERENCES football.dim_fantasy_teams (team_key) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_matchup ADD CONSTRAINT fact_matchup_opponent_team_key_fkey FOREIGN KEY (opponent_team_key) REFERENCES football.dim_fantasy_teams (team_key) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_matchup ADD CONSTRAINT fact_matchup_season_id_fkey FOREIGN KEY (season_id) REFERENCES football.dim_season (season_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_nfl_combine_pro_day_metrics ADD CONSTRAINT fact_nfl_combine_pro_day_metrics_gsis_id_fkey FOREIGN KEY (gsis_id) REFERENCES football.dim_nfl_players (gsis_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_nfl_injuries ADD CONSTRAINT fact_nfl_injuries_gsis_id_fkey FOREIGN KEY (gsis_id) REFERENCES football.dim_nfl_players (gsis_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_nfl_snap_counts ADD CONSTRAINT fact_nfl_snap_counts_gsis_id_fkey FOREIGN KEY (gsis_id) REFERENCES football.dim_nfl_players (gsis_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_period_scoring ADD CONSTRAINT fact_period_scoring_team_key_fkey FOREIGN KEY (team_key) REFERENCES football.dim_fantasy_teams (team_key) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_period_scoring ADD CONSTRAINT fact_period_scoring_season_id_fkey FOREIGN KEY (season_id) REFERENCES football.dim_season (season_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_preseason_salary ADD CONSTRAINT fact_preseason_salary_team_key_fkey FOREIGN KEY (team_key) REFERENCES football.dim_fantasy_teams (team_key) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_preseason_salary ADD CONSTRAINT fact_preseason_salary_contract_id_fkey FOREIGN KEY (contract_id) REFERENCES football.dim_contract (contract_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_preseason_salary ADD CONSTRAINT fact_preseason_salary_season_id_fkey FOREIGN KEY (season_id) REFERENCES football.dim_season (season_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_rookie_rankings ADD CONSTRAINT fact_rookie_rankings_gsis_id_fkey FOREIGN KEY (gsis_id) REFERENCES football.dim_nfl_players (gsis_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_roster_state ADD CONSTRAINT fact_roster_state_team_key_fkey FOREIGN KEY (team_key) REFERENCES football.dim_fantasy_teams (team_key) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_roster_state ADD CONSTRAINT fact_roster_state_contract_id_fkey FOREIGN KEY (contract_id) REFERENCES football.dim_contract (contract_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_roster_state ADD CONSTRAINT fact_roster_state_season_id_fkey FOREIGN KEY (season_id) REFERENCES football.dim_season (season_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_roster_transactions ADD CONSTRAINT fact_roster_transactions_gsis_id_fkey FOREIGN KEY (gsis_id) REFERENCES football.dim_nfl_players (gsis_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_roster_transactions ADD CONSTRAINT fact_roster_transactions_team_key_fkey FOREIGN KEY (team_key) REFERENCES football.dim_fantasy_teams (team_key) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_roster_transactions ADD CONSTRAINT fact_roster_transactions_contract_id_fkey FOREIGN KEY (contract_id) REFERENCES football.dim_contract (contract_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_roster_transactions ADD CONSTRAINT fact_roster_transactions_asset_id_fkey FOREIGN KEY (asset_id) REFERENCES football.dim_roster_asset (asset_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_roster_transactions ADD CONSTRAINT fact_roster_transactions_season_id_fkey FOREIGN KEY (season_id) REFERENCES football.dim_season (season_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_team_cap ADD CONSTRAINT fact_team_cap_team_key_fkey FOREIGN KEY (team_key) REFERENCES football.dim_fantasy_teams (team_key) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_team_cap ADD CONSTRAINT fact_team_cap_season_id_fkey FOREIGN KEY (season_id) REFERENCES football.dim_season (season_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_trade_log ADD CONSTRAINT fact_trade_log_gsis_id_fkey FOREIGN KEY (gsis_id) REFERENCES football.dim_nfl_players (gsis_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_trade_log ADD CONSTRAINT fact_trade_log_team_key_from_fkey FOREIGN KEY (team_key_from) REFERENCES football.dim_fantasy_teams (team_key) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_trade_log ADD CONSTRAINT fact_trade_log_team_key_to_fkey FOREIGN KEY (team_key_to) REFERENCES football.dim_fantasy_teams (team_key) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_trade_log ADD CONSTRAINT fact_trade_log_asset_id_fkey FOREIGN KEY (asset_id) REFERENCES football.dim_roster_asset (asset_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ops.change_poll_state ADD CONSTRAINT change_poll_state_team_key_fkey FOREIGN KEY (team_key) REFERENCES football.dim_fantasy_teams (team_key) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.dim_contract ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.dim_division ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.dim_dynasty_crosswalk ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.dim_dynasty_metric ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.dim_fantasy_teams ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.dim_fantrax_crosswalk ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.dim_nfl_players ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.dim_nfl_teams ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.dim_pick_value_curve ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.dim_player_alias ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.dim_position ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.dim_position_ceiling ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.dim_rookie_prospect ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.dim_roster_asset ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.dim_school ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.dim_scoring_period ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.dim_season ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.fact_dead_money ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.fact_draft_pick ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.fact_draft_pick_future ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.fact_dynasty_ranking_metrics ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.fact_fantasy_teams ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.fact_fantrax_adp ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.fact_matchup ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.fact_minor_eligibility ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.fact_nfl_combine_pro_day_metrics ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.fact_nfl_injuries ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.fact_nfl_snap_counts ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.fact_period_scoring ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.fact_preseason_salary ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.fact_rookie_rankings ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.fact_roster_state ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.fact_roster_transactions ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.fact_team_cap ENABLE ROW LEVEL SECURITY;

ALTER TABLE football.fact_trade_log ENABLE ROW LEVEL SECURITY;

ALTER TABLE ops.change_poll_state ENABLE ROW LEVEL SECURITY;

ALTER TABLE ops.etl_run_log ENABLE ROW LEVEL SECURITY;

ALTER TABLE ops.review_check ENABLE ROW LEVEL SECURITY;

ALTER TABLE ops.review_dynasty_crosswalk ENABLE ROW LEVEL SECURITY;

ALTER TABLE ops.review_fantrax_crosswalk ENABLE ROW LEVEL SECURITY;

ALTER TABLE ops.review_fuzzy_matches ENABLE ROW LEVEL SECURITY;

ALTER TABLE shared.owner ENABLE ROW LEVEL SECURITY;

GRANT USAGE ON SCHEMA football TO etl_writer, etl_reader;

GRANT USAGE ON SCHEMA ops TO etl_writer, etl_reader;

GRANT SELECT, INSERT, UPDATE, DELETE ON football.dim_contract TO etl_writer;

GRANT SELECT ON football.dim_contract TO etl_reader;

CREATE POLICY etl_writer_all ON football.dim_contract FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.dim_contract FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.dim_division TO etl_writer;

GRANT SELECT ON football.dim_division TO etl_reader;

CREATE POLICY etl_writer_all ON football.dim_division FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.dim_division FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.dim_dynasty_crosswalk TO etl_writer;

GRANT SELECT ON football.dim_dynasty_crosswalk TO etl_reader;

CREATE POLICY etl_writer_all ON football.dim_dynasty_crosswalk FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.dim_dynasty_crosswalk FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.dim_dynasty_metric TO etl_writer;

GRANT SELECT ON football.dim_dynasty_metric TO etl_reader;

CREATE POLICY etl_writer_all ON football.dim_dynasty_metric FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.dim_dynasty_metric FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.dim_fantasy_teams TO etl_writer;

GRANT SELECT ON football.dim_fantasy_teams TO etl_reader;

CREATE POLICY etl_writer_all ON football.dim_fantasy_teams FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.dim_fantasy_teams FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.dim_fantrax_crosswalk TO etl_writer;

GRANT SELECT ON football.dim_fantrax_crosswalk TO etl_reader;

CREATE POLICY etl_writer_all ON football.dim_fantrax_crosswalk FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.dim_fantrax_crosswalk FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.dim_nfl_players TO etl_writer;

GRANT SELECT ON football.dim_nfl_players TO etl_reader;

CREATE POLICY etl_writer_all ON football.dim_nfl_players FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.dim_nfl_players FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.dim_nfl_teams TO etl_writer;

GRANT SELECT ON football.dim_nfl_teams TO etl_reader;

CREATE POLICY etl_writer_all ON football.dim_nfl_teams FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.dim_nfl_teams FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.dim_pick_value_curve TO etl_writer;

GRANT SELECT ON football.dim_pick_value_curve TO etl_reader;

CREATE POLICY etl_writer_all ON football.dim_pick_value_curve FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.dim_pick_value_curve FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.dim_player_alias TO etl_writer;

GRANT SELECT ON football.dim_player_alias TO etl_reader;

CREATE POLICY etl_writer_all ON football.dim_player_alias FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.dim_player_alias FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.dim_position TO etl_writer;

GRANT SELECT ON football.dim_position TO etl_reader;

CREATE POLICY etl_writer_all ON football.dim_position FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.dim_position FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.dim_position_ceiling TO etl_writer;

GRANT SELECT ON football.dim_position_ceiling TO etl_reader;

CREATE POLICY etl_writer_all ON football.dim_position_ceiling FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.dim_position_ceiling FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.dim_rookie_prospect TO etl_writer;

GRANT SELECT ON football.dim_rookie_prospect TO etl_reader;

CREATE POLICY etl_writer_all ON football.dim_rookie_prospect FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.dim_rookie_prospect FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.dim_roster_asset TO etl_writer;

GRANT SELECT ON football.dim_roster_asset TO etl_reader;

CREATE POLICY etl_writer_all ON football.dim_roster_asset FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.dim_roster_asset FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.dim_school TO etl_writer;

GRANT SELECT ON football.dim_school TO etl_reader;

CREATE POLICY etl_writer_all ON football.dim_school FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.dim_school FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.dim_scoring_period TO etl_writer;

GRANT SELECT ON football.dim_scoring_period TO etl_reader;

CREATE POLICY etl_writer_all ON football.dim_scoring_period FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.dim_scoring_period FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.dim_season TO etl_writer;

GRANT SELECT ON football.dim_season TO etl_reader;

CREATE POLICY etl_writer_all ON football.dim_season FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.dim_season FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.fact_dead_money TO etl_writer;

GRANT SELECT ON football.fact_dead_money TO etl_reader;

CREATE POLICY etl_writer_all ON football.fact_dead_money FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.fact_dead_money FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.fact_draft_pick TO etl_writer;

GRANT SELECT ON football.fact_draft_pick TO etl_reader;

CREATE POLICY etl_writer_all ON football.fact_draft_pick FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.fact_draft_pick FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.fact_draft_pick_future TO etl_writer;

GRANT SELECT ON football.fact_draft_pick_future TO etl_reader;

CREATE POLICY etl_writer_all ON football.fact_draft_pick_future FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.fact_draft_pick_future FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.fact_dynasty_ranking_metrics TO etl_writer;

GRANT SELECT ON football.fact_dynasty_ranking_metrics TO etl_reader;

CREATE POLICY etl_writer_all ON football.fact_dynasty_ranking_metrics FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.fact_dynasty_ranking_metrics FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.fact_fantasy_teams TO etl_writer;

GRANT SELECT ON football.fact_fantasy_teams TO etl_reader;

CREATE POLICY etl_writer_all ON football.fact_fantasy_teams FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.fact_fantasy_teams FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.fact_fantrax_adp TO etl_writer;

GRANT SELECT ON football.fact_fantrax_adp TO etl_reader;

CREATE POLICY etl_writer_all ON football.fact_fantrax_adp FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.fact_fantrax_adp FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.fact_matchup TO etl_writer;

GRANT SELECT ON football.fact_matchup TO etl_reader;

CREATE POLICY etl_writer_all ON football.fact_matchup FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.fact_matchup FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.fact_minor_eligibility TO etl_writer;

GRANT SELECT ON football.fact_minor_eligibility TO etl_reader;

CREATE POLICY etl_writer_all ON football.fact_minor_eligibility FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.fact_minor_eligibility FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.fact_nfl_combine_pro_day_metrics TO etl_writer;

GRANT SELECT ON football.fact_nfl_combine_pro_day_metrics TO etl_reader;

CREATE POLICY etl_writer_all ON football.fact_nfl_combine_pro_day_metrics FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.fact_nfl_combine_pro_day_metrics FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.fact_nfl_injuries TO etl_writer;

GRANT SELECT ON football.fact_nfl_injuries TO etl_reader;

CREATE POLICY etl_writer_all ON football.fact_nfl_injuries FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.fact_nfl_injuries FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.fact_nfl_snap_counts TO etl_writer;

GRANT SELECT ON football.fact_nfl_snap_counts TO etl_reader;

CREATE POLICY etl_writer_all ON football.fact_nfl_snap_counts FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.fact_nfl_snap_counts FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.fact_period_scoring TO etl_writer;

GRANT SELECT ON football.fact_period_scoring TO etl_reader;

CREATE POLICY etl_writer_all ON football.fact_period_scoring FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.fact_period_scoring FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.fact_preseason_salary TO etl_writer;

GRANT SELECT ON football.fact_preseason_salary TO etl_reader;

CREATE POLICY etl_writer_all ON football.fact_preseason_salary FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.fact_preseason_salary FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.fact_rookie_rankings TO etl_writer;

GRANT SELECT ON football.fact_rookie_rankings TO etl_reader;

CREATE POLICY etl_writer_all ON football.fact_rookie_rankings FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.fact_rookie_rankings FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.fact_roster_state TO etl_writer;

GRANT SELECT ON football.fact_roster_state TO etl_reader;

CREATE POLICY etl_writer_all ON football.fact_roster_state FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.fact_roster_state FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.fact_roster_transactions TO etl_writer;

GRANT SELECT ON football.fact_roster_transactions TO etl_reader;

CREATE POLICY etl_writer_all ON football.fact_roster_transactions FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.fact_roster_transactions FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.fact_team_cap TO etl_writer;

GRANT SELECT ON football.fact_team_cap TO etl_reader;

CREATE POLICY etl_writer_all ON football.fact_team_cap FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.fact_team_cap FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON football.fact_trade_log TO etl_writer;

GRANT SELECT ON football.fact_trade_log TO etl_reader;

CREATE POLICY etl_writer_all ON football.fact_trade_log FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.fact_trade_log FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON ops.change_poll_state TO etl_writer;

GRANT SELECT ON ops.change_poll_state TO etl_reader;

CREATE POLICY etl_writer_all ON ops.change_poll_state FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON ops.change_poll_state FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON ops.etl_run_log TO etl_writer;

GRANT SELECT ON ops.etl_run_log TO etl_reader;

CREATE POLICY etl_writer_all ON ops.etl_run_log FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON ops.etl_run_log FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON ops.review_check TO etl_writer;

GRANT SELECT ON ops.review_check TO etl_reader;

CREATE POLICY etl_writer_all ON ops.review_check FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON ops.review_check FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON ops.review_dynasty_crosswalk TO etl_writer;

GRANT SELECT ON ops.review_dynasty_crosswalk TO etl_reader;

CREATE POLICY etl_writer_all ON ops.review_dynasty_crosswalk FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON ops.review_dynasty_crosswalk FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON ops.review_fantrax_crosswalk TO etl_writer;

GRANT SELECT ON ops.review_fantrax_crosswalk TO etl_reader;

CREATE POLICY etl_writer_all ON ops.review_fantrax_crosswalk FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON ops.review_fantrax_crosswalk FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON ops.review_fuzzy_matches TO etl_writer;

GRANT SELECT ON ops.review_fuzzy_matches TO etl_reader;

CREATE POLICY etl_writer_all ON ops.review_fuzzy_matches FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON ops.review_fuzzy_matches FOR SELECT TO etl_reader USING (true);

CREATE FUNCTION shared.pii_token_hashes() RETURNS SETOF text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
    SELECT encode(sha256(convert_to(s.token, 'UTF8')), 'hex')
    FROM (
        SELECT regexp_split_to_table(lower(o.human_name), '\s+') AS token FROM shared.owner o
        UNION
        SELECT lower(o.fantrax_username) FROM shared.owner o
    ) s
    WHERE s.token IS NOT NULL AND s.token <> ''
$fn$;

REVOKE EXECUTE ON FUNCTION shared.pii_token_hashes() FROM PUBLIC;

GRANT USAGE ON SCHEMA shared TO etl_writer;

GRANT EXECUTE ON FUNCTION shared.pii_token_hashes() TO etl_writer;

CREATE UNIQUE INDEX review_check_one_open_idx ON ops.review_check (check_name, table_name, row_key) WHERE resolved_at IS NULL;
