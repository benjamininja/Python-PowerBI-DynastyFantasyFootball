-- registry_state sha256: 203d1590b985a0dd04220433b86e64fde99e99c8c297e645e45018d971941e4c

CREATE TABLE football.fact_nfl_minor_eligibility (
    gsis_id text NOT NULL,
    season integer NOT NULL,
    week text NOT NULL,
    capture_date date,
    career_games integer,
    eligible boolean,
    CONSTRAINT fact_nfl_minor_eligibility_pkey PRIMARY KEY (gsis_id, season, week)
);

ALTER TABLE football.fact_nfl_minor_eligibility ADD CONSTRAINT fact_nfl_minor_eligibility_gsis_id_fkey FOREIGN KEY (gsis_id) REFERENCES football.dim_nfl_players (gsis_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_nfl_minor_eligibility ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE, DELETE ON football.fact_nfl_minor_eligibility TO etl_writer;

GRANT SELECT ON football.fact_nfl_minor_eligibility TO etl_reader;

CREATE POLICY etl_writer_all ON football.fact_nfl_minor_eligibility FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.fact_nfl_minor_eligibility FOR SELECT TO etl_reader USING (true);
