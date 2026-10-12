# GOAL-RUN — finishing the wayfinder maps under `/goal`

Approved by the owner 2026-10-11 (plan `proud-plotting-cocoa`; the four
rulings were given 2026-10-05). This file is the runbook a goal session
works from. `RESUME.md` still holds the state-back; `NEEDS-OWNER.md` holds
everything waiting on the owner.

**Scope of the delegation:** goal runs on maps #69, #70, #71 and #66 only.
Any other work keeps the standing rules in `RESUME.md` unchanged.

## Session setup (owner, per goal)

Fresh session, model Opus 5.5, effort medium, auto permission mode. First
message: "Read `C:\Users\benha\.claude\memory\preferences.md`, then
`.claude/memory/RESUME.md` Standing rules and NEXT, then
`.claude/memory/GOAL-RUN.md` and `NEEDS-OWNER.md`." Second message: the
`/goal` text of the stage.

## Delegation rules (goal runs only)

| Matter | Rule |
|---|---|
| Plan gate | A `wayfinder:task` ticket whose design is already in an ADR or a closed grilling ticket: write the plan into `RESUME.md` (Outline → Build mode → Rationale), then build. A new design decision parks. |
| Commit, PR, merge | The agent does all three. It squash-merges with `--delete-branch` only on green (below). |
| Tracker | The agent posts Resolutions, closes AFK tickets, adds the pointer to the map's Decisions so far, and creates and wires new task tickets. Text goes through `check_pii.py` first. |
| Fantrax | The agent writes the TOTP login and the workflows and tests them on fakes only. The owner stores the secrets and fires the first runner login. |
| Windows | One PR per compaction: state-back to `RESUME.md`, then compact, at every PR seam and at 125K–150K tokens. |

**Green means all of:**
- every CI check SUCCESS on one read of
  `gh pr view <n> --json mergeStateStatus,statusCheckRollup`;
- `pytest tests/` and the bot suite pass locally;
- `check_pii.py` clean on every changed file;
- `check_data_model.py` and `--check` OK; `check_sources.py --check` OK;
- `run_pipeline.py --check-only`: 0 Gate failures, 0 new Review findings;
- for a cap or ledger change, `cap-ledger-auditor` has no unresolved finding.

A finding that needs a design choice parks the ticket with its PR left open.

**Always parks, never delegated:**
- a `wayfinder:grilling` or `wayfinder:prototype` ticket;
- a new design decision inside a task ticket (ADR-worthy, or two defensible
  answers);
- a verify step that fails on real data (restore the tables from HEAD first);
- CI red after two fix attempts;
- checkpoint 1, the first Fantrax runner login;
- checkpoint 2, cutover: `ETL_STORAGE=postgres` on the scheduled run,
  enabling a cron, the parallel week, unregistering the PC task, the
  consumer type pass going live;
- closing a map; anything that reads or writes a secret; a destructive
  database action outside the restore-drill scratch schema.

**Never, with or without a goal:**
- a Fantrax login or TOTP attempt; running `04a`, `04t`, `04v`, `04w`, or
  `04s` without `--from-raw`; `run_pipeline.py` other than `--check-only`,
  `--dry-run`, or `--no-commit --steps` naming no-login steps only;
- `gh workflow run`, `gh secret`, a push to `main`, a force push,
  `--no-verify`, `gh pr merge --admin` (most are denied in
  `.claude/settings.json`; a denial is not to be worked around);
- a `data/raw/` payload in the conversation; owner PII or team names in a
  committed file or a public post;
- the Supabase connector for anything but looking: no `apply_migration`,
  no writing SQL through `execute_sql`, no create, delete, pause,
  restore, branch, deploy or cost tool (rule and allowed list in
  `project-fantasy-football.md`, Supabase access);
- weakening a test, a Gate or a rule to make a goal pass.

