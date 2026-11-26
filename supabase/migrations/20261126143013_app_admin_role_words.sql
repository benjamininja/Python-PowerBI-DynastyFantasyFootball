-- registry_state sha256: 09cdf64c2ce9bde000c4c6ec8c87ae30b74672c3e4a4769f4feaea24f9e509b6

ALTER TABLE shared.app_role DROP CONSTRAINT app_role_chk_ae503904;

ALTER TABLE shared.app_role DROP CONSTRAINT app_role_chk_9452c2af;

UPDATE shared.app_role SET role = 'app_admin' WHERE role = 'site_admin';

ALTER TABLE shared.app_role ADD CONSTRAINT app_role_chk_dcbe11c9 CHECK (role IN ('owner', 'commissioner', 'app_admin'));

ALTER TABLE shared.app_role ADD CONSTRAINT app_role_chk_5a656913 CHECK ((role = 'app_admin' AND league_key = '*') OR (role IN ('owner', 'commissioner') AND league_key <> '*'));

CREATE FUNCTION shared.caller_is_app_admin() RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
    SELECT EXISTS (
        SELECT 1
        FROM shared.app_role r
        JOIN auth.identities i ON i.provider = 'discord' AND i.provider_id = r.discord_user_id
        WHERE r.role = 'app_admin' AND r.league_key = '*' AND i.user_id = auth.uid()
    )
$fn$;

REVOKE EXECUTE ON FUNCTION shared.caller_is_app_admin() FROM PUBLIC;

GRANT USAGE ON SCHEMA shared TO authenticated;

GRANT EXECUTE ON FUNCTION shared.caller_is_app_admin() TO authenticated;

CREATE OR REPLACE FUNCTION shared.load_app_roles(p_discord_ids text[], p_roles text[]) RETURNS TABLE (rows_before integer, rows_after integer)
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
    WHERE u.r IS NULL OR u.r NOT IN ('owner', 'commissioner', 'app_admin');
    IF v_bad > 0 THEN
        RAISE EXCEPTION 'App roles tab: refused, % role(s) are not owner, commissioner or app_admin; nothing changed', v_bad;
    END IF;
    SELECT count(*) - count(DISTINCT (u.i, u.r)) INTO v_bad FROM unnest(p_discord_ids, p_roles) AS u(i, r);
    IF v_bad > 0 THEN
        RAISE EXCEPTION 'App roles tab: refused, % repeated row(s); nothing changed', v_bad;
    END IF;
    SELECT count(*) INTO rows_before FROM shared.app_role;
    BEGIN
        DELETE FROM shared.app_role WHERE true;
        INSERT INTO shared.app_role (discord_user_id, role, league_key)
        SELECT u.i, u.r, CASE u.r WHEN 'app_admin' THEN '*' ELSE 'main' END
        FROM unnest(p_discord_ids, p_roles) AS u(i, r);
    EXCEPTION WHEN OTHERS THEN
        RAISE EXCEPTION 'App roles tab: the load failed (SQLSTATE %); nothing changed', SQLSTATE;
    END;
    SELECT count(*) INTO rows_after FROM shared.app_role;
    RETURN NEXT;
END
$fn$;

DROP FUNCTION shared.caller_is_site_admin();
