-- registry_state sha256: 07d1e31812fbb1530dd29acac4a30bf1e1552812c1b6f7bf0ec7187fe05e8f14

CREATE TABLE football.dim_fantrax_scoring_rule (
    season_id text NOT NULL,
    category_id text NOT NULL,
    category_code text,
    category_name text,
    scoring_group text,
    position text NOT NULL,
    points double precision NOT NULL,
    captured_at timestamptz,
    CONSTRAINT dim_fantrax_scoring_rule_pkey PRIMARY KEY (season_id, category_id, position)
);

ALTER TABLE football.dim_fantrax_scoring_rule ADD CONSTRAINT dim_fantrax_scoring_rule_season_id_fkey FOREIGN KEY (season_id) REFERENCES football.dim_season (season_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.dim_fantrax_scoring_rule ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE, DELETE ON football.dim_fantrax_scoring_rule TO etl_writer;

GRANT SELECT ON football.dim_fantrax_scoring_rule TO etl_reader;

CREATE POLICY etl_writer_all ON football.dim_fantrax_scoring_rule FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.dim_fantrax_scoring_rule FOR SELECT TO etl_reader USING (true);