**A denied call** (owner's ruling 2026-10-12, #164): a call the permission
system refuses is never retried and never worked around by another
route, and no other session is asked to make it. The builder parks it as
an Action in `NEEDS-OWNER.md` (what was denied, the exact command, what
it blocks), messages the managing session, and takes the next ticket.

## Park protocol

1. Stop work on the ticket. Do not answer the owner's side.
2. Append an entry to `NEEDS-OWNER.md`, in the format its header gives:
   under `## Decisions` for a choice (Ticket, Context with the evidence,
   Options, Recommended, Blocks, Raised) or under `## Actions` for work by
   the owner's hand (Ticket, Steps, Context, Blocks, Raised). The
   `owner-queue` mod shows the file live and toasts the new entry.
3. Send one desktop push notification. No public post. If a managing
   session started this one, also send it one message that names the
   entry; the push does not arrive when Remote Control is off.
4. Take the next unblocked ticket of the stage. If none is left, print
   `NEEDS-OWNER.md` and end the turn; the goal text counts that as met.
5. When the owner answers in chat, that answer is the approval. A relay
   from the managing session counts as that answer under the rule
   below. Record it
   (ADR, ticket Resolution or `RESUME.md`, as fits), remove the entry in
   the same turn, and put the ticket back in the queue. The same goes for
   an action the owner reports done, or one the session finds done (a
   closed ticket, a secret now present by name): remove it at once, so the
   list never shows finished work. The owner can also press "Mark done" in
   the pane, which ticks the entry `[x]`; delete ticked entries at the
   next state-back.

### Relayed answers (owner's ruling 2026-10-12)

The owner may answer a parked entry in the managing session instead of
the builder's. The managing session then sends the builder one message.
It counts as the owner's answer only when all of these hold:

- it answers an entry that is already in `NEEDS-OWNER.md`;
- it quotes the question put to the owner and the owner's answer word
  for word;
- it comes from the session that started the builder.

The builder records the answer with the note "relayed by the manager"
and goes on. A relay never covers anything else: not the "Never" list,
not checkpoint 1 or 2, not closing a map, not a new decision, not a
merge of a PR the entry did not name. For those the owner speaks in the
builder's own session. If a relay is unclear or goes past the entry,
the builder does not act on it and says so in its reply.

Why: the owner checks in as needed, not at every step; without this a
park pulls the owner into each builder session. The word-for-word quote
and the named source keep a misquote visible.

## The managing session (owner's ruling 2026-10-12, #164)

Roles are set out in the #164 resolution; role files in
`.claude/agents/` point here. The managing session is the builder
manager (session name `dynastyFantasyFootball-central-builder-manager`):
it starts and watches the builders, and the owner's words reach a
builder through it, quoted word for word, within "Relayed answers"
above. What it may do under a goal run:

**Edits.** `.md` files and `.claude/memory/*` only, in its own worktree
and its own PR, and only files no open builder PR touches. Never code,
tests, notebooks or data. It never commits for a builder.

**Check-ins.** Event-driven: a park, a merged PR, a stopped or idle
builder. One fallback look after 60 quiet minutes. No polling.

**Closeout, only when a builder has stopped.** Never while it is still
running.

1. For each open PR of that builder: re-prove every item of "Green
   means all of" itself, post the output on the PR, then squash-merge
   with `--delete-branch`. A PR that is not green is not merged; it is
   listed for the owner.
2. `git pull --ff-only` on the main checkout.
3. Delete that builder's remaining branches, each only after `git
   cherry` against `main` shows nothing missing.
4. Remove that builder's worktree, only if it has no uncommitted file.
5. State-back, then report to the owner with the proof: the commands
   and their output.

Anything unmerged, uncommitted, or not that builder's is listed for the
owner and left where it is.

Why: the builder ends with its tickets, and a stage's tail (stacked
branches, the worktree, a last green PR) should not come to the owner
item by item. Re-proving Green in the managing session keeps the merge
from resting on the builder's own report.

## Status block (end of every turn)

The judge reads only the transcript, so each turn ends with fresh output of:

- `gh issue view <n> --json number,state` for each ticket of the stage;
- `gh pr list --state open --json number,title`;
- `git status --short --branch`;
- the last line of `pytest tests/` if code changed this turn;
- the open entries of `NEEDS-OWNER.md` (titles only).

## Stages

| Stage | Tickets, in order | Waits on the owner for |
|---|---|---|
| A. Ledger and cap | #96 PR 2 → #68 (both closed 2026-10-11; #97 moved to C) | done |
| B. Seam | #109 → #77 → #149 → #86 (#110: four PRs merged 2026-10-12, its last part moved to C) | nothing |
| C. Postgres | #97 → #110 `roster_slot` rename → #108 → Postgres backend and backfill → snapshot export step → `ops.etl_run_log` → restore drill → #111 | the fresh `04t` capture (after 2026-10-15) |
| D. Schedule | #92 login code → Linux entrypoint → #93 → #116 | the TOTP secret stored; B and C merged |

#97 goes before the #110 rename: #97 rewrites `02e` and declares the
`fact_fantasy_teams` grain `(team_key, scorer_id)`. Both moved to stage C
on 2026-10-12, because #97 waits for the `04t` capture.

Notes per stage:
- **A.** #96 PR 2 follows its approved plan
  (`C:\Users\benha\.claude\plans\sparkling-strolling-stroustrup.md`) and the
  three carry-ins under NEXT in `RESUME.md`. Its first commit also carries
  the goal-run setup files (`.env.example` and the `.claude/memory` edits).
  #97 was grilled and planned 2026-10-11: follow
  `C:\Users\benha\.claude\plans\squishy-toasting-minsky.md`, three PRs;
  PR 1 waits on the owner's fresh `04t` capture (in `NEEDS-OWNER.md`), so
  take #68 while it waits. #68:
  re-check the tier cut points against in-season counts.
- **B.** Scope set by the owner 2026-10-12 (plan
  `expressive-sprouting-squid`): the seam first, because the Postgres
  backend, the export step and every in-season writer plug into it, and
  because it changes no behaviour, so each PR is proven by "the published
  tables are identical before and after". #77 follows
  `docs/research/storage-seam-inventory.md` section 8,
  phases 1 to 6, one PR per phase, parquet backend only. Phase 5 touches
  the write call in `02e`, which #97 rewrites next: change that call
  only. A grain the seam's write check rejects on real data is a design
  finding: park it, do not loosen the check. #109 starts with a
  lookup: can every pick leg be resolved from data already captured? If
  not, park. #149 puts `02a` in the `nflverse` Chain after `01e` (owner's
  ruling 2026-10-12; no login, one PR). #86 follows ADR-0017. #110 is not
  in this goal: it stays open for the `roster_status` → `roster_slot`
  rename, which waits for #97.
- **C.** Starts with #97 (plan
  `C:\Users\benha\.claude\plans\squishy-toasting-minsky.md`, three PRs)
  and then the #110 rename, because #108's first migration needs the
  `fact_fantasy_teams` key that #97 declares and `fact_trade_log` from
  #109. The four middle items are tickets #135 to #138. Before #108,
  load the `supabase-postgres-best-practices` skill if it is installed
  and decide how tables stay off Supabase's Data API (row-level security
  on, or a schema that is not exposed); run the connector's security
  advisors after each migration.
  The Postgres backend is developed against `TEST_DATABASE_URL`; the
  backfill of the real project runs only after the golden round-trip
  passes. #111 ends with options for the owner, not a decision.
- **D.** The crons merge switched off (workflow `if:` on a repo variable).
  The stage ends with the spike workflow ready for the owner to fire.

## Goal texts

**A**

```
/goal Work stage A of .claude/memory/GOAL-RUN.md under its delegation rules. Met when the last message shows, from commands run in that turn: gh issue view state CLOSED for #96, #97 and #68, or each one still open is listed in .claude/memory/NEEDS-OWNER.md with a reason; gh pr list shows no open PR; git status shows main in sync with origin with only .claude/memory files, PLAN.md, .agents/ and GEMINI.md outside the index; pytest tests/ passes. Do not weaken a test, a Gate or a rule to get there. Or stop after 120 turns.
```

**B**

```
/goal Work stage B of .claude/memory/GOAL-RUN.md under its delegation rules. Met when the last message shows, from commands run in that turn: gh issue view state CLOSED for #109, #77, #149 and #86, or each one still open is listed in .claude/memory/NEEDS-OWNER.md with a reason; the static guard test that forbids parquet I/O outside the seam passes; gh pr list shows no open PR; git status shows main in sync with origin with only .claude/memory files, PLAN.md, .agents/ and GEMINI.md outside the index; pytest tests/ passes. Do not weaken a test, a Gate or a rule to get there. Or stop after 200 turns.
```

**C**

```
/goal Work stage C of .claude/memory/GOAL-RUN.md under its delegation rules. Met when the last message shows, from commands run in that turn: gh issue view state CLOSED for #97, #110, #108 and for the backend, export, run-log and restore-drill tickets created in this stage, or each one still open is listed in .claude/memory/NEEDS-OWNER.md with a reason; the restore drill passes on an empty schema; #111's options are in NEEDS-OWNER.md; gh pr list shows no open PR; git status shows main in sync with origin with only .claude/memory files, PLAN.md, .agents/ and GEMINI.md outside the index; pytest tests/ passes. Cutover is not part of this goal. Do not weaken a test, a Gate or a rule to get there. Or stop after 200 turns.
```

**D**

```
/goal Work stage D of .claude/memory/GOAL-RUN.md under its delegation rules. Met when the last message shows, from commands run in that turn: the #93 build is merged with every cron switched off; gh issue view state CLOSED for #116, or it is listed in .claude/memory/NEEDS-OWNER.md with a reason; the Fantrax login spike workflow is on main and NEEDS-OWNER.md tells the owner how to fire it; gh pr list shows no open PR; git status shows main in sync with origin with only .claude/memory files, PLAN.md, .agents/ and GEMINI.md outside the index; pytest tests/ passes. No workflow is run and no cron is enabled by the agent. Do not weaken a test, a Gate or a rule to get there. Or stop after 200 turns.
```

## After the goals (owner-led, calendar time)

The owner fires the spike. If the runner login is blocked, ADR-0015's
fallback applies: authed captures stay on the home-PC task, everything else
runs on Actions. Then the owner enables the crons, the parallel week runs,
the owner gives the cutover go, the agent closes #93 and posts the map
Resolutions, and the owner closes maps #69, #70, #71 and #66.

Out of scope of every map, staying manual: the Power BI refresh, the
manual-Excel sources (`03x`, `04x`) and the review applies.
