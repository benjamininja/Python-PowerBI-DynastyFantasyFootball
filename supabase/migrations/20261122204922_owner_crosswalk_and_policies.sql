-- registry_state sha256: 97f74c6a42548c6f315a46f8b41a099cf129dd14aba76a55cc1863c59f46fcec

CREATE TABLE app.team_choice_sharing (
    season_id text NOT NULL,
    team_key text NOT NULL,
    shared boolean NOT NULL,
    changed_by uuid,
    changed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT team_choice_sharing_pkey PRIMARY KEY (season_id, team_key)
);

CREATE TABLE shared.owner_crosswalk (
    team_key text NOT NULL,
    discord_user_id text NOT NULL,
    CONSTRAINT owner_crosswalk_pkey PRIMARY KEY (team_key, discord_user_id),
    CONSTRAINT owner_crosswalk_chk_4fe7a3e2 CHECK (length(discord_user_id) BETWEEN 17 AND 20 AND discord_user_id !~ '[^0-9]')
);

ALTER TABLE app.team_choice_sharing ADD CONSTRAINT team_choice_sharing_season_id_fkey FOREIGN KEY (season_id) REFERENCES football.dim_season (season_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE app.team_choice_sharing ADD CONSTRAINT team_choice_sharing_team_key_fkey FOREIGN KEY (team_key) REFERENCES football.dim_fantasy_teams (team_key) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE shared.owner_crosswalk ADD CONSTRAINT owner_crosswalk_team_key_fkey FOREIGN KEY (team_key) REFERENCES football.dim_fantasy_teams (team_key) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE app.team_choice_sharing ENABLE ROW LEVEL SECURITY;

ALTER TABLE shared.owner_crosswalk ENABLE ROW LEVEL SECURITY;

CREATE FUNCTION shared.caller_team_keys() RETURNS SETOF text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
    SELECT c.team_key
    FROM shared.owner_crosswalk c
    JOIN auth.identities i ON i.provider = 'discord' AND i.provider_id = c.discord_user_id
    WHERE i.user_id = auth.uid()
$fn$;

REVOKE EXECUTE ON FUNCTION shared.caller_team_keys() FROM PUBLIC;

GRANT USAGE ON SCHEMA shared TO authenticated;

GRANT EXECUTE ON FUNCTION shared.caller_team_keys() TO authenticated;

CREATE FUNCTION shared.choice_window(p_season_id text, p_choice_kind text) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
    SELECT coalesce(
        (SELECT CASE WHEN d.deadline_at > clock_timestamp() THEN 'open' ELSE 'passed' END
         FROM ops.choice_deadline d
         WHERE d.season_id = p_season_id AND d.choice_kind = p_choice_kind),
        'none')
$fn$;

REVOKE EXECUTE ON FUNCTION shared.choice_window(text, text) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION shared.choice_window(text, text) TO authenticated;

GRANT USAGE ON SCHEMA app TO authenticated;

REVOKE ALL ON SCHEMA app FROM anon;

REVOKE ALL ON ALL TABLES IN SCHEMA app FROM anon;

ALTER DEFAULT PRIVILEGES IN SCHEMA app REVOKE ALL ON TABLES FROM anon;

GRANT SELECT ON app.team_choice_sharing TO authenticated;

GRANT INSERT (season_id, team_key, shared, changed_by) ON app.team_choice_sharing TO authenticated;

GRANT UPDATE (shared, changed_by) ON app.team_choice_sharing TO authenticated;

CREATE POLICY signed_in_select_all ON app.team_choice_sharing FOR SELECT TO authenticated USING (true);

CREATE POLICY owner_insert_own_team_while_open ON app.team_choice_sharing FOR INSERT TO authenticated WITH CHECK (team_key IN (SELECT shared.caller_team_keys()) AND (shared.choice_window(season_id, 'resign') = 'open' OR shared.choice_window(season_id, 'fa_keep') = 'open') AND changed_by = auth.uid());

CREATE POLICY owner_update_own_team_while_open ON app.team_choice_sharing FOR UPDATE TO authenticated USING (team_key IN (SELECT shared.caller_team_keys()) AND (shared.choice_window(season_id, 'resign') = 'open' OR shared.choice_window(season_id, 'fa_keep') = 'open')) WITH CHECK (team_key IN (SELECT shared.caller_team_keys()) AND (shared.choice_window(season_id, 'resign') = 'open' OR shared.choice_window(season_id, 'fa_keep') = 'open') AND changed_by = auth.uid());

GRANT SELECT ON app.contract_choices TO authenticated;

GRANT INSERT (season_id, team_key, scorer_id, choice_kind, choice, origin, changed_by) ON app.contract_choices TO authenticated;

GRANT UPDATE (choice, origin, changed_by) ON app.contract_choices TO authenticated;

CREATE POLICY owner_select_own_team ON app.contract_choices FOR SELECT TO authenticated USING (team_key IN (SELECT shared.caller_team_keys()));

CREATE POLICY signed_in_select_shared_team ON app.contract_choices FOR SELECT TO authenticated USING (EXISTS (SELECT 1 FROM app.team_choice_sharing s WHERE s.season_id = contract_choices.season_id AND s.team_key = contract_choices.team_key AND s.shared));

CREATE POLICY signed_in_select_after_deadline ON app.contract_choices FOR SELECT TO authenticated USING (shared.choice_window(season_id, choice_kind) = 'passed');

CREATE POLICY owner_insert_own_team_while_open ON app.contract_choices FOR INSERT TO authenticated WITH CHECK (team_key IN (SELECT shared.caller_team_keys()) AND shared.choice_window(season_id, choice_kind) = 'open' AND origin = 'app' AND changed_by = auth.uid());

CREATE POLICY owner_update_own_team_while_open ON app.contract_choices FOR UPDATE TO authenticated USING (team_key IN (SELECT shared.caller_team_keys()) AND shared.choice_window(season_id, choice_kind) = 'open') WITH CHECK (team_key IN (SELECT shared.caller_team_keys()) AND shared.choice_window(season_id, choice_kind) = 'open' AND origin = 'app' AND changed_by = auth.uid());

CREATE TRIGGER team_choice_sharing_set_changed_at BEFORE UPDATE ON app.team_choice_sharing FOR EACH ROW EXECUTE FUNCTION ops.set_changed_at();
