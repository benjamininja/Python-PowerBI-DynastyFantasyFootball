# NEEDS-OWNER — what is waiting on the owner

Every session appends here when it needs the owner (protocol in
`GOAL-RUN.md`). The `owner-queue` mod reads this file and shows it live, so
keep the format:

- two sections only, `## Decisions` and `## Actions`;
- one item per `### [ ] Title`;
- fields as `- Label: value`. Decisions carry Ticket, Context, Options,
  Recommended, Blocks, Raised. Actions carry Ticket, Steps, Context, Blocks,
  Raised;
- a Decision's choices are written `- Options: (a) ...; (b) ...` and
  `- Recommended: (a), because ...`. The pane shows one button per
  option;
- secrets are named, never written. No owner PII, no team names.

The owner answers by a button in the pane, or in chat. A button writes
`- Answer: ...` as the last field of the entry and sends the answer to
that session's chat. **No agent writes, edits or removes an `Answer:`
line.** A pane answer is the owner's wherever it lands: the session that
picks it up records it on the ticket, acts, and removes the entry (or
marks an Action `[x]` until the next state-back).

The pane reads the **main checkout's** copy of this file, from any
session or worktree. That copy is the queue; a worktree's copy is not
shown.

This file is the one place for what waits on the owner, across every
session (owner, 2026-10-12). A session that may not write it (the
planner) sends the builder manager a ready entry. Each entry says who
raised it and when, and each answer is recorded on its ticket, so it
can be traced.

## Decisions

### [ ] PR #207: keep the by-player relationship on Dead Money?
- Ticket: #140
- Context: the ticket names two relationships for `Fact_DeadMoney`
  (team, season). The builder added a third, `Fact_DeadMoney[GSISID]`
  to `Dim_NFLPlayers`, because two report visuals break `Dead Money -
  Active - Current Year` by player; without it the team's total repeats
  on every player row. The auditor's worry: under a player filter, a
  Dead Money row with no `gsis_id` would drop out of `Remaining Salary
  Cap`. Measured by the manager: 34 rows, 0 with no `gsis_id`.
- Options: (a) keep it; (b) the builder deletes the one block in `relationships.tmdl` and the two visuals are changed later
- Recommended: (a), because the two visuals need it and no row is affected today
- Blocks: the merge of #207.
- Raised: 2026-10-12, by the #140 builder through the builder manager

### [ ] A builder cannot write its memory files: where does its plan go?
- Ticket: #166, #140
- Context: the #140 builder's Edit of `RESUME.md` and `NEEDS-OWNER.md`
  in its own worktree was denied in `dontAsk` mode. No rule in
  `.claude/builders.settings.json` names `.claude/memory`; the likely
  cause is the CLI's own guard on any path under a `.claude/` folder,
  which asks, and `dontAsk` turns an ask into a denial. Not retried.
  So a builder cannot write its plan into `RESUME.md`, park an entry in
  its `NEEDS-OWNER.md`, or update a memory doc. The #140 builder went
  on with the build and will put its plan (Outline, Build mode,
  Rationale) in the PR body; it sent its park to the manager by
  message.
- Options: (a) you add `"Edit(.claude/memory/**)"` and `"Write(.claude/memory/**)"` to `allow` in the builders' file, and until that is proven a builder's plan rides in its PR body, its parks come by message, and the manager writes the memory-doc updates in its own PR; (b) no settings change: (a)'s stopgap becomes the rule and the manager writes it into `GOAL-RUN.md`; (c) stop the #140 builder until its plan can be written to `RESUME.md`
- Recommended: (a), because the rules as written need a builder to write those files, an allow rule is the smallest change, and you review #140's diff before its merge either way
- Blocks: nothing running; a stage C builder would hit the same wall at its first state-back.
- Raised: 2026-10-12, by the #140 builder through the builder manager

## Actions

