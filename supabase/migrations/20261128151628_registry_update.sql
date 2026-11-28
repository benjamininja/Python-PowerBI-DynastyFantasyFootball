-- registry_state sha256: c48878e2d6c763d5d949f7eec590ecf05700e2f977e37085e5e904fc481e9443

CREATE TABLE football.dim_scoring_category (
    category_id text NOT NULL,
    category_code text NOT NULL,
    category_name text NOT NULL,
    category_group text NOT NULL,
    group_sort_order integer NOT NULL,
    unit text NOT NULL,
    nflverse_columns text,
    CONSTRAINT dim_scoring_category_pkey PRIMARY KEY (category_id),
    CONSTRAINT dim_scoring_category_chk_4c39273f CHECK (category_group IN ('Passing', 'Rushing', 'Receiving', 'Special teams', 'Defense, tackles', 'Defense, big plays', 'Other')),
    CONSTRAINT dim_scoring_category_chk_12b53427 CHECK (group_sort_order BETWEEN 1 AND 7)
);

ALTER TABLE football.dim_scoring_category ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE, DELETE ON football.dim_scoring_category TO etl_writer;

GRANT SELECT ON football.dim_scoring_category TO etl_reader;

CREATE POLICY etl_writer_all ON football.dim_scoring_category FOR ALL TO etl_writer USING (true) WITH CHECK (true);

CREATE POLICY etl_reader_select ON football.dim_scoring_category FOR SELECT TO etl_reader USING (true);
