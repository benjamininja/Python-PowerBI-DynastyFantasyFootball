-- registry_state sha256: fd50cbe41fda997f6b848c4cd86797fc93c8b343d603b6df0695ba1185d6f925

CREATE TABLE shared.fantasy_team (
    team_key text NOT NULL,
    league_key text NOT NULL,
    fantrax_team_id text,
    team_name text,
    division text,
    CONSTRAINT fantasy_team_pkey PRIMARY KEY (team_key)
);

CREATE TABLE shared.league (
    league_key text NOT NULL,
    sport text,
    league_name text,
    fantrax_league_id text NOT NULL,
    CONSTRAINT league_pkey PRIMARY KEY (league_key)
);

ALTER TABLE shared.fantasy_team ADD CONSTRAINT fantasy_team_league_key_fkey FOREIGN KEY (league_key) REFERENCES shared.league (league_key) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE shared.fantasy_team ENABLE ROW LEVEL SECURITY;

ALTER TABLE shared.league ENABLE ROW LEVEL SECURITY;

CREATE FUNCTION shared.load_leagues(p_league_keys text[], p_sports text[], p_league_names text[], p_fantrax_ids text[]) RETURNS TABLE (rows_before integer, rows_after integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $fn$
DECLARE
    v_keys integer := coalesce(cardinality(p_league_keys), 0);
    v_bad integer;
BEGIN
    IF v_keys = 0 OR v_keys <> coalesce(cardinality(p_sports), 0) OR v_keys <> coalesce(cardinality(p_league_names), 0)
            OR v_keys <> coalesce(cardinality(p_fantrax_ids), 0) THEN
        RAISE EXCEPTION 'League Associations tab: refused, % key(s) and arrays of unequal length or none; nothing changed', v_keys;
    END IF;
    SELECT count(*) INTO v_bad FROM unnest(p_league_keys) AS u(k)
    WHERE u.k IS NULL OR u.k !~ '^[a-z][a-z0-9_]*$';
    IF v_bad > 0 THEN
        RAISE EXCEPTION 'League Associations tab: refused, % key(s) are not a plain lowercase word; nothing changed', v_bad;
    END IF;
    SELECT count(*) INTO v_bad FROM unnest(p_fantrax_ids) AS u(f)
    WHERE u.f IS NULL OR btrim(u.f) = '';
    IF v_bad > 0 THEN
        RAISE EXCEPTION 'League Associations tab: refused, % row(s) have no Fantrax league id; nothing changed', v_bad;
    END IF;
    SELECT (count(*) - count(DISTINCT u.k)) + (count(*) - count(DISTINCT u.f)) INTO v_bad
    FROM unnest(p_league_keys, p_fantrax_ids) AS u(k, f);
    IF v_bad > 0 THEN
        RAISE EXCEPTION 'League Associations tab: refused, % repeated key(s) or Fantrax id(s); nothing changed', v_bad;
    END IF;
    SELECT count(*) INTO rows_before FROM shared.league;
    BEGIN
        DELETE FROM shared.league WHERE true;
        INSERT INTO shared.league (league_key, sport, league_name, fantrax_league_id)
        SELECT u.k, u.s, u.n, u.f FROM unnest(p_league_keys, p_sports, p_league_names, p_fantrax_ids) AS u(k, s, n, f);
    EXCEPTION WHEN OTHERS THEN
        RAISE EXCEPTION 'League Associations tab: the load failed (SQLSTATE %); nothing changed', SQLSTATE;
    END;
    SELECT count(*) INTO rows_after FROM shared.league;
    RETURN NEXT;
END
$fn$;

REVOKE EXECUTE ON FUNCTION shared.load_leagues(text[], text[], text[], text[]) FROM PUBLIC;

GRANT USAGE ON SCHEMA shared TO etl_writer;

GRANT EXECUTE ON FUNCTION shared.load_leagues(text[], text[], text[], text[]) TO etl_writer;

CREATE FUNCTION shared.load_teams(p_team_keys text[], p_league_keys text[], p_fantrax_team_ids text[], p_team_names text[], p_divisions text[]) RETURNS TABLE (rows_before integer, rows_after integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $fn$
DECLARE
    v_keys integer := coalesce(cardinality(p_team_keys), 0);
    v_bad integer;
BEGIN
    IF v_keys = 0 OR v_keys <> coalesce(cardinality(p_league_keys), 0)
            OR v_keys <> coalesce(cardinality(p_fantrax_team_ids), 0)
            OR v_keys <> coalesce(cardinality(p_team_names), 0) OR v_keys <> coalesce(cardinality(p_divisions), 0) THEN
        RAISE EXCEPTION 'team tab: refused, % team key(s) and arrays of unequal length or none; nothing changed', v_keys;
    END IF;
    SELECT count(*) INTO v_bad FROM unnest(p_team_keys) AS u(t)
    WHERE u.t IS NULL OR btrim(u.t) = '';
    IF v_bad > 0 THEN
        RAISE EXCEPTION 'team tab: refused, % row(s) have no team key; nothing changed', v_bad;
    END IF;
    SELECT count(*) INTO v_bad FROM unnest(p_league_keys) AS u(k)
    WHERE u.k IS NULL OR NOT EXISTS (SELECT 1 FROM shared.league l WHERE l.league_key = u.k);
    IF v_bad > 0 THEN
        RAISE EXCEPTION 'team tab: refused, % row(s) name a league the league table does not have; nothing changed', v_bad;
    END IF;
    SELECT count(*) - count(DISTINCT u.t) INTO v_bad FROM unnest(p_team_keys) AS u(t);
    IF v_bad > 0 THEN
        RAISE EXCEPTION 'team tab: refused, % repeated team key(s); nothing changed', v_bad;
    END IF;
    SELECT count(*) INTO rows_before FROM shared.fantasy_team;
    BEGIN
        DELETE FROM shared.fantasy_team WHERE true;
        INSERT INTO shared.fantasy_team (team_key, league_key, fantrax_team_id, team_name, division)
        SELECT u.t, u.k, u.f, u.n, u.d
        FROM unnest(p_team_keys, p_league_keys, p_fantrax_team_ids, p_team_names, p_divisions) AS u(t, k, f, n, d);
    EXCEPTION WHEN OTHERS THEN
        RAISE EXCEPTION 'team tab: the load failed (SQLSTATE %); nothing changed', SQLSTATE;
    END;
    SELECT count(*) INTO rows_after FROM shared.fantasy_team;
    RETURN NEXT;
END
$fn$;

REVOKE EXECUTE ON FUNCTION shared.load_teams(text[], text[], text[], text[], text[]) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION shared.load_teams(text[], text[], text[], text[], text[]) TO etl_writer;

CREATE UNIQUE INDEX league_fantrax_league_id_key ON shared.league (fantrax_league_id);
