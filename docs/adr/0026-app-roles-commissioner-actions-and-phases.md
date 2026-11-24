# App roles, commissioner actions and choice-window phases: who may do what in the owners' app

- Status: proposed. The design was settled with the owner on [#654](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/654) on 2026-11-23, by button in the planner's chat; each answer is a comment on that ticket. Nine answers are the owner's words. The points marked *(planner)* are the planner's rulings, and the owner accepts or sends back any of them at review. Docs only: nothing in this ADR is built by the PR that records it.
- Date: 2026-11-23
- Amends:
  - [ADR-0025](0025-owner-write-path-contract-choices.md): decision 3 (a third `origin`, a history of every row version, the commissioner's tables), decision 4 (a second stored instant, `final`), decision 6 (roles, a role table, new functions and grants), decision 9 (the page's address, its session and its content security policy) and decision 10 point 1 (ruled: the published table carries no `locked_value`).
  - [ADR-0018](0018-supabase-schema-and-rls.md): decision 9 (`authenticated` gains the grants named here) and decision 10 (owner PII in `shared` is now in three tables, and the hash list gains the role table's ids).
  - [ADR-0015](0015-etl-on-github-actions-owner-pii-confined.md): decision 4 (three tables, same confinement).
- Builds on: [ADR-0024](0024-season-rollover-2027.md) decision 5 (the rollover contract step reads the choices; it now reads only `final` ones).
- Scope:
  - `docs/data_model.yml` and `scripts/generate_migrations.py` (new tables, policies, trigger functions, a definer flag for trigger functions)
  - `supabase/migrations/`, `tests/test_migrations_apply.py`, a new tracked role, phase and action table
  - `scripts/print_choice_deadline.py` and a new loader for the role table
  - `mouserat_trade-bud/` (the choices page) and a new browser run in CI
  - The site's address (a custom domain) and the Supabase URL settings that name it

## Context

- **ADR-0025 knows one kind of signed-in person: an owner.** The league also has commissioners, and one person runs the app. The owner asked (#654) to walk through the app from any perspective, to check one person's access, to switch between his own roles with the lowest shown first, and to have every button of every role in every phase tested.
- **That ask is four separate powers,** with very different risk:

  | Power | What it is | Risk |
  |---|---|---|
  | Role switch | A person picks which of their own roles is active | None: it only narrows |
  | View-as | Seeing the page as another role or team sees it, read-only | A read of private choices, unless masked |
  | Act-as | Saving a choice as another person | `changed_by` stops proving who chose |
  | Phase mimic | Seeing the app as window open, deadline passed, and so on | Not possible live: the phase is the database's clock, and a passed deadline cannot be moved (ADR-0025 decision 4) |

- **Commissioners are owners too.** A commissioner who can read a rival's choices before a deadline has an edge. [Principle 3](../PRINCIPLES.md) binds the commissioner and asks for edges kept by machine.
- **A role that can update a row through the Data API can read it.** PostgreSQL applies the SELECT policies to an UPDATE that has a WHERE clause, and to the existing row of an `INSERT ... ON CONFLICT DO UPDATE` (the CREATE POLICY reference, policies applied by command type). A plain INSERT that returns nothing needs no SELECT policy.
- **Supabase's guidance on definer functions.** Its row-level security guide says never to create a `SECURITY DEFINER` function in an exposed schema, and to pin `search_path` to empty on every one. ADR-0025 already keeps its two in `shared`.
- **The site shares a browser origin.** It is served from the account's GitHub Pages address with no custom domain, and a browser treats every Pages site of one account as one site. A session kept in the browser there can be read by a script on any of them.
- **The Free plan allows two projects, and pauses an idle one after about seven days** (Supabase billing and pausing guides). ADR-0014 decision 7 keeps the project on Free.
- **No league key exists** in `docs/data_model.yml`: one league and one sport are assumed. The owner wants one app for several Fantrax leagues and sports, football first and baseball second ([#658](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/658)).

## Decision

1. **Four standings, and a role switch** (questions 1 and 6).
   - A signed-in person is a **stranger** (no role: reads what is shared or public, writes nothing), an **owner** (a person the crosswalk links to a team, as in ADR-0025), a **commissioner**, or a **site admin**. One person may hold several.
   - The page opens on the lowest role the person holds, in the owner's order: owner, then commissioner, then site admin. Switching is a page setting. It narrows what the page shows and grants nothing.
   - The live app gets the role switch and a read-only view-as. Act-as and phase mimic exist only on fake data (decision 7).

2. **Roles are recorded in `shared.app_role`** (question 6).
   - One row per person and role, for `commissioner` and `site_admin`. Owner stays derived from `shared.owner_crosswalk`.
   - It is loaded as the crosswalk is: a tracked script prints SQL to a path the owner names, and the owner runs it in the SQL editor (ADR-0025 decision 7). No agent writes it.
   - It is a third table of Discord ids in `shared`: row-level security on, no grant to any role, never exported, and its ids join `shared.pii_token_hashes()`.
   - A role is never read from the sign-in token or from user metadata.
   - *(planner)* **A policy asks about a team, never about a person alone.** The check is whether the caller may act as commissioner for this team, so that a league scope changes one function body and no policy. A commissioner's row records its league. The form of that column is the foundations brief's to propose, because the league key itself is #658's.

3. **Live view-as is masked** (question 2).
   - A site admin sees, for a team: how many identities the crosswalk links, how many of those have signed in, each choice window's state, and how many choice rows exist. Never a Discord id, and never another team's choice values before that row's deadline has passed or the team shares.
   - The site admin role carries no write. A site admin writes only through another role they hold.
   - No new read policy on `app.contract_choices` exists for it.

4. **A commissioner action** (questions 3, 4 and 8).
   - A commissioner may enter or change a team's choices in the app while a window is `open` or `passed`. The owner's word: it must be clear when a commissioner did it, with a reason from a list and a dated note, one reason and note for all changes on that team.
   - **An action is one batch:** one team, one season, one reason, one note that may not be empty, who acted and when (set by the database). Each row it changes is an item of that action.
   - **Record-first.** No commissioner write exists outside an action. The team's owners can read the action at once.
   - **Own team refused.** The database refuses an action on a team the commissioner owns. Another commissioner does it. With a sole commissioner, that one case falls back to the owner's SQL-editor hand path, which the history (decision 5) records like any other write.
   - **Blind before a deadline.** A commissioner never holds SELECT, INSERT or UPDATE on another team's rows of `app.contract_choices`. The commissioner inserts the action and its items, which are their own rows. A trigger owned by the database applies each item to the choices table, with `origin` set to `commissioner` and `changed_by` set to the commissioner. Nothing is returned from the choices table, so the commissioner is never shown what was there. Once a deadline has passed the values are public to every signed-in user, as ADR-0025 already has it.
   - **No function is exposed.** The trigger function lives outside `app`, with `search_path` empty and EXECUTE revoked from `PUBLIC`. The owner chose one database function (question 8); the trigger function is that function, and the app cannot call it. This follows Supabase's guidance and keeps ADR-0025's rule that the Data API can call nothing.
   - **An owner may overwrite** a commissioner's entry while the window is open. The row returns to `origin` `app`.
   - *(planner)* **The reasons** are a small table, so a new reason is a new row: owner absent, owner request, commissioner ruling, data fix, other.
   - *(planner)* **Who reads an action.** Its reason, who acted and when: the team's owners and every commissioner at once, and every signed-in user once the deadline of a choice it touched has passed. Its items follow the choice they changed. Its note: the team's owners and the commissioners only, because a note may say something personal.

5. **Every version of a choice row is kept** (question 3; the timing is the planner's).
   - `app.contract_choice_history` is append-only. A trigger writes one row for every insert and update of `app.contract_choices`, by any role and any route, the SQL editor included. No role is granted a write on it.
   - A history row is readable under the same rules as the choice it belongs to.
   - It lands before the page accepts its first write, because a history cannot be filled in afterwards.

6. **Four phases, from one table** (question 5).

   | State | Source | Owners | Commissioners |
   |---|---|---|---|
   | `none` | no row in `ops.choice_deadline` | no write | no write |
   | `open` | `deadline_at` is later than now | write their own team | write through an action |
   | `passed` | `deadline_at` is at or before now | locked; choices public | write through an action |
   | `final` | `final_at` is at or before now | locked | locked |

   - `ops.choice_deadline` gains `final_at`, required and later than `deadline_at`. The same script prints both instants, and the same guard refuses a change to one that has passed.
   - `shared.choice_window()` returns `final` as a fourth state. `ops.choice_deadline` stays the one source of every phase.
   - The rollover contract step ([#559](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/559)) reads only `final` choices. The published copy of ADR-0025 decision 3 is made once a deadline has passed and made again after a commissioner action; from `final` it no longer changes.

7. **The walk-through is a tracked table, proven twice** (question 7).
   - *(planner)* **One table of role, phase and action,** each cell saying shown or hidden, allowed or refused. It is the one source for the policy tests, the browser run and the owner's own checklist.
   - **At the database, on every PR:** the policy tests prove every cell. The policies are the boundary; the page only shows or hides.
   - **In a browser, for PRs that touch the page:** a scripted run on a throwaway Supabase stack inside the CI job, with made-up users and deadline rows set per phase. It saves a screenshot of every cell. Act-as and phase mimic live here and nowhere else. The same stack can run on the owner's PC.
   - **No impersonation code is in the page.** The test opens the browser already signed in as a made-up user.
   - **No second Supabase project.** The owner chose against a hosted staging copy.

8. **The page's address and session** (question 9).
   - The app is served from a domain of its own, so no other site shares its storage. *(planner)* The name is neutral to league and sport, with each league a path under one sign-in.
   - Until that domain is live, the page keeps the session for the tab only.
   - *(planner)* The public page has one backend, fixed at build; no link or setting switches it. A content security policy pins the page's network calls to that backend and its scripts to the pinned build.

9. **`locked_value` is not published** (ADR-0025 decision 10 point 1; the planner's ruling, [#548](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/548#issuecomment-7103631284)). The published after-deadline table has no `locked_value` column. The price is stored once, in `fact_salary_price_list`. The page shows each candidate's locked price from it, and the rollover step joins it on season and `scorer_id`.

10. **Not decided here.**
    1. **How the page learns a window's state and instants, and how view-as reaches the page.** The policies read them through functions the page cannot call. *(planner's lean)* A view in `app` that runs as the caller, over a `shared` function granted by name; no definer function in the exposed schema. Brief 4 and the view-as brief settle it.
    2. **The `final` instant of the one deadline row that exists** (counted 2026-11-23: one row, already passed). The date is the owner's, as the deadline's was.
    3. **How long an open action accepts items.** The commissioner brief proposes it.
    4. **A commissioner status board** (per team, how many candidates have no choice yet; counts only). Proposed with the commissioner brief.
    5. **Whether an action's reason is published** with the choice. Today only `origin` is.
    6. **The domain's name,** and the league key (#658).

## Alternatives considered

- **A live site-admin role that acts as any user.** Rejected: one account could write every team's choices, and `changed_by` would stop proving who chose (principle 4).
- **Live view-as with full values,** logged or not. Rejected by the owner for the masked form: the app must not be a button for reading a rival's private choices, and exact rendering is the browser run's job.
- **A read-only commissioner, with every change by the owner's SQL-editor paste.** The planner's recommendation; the owner chose in-app writes before and after a deadline, for the absent owner and the mis-click.
- **A commissioner's own team allowed and flagged.** Rejected: a flag is the only check on changing one's own locked choice.
- **Reason and note attached on save, with no gate.** Rejected: looking would leave no trace.
- **Read and write through the action before a deadline.** The first answer to question 4; tightened by question 8, because an update through the Data API is also a read.
- **A function the page calls.** Rejected for a trigger behind ordinary inserts: Supabase's guidance is that no definer function sits in an exposed schema.
- **Three phases, with corrections never closing.** Rejected: a change after rollover would disagree with a contract already rolled.
- **`final` derived from the season's start date.** Rejected: the cutoff could not be set apart from the calendar.
- **A role column on the crosswalk.** Rejected: wrong grain. A role is per person and the crosswalk is per team and person.
- **A role claim on the Supabase user.** Rejected: outside the registry, the generator and the auditor, and stale until a token refreshes.
- **A hosted staging project.** First recommended by the planner, then rejected by the owner after a second pass: on Free it pauses when idle, its hand-set dashboard settings drift, and a paste can land in the wrong project.
- **A session kept on the shared address, or for the tab only with no domain.** Rejected for a domain of the app's own.
- **The price stamped on every published row.** Rejected: the same dollar figure in two tables.
- **The multi-league model first.** Rejected by the owner: football launches first, built ready for it.

## Consequences

- **This PR changes no behaviour.** The builds are briefs, in this order: the foundations (history, `final`, `origin` `commissioner`, the role table, the role, phase and action table and its tests); brief 4 of #548 (the owner's page); the after-deadline copy; the commissioner's action; the site admin's view-as; the browser run. Brief 4 lands outside 2026-12-03 to 2027-01-07.
- **The generator learns one thing.** Trigger functions are rendered without `SECURITY DEFINER` today. The history writer and the item applier need it, so the registry gains a flag for it, with the pinned `search_path` and the revoked EXECUTE it already applies.
- **`GOAL-RUN.md`'s check after a schema change gains lines** when the foundations brief lands: the new tables have row-level security on, `authenticated` holds only what this ADR and ADR-0025 list, and `shared.app_role` has no grant. The planner sends the manager the text when that brief opens. The supabase-auditor's basis gains this ADR, by the planner's own PR.
- **Owner PII grows by one table,** under the confinement of ADR-0015 decision 4.
- **A commissioner cannot see what an owner already entered** before a deadline, and overwrites it blind. The history keeps what was overwritten, and the owner can change it back while the window is open.
- **A sole commissioner cannot act on their own team in the app.** That case is the hand path.
- **The project's owner can still read everything** from the dashboard (ADR-0025, Consequences). Masking and the blind write bind the app's roles, not that account.
- **Moving to a custom domain moves the whole site,** trade-bud's page and the docs included. Links to the old address redirect, and the Supabase and Discord redirect addresses name the new one. The steps are the owner's hands, written with brief 4.
- **The browser run adds CI time** on page PRs only. Its first brief measures how long the stack takes to start before the run is made a required check.
- **Multi-league (#658) will add later migrations,** for example a league key on deadlines. The role check per team (decision 2) and the neutral names are what this ADR does now to keep that cheap.
