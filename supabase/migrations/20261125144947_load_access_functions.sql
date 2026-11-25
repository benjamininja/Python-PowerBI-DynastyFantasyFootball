-- registry_state sha256: 4484bf0e34909dcfbd5cc51e6b99862eaaa1405836e0c1f8926d49ec1d426edb

CREATE FUNCTION shared.load_owner_crosswalk(p_team_keys text[], p_discord_ids text[]) RETURNS TABLE (rows_before integer, rows_after integer)
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
    WHERE u.t IS NULL OR NOT EXISTS (SELECT 1 FROM football.dim_fantasy_teams d WHERE d.team_key = u.t);
    IF v_bad > 0 THEN
        RAISE EXCEPTION 'owner tab: refused, % row(s) name a team the database does not have; nothing changed', v_bad;
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

REVOKE EXECUTE ON FUNCTION shared.load_owner_crosswalk(text[], text[]) FROM PUBLIC;

GRANT USAGE ON SCHEMA shared TO etl_writer;

GRANT EXECUTE ON FUNCTION shared.load_owner_crosswalk(text[], text[]) TO etl_writer;

CREATE FUNCTION shared.load_app_roles(p_discord_ids text[], p_roles text[]) RETURNS TABLE (rows_before integer, rows_after integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $fn$
DECLARE
    v_ids integer := coalesce(cardinality(p_discord_ids), 0);
    v_roles integer := coalesce(cardinality(p_roles), 0);
    v_bad integer;
BEGIN
    IF v_ids = 0 OR v_ids <> v_roles THEN
        RAISE EXCEPTION 'App roles tab: refused, % id(s) and % role(s); nothing changed', v_ids, v_roles;
    END IF;
    SELECT count(*) INTO v_bad FROM unnest(p_discord_ids) AS u(i)
    WHERE u.i IS NULL OR length(u.i) NOT BETWEEN 17 AND 20 OR u.i ~ '[^0-9]';
    IF v_bad > 0 THEN
        RAISE EXCEPTION 'App roles tab: refused, % id(s) are not 17 to 20 digits; nothing changed', v_bad;
    END IF;
    SELECT count(*) INTO v_bad FROM unnest(p_roles) AS u(r)
    WHERE u.r IS NULL OR u.r NOT IN ('commissioner', 'site_admin');
    IF v_bad > 0 THEN
        RAISE EXCEPTION 'App roles tab: refused, % role(s) are neither commissioner nor site_admin; nothing changed', v_bad;
    END IF;
    SELECT count(*) - count(DISTINCT (u.i, u.r)) INTO v_bad FROM unnest(p_discord_ids, p_roles) AS u(i, r);
    IF v_bad > 0 THEN
        RAISE EXCEPTION 'App roles tab: refused, % repeated row(s); nothing changed', v_bad;
    END IF;
    SELECT count(*) INTO rows_before FROM shared.app_role;
    BEGIN
        DELETE FROM shared.app_role WHERE true;
        INSERT INTO shared.app_role (discord_user_id, role, league_key)
        SELECT u.i, u.r, CASE u.r WHEN 'site_admin' THEN '*' ELSE 'main' END
        FROM unnest(p_discord_ids, p_roles) AS u(i, r);
    EXCEPTION WHEN OTHERS THEN
        RAISE EXCEPTION 'App roles tab: the load failed (SQLSTATE %); nothing changed', SQLSTATE;
    END;
    SELECT count(*) INTO rows_after FROM shared.app_role;
    RETURN NEXT;
END
$fn$;

REVOKE EXECUTE ON FUNCTION shared.load_app_roles(text[], text[]) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION shared.load_app_roles(text[], text[]) TO etl_writer;
