-- registry_state sha256: 0c354d7099cab6f784d3ee9ccb692f6d655ea11e1b576beca79a1611a0789e8c

CREATE TABLE app.contract_choice_history (
    history_id uuid NOT NULL DEFAULT gen_random_uuid(),
    season_id text NOT NULL,
    team_key text NOT NULL,
    scorer_id text NOT NULL,
    choice_kind text NOT NULL,
    choice text NOT NULL,
    origin text NOT NULL,
    changed_by uuid,
    changed_at timestamptz NOT NULL,
    action_id uuid,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT contract_choice_history_pkey PRIMARY KEY (history_id)
);

ALTER TABLE ops.choice_deadline ADD COLUMN final_at timestamptz NOT NULL DEFAULT timestamptz '2027-03-01 04:59:59+00';

ALTER TABLE app.contract_choices DROP CONSTRAINT contract_choices_chk_5afa80de;

ALTER TABLE app.contract_choices ADD CONSTRAINT contract_choices_chk_1db856f6 CHECK (origin IN ('loader', 'app', 'commissioner'));

ALTER TABLE ops.choice_deadline ADD CONSTRAINT choice_deadline_chk_396ca595 CHECK (final_at > deadline_at);

ALTER TABLE app.contract_choice_history ADD CONSTRAINT contract_choice_history_season_id_fkey FOREIGN KEY (season_id) REFERENCES football.dim_season (season_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE app.contract_choice_history ADD CONSTRAINT contract_choice_history_team_key_fkey FOREIGN KEY (team_key) REFERENCES football.dim_fantasy_teams (team_key) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE app.contract_choice_history ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION shared.choice_window(p_season_id text, p_choice_kind text) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
    SELECT coalesce(
        (SELECT CASE WHEN d.final_at <= clock_timestamp() THEN 'final'
                     WHEN d.deadline_at > clock_timestamp() THEN 'open'
                     ELSE 'passed' END
         FROM ops.choice_deadline d
         WHERE d.season_id = p_season_id AND d.choice_kind = p_choice_kind),
        'none')
$fn$;

GRANT USAGE ON SCHEMA app TO authenticated;

REVOKE ALL ON SCHEMA app FROM anon;

REVOKE ALL ON ALL TABLES IN SCHEMA app FROM anon;

ALTER DEFAULT PRIVILEGES IN SCHEMA app REVOKE ALL ON TABLES FROM anon;

GRANT SELECT ON app.contract_choice_history TO authenticated;

CREATE POLICY owner_select_own_team ON app.contract_choice_history FOR SELECT TO authenticated USING (team_key IN (SELECT shared.caller_team_keys()));

CREATE POLICY signed_in_select_shared_team ON app.contract_choice_history FOR SELECT TO authenticated USING (EXISTS (SELECT 1 FROM app.team_choice_sharing s WHERE s.season_id = contract_choice_history.season_id AND s.team_key = contract_choice_history.team_key AND s.shared));

CREATE POLICY signed_in_select_after_deadline ON app.contract_choice_history FOR SELECT TO authenticated USING (shared.choice_window(season_id, choice_kind) IN ('passed', 'final'));

ALTER POLICY signed_in_select_after_deadline ON app.contract_choices USING (shared.choice_window(season_id, choice_kind) IN ('passed', 'final'));

CREATE FUNCTION ops.record_choice_history() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $fn$
BEGIN
    IF TG_OP = 'UPDATE' AND NOT EXISTS (
        SELECT 1 FROM app.contract_choice_history h
        WHERE h.season_id = OLD.season_id AND h.team_key = OLD.team_key
          AND h.scorer_id = OLD.scorer_id AND h.choice_kind = OLD.choice_kind
    ) THEN
        INSERT INTO app.contract_choice_history
            (season_id, team_key, scorer_id, choice_kind, choice, origin, changed_by, changed_at)
        VALUES (OLD.season_id, OLD.team_key, OLD.scorer_id, OLD.choice_kind, OLD.choice,
                OLD.origin, OLD.changed_by, OLD.changed_at);
    END IF;
    INSERT INTO app.contract_choice_history
        (season_id, team_key, scorer_id, choice_kind, choice, origin, changed_by, changed_at)
    VALUES (NEW.season_id, NEW.team_key, NEW.scorer_id, NEW.choice_kind, NEW.choice,
            NEW.origin, NEW.changed_by, NEW.changed_at);
    RETURN NULL;
END;
$fn$;

REVOKE EXECUTE ON FUNCTION ops.record_choice_history() FROM PUBLIC;

CREATE TRIGGER contract_choices_record_history AFTER INSERT OR UPDATE ON app.contract_choices FOR EACH ROW EXECUTE FUNCTION ops.record_choice_history();

CREATE INDEX contract_choice_history_key_idx ON app.contract_choice_history (season_id, team_key, scorer_id, choice_kind);
