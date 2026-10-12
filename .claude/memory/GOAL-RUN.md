# GOAL-RUN — finishing the wayfinder maps under `/goal`

Approved by the owner 2026-10-11 (plan `proud-plotting-cocoa`; the four
rulings were given 2026-10-05). This file is the runbook a goal session
works from. `RESUME.md` still holds the state-back; `NEEDS-OWNER.md` holds
everything waiting on the owner.

**Scope of the delegation:** goal runs on maps #69, #70, #71 and #66 only.
Any other work keeps the standing rules in `RESUME.md` unchanged.

## Session setup (builder manager, per dispatch)

Owner's ruling 2026-10-12, #166. The builder manager starts every
builder from PowerShell with the CLI at its full path. It copies the
tier: for a stage, from the Tier column under "Stages"; for a single
ticket, from the ticket's own `Tier:` line; otherwise from the brief.
It never picks one. No tier, no dispatch: it asks the planner.

| Tier | Model and effort | For | Turn cap |
|---|---|---|---|
| low | Sonnet 5.5, medium | tightly scoped work | 30 |
| medium | Sonnet 5.5, high | work with an investigative step | 80 |
| high | Opus 5.5, medium | a stage or other large work | 200 |

The turn cap is written into the prompt ("Or stop after N turns"), as
the goal texts below already do.

1. Make the worktree: `git worktree add .claude/worktrees/<name> -b
   worktree-<name>` from the main checkout. Made this way it holds no
   settings file of its own.
2. Build its `.venv` (`python -m venv .venv`, then
   `.venv/Scripts/python.exe -m pip install -r requirements.txt`) and
   check that `pytest` collects. A read-only low job whose brief says
   `venv: no` skips this step.
3. Start, from the main checkout: `claude.exe --bg -w <name> --name
   <name> --model <tier's model> --effort <tier's effort>
   --permission-mode dontAsk --settings <main checkout>\.claude\builders.settings.json
   --agent stage-builder <prompt>`. `-w` takes the worktree that is
   already there. The prompt is the read line below, then the `/goal`
   text or the brief. It is read from a file and holds **no double
   quote**: PowerShell cuts the prompt off at the first one. Never from
   Git Bash: it rewrites `/goal` into a path.
4. Check in `claude agents --json` that it has a `pid` and that its
   `cwd` is `.claude/worktrees/<name>`. If it is not, stop it at once.
5. Watch `status`, `state` and `waitingFor` in `claude agents --json`
   and the transcript `.jsonl`; `claude logs` is not readable.
6. Follow up: `claude stop <id>` first, then `claude --resume
   <sessionId> --bg <message>` from the builder's worktree, with the
   same mode and settings. Resuming a session that is still alive
   starts a copy. Remove with `claude rm <id>` only at closeout; it
   refuses while the worktree holds an uncommitted file.

(Order and the two warnings proven by the dry dispatch of 2026-10-12.)

The read line, first in every builder's prompt: "Read
`C:\Users\benha\.claude\memory\preferences.md`, then
`.claude/memory/RESUME.md` Standing rules and NEXT, then
`.claude/memory/GOAL-RUN.md` and `NEEDS-OWNER.md`."

**A job in no plan.** The manager may dispatch a read-only or tightly
scoped job at low only, with the low turn cap, and names it in its next
report. Anything that would need medium or high goes to the planner or
the owner first.

**Outgrown tier.** A builder whose work turns out bigger than its tier
parks with what it found. The planner sets a new tier; the manager
dispatches again.

## Delegation rules (goal runs only)

