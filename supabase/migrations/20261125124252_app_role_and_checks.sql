-- registry_state sha256: cc3207058da5d4a9e54435bbae9348861b7d726d8d5c9b891bd67f241da221d8

CREATE TABLE shared.app_role (
    discord_user_id text NOT NULL,
    role text NOT NULL,
    league_key text NOT NULL,
    CONSTRAINT app_role_pkey PRIMARY KEY (discord_user_id, role, league_key),
    CONSTRAINT app_role_chk_4fe7a3e2 CHECK (length(discord_user_id) BETWEEN 17 AND 20 AND discord_user_id !~ '[^0-9]'),
    CONSTRAINT app_role_chk_ae503904 CHECK (role IN ('commissioner', 'site_admin')),
    CONSTRAINT app_role_chk_9452c2af CHECK ((role = 'site_admin' AND league_key = '*') OR (role = 'commissioner' AND league_key <> '*'))
);

ALTER TABLE shared.app_role ENABLE ROW LEVEL SECURITY;

CREATE FUNCTION shared.caller_is_commissioner_for(p_team_key text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
    SELECT EXISTS (
        SELECT 1
        FROM shared.app_role r
        JOIN auth.identities i ON i.provider = 'discord' AND i.provider_id = r.discord_user_id
        JOIN football.dim_fantasy_teams t ON t.team_key = p_team_key
        WHERE r.role = 'commissioner' AND r.league_key = 'main' AND i.user_id = auth.uid()
    )
$fn$;

REVOKE EXECUTE ON FUNCTION shared.caller_is_commissioner_for(text) FROM PUBLIC;

GRANT USAGE ON SCHEMA shared TO authenticated;

GRANT EXECUTE ON FUNCTION shared.caller_is_commissioner_for(text) TO authenticated;

CREATE FUNCTION shared.caller_is_site_admin() RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
    SELECT EXISTS (
        SELECT 1
        FROM shared.app_role r
        JOIN auth.identities i ON i.provider = 'discord' AND i.provider_id = r.discord_user_id
        WHERE r.role = 'site_admin' AND r.league_key = '*' AND i.user_id = auth.uid()
    )
$fn$;

REVOKE EXECUTE ON FUNCTION shared.caller_is_site_admin() FROM PUBLIC;

GRANT EXECUTE ON FUNCTION shared.caller_is_site_admin() TO authenticated;

CREATE OR REPLACE FUNCTION shared.pii_token_hashes() RETURNS SETOF text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
    SELECT encode(sha256(convert_to(s.token, 'UTF8')), 'hex')
    FROM (
        SELECT regexp_split_to_table(lower(o.human_name), '[[:space:]]+') AS token FROM shared.owner o
        UNION
        SELECT lower(o.fantrax_username) FROM shared.owner o
        UNION
        SELECT c.discord_user_id FROM shared.owner_crosswalk c
        UNION
        SELECT r.discord_user_id FROM shared.app_role r
    ) s
    WHERE s.token IS NOT NULL AND s.token <> ''
$fn$;
