-- registry_state sha256: 5bbe4ca23eb204065dec6ed91fb96cf2358a6c73c77d324a2c96dcde5ebd5d0e

CREATE TABLE football.fact_salary_price_list (
    season integer NOT NULL,
    scorer_id text NOT NULL,
    salary double precision NOT NULL,
    pulled_on date NOT NULL,
    CONSTRAINT fact_salary_price_list_pkey PRIMARY KEY (season, scorer_id),
    CONSTRAINT fact_salary_price_list_chk_5e9e1cc0 CHECK (salary >= 0)
);

ALTER TABLE football.fact_salary_price_list ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE, DELETE ON football.fact_salary_price_list TO etl_writer;

GRANT SELECT ON football.fact_salary_price_list TO etl_reader;

CREATE POLICY etl_writer_all ON football.fact_salary_price_list FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.fact_salary_price_list FOR SELECT TO etl_reader USING (true);