| Matter | Rule |
|---|---|
| Plan gate | A `wayfinder:task` ticket whose design is already in an ADR or a closed grilling ticket: write the plan into `RESUME.md` (Outline → Build mode → Rationale), then build. A new design decision parks. |
| Commit, PR, merge | Two-key merge (owner's ruling 2026-10-12). The builder commits, pushes its own branch and opens the PR. It does not merge. When the PR is green by its own check it messages the manager, ends its turn and waits. The manager re-proves green (below), squash-merges with `--delete-branch`, pulls, and wakes the builder, which starts its next branch from the new `origin/main`. |
| Tracker | The builder posts Resolutions as comments and creates new task tickets (`Tier: unset`). A ticket closes through its PR's closing keyword when the manager merges. The manager closes or edits any other ticket and adds the pointer to the map's Decisions so far. Text goes through `check_pii.py` first. |
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
A builder runs in `dontAsk` with `.claude/builders.settings.json`, so a
call not on that list is a denied call. Two limits, found in the dry
dispatch of 2026-10-12: a read-only command runs without a rule, and
the owner's user-level allow rules reach a builder too. So what a
builder must never do is a **deny** rule in the builders' file (a deny
beats an allow from anywhere): merging, `gh api`, `python -c`, closing
or editing a ticket, and the "Never" list.

## Park protocol

Owner's ruling 2026-10-12: "when there are questions/decisions for me
or actions needed of me, this is where we are moving it so the context
is sticky even though the session itself has gained new entries. it's a
shared entry across sessions. everything should be clear on tracing."
So every session, not only a builder, puts what it leaves with the
owner into `NEEDS-OWNER.md`. The planner does not write that file: it
sends the builder manager a ready entry. Chat alone is not enough.

1. Stop work on the ticket. Do not answer the owner's side.
2. Append an entry to `NEEDS-OWNER.md`, in the format its header gives:
   under `## Decisions` for a choice (Ticket, Context with the evidence,
   Options, Recommended, Blocks, Raised) or under `## Actions` for work by
   the owner's hand (Ticket, Steps, Context, Blocks, Raised). Options
   are written `(a) ...; (b) ...` and Recommended `(a), because ...`.
   The `owner-queue` pane reads the main checkout's copy only, and only
   the manager and the planner have the pane. So a builder writes the
   entry in its worktree's copy, and the manager copies it into the
   main checkout's copy at once, when the builder's message of step 3
   arrives.
3. Send one desktop push notification. No public post. If a managing
   session started this one, also send it one message that names the
   entry; the push does not arrive when Remote Control is off.
4. Take the next unblocked ticket of the stage. If none is left, print
   `NEEDS-OWNER.md` and end the turn; the goal text counts that as met.
5. The owner answers by a button in the pane or in chat; either is the
   approval. A button writes an `Answer:` line into the entry, which no
   agent writes, edits or removes. A pane answer is the owner's
   wherever it lands: the session that picks it up acts on it, and for
   a builder's entry the manager relays it, quoting the line. A relay
   from the managing session counts as the owner's answer under the
   rule below. Record it
   (ADR, ticket Resolution or `RESUME.md`, as fits), remove the entry in
   the same turn, and put the ticket back in the queue. The same goes for
   an action the owner reports done, or one the session finds done (a
   closed ticket, a secret now present by name): remove it at once, so the
   list never shows finished work. The owner can also press "Mark done" in
   the pane, which ticks the entry `[x]`; delete ticked entries at the
   next state-back.

### Relayed answers (owner's rulings 2026-10-12, #166)

The owner may answer a parked entry in the managing session instead of
the builder's. The managing session then sends the builder one message.
It counts as the owner's answer only when all of these hold:

- it answers an entry that is already in `NEEDS-OWNER.md`;
- it quotes the question put to the owner and the owner's answer word
  for word;
- it comes from the session that started the builder.

