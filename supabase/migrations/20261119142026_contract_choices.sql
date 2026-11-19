-- registry_state sha256: fcdb8070a5419a9f6c4b47ae7b195556070cf39e578f01b30328202f8306e317

CREATE SCHEMA app;

CREATE TABLE app.contract_choices (
    season_id text NOT NULL,
    team_key text NOT NULL,
    scorer_id text NOT NULL,
    choice_kind text NOT NULL,
    choice text NOT NULL,
    locked_value double precision,
    origin text NOT NULL,
    changed_by uuid,
    changed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT contract_choices_pkey PRIMARY KEY (season_id, team_key, scorer_id, choice_kind),
    CONSTRAINT contract_choices_chk_56c5e027 CHECK (choice_kind IN ('resign', 'fa_keep')),
    CONSTRAINT contract_choices_chk_5afa80de CHECK (origin IN ('loader', 'app')),
    CONSTRAINT contract_choices_chk_5976629a CHECK ((choice_kind = 'resign' AND choice IN ('resign', 'decline')) OR (choice_kind = 'fa_keep' AND choice IN ('keep', 'let_go')))
);

CREATE TABLE ops.choice_deadline (
    season_id text NOT NULL,
    choice_kind text NOT NULL,
    deadline_at timestamptz NOT NULL,
    CONSTRAINT choice_deadline_pkey PRIMARY KEY (season_id, choice_kind),
    CONSTRAINT choice_deadline_chk_56c5e027 CHECK (choice_kind IN ('resign', 'fa_keep'))
);

ALTER TABLE app.contract_choices ADD CONSTRAINT contract_choices_season_id_fkey FOREIGN KEY (season_id) REFERENCES football.dim_season (season_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE app.contract_choices ADD CONSTRAINT contract_choices_team_key_fkey FOREIGN KEY (team_key) REFERENCES football.dim_fantasy_teams (team_key) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ops.choice_deadline ADD CONSTRAINT choice_deadline_season_id_fkey FOREIGN KEY (season_id) REFERENCES football.dim_season (season_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE app.contract_choices ENABLE ROW LEVEL SECURITY;

ALTER TABLE ops.choice_deadline ENABLE ROW LEVEL SECURITY;

GRANT USAGE ON SCHEMA app TO etl_writer;

GRANT SELECT ON app.contract_choices TO etl_writer;

CREATE POLICY etl_writer_select_after_deadline ON app.contract_choices FOR SELECT TO etl_writer USING (EXISTS (SELECT 1 FROM ops.choice_deadline d WHERE d.season_id = contract_choices.season_id AND d.choice_kind = contract_choices.choice_kind AND d.deadline_at < clock_timestamp()));

GRANT SELECT ON ops.choice_deadline TO etl_writer;

GRANT SELECT ON ops.choice_deadline TO etl_reader;

CREATE POLICY etl_writer_select ON ops.choice_deadline FOR SELECT TO etl_writer USING (true);

CREATE POLICY etl_reader_select ON ops.choice_deadline FOR SELECT TO etl_reader USING (true);

CREATE FUNCTION ops.refuse_passed_deadline_change() RETURNS trigger
LANGUAGE plpgsql SET search_path = ''
AS $fn$
BEGIN
    IF OLD.deadline_at < clock_timestamp() THEN
        RAISE EXCEPTION 'a deadline that has passed cannot be changed';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$fn$;

REVOKE EXECUTE ON FUNCTION ops.refuse_passed_deadline_change() FROM PUBLIC;

CREATE FUNCTION ops.set_changed_at() RETURNS trigger
LANGUAGE plpgsql SET search_path = ''
AS $fn$
BEGIN
    NEW.changed_at := clock_timestamp();
    RETURN NEW;
END;
$fn$;

REVOKE EXECUTE ON FUNCTION ops.set_changed_at() FROM PUBLIC;

CREATE TRIGGER contract_choices_set_changed_at BEFORE UPDATE ON app.contract_choices FOR EACH ROW EXECUTE FUNCTION ops.set_changed_at();

CREATE TRIGGER choice_deadline_guard_row BEFORE UPDATE OR DELETE ON ops.choice_deadline FOR EACH ROW EXECUTE FUNCTION ops.refuse_passed_deadline_change();
