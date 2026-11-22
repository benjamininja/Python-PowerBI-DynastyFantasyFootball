-- A stand-in for the parts of Supabase's auth setup the migrations name (#548
-- brief 3, ADR-0025). Run on a throwaway Postgres only, before the migrations:
-- CREATE POLICY and CREATE FUNCTION resolve auth.uid() and auth.identities when
-- they run. Each object is made only when absent, so a database that already
-- has Supabase's own is left untouched. It never lives in supabase/migrations/
-- and never runs against the real project.
DO $stub$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon') THEN
        CREATE ROLE anon NOLOGIN NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated NOLOGIN NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_namespace WHERE nspname = 'auth') THEN
        CREATE SCHEMA auth;
        GRANT USAGE ON SCHEMA auth TO anon, authenticated;
    END IF;
    IF to_regclass('auth.identities') IS NULL THEN
        CREATE TABLE auth.identities (user_id uuid, provider text, provider_id text);
    END IF;
    IF NOT EXISTS (SELECT FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                   WHERE n.nspname = 'auth' AND p.proname = 'uid') THEN
        CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE
        AS $uid$ SELECT nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $uid$;
        GRANT EXECUTE ON FUNCTION auth.uid() TO anon, authenticated;
    END IF;
END
$stub$;