The builder records the answer with the note "relayed by the manager"
and goes on. Under these three conditions a relay may answer any parked
entry, including checkpoint 1, checkpoint 2, closing a map and a new
decision (owner's ruling 2026-10-12, #166). A relay never lifts the
"Never" list, and it never covers a question the builder has not
parked: the builder parks first, then the answer comes. If a relay is
unclear or goes past the entry, the builder does not act on it and says
so in its reply.

Why: the owner checks in as needed, not at every step; without this a
park pulls the owner into each builder session. The word-for-word quote
and the named source keep a misquote visible.

## The managing session (owner's rulings 2026-10-12, #164, #166)

Roles are set out in the #164 resolution; role files in
`.claude/agents/` point here. The managing session is the builder
manager (session name `dynastyFantasyFootball-central-builder-manager`):
it starts and watches the builders, and the owner's words reach a
builder through it, quoted word for word, within "Relayed answers"
above. What it may do under a goal run:

**Edits.** `.md` files and `.claude/memory/*` only, in its own worktree
and its own PR, and only files no open builder PR touches. Never code,
tests, notebooks or data. It never commits for a builder.

**Merges (owner's ruling 2026-10-12).** The owner's words: "you should
be merging the prs and then cleaning up and resetting. to me they are
all the same sequence (approval) gate." So the owner's approval of a PR
is one gate. After it the manager merges on green (one CI read,
squash, `--delete-branch`), pulls, deletes the local branch and leaves
the main checkout clean on `main`. This covers its own PRs and a rule
change the owner has approved; the owner no longer merges those by
hand. A settings or permission file stays the owner's own commit.

**Merging a builder's PR (two-key merge, owner's ruling 2026-10-12).**
A builder may not merge. When it messages that a PR is green, the
manager re-proves every item of "Green means all of" itself, posts the
output on the PR, squash-merges with `--delete-branch`, pulls, and
wakes the builder. A PR that is not green goes back to the builder with
the failing output; it is not merged. Why: nothing reaches `main` on
one session's own report, while the builder's branch is still pushed,
so its work is backed up and tested by CI. Cost: the builder waits a
few minutes per PR.

**Check-ins.** Event-driven: a park, a PR reported green, a stopped or
idle builder. One fallback look after 60 quiet minutes. No polling.

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

| Stage | Tier | Tickets, in order | Waits on the owner for |
|---|---|---|---|
| A. Ledger and cap | done | #96 PR 2 → #68 (both closed 2026-10-11; #97 moved to C) | done |
| B. Seam | high | #109 → #77 → #149 → #86 (all closed 2026-10-12; #110's last part moved to C) | done |
| C. Postgres | high | #97 → #110 `roster_slot` rename → #108 → Postgres backend and backfill → snapshot export step → `ops.etl_run_log` → restore drill → #111 | the fresh `04t` capture (after Wednesday 2026-10-14, 8:00 am) |
| D. Schedule | high | #92 login code → Linux entrypoint → #93 → #116 | the TOTP secret stored; B and C merged |

A ticket's own `Tier:` line says what it needs if dispatched alone. In
a stage run the stage's tier applies, and it is never lower than the
highest ticket in the stage. A ticket a builder creates says `Tier:
unset` and is not dispatched alone until the planner has set it.

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
- **C.** Before the stage is dispatched, #186 is done: a tracked
  `scripts/compare_tables.py` and a `--raw-dir` argument on `02d`, so
  the stage's proofs are exact commands on the builders' list. It is
  `Tier: low` and is dispatched alone. The stage starts with #97 (plan
  `C:\Users\benha\.claude\plans\squishy-toasting-minsky.md`, three PRs)
  and then the #110 rename, because #108's first migration needs the
  `fact_fantasy_teams` key that #97 declares and `fact_trade_log` from
  #109. The four middle items are tickets #135 to #138. Before #108,
  load the `supabase-postgres-best-practices` skill if it is installed
  and decide how tables stay off Supabase's Data API (row-level security
  on, or a schema that is not exposed); run the connector's security
  advisors after each migration.
  `migrate.yml` is live from the day #108 merges (owner's ruling
  2026-10-12): it is the only way the schema reaches the real project
  without an agent writing to it. #108's PR names the secret it reads
  and waits for the owner to store it.
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
