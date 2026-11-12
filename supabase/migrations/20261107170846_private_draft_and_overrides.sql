-- registry_state sha256: d3240a17ea369b352e2412cea4bba7ef9f6b2b6698d3f75e37fe5de8cd1bb9da

CREATE TABLE ops.dim_fantrax_crosswalk_override (
    scorer_id text NOT NULL,
    gsis_id text NOT NULL,
    note text,
    recorded_at timestamptz NOT NULL,
    origin text NOT NULL,
    CONSTRAINT dim_fantrax_crosswalk_override_pkey PRIMARY KEY (scorer_id),
    CONSTRAINT dim_fantrax_crosswalk_override_chk_ae6113e7 CHECK (origin IN ('csv', 'apply_script'))
);

CREATE TABLE ops.dim_startup_draft_scorer (
    scorer_id text NOT NULL,
    player_name text,
    position_raw text,
    nfl_team text,
    is_rookie boolean,
    CONSTRAINT dim_startup_draft_scorer_pkey PRIMARY KEY (scorer_id)
);

CREATE TABLE ops.fact_startup_draft_slot (
    division_id text NOT NULL,
    round integer NOT NULL,
    pick_in_round integer NOT NULL,
    team_id text,
    scorer_id text,
    picked_at timestamptz,
    CONSTRAINT fact_startup_draft_slot_pkey PRIMARY KEY (division_id, round, pick_in_round)
);

ALTER TABLE ops.dim_fantrax_crosswalk_override ENABLE ROW LEVEL SECURITY;

ALTER TABLE ops.dim_startup_draft_scorer ENABLE ROW LEVEL SECURITY;

ALTER TABLE ops.fact_startup_draft_slot ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE, DELETE ON ops.dim_fantrax_crosswalk_override TO etl_writer;

GRANT SELECT ON ops.dim_fantrax_crosswalk_override TO etl_reader;

CREATE POLICY etl_writer_all ON ops.dim_fantrax_crosswalk_override FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON ops.dim_fantrax_crosswalk_override FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON ops.dim_startup_draft_scorer TO etl_writer;

GRANT SELECT ON ops.dim_startup_draft_scorer TO etl_reader;

CREATE POLICY etl_writer_all ON ops.dim_startup_draft_scorer FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON ops.dim_startup_draft_scorer FOR SELECT TO etl_reader USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON ops.fact_startup_draft_slot TO etl_writer;

GRANT SELECT ON ops.fact_startup_draft_slot TO etl_reader;

CREATE POLICY etl_writer_all ON ops.fact_startup_draft_slot FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON ops.fact_startup_draft_slot FOR SELECT TO etl_reader USING (true);
