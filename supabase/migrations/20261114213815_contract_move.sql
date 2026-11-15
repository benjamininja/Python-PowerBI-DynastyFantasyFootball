-- registry_state sha256: 4e3860a6c65b6780e4b0622243f96d77e3127ab3f5a1499bbce8cb25127a11a0

CREATE TABLE football.fact_contract_move (
    list_name text NOT NULL,
    conference text,
    division text,
    team_key text NOT NULL,
    scorer_id text NOT NULL,
    gsis_id text,
    player_name text,
    position text,
    nfl_team text,
    contract_now text,
    move_to text,
    reason text,
    nfl_games integer,
    roster_slot text,
    salary double precision,
    status text NOT NULL,
    CONSTRAINT fact_contract_move_pkey PRIMARY KEY (list_name, team_key, scorer_id)
);

ALTER TABLE football.fact_contract_move ADD CONSTRAINT fact_contract_move_team_key_fkey FOREIGN KEY (team_key) REFERENCES football.dim_fantasy_teams (team_key) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_contract_move ADD CONSTRAINT fact_contract_move_gsis_id_fkey FOREIGN KEY (gsis_id) REFERENCES football.dim_nfl_players (gsis_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE football.fact_contract_move ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE, DELETE ON football.fact_contract_move TO etl_writer;

GRANT SELECT ON football.fact_contract_move TO etl_reader;

CREATE POLICY etl_writer_all ON football.fact_contract_move FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.fact_contract_move FOR SELECT TO etl_reader USING (true);
