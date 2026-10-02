# Supabase platform facts for this pipeline

Research ticket #73 (map #69, Supabase storage foundation). Sources read 2026-09-26.
Where a fact comes from community reports and not official docs, it is marked **[community]**.

Context: 28 `data/*.parquet` files total about 3.8 MB on disk today (the same order as the
~1,300-row projections in ADR-0012). Writer: a Windows Task Scheduler job on a home PC.
Readers: Power BI (PBIP), a discord.py bot on Railway, and a GitHub Pages build in Actions.

## 1. Free-tier limits and cost triggers

| Item | Free | Pro ($25/mo) |
|---|---|---|
| DB size | 500 MB (shared CPU, 500 MB RAM) | 8 GB disk, then $0.125/GB |
| Egress | 5 GB | 250 GB, then $0.09/GB |
| File storage | 1 GB | 100 GB |
| Active projects | 2 per org (paused projects don't count) | $10/mo compute credit covers one Micro instance |
| Pause on inactivity | Yes, after 1 week | Never |
| Backups | None | Daily, 7-day retention |
| PITR | Not available | Add-on, ~$100/mo (7-day) to ~$400/mo (28-day) |

- Going over a free quota: you get an email, then a one-time grace period. After that the
  restrictions can include pausing, read-only DB mode, or HTTP 402 on API calls. There is
  no second grace period. ([billing FAQ](https://supabase.com/docs/guides/platform/billing-faq))
- Sources: [pricing](https://supabase.com/pricing), [billing FAQ](https://supabase.com/docs/guides/platform/billing-faq).

**Pause rule** ([free-project-pausing](https://supabase.com/docs/guides/platform/free-project-pausing)):
- A project is "inactive" when it gets too little *user database activity* over the past week.
  Per the docs, "a few user requests to the database each day" over that week is usually enough.
  Visiting the dashboard does not count.
- You get a warning email about 7 days before the pause and a second email after it.
- Restore by clicking **Resume project** in the dashboard. The docs page gives a 1-year restore
  window. An older troubleshooting page says 90 days, then download the backup and migrate
  ([restore-after-90-days](https://supabase.com/docs/guides/troubleshooting/restore-project-after-90-days-pause)).
  Plan against the stricter number.
- Upgrading to a paid plan is the only prevention the docs name.
- **For us:** the ETL writes daily in-season, and the bot and Power BI read regularly, so the
  project should stay active. The risk is the off-season: the scheduled job stops, the league
  goes quiet, and within about a week the DB pauses and all three consumers break. Mitigation:
  a daily keep-alive query (an Actions cron or Task Scheduler job running `select 1` against a
  user table), or pay for Pro.

## 2. Connecting from the scheduled Python job

From [connecting-to-postgres](https://supabase.com/docs/guides/database/connecting-to-postgres):

| Mode | Host:port | IP | Notes |
|---|---|---|---|
| Direct | `db.<ref>.supabase.co:5432` | **IPv6 only** unless you buy the IPv4 add-on | For long-lived servers |
| Supavisor **session** | `aws-<n>-<region>.pooler.supabase.com:5432` | IPv4, all plans | Prepared statements and session state work |
| Supavisor **transaction** | same host, `:6543` | IPv4 | Serverless use. No prepared statements, cursors or session state |
| Dedicated pooler | `db.<ref>.supabase.co:6543` | — | Paid plans only |

- Pooler usernames take the form `postgres.<project-ref>`.
- **Recommendation: session pooler on :5432.** Home ISPs and Railway egress are often IPv4-only,
  and session mode keeps COPY, temp tables and `SET statement_timeout` working.
- **Timeouts** ([timeouts](https://supabase.com/docs/guides/database/postgres/timeouts)):
  - `anon` 3 s, `authenticated` 8 s, `service_role` falls back to 8 s.
  - The `postgres` role is capped by a 2-minute global timeout.
  - Dashboard and Data API queries have a 60 s maximum.
  - `SET statement_timeout` works only over a direct or session-pooler connection.
- **Client choice:**
  - **psycopg 3** (plain, or under SQLAlchemy 2.x with `postgresql+psycopg://`) for the ETL.
    Supabase recommends COPY for bulk loads
    ([tables](https://supabase.com/docs/guides/database/tables)). psycopg 3 exposes it as
    `cur.copy("COPY t (...) FROM STDIN")` with `write_row` or `write`
    ([psycopg COPY](https://www.psycopg.org/psycopg3/docs/basic/copy.html)).
    Pattern: TRUNCATE+COPY in one transaction per table, or COPY into staging then swap.
    pandas `to_sql` works but is slower.
  - **supabase-py / PostgREST** is a poor fit for bulk writes. Responses are capped at
    **1,000 rows by default** (configurable) and calls hit role timeouts. It's fine for small
    bot reads ([limit ref](https://supabase.com/docs/reference/python/limit)).
- SSL: the server accepts non-SSL connections by default. You can enable enforcement, and it
  then covers direct, Supavisor and PgBouncer connections. The CA cert (`prod-ca-2021.crt`)
  can be downloaded under Database Settings → SSL Configuration. Use `sslmode=verify-full`
  with it ([ssl-enforcement](https://supabase.com/docs/guides/platform/ssl-enforcement)).

## 3. Power BI

From the [PostgreSQL connector docs](https://learn.microsoft.com/en-us/power-query/connectors/postgresql)
(updated 2026-07-31):

- **Npgsql is bundled.** It has shipped with Desktop since Dec 2019; Desktop since Oct 2024
  bundles Npgsql 4.0.17. The on-premises gateway bundles it since June 2025. Installing Npgsql
  4.1+ is *not* supported.
- The connector supports Import and DirectQuery. Auth is database user/password or Entra ID.
  It is supported over a **cloud connection** or through a VNet or on-prem gateway.
- Encryption: if the server's certificate isn't trusted, "your machine might be required to
  install the PostgreSQL server's SSL certificate into its Trusted Root Certification Authorities."
- **BLOCKER-ish [community]:** Supabase certificates chain to Supabase's own root CA, which
  Microsoft's cloud does not trust. Reports up to Mar 2026 say Power BI **service** scheduled
  refresh over a cloud connection fails certificate validation, even with "encrypt connection"
  cleared. The working route is an **on-premises data gateway** on a machine that has the
  Supabase CA installed ([supabase discussion #13885](https://github.com/orgs/supabase/discussions/13885)).
  Another route is to skip the PG connector and call PostgREST through `Web.Contents`
  ([dev.to walkthrough](https://dev.to/jenniekibiri/how-to-connect-supabase-to-microsoft-power-bi-50p8)).
- **Desktop:** import the CA into Windows Trusted Root, or clear "Encrypt connections" in
  Data source settings. Also connect to the session-pooler host, because direct is IPv6-only.
- The home PC already runs the ETL, so it can also host a personal-mode or standard gateway.
  That costs nothing but ties service refresh to the PC being on. This is no worse than today's
  `File.Contents` local-path refresh, which also needs a gateway.

## 4. API keys and RLS

From [api-keys](https://supabase.com/docs/guides/api/api-keys):

- **New model:**
  - `sb_publishable_…`: safe in browsers. Maps to the `anon` or `authenticated` role, so it
    **respects RLS**.
  - `sb_secret_…`: server-side only. Maps to `service_role` (BYPASSRLS), giving full access.
    It returns 401 when called from a browser, detected by User-Agent.
- Legacy JWT `anon` / `service_role` keys are **deprecated by end of 2026**. Use the new keys
  from day one.
- These keys only gate the Data API (PostgREST). Direct or pooler Postgres connections use DB
  roles and passwords instead. Plan: ETL uses a DB role with write grants; Power BI uses a
  read-only DB role.
- The bot has two options. It can use a read-only DB role over the pooler, or a publishable key
  with RLS `select`-only policies. **Never an anon-writable RLS** (the HoD reference pattern,
  rejected in #69). Enable RLS on every `public` table; with no policies, the Data API exposes
  nothing to publishable keys.
- Pages builds in Actions, so it can keep building static JSON from a secret-held read
  connection. Nothing goes to the browser, which keeps ADR-0012's "no secrets in production".

## 5. Backups / PITR

([backups](https://supabase.com/docs/guides/platform/backups))

- **Free: no automated backups and no PITR.** Supabase tells free users to run
  `supabase db dump` regularly and keep the dumps off-site.
- Pro: daily backups with 7-day retention. PITR is a paid add-on at about $100/mo or more.
- For us: parquet-in-git (or a periodic `pg_dump`/parquet snapshot commit) stays the de facto
  backup on free tier. The ETL can also rebuild everything from raw sources.

## 6. Migrations in the repo (Supabase CLI)

([database-migrations](https://supabase.com/docs/guides/deployment/database-migrations))

- `supabase init` creates `supabase/`.
- `supabase login` authenticates with a personal access token, then `supabase link --project-ref <ref>`.
- `supabase migration new <name>` creates `supabase/migrations/<timestamp>_<name>.sql`.
- `supabase db push` applies pending migrations to the remote project.
- `supabase db diff` captures dashboard edits as a migration; `supabase db pull` pulls the
  remote schema.
- `supabase db reset` and the local stack need **Docker**. `db push` does not, so a push-only
  workflow from the Windows PC or from Actions works without Docker.
- Rule from the docs: never change the remote schema directly. All DDL goes through migration
  files.

## Blockers and cost triggers

- **Blocker for service refresh without a gateway [community]:** the Supabase CA is untrusted
  by the Power BI cloud. Expect to need an on-prem gateway, or a Web/PostgREST connector workaround.
- **Direct connection is IPv6-only.** Use the session pooler unless you pay for the IPv4 add-on.
- **Off-season pause after 7 days idle** breaks every consumer. It needs a keep-alive job or Pro.
- **No backups on Free.** Keep a git or dump-based backup.
- Cost triggers:
  - Pro ($25/mo) for no pausing and daily backups.
  - IPv4 add-on (only if the direct connection is needed).
  - PITR (about $100/mo).
  - Egress over 5 GB. Unlikely with MB-scale data, but a Power BI DirectQuery model or full
    reloads on every bot command could add up. Prefer Import mode.
- Size is a non-issue: about 4 MB of parquet against a 500 MB cap.

## Implications for A1/A4

**A1 (storage role, backend, seam, and load):**
- The Free plan fits the data volume.
- The seam's Postgres backend should use psycopg 3 against the **session pooler**, with
  TRUNCATE+COPY per table in one transaction (a staging swap for large facts).
- Put migrations in `supabase/migrations/` and apply them with `supabase db push`. No Docker
  is needed for push.
- The ADR must choose between:
  - keeping parquet-in-git as backup/snapshot (recommended on Free, since there are no
    backups), and
  - retiring `commit_data`.
- It must also choose between a keep-alive job and paying for Pro.
- Use the new `sb_secret_`/`sb_publishable_` keys only. Grant DB roles per consumer: an ETL
  writer, and a read-only role for Power BI and the bot.

**A4 (consumer cutover):**
- Power BI: PostgreSQL connector (Npgsql bundled) over the session-pooler host.
  - Desktop needs the Supabase CA in Trusted Root, or encryption turned off.
  - Service scheduled refresh should **assume an on-prem gateway** on the home PC (the same
    dependency as today's local-file refresh).
  - Prefer Import over DirectQuery, for egress reasons and the timeouts above.
- Bot on Railway: a read-only role over the IPv4 pooler (psycopg). supabase-py with a
  publishable key and select-only RLS is also workable; watch the 1,000-row cap.
- trade-bud `pages.yml`: keep the static export (ADR-0012 stands). Only the source changes:
  Actions reads Postgres with a repo secret instead of checked-out parquet, and no key reaches
  the browser.
