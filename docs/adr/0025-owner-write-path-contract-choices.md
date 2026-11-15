# Owner write path: signed-in owners record their contract choices through row-level security

- Status: proposed. The design was settled with the owner on [#548](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/548) on 2026-11-14 (pop-up answers, in the ticket body). The planner's answers to its twelve open questions are in [the planner's check](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/548#issuecomment-6885194229): three are the owner's words (Q5, Q8, Q9) and nine are the planner's rulings. The owner accepts or sends back this ADR at review. Docs only: nothing in this ADR is built by the PR that records it. The builds are briefs 2 to 4 of #548.
- Date: 2026-11-15
- Amends:
  - [ADR-0012](0012-static-export-for-trade-bud.md): the static app now signs owners in, on one page. Still no server and no secret in production.
  - [ADR-0014](0014-supabase-system-of-record-static-serving.md): decision 1 (a second, narrow writer beside the etl seam) and decision 7 (the user-writes trigger has fired).
  - [ADR-0018](0018-supabase-schema-and-rls.md): decision 9 (one schema is exposed to the Data API, and `authenticated` gets grants and policies on it) and decision 10 (the hash list gains the crosswalk's ids).
- Reads with: [ADR-0015](0015-etl-on-github-actions-owner-pii-confined.md) decision 4. Its confinement of owner PII to the `shared` schema is extended to one more table (decision 5 below); its rule is not changed.
- Builds on: [ADR-0024](0024-season-rollover-2027.md), decision 5 (keep choices enter the repo through a tracked loader into the choice table this ADR defines) and decision 8 (locked values come from the price list of [#554](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/554)).
- Scope:
  - `docs/data_model.yml` and `scripts/generate_migrations.py` (a new schema, owner policies, the new tables)
  - `supabase/migrations/` (roles, grants, policies, two `SECURITY DEFINER` functions)
  - `scripts/load_contract_choices.py` and `scripts/load_owner_crosswalk.py`
  - `mouserat_trade-bud/` (a new page, `choices.html`, and its static candidate list), `.github/workflows/pages.yml`
  - Supabase dashboard settings: the Discord provider, the Email provider, URL configuration, exposed schemas

## Context

- **Owners' contract choices exist only in chat.** At the re-sign deadline each owner decides, for every Year-2 player, to re-sign or decline, and for every FA pickup, to keep or let go (bylaws 5.2, 12.2 and 12.3). Nothing in the repo records them, and the rollover contract step ([#559](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/559)) has nothing to read. [ADR-0024](0024-season-rollover-2027.md) decision 5 needs the choice table before 2027-03-01.
- **Every table today has one writer.** ADR-0014 decision 1: every ETL write goes through the storage seam. ADR-0018 decision 9: `etl_writer` is the only writer, a read-only login reads `football` and `ops`, and `anon` and `authenticated` have no grants and no policies. No schema is exposed to the Data API. Only the ETL connects to the database.
- **Serving is static.** ADR-0012: trade-bud is precomputed JSON on GitHub Pages, with no server, no database and no secret in production. Its "client-side checks are affordances" consequence rests on there being no trust boundary left to defend. A page that writes has one.
- **Supabase Free.** ADR-0014 decision 7 names "user writes or auth" as a trigger for Pro with live reads. Free pauses after seven idle days and has no backups. The daily run's `etl_run_log` row keeps the project active (ADR-0014 decision 5).
- **Owner PII.** ADR-0015 decision 4 confines it to `shared.owner`: row-level security on, no grant to any read or anon role, never exported. A Discord user id is owner PII.
- **Anyone with a Discord account can create a Supabase user** through the Discord provider. Signing in proves a Discord identity. It proves no team.
- **The principles.** [Principle 3](../PRINCIPLES.md): rules have hard edges and are enforced by machine, so the deadline and the team match are enforced by the database, not by the page or by good faith. Principle 4: a dispute is settled by the record, so a choice row says who changed it last and when. Principle 5: the app records an owner's own choice and decides nothing for the owner.

## Decision

1. **A second writer, narrow.**
   - Signed-in owners write exactly two tables, the choices table and the share toggle (decision 3), through the publishable key and row-level security. There is no server.
   - The etl seam stays the only writer of every other table. The owner's SQL-editor hand loads (decision 7) are the third kind of write, as `shared.owner` is hand-kept today (ADR-0018 decision 10).
   - This amends ADR-0014 decision 1: "every ETL write goes through the seam" stays true, and the ETL is no longer the only writer to the database.

2. **Sign-in.**
   - Owners sign in with Discord through Supabase Auth. No Fantrax credential and no password touches the app. The Email provider is off, so no account exists outside Discord.
   - **The write policy takes the Discord id from `auth.identities`** (provider `discord`, column `provider_id`), joined on `auth.uid()`. It never reads the id from user metadata, which a signed-in user can change for themselves.
   - A user with no crosswalk row matches no team and can write nothing. A signed-out visitor holds no role with any grant (decision 6).

3. **The choices table and the share toggle,** in a new schema `app`, and nothing else in that schema (Q1).
   - **`app.contract_choices`.** Grain `(season_id, team_key, scorer_id, choice_kind)`: one row per rostered copy and kind. `scorer_id` is Fantrax's roster key (ADR-0018 decision 5). It has no foreign key, because `scorer_id` to the crosswalk is a dirty edge (ADR-0018 decision 6). `team_key` references `dim_fantasy_teams` and `season_id` references `dim_season`.
   - **Values.**

     | `choice_kind` | For | `choice` |
     |---|---|---|
     | `resign` | a Year-2 player | `resign` or `decline` |
     | `fa_keep` | an FA copy | `keep` or `let_go` |

     A row whose `choice` does not belong to its `choice_kind` is refused by a check. `let_go` and `decline` are values: nothing is deleted, and no owner can delete a row.
   - **`locked_value`.** Nullable. The value the price list ([#554](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/554)) locked for the copy at the year's one pull ([ADR-0024](0024-season-rollover-2027.md) decisions 5 and 8). The loader copies it in (Q4). An owner cannot write this column (decision 6).
   - **`origin`.** `loader` or `app`.
   - **Who changed it last, and when.** `changed_by` is the Supabase user id (`auth.uid()`) of the signed-in user, null on a loader row. It is never a Discord id. `changed_at` is set by the database, never by the client. An owner's write sets `origin` to `app`, `changed_by` to the caller and `changed_at` to now, on an insert and on an update.
   - **`app.team_choice_sharing`** (Q11). Grain `(season_id, team_key)`, one `shared` boolean, with `changed_by` and `changed_at` as above. One toggle per team and season covers all of that team's choices.
   - **Visibility.** Private by default.
     - An owner reads every row of a team the crosswalk links to them.
     - Anyone signed in reads another team's rows only while that team's toggle is on, or once the row's own deadline has passed.
     - After the deadline every row is public, in the app (all signed-in users) and in the published snapshot (below).
     - A team's toggle can be changed while the window of at least one of the season's choice kinds is open.
   - **Editable until the deadline, then locked.** An owner inserts or updates a row of a team the crosswalk links to them, only while the deadline for the row's `(season_id, choice_kind)` has not passed. After it every owner write is refused.
   - **The published snapshot carries a choice only after its deadline** (Q6). The choices table is private, so the exporter never reads it. After a `(season_id, choice_kind)` deadline passes, a pipeline step copies those rows into a published `football` table, without `changed_by`. That step and its table are a brief of their own, which the planner writes when brief 2 is in review. They are not part of briefs 1 to 4. The exporter stays a plain one-to-one map of tables to files.

4. **The deadline.**
   - **One source of truth: `ops.choice_deadline`** (Q3). Grain `(season_id, choice_kind)`, one `deadline_at timestamptz`. The write policy reads it at write time, through a function (decision 6). The ETL reads it through the seam. `LeagueConfig` holds no deadline.
   - **The instant** (Q9, the owner's word). The end of the deadline day in `America/New_York`: 23:59:59. For 2026-11-19 that is 2026-11-20 04:59:59 UTC. The bylaws name the day and no clock time. A write is refused once the database's clock is later than `deadline_at`. **No row means closed:** a missing deadline refuses every write.
   - `LeagueConfig.resign_deadline` stays as it is until this table is live. Then the reader of [#545](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/545) moves to the table, in a follow-up the planner tickets.

5. **The owner crosswalk: `shared.owner_crosswalk`** (Q7).
   - Grain `(team_key, discord_user_id)`. Co-owners are allowed: several users per team. A user may own more than one team.
   - It lives in `shared`, beside `shared.owner`. Row-level security is on. `etl_writer`, `etl_reader`, `anon` and `authenticated` hold no grant on it, so no one reads it through the Data API. Only the two `SECURITY DEFINER` functions of decision 6 read it. It is database only: never exported, never committed. A Discord id appears nowhere on GitHub.
   - Its ids join `shared.pii_token_hashes()` (ADR-0018 decision 10): the function also returns the sha256 of each `discord_user_id`, so the data-commit check fails a commit that holds one. `etl_writer` still has EXECUTE on that one function and no grant on any `shared` table.
   - `discord_user_id` is digits only, 17 to 20 long. `team_key` references `dim_fantasy_teams`.

6. **Roles, grants and exposure.**
   - **Exposure.** One schema is exposed to the Data API: `app`. The dashboard's Exposed schemas list names `app` and no other schema. `public` stays empty. `football`, `ops` and `shared` stay unexposed. This amends ADR-0018 decision 9, which exposed none.
   - **`anon`:** no grant and no policy, in any schema. The migration revokes anything `anon` could inherit on `app`, and the policy tests assert it.
   - **`authenticated`:**
     - USAGE on `app`;
     - SELECT on both `app` tables;
     - INSERT and UPDATE on `app.contract_choices` and `app.team_choice_sharing`, by column: on insert the key columns, `choice` (or `shared`), `origin` and `changed_by`; on update only `choice` (or `shared`), `origin` and `changed_by`; never `locked_value` and never `changed_at`, which the database sets. A policy check holds `origin` to `app` and `changed_by` to the caller;
     - no DELETE;
     - USAGE on `shared` and EXECUTE on the two functions below, and nothing else on `shared`, `ops` or `football`.
   - **Two `SECURITY DEFINER` functions in `shared`,** after the pattern of `shared.pii_token_hashes()`: `search_path` pinned empty, EXECUTE revoked from `PUBLIC`, granted to `authenticated` only. One returns the signed-in user's `team_key`s: the crosswalk joined to `auth.identities` on the Discord id, for `auth.uid()`. The other says whether the deadline of a `(season_id, choice_kind)` is still open. Policies call them. They live in `shared`, which is not exposed, so the Data API cannot call them as RPC.
   - **Policies.** Each `app` table has row-level security on, one `TO etl_writer USING (true)` policy as for every table in a granted schema, and the owner policies. The generator emits the owner policies from a new registry field, as it emits the etl policies today (Q2; ADR-0018 decision 3). No hand-written SQL stands beside the generator. The policies land in brief 3, beside the crosswalk they read.
   - **`etl_writer` and `etl_reader`** keep ADR-0018 decisions 9 and 10 otherwise unchanged: no BYPASSRLS, no grant on `shared.owner`. `app` joins the schemas the generator grants: `etl_writer` gets DML and `etl_reader` gets SELECT, with their policies. `shared.owner` and the crosswalk stay without a grant for both.

7. **How the two loaders reach the database** (Q5, the owner's word).
   - `scripts/load_contract_choices.py` and `scripts/load_owner_crosswalk.py` each validate their xlsx, print counts only, and write a SQL file to a path the owner names outside every repository. The owner runs it in the Supabase SQL editor.
   - **No loader connects to the database.** No agent connects with write rights, no role and no grant is added, and no Never line of `GOAL-RUN.md` changes.
   - The crosswalk's SQL file holds Discord ids. It is written only to the owner's named path, and the loader prints that path and counts, nothing else.
   - **An FA copy missing from the 2026 file** (Q10): the loader writes nothing for it and prints the missing count. A missing row means no choice made, and the rollover contract step ([#559](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/559)) reads no row as let go (bylaws: an unkept FA returns to the pool). The rule lives in one place.

8. **ADR-0014 decision 7: Free stays.** The trigger "user writes or auth" has fired (Q8, the owner's word). It is judged not to need Pro, because the daily run keeps the project active and only the choices page depends on the live database. Revisit if the project ever pauses inside a choice window.

9. **The page** (Q12).
   - A new `mouserat_trade-bud/frontend/choices.html`, with the root page pointing to it until rollover. `index.html` keeps no dependency and its single `api(path)`.
   - The choices page loads one pinned `supabase-js` build from a CDN with an integrity hash. Its network layer is the one function for static files plus one Supabase client.
   - The publishable key is a committed constant. It is public by design and grants nothing without a signed-in user matched to a team (decision 2). The page holds no other key and no secret.
   - The candidates of each team (Year-2 copies and FA copies, with their published salary) are static JSON from `export_static.py`, computed by a router and only exported, as ADR-0012 requires. The choices themselves come live from the Data API.
   - The project rules name the frontend as one dependency-free page. That stays true of trade-bud's `index.html`; brief 4 updates that text to say the choices page signs owners in.

10. **Not decided here.** Three points the planner's answers do not settle. Each needs a ruling before the brief that builds it.
    1. **What fills `locked_value` on an app-origin row** (the 2027 re-sign). Decision 3 fixes only that an owner cannot write it, and that the loader copies it for a loader row. **Recommend:** a database-side fill from the price list, by the deadline brief the planner writes for the published copy; the 2027 "New Value" has no source until #554's 2027 pull.
    2. **How a row of `ops.choice_deadline` gets in.** **Recommend:** hand-kept in the SQL editor, like `shared.owner`: one row per season and kind, set by the owner's decision, with the statement given in the brief that needs it. Brief 2 needs the 2026 row.
    3. **A copy of private choices before the deadline.** On Free there is no backup, and no public copy exists until the deadline. A lost project loses the choices owners entered in the app. **Recommend:** the owner accepts the risk for 2027, or exports the table by hand before the deadline. It is the owner's call (cost).

## Alternatives considered

- **A hosted backend** (Railway, beside the bot). Rejected, as ADR-0012 rejected it: a live server for a single narrow write path, and a secret to hold. Row-level security gives the same control with no server and the page holds only the publishable key.
- **Choices collected by the Discord bot.** Rejected: the bot does no writes, ever (project rules), and it would need a store of its own.
- **A Drive sheet as the record.** Rejected: it has no deadline lock, no per-owner identity and no history of who changed what. Principle 3 asks for hard edges enforced by machine, and Principle 4 for a record anyone can check.
- **Password or magic-link accounts.** Rejected: a second credential for owners to lose, and an account that no crosswalk row ties to a team. Discord is where the league already is.
- **Reading the Discord id from user metadata.** Rejected: a signed-in user can edit their own metadata, so the check could be spoofed. `auth.identities` is written by Supabase Auth only.
- **Q1 (b): expose only `SECURITY DEFINER` functions and no table.** Rejected: it adds hand-written function logic the generator does not own. The policies are the control and the auditor reads them.
- **Q2 (b): a hand-written migration for the owner policies.** Rejected: ADR-0018 decision 3 makes the registry the one source of DDL.
- **Q3 (b): a `LeagueConfig` field copied into the database by each run.** Rejected: two copies, and a window where they differ.
- **Q4 (b): leave `locked_value` empty and let #559 fill it.** Rejected: ADR-0024 decision 5 says the loader stores it.
- **Q5 (b): the owner changes the Never line so the loaders run live on the owner's word, with a write path into `shared`.** Rejected by the owner: an agent would hold write rights to the live database, and the crosswalk's ids would pass through one.
- **Q6 (b): teach the exporter a row filter for the choices table.** Rejected: a filter bug could publish a private choice. The exporter stays a plain one-to-one map.
- **Q7 (b): the crosswalk in `app`, unreadable to `authenticated` by policy.** Rejected: it puts owner PII one policy mistake from the Data API.
- **Q8 (b): move to Pro now.** Rejected by the owner: the daily run already keeps the project active, and only one page needs the live database.
- **Q9 (b): the time the commissioners announce.** Rejected by the owner: a clock time the policy cannot read until someone types it.
- **Q10 (b): the loader writes let go for every copy not listed.** Rejected: the rule would live in two places.
- **Q11 (b): a share column on each choice row.** Rejected: one toggle per team, and a column can disagree with itself across rows.
- **Q12 alternatives.** A tab inside `index.html`: rejected, it would give trade-bud's dependency-free page a dependency. Hand-written calls to the Auth and Data APIs with `fetch`: rejected, because the sign-in flow and token refresh are what hand-written code gets wrong. The key as a repo variable read at build: rejected, because the key is public by design and a variable adds a step with nothing to protect.

## Consequences

- **This PR changes no behaviour.** It records the decisions. Briefs 2 to 4 of #548 cite this ADR:
  1. brief 2: the choices table, the deadline table, the 2026 keep loader;
  2. brief 3: the crosswalk, its loader and the owner policies;
  3. brief 4: the sign-in and the page.
- **A `GOAL-RUN.md` line stops being true when brief 2 or brief 3 lands.** "After a schema change lands" says every table in `football`, `ops` and `shared` has RLS on, the read-only login has SELECT on `football` and `ops` only, and `anon` and `authenticated` have no grants and no policies. Once the briefs land: RLS is on in `app` too; the read-only login also has SELECT on `app`; `anon` has no grant and no policy, and `authenticated` has only the grants and policies of decision 6. The text is the owner's to change. The planner sends the manager the replacement when brief 3 opens. This PR writes nothing under `.claude/`.
- **The supabase-auditor's basis gains this ADR.** It audits against ADR-0014, ADR-0015 and ADR-0018 today. An agent file is the owner's or the planner's own PR, and this PR does not touch it.
- **ADR-0015 decision 4 names one table.** The crosswalk is a second table under the same confinement. This PR adds no note to ADR-0015; the planner may add one.
- **The app's surface dies with the project if Supabase pauses; the rest of serving does not.** The bot, Power BI and trade-bud read the published snapshot (ADR-0014 decision 2). Only the choices page needs the live database.
- **Sign-in is open to any Discord account; the policy is the gate.** A stranger who signs in can read what teams share and what a passed deadline made public, and write nothing.
- **A policy bounds the team, not the candidate.** An owner can write a row for any `scorer_id` of their own team, not only for a listed candidate. The page lists only candidates, and the rollover contract step reads only rows that match its candidates. Brief 2 or 3 decides whether the registry can check more.
- **Owner PII grows by one table.** The crosswalk's ids reach `shared.pii_token_hashes()`. Brief 3 counts the published rows that a 17 to 20 digit token would flag, and parks if the count is above zero.
- **The page renders names from static JSON.** Brief 4 escapes every name it writes into the page, and the security-review skill reads it. The page's Supabase session lives in the browser, and the publishable key is the only key the page holds.
- **The Supabase dashboard settings are the owner's hands** (brief 4's Actions): the Discord provider, the Email provider off, URL configuration, and the exposed schema.
- **CLAUDE.md and `mouserat_trade-bud/README.md` change in brief 4,** where they say the frontend is one dependency-free page and trade-bud holds no server.
