-- registry_state sha256: 78e983ff1210ade69bf9e4dfd60b230edcf94adeb127559a6e1056c4a3827414

CREATE FUNCTION shared.choice_windows() RETURNS TABLE (season_id text, choice_kind text, state text, deadline_at timestamptz, final_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
    SELECT d.season_id, d.choice_kind, shared.choice_window(d.season_id, d.choice_kind), d.deadline_at, d.final_at
    FROM ops.choice_deadline d
$fn$;

REVOKE EXECUTE ON FUNCTION shared.choice_windows() FROM PUBLIC;

GRANT USAGE ON SCHEMA shared TO authenticated;

GRANT EXECUTE ON FUNCTION shared.choice_windows() TO authenticated;

GRANT USAGE ON SCHEMA app TO authenticated;

REVOKE ALL ON SCHEMA app FROM anon;

REVOKE ALL ON ALL TABLES IN SCHEMA app FROM anon;

ALTER DEFAULT PRIVILEGES IN SCHEMA app REVOKE ALL ON TABLES FROM anon;

CREATE VIEW app.choice_windows WITH (security_invoker = true) AS
    SELECT r.season_id, r.choice_kind, r.state, r.deadline_at, r.final_at
    FROM shared.choice_windows() AS r(season_id, choice_kind, state, deadline_at, final_at);

REVOKE ALL ON app.choice_windows FROM PUBLIC, anon, authenticated;

GRANT SELECT ON app.choice_windows TO authenticated;

CREATE VIEW app.my_teams WITH (security_invoker = true) AS
    SELECT r.team_key
    FROM shared.caller_team_keys() AS r(team_key);

REVOKE ALL ON app.my_teams FROM PUBLIC, anon, authenticated;

GRANT SELECT ON app.my_teams TO authenticated;
