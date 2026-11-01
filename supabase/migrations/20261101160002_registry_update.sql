-- registry_state sha256: d2f1c0678dd4015a65cfddc4c763a4084f55499a35da9187c2b5545b817996a7

CREATE TABLE football.dim_gsis_link (
    old_gsis_id text NOT NULL,
    new_gsis_id text NOT NULL,
    method text,
    decided_date date,
    CONSTRAINT dim_gsis_link_pkey PRIMARY KEY (old_gsis_id)
);

ALTER TABLE football.dim_gsis_link ADD CONSTRAINT dim_gsis_link_new_gsis_id_fkey FOREIGN KEY (new_gsis_id) REFERENCES football.dim_nfl_players (gsis_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.dim_gsis_link ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE, DELETE ON football.dim_gsis_link TO etl_writer;

GRANT SELECT ON football.dim_gsis_link TO etl_reader;

CREATE POLICY etl_writer_all ON football.dim_gsis_link FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.dim_gsis_link FOR SELECT TO etl_reader USING (true);
