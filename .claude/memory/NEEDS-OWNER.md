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

## Actions

### [ ] Approve the planner state PR #216
- Ticket: #151, #162
- Steps: read
  https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/pull/216
  (`PLANNER.md` only) and say "approved" in the manager's session, or
  say what to change. The manager then merges it and cleans up.
- Context: the planner's record of the GitHub Project it built and of
  the correction to #140.
- Blocks: nothing in the build.
- Raised: 2026-10-12, by the planner

### [ ] Finish the GitHub Project's views by hand
- Ticket: #151
- Steps: 1. Open https://github.com/users/benjamininja/projects/2
  2. In view "By stage" open the view menu, Group by, Milestone. 3. In
  view "By map", Group by, Parent issue. 4. Three-dot menu, Workflows,
  "Auto-add to project": pick this repository, filter
  `is:issue,pr is:open`, turn it on and save.
- Context: the Project and its three views exist; the API cannot set a
  view's grouping or the auto-add workflow.
- Blocks: nothing; until auto-add is on the planner adds new tickets
  itself.
- Raised: 2026-10-12, by the planner

### [ ] Check the Dead Money model in Power BI Desktop
- Ticket: #211
- Steps: open `pbi/mouserat2`, refresh, look at the Dead Money
  measures for a team that has dead money, and write the result on
  #211.
- Context: PR #207 merged on your word ("merge 207", 2026-10-12)
  without this check. Power BI is deprioritized; do it when Power BI
  is next opened. Until #97, the report exempts IR-slot salary and
  the bot does not, so the two differ by each team's IR salary.
- Blocks: nothing.
- Raised: 2026-10-12, by the planner

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

### [ ] Add four allow rules to the builders' file
- Ticket: #166, #186
- Steps: 1. In `.claude/builders.settings.json` add to `allow`:
  `"Bash(.venv/Scripts/python.exe scripts/compare_tables.py *)"` and
  `"Bash(.venv/Scripts/python.exe notebooks/02d_fact_roster_transactions.py --raw-dir *)"`,
  `"Edit(.claude/memory/**)"` and `"Write(.claude/memory/**)"` (your
  pane answer of 2026-10-12: a builder writes its own memory files).
  2. Optional, same file, add to `deny`:
  `"Edit(.claude/managers.settings.json)"` and
  `"Write(.claude/managers.settings.json)"`. 3. Optional, in
  `.claude/managers.settings.json` add to `deny`:
  `"Edit(.claude/agents/**)"` and `"Write(.claude/agents/**)"`. 4. Say
  "commit the settings files" and the manager commits and merges them.
- Context: both files are tracked since PR #197. #186 is merged, so its
  two proof commands exist and need one rule each; without them a stage C
  builder parks at its first "tables identical" proof.
  A builder's Edit under `.claude/memory/` is denied in `dontAsk` mode
  today; whether an allow rule lifts that is proven at the next
  dispatch. Until then a builder's plan rides in its PR body, its
  parks come by message, and the manager writes the memory docs.
- Blocks: stage C's proofs. Not #97's start.
- Raised: 2026-10-12, by the builder manager

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
