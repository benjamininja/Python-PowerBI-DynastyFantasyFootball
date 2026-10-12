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
- text the owner must paste goes in a fenced block (three backticks),
  one fence per paste, written exactly as it is pasted. Inline code is
  for names only. The pane draws one Copy button per fence;
- an entry whose answer should come back to a session carries
  `- Session: <that session's id>`. Leave it out for an entry any
  session may act on (owner-queue 0.5.0);
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

### [ ] Clear the stale worktree entries OneDrive will not let go
- Ticket: #167, #164
- Steps: 1. Archive or close the idle session "Fix null overall_rank in
  04a in-season pulls"; it holds the empty folder
  `.claude/worktrees/brave-euclid-5d75b2`. 2. Pause OneDrive sync (tray
  icon, Pause syncing). 3. In a terminal at the repo root run the three
  blocks below. 4. Resume OneDrive sync and say "done" in the manager's
  session.

```powershell
Remove-Item -Recurse -Force .claude\worktrees\brave-euclid-5d75b2
```

```powershell
git worktree prune -v
```

```powershell
git -C ..\skills-plugins-hooks-agents worktree prune -v
```

- Context: on your word (2026-10-12) the manager deleted four of the
  five leftover folders, removed the upstream scratch worktrees
  `spha-wt` and `oq39` (the planner said it was finished with it)
  and deleted the local branch `owner-queue-030`. What is left is harmless and only untidy: one empty folder
  held by the idle session, five stale entries under `.git/worktrees/`
  of this repository and two (`spha-wt`, `oq39`) in the upstream
  repository.
  Git reports "Permission denied" on deleting them, in the manager's
  shell and in yours; the folders carry OneDrive's attributes, so the
  likely holder is OneDrive sync. `git worktree list` is already
  correct in both repositories. The planner's new scratch worktree
  of the upstream repository (branch `session-dispatch-plugin`) is
  live and stays.
- Blocks: nothing.
- Raised: 2026-10-12, by the builder manager

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