### [ ] Review PR #207 (Power BI Dead Money) and refresh in Power BI Desktop
- Ticket: #140
- Steps: 1. Read
  https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/pull/207
  by commit (four commits: model, measures, `status` retirement, audit
  follow-up). 2. Check out the branch: `git fetch origin` then
  `git switch feat/140-pbi-dead-money` will fail while the builder's
  worktree holds it, so open
  `.claude/worktrees/b140-pbi-dead-money/pbi/mouserat2/Mouserat2.pbip`
  in Power BI Desktop. 3. Refresh: it should succeed with `status` gone
  and `Fact_DeadMoney` loaded. 4. Model view: three new relationships
  on `Fact_DeadMoney`, many-to-one, single direction, active. 5. On the
  Fantasy Teams page compare `Dead Money - Active - Current Year` and
  `Remaining Salary Cap` per team with what the bot shows; IR-slot
  salary is the one expected difference until #97. 6. Check the column
  widths of the four pivots that lost a selector. 7. Say "approved" in
  the manager's session, or say what to change. The manager then
  merges and cleans up.
- Context: the manager re-proved Green and posted it on the PR: 779
  tests and the bot suite pass; 33 tables identical to `main`, and
  `fact_fantasy_teams` differs only by the dropped `status` column
  (one value, `active`, on all 1,103 rows). No agent can open Power BI
  Desktop, so the refresh and the 28-team check of the ticket are
  yours. Also in the PR beyond the ticket: four report visuals lose a
  dead `columnWidth` selector; `data/fact_fantasy_teams.parquet` is
  committed from the branch; audit findings went to ticket #206
  (`Tier: unset`, the planner's).
- Blocks: the merge of #207.
- Raised: 2026-10-12, by the builder manager

### [ ] Try owner-queue 0.4.0 in a fresh session
- Ticket: #167
- Steps: 1. Start a new session (a running one keeps its old copy).
  2. Type `/owner`. Check the first line reads `owner-queue 0.4.0` and
  the footer names the main checkout's file. 3. Open a decision and
  press an option, open an action and press Mark done: both show in
  green and `NEEDS-OWNER.md` is unchanged. 4. Press Clear, stage them
  again, press Submit: the file gains the `Answer:` line and the ticked
  box, and one message arrives in chat. 5. Press a Copy button of a
  code span and paste it. 6. Type `/owner show a1` and select the
  printed text with the mouse. 7. Press "Open the queue file" and say
  whether it opened. 8. Tell the planner what did not work.
- Context: 0.4.0 stages a pressed option or Mark done and writes
  nothing until Submit. 18 automated tests pass; none of this has been
  pressed in the real pane. Upstream copy is commit 359a15a on PR 39 of
  the skills repository. A session started before 2026-10-12 still runs
  an older copy that reads its own worktree's file: an answer pressed
  there does not reach the main checkout's queue and does not count.
- Blocks: nothing.
- Raised: 2026-10-12, by the planner

### [ ] Remove two scratch worktrees of the upstream repo
- Ticket: #167
- Steps: in `C:\Users\benha\OneDrive\Documents\GitHub\skills-plugins-hooks-agents`
  run `git worktree list`, then `git worktree remove` on the two entries
  under `AppData\Local\Temp\claude` (folders `oq39` and `spha-wt`), then
  `git branch -D owner-queue-030`.
- Context: `oq39` is the planner's, made today to put 0.3.0 on upstream
  PR #39 without touching your checkout; it is clean and pushed.
  `spha-wt` is from an earlier session. The planner does not delete a
  worktree or branch without your yes.
- Blocks: nothing.
- Raised: 2026-10-12, by the planner

### [ ] Fresh 04t capture, after Wednesday 2026-10-14, 8:00 am
- Ticket: #97 (task, map #70)
- Steps: once the waiver run of Wednesday 2026-10-14, 8:00 am, has
  executed your claim and its conditional drop, run `python notebooks/04t_fantrax_transaction_history.py`
  from the repo root. Then say "04t done" in chat.
- Context: the date moved from Thursday on your word, 2026-10-12: the
  rules page says bids are "processed on: Wed, Thu at 8:00 am" and the
  published ledger holds 66 Wednesday and 59 Thursday waiver claims. A
  later capture (Friday, say) holds the same row and needs nothing
  more. If the claim lost its bid there is no row: say so, and one new
  claim or drop made after a lineup lock replaces it.
  #97 PR 1 needs a ledger that holds a move made after a lineup
  lock. A session cannot run `04t` (deny rules in `.claude/settings.json`).
  The same row tests the bid rule of #68.
- Blocks: #97 PR 1, and through it the #110 rename and #108's first
  migration: all of stage C.
- Raised: 2026-10-11, #97 grill

### [ ] Approve two additions to the manager's rules
- Ticket: #166, #162
- Steps: say "approved, write the rule PR" in the manager's session, or
  say what to change. The manager then writes them into `GOAL-RUN.md`,
  merges and cleans up.
- Context: (1) the dispatch recipe also passes the eleven deny rules
  with `--disallowedTools`, a belt beside the builders' file that can
  only deny. (2) The manager asks the planner for a read when a
  builder's PR changes an ADR, a grain or a key, touches a file its
  ticket did not name, leaves a done condition unmet or reworded, adds
  a design choice, or outgrew its tier. A read does not replace the
  re-proof of Green; a "plan breach" holds the merge until planner and
  manager agree or you rule.
- Blocks: nothing today; stage C would run under them.
- Raised: 2026-10-12, by the builder manager and the planner

### [ ] Add the two proof-command rules to the builders' file
- Ticket: #166, #186
- Steps: 1. In `.claude/builders.settings.json` add to `allow`:
  `"Bash(.venv/Scripts/python.exe scripts/compare_tables.py *)"` and
  `"Bash(.venv/Scripts/python.exe notebooks/02d_fact_roster_transactions.py --raw-dir *)"`.
  2. Optional, same file, add to `deny`:
  `"Edit(.claude/managers.settings.json)"` and
  `"Write(.claude/managers.settings.json)"`. 3. Optional, in
  `.claude/managers.settings.json` add to `deny`:
  `"Edit(.claude/agents/**)"` and `"Write(.claude/agents/**)"`. 4. Say
  "commit the settings files" and the manager commits and merges them.
- Context: both files are tracked since PR #197. #186 is merged, so its
  two proof commands exist and need one rule each; without them a stage C
  builder parks at its first "tables identical" proof.
- Blocks: stage C's proofs. Not #97's start.
- Raised: 2026-10-12, by the builder manager

### [ ] Turn on Projects and give the planner's token the project scope
- Ticket: #151
- Steps: 1. Repository Settings, Features: tick Projects. 2. In a
  terminal run `gh auth refresh -s project` and finish the browser step.
  3. Say "projects ready" in the planner's session. The planner then
  creates the Project and adds the tickets, and gives you the steps for
  the saved views and the auto-add workflow, which GitHub lets only a
  person set in the page.
- Context: you ruled a Project as a derived view of the maps, stages as
  milestones. Projects are off on the repository and the token has the
  scopes gist, read:org, repo and workflow only. Milestones work without
  this.
- Blocks: the board only; nothing in the build.
- Raised: 2026-10-12, by the planner

### [ ] Free the last leftover worktree folder
- Ticket: #164 (closeout)
- Steps: 1. Archive or close the idle session "Fix null overall_rank in
  04a in-season pulls"; it sits in `.claude/worktrees/brave-euclid-5d75b2`
  and Windows will not delete the folder while it does. 2. Delete that
  folder. 3. Run `git worktree prune` in the main checkout.
- Context: on your word the manager deleted the other three leftover
  folders on 2026-10-12. `git worktree prune` is refused to the manager
  (it writes inside `.git`), so five stale entries stay under
  `.git/worktrees/` until you run it.
- Blocks: nothing.
- Raised: 2026-10-12, by the builder manager

### [ ] Store the database secret for `migrate.yml` (later)
- Ticket: #108 (task, map #69)
- Steps: when #108's PR names the Actions secret it reads, store that
  secret in the repository's `main`-only environment. Then say so in
  chat.
- Context: you ruled on 2026-10-12 that `migrate.yml` is live from the
  day #108 merges. It applies the migrations to the real project on
  merge, so the secret must be there first. No agent reads or writes a
  secret.
- Blocks: merging #108.
- Raised: 2026-10-12, by the builder manager

### [ ] Fire the first Fantrax runner login (later)
- Ticket: #92, #93
- Steps: once stage D has merged the spike workflow, run it with
  `workflow_dispatch` and report the result in chat.
- Context: checkpoint 1. If the runner is blocked, authed captures stay on
  the home PC (ADR-0015).
- Blocks: enabling the crons.
- Raised: 2026-10-11, goal-run setup

### [ ] Cutover (later)
- Ticket: #93
- Steps: enable the crons, let the parallel week run, give the cutover go
  in chat, unregister the PC task.
- Context: checkpoint 2, after stages C and D.
- Blocks: closing #93 and maps #69, #70, #71.
- Raised: 2026-10-11, goal-run setup
