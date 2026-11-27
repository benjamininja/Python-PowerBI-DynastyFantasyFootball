-- registry_state sha256: 00086f2c7f0546b3879fe90d2e373925afd89538ed7362371321297ecda4fdcd

UPDATE shared.app_role SET league_key = 'football' WHERE league_key = 'main';

ALTER TABLE shared.owner_crosswalk DROP CONSTRAINT owner_crosswalk_team_key_fkey;

DELETE FROM shared.owner_crosswalk WHERE true;

ALTER TABLE shared.owner_crosswalk ADD CONSTRAINT owner_crosswalk_team_key_fkey FOREIGN KEY (team_key) REFERENCES shared.fantasy_team (team_key) DEFERRABLE INITIALLY DEFERRED;

DROP FUNCTION shared.load_app_roles(text[], text[]);

CREATE FUNCTION shared.load_app_roles(p_discord_ids text[], p_roles text[], p_league_keys text[]) RETURNS TABLE (rows_before integer, rows_after integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $fn$
DECLARE
    v_ids integer := coalesce(cardinality(p_discord_ids), 0);
    v_roles integer := coalesce(cardinality(p_roles), 0);
    v_leagues integer := coalesce(cardinality(p_league_keys), 0);
    v_bad integer;
BEGIN
    IF v_ids = 0 OR v_ids <> v_roles OR v_ids <> v_leagues THEN
        RAISE EXCEPTION 'App roles tab: refused, % id(s), % role(s) and % league(s); nothing changed', v_ids, v_roles, v_leagues;
    END IF;
    SELECT count(*) INTO v_bad FROM unnest(p_discord_ids) AS u(i)
    WHERE u.i IS NULL OR length(u.i) NOT BETWEEN 17 AND 20 OR u.i ~ '[^0-9]';
    IF v_bad > 0 THEN
        RAISE EXCEPTION 'App roles tab: refused, % id(s) are not 17 to 20 digits; nothing changed', v_bad;
    END IF;
    SELECT count(*) INTO v_bad FROM unnest(p_roles) AS u(r)
    WHERE u.r IS NULL OR u.r NOT IN ('owner', 'commissioner', 'app_admin');
    IF v_bad > 0 THEN
        RAISE EXCEPTION 'App roles tab: refused, % role(s) are not owner, commissioner or app_admin; nothing changed', v_bad;
    END IF;
    SELECT count(*) INTO v_bad FROM unnest(p_roles, p_league_keys) AS u(r, k)
    WHERE u.k IS NULL OR (u.r = 'app_admin') <> (u.k = '*');
    IF v_bad > 0 THEN
        RAISE EXCEPTION 'App roles tab: refused, % row(s) pair a role and a league wrongly (app_admin holds every league, the others one); nothing changed', v_bad;
    END IF;
    SELECT count(*) INTO v_bad FROM unnest(p_league_keys) AS u(k)
    WHERE u.k <> '*' AND NOT EXISTS (SELECT 1 FROM shared.league l WHERE l.league_key = u.k);
    IF v_bad > 0 THEN
        RAISE EXCEPTION 'App roles tab: refused, % row(s) name a league the league table does not have; nothing changed', v_bad;
    END IF;
    SELECT count(*) - count(DISTINCT (u.i, u.r, u.k)) INTO v_bad FROM unnest(p_discord_ids, p_roles, p_league_keys) AS u(i, r, k);
    IF v_bad > 0 THEN
        RAISE EXCEPTION 'App roles tab: refused, % repeated row(s); nothing changed', v_bad;
    END IF;
    SELECT count(*) INTO rows_before FROM shared.app_role;
    BEGIN
        DELETE FROM shared.app_role WHERE true;
        INSERT INTO shared.app_role (discord_user_id, role, league_key)
        SELECT u.i, u.r, u.k
        FROM unnest(p_discord_ids, p_roles, p_league_keys) AS u(i, r, k);
    EXCEPTION WHEN OTHERS THEN
        RAISE EXCEPTION 'App roles tab: the load failed (SQLSTATE %); nothing changed', SQLSTATE;
    END;
    SELECT count(*) INTO rows_after FROM shared.app_role;
    RETURN NEXT;
END
$fn$;

REVOKE EXECUTE ON FUNCTION shared.load_app_roles(text[], text[], text[]) FROM PUBLIC;

GRANT USAGE ON SCHEMA shared TO etl_writer;

GRANT EXECUTE ON FUNCTION shared.load_app_roles(text[], text[], text[]) TO etl_writer;

CREATE OR REPLACE FUNCTION shared.load_owner_crosswalk(p_team_keys text[], p_discord_ids text[]) RETURNS TABLE (rows_before integer, rows_after integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $fn$
DECLARE
    v_keys integer := coalesce(cardinality(p_team_keys), 0);
    v_ids integer := coalesce(cardinality(p_discord_ids), 0);
    v_bad integer;
BEGIN
    IF v_keys = 0 OR v_keys <> v_ids THEN
        RAISE EXCEPTION 'owner tab: refused, % team key(s) and % id(s); nothing changed', v_keys, v_ids;
    END IF;
    SELECT count(*) INTO v_bad FROM unnest(p_discord_ids) AS u(i)
    WHERE u.i IS NULL OR length(u.i) NOT BETWEEN 17 AND 20 OR u.i ~ '[^0-9]';
    IF v_bad > 0 THEN
        RAISE EXCEPTION 'owner tab: refused, % id(s) are not 17 to 20 digits; nothing changed', v_bad;
    END IF;
    SELECT count(*) INTO v_bad FROM unnest(p_team_keys) AS u(t)
    WHERE u.t IS NULL OR NOT EXISTS (SELECT 1 FROM shared.fantasy_team d WHERE d.team_key = u.t);
    IF v_bad > 0 THEN
        RAISE EXCEPTION 'owner tab: refused, % row(s) name a team the team list does not have; nothing changed', v_bad;
    END IF;
    SELECT count(*) - count(DISTINCT (u.t, u.i)) INTO v_bad FROM unnest(p_team_keys, p_discord_ids) AS u(t, i);
    IF v_bad > 0 THEN
        RAISE EXCEPTION 'owner tab: refused, % repeated row(s); nothing changed', v_bad;
    END IF;
    SELECT count(*) INTO rows_before FROM shared.owner_crosswalk;
    BEGIN
        DELETE FROM shared.owner_crosswalk WHERE true;
        INSERT INTO shared.owner_crosswalk (team_key, discord_user_id)
        SELECT u.t, u.i FROM unnest(p_team_keys, p_discord_ids) AS u(t, i);
    EXCEPTION WHEN OTHERS THEN
        RAISE EXCEPTION 'owner tab: the load failed (SQLSTATE %); nothing changed', SQLSTATE;
    END;
    SELECT count(*) INTO rows_after FROM shared.owner_crosswalk;
    RETURN NEXT;
END
$fn$;

CREATE OR REPLACE FUNCTION shared.caller_is_commissioner_for(p_team_key text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
    SELECT EXISTS (
        SELECT 1
        FROM shared.app_role r
        JOIN auth.identities i ON i.provider = 'discord' AND i.provider_id = r.discord_user_id
        JOIN shared.fantasy_team t ON t.team_key = p_team_key AND t.league_key = r.league_key
        WHERE r.role = 'commissioner' AND i.user_id = auth.uid()
    )
$fn$;
