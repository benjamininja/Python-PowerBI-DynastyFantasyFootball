-- registry_state sha256: a9714c3c027b5ad6d7d0fe0d2161cbb5f7cc5a8213b1efb83d63c56445989156

CREATE TABLE ops.dim_fantasy_team_alias (
    name_clean text NOT NULL,
    fantrax_team_id text NOT NULL,
    decision text NOT NULL,
    score integer,
    source text,
    recorded_at timestamptz NOT NULL,
    CONSTRAINT dim_fantasy_team_alias_pkey PRIMARY KEY (name_clean),
    CONSTRAINT dim_fantasy_team_alias_chk_c7509287 CHECK (decision IN ('seed', 'guess', 'owner'))
);

ALTER TABLE ops.dim_fantasy_team_alias ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE, DELETE ON ops.dim_fantasy_team_alias TO etl_writer;

GRANT SELECT ON ops.dim_fantasy_team_alias TO etl_reader;

CREATE POLICY etl_writer_all ON ops.dim_fantasy_team_alias FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON ops.dim_fantasy_team_alias FOR SELECT TO etl_reader USING (true);
