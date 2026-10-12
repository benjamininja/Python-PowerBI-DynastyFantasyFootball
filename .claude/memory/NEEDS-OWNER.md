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

### [ ] Read the spike workflow in PR #228, then say "merge 228"
- Ticket: #225, #92
- Steps: 1. Open
  https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/pull/228/files
  and read `.github/workflows/fantrax-runner-spike.yml` (53 lines); the
  driver it runs is `scripts/runner_spike.py`. 2. The PR body lists
  eight judgement calls to check. 3. Say "merge 228" in the manager's
  session, or say what to change.
- Context: the ticket names your read before the merge, because the
  workflow handles secrets and a login. It cannot run on its own: its
  only trigger is a manual run, from `main`, in an environment named
  `fantrax-spike` that does not exist until you make it. The manager
  re-proved Green (output on the PR): 816 tests, 0 Gate failures. The
  run log of a public repository is public; the driver prints verdicts,
  HTTP statuses and seconds only. The planner read the PR as no
  breach. You answered in the pane (2026-10-12 17:19): the error
  code and exception class name on the log are accepted as built,
  and the spike is fired as soon as the secrets are stored. So one
  word is left: "merge 228". After the merge the next Action (make
  the environment, store the secrets, fire the run) is added here.
- Blocks: #225, and through it #92.
- Raised: 2026-10-12, by the builder manager

### [ ] Approve the planner state PR #226
- Ticket: #167, #225
- Steps: read
  https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/pull/226
  (`PLANNER.md` only) and say "approved" in the manager's session, or
  say what to change. The manager then merges it and cleans up.
- Context: the planner's state before its compact: the dispatch plugin
  in hand, the milestones, #225.
- Blocks: nothing in the build.
- Raised: 2026-10-12, by the planner

### [ ] #230: report what the Fantrax code prompt looks like
- Ticket: #230
- Session: 22ca1b72-576b-45a1-8435-30ad14e53bda
- Steps: 1. Log in to Fantrax once in a normal browser window where the
  code prompt appears (a private window does it). 2. At the prompt,
  note the label of the code field and the text of the button that
  submits it. 3. Write both on #230, or say them in a session. No
  code, secret or account detail goes on the ticket.
- Context: #230 is the ticket for the login answering the
  second-factor code prompt (TOTP), medium tier, stage D. The login
  code fills the email and the password only. The fill step for the
  code is written against what you report, not against a guess; no
  agent may look.
- Blocks: the dispatch of #230.
- Raised: 2026-10-12, by the planner

### [ ] Skills PR 46: review, run the security review, merge
- Ticket: #167
- Session: 22ca1b72-576b-45a1-8435-30ad14e53bda
- Steps: 1. Open a session rooted in the skills repository and run
  `/security-review` on branch `session-dispatch-plugin`. It did not
  run from the planner's session, where the command is not available.
  2. Read https://github.com/benjamininja/skills-plugins-hooks-agents/pull/46
  , most of all `scripts/dispatch.ps1`. 3. Merge it. 4. Pull the live
  clone at `C:\Users\benha\claude-live\skills-plugins-hooks-agents`.
- Context: the dispatch plugin (#167 step 2) is a dry-run-first script
  that starts a builder, two skills and templates. 12 tests of the
  script pass; the full suite passed (155) before the last script
  change; CI runs it all.
- Blocks: the three #167 entries below, and #218.
- Raised: 2026-10-12, by the planner

### [ ] #167: write the two owner-only files for the dispatch script
- Ticket: #167
- Session: 22ca1b72-576b-45a1-8435-30ad14e53bda
- Steps: 1. Create `.claude/dispatch.json` in the main checkout with
  the first block. 2. Create `dispatch-projects.json` in your user
  `.claude` folder with the second block. 3. Say so in the manager's
  session, and say whether `dispatch.json` is to be committed.

```json
{
  "agent": "stage-builder",
  "buildersSettings": ".claude/builders.settings.json",
  "claude": "C:\\Users\\benha\\.local\\bin\\claude.exe",
  "setup": [
    "python -m venv .venv",
    ".venv\\Scripts\\python.exe -m pip install -r requirements.txt"
  ],
  "readLine": "Read C:\\Users\\benha\\.claude\\memory\\preferences.md, then .claude/memory/RESUME.md Standing rules and NEXT, then .claude/memory/GOAL-RUN.md and NEEDS-OWNER.md."
}
```

```json
{
  "projects": [
    "C:/Users/benha/OneDrive/Documents/GitHub/Python-PowerBI-DynastyFantasyFootball"
  ]
}
```

- Context: waits on skills PR 46. The script refuses to run without
  the first file, and refuses `-Apply` in a project that is not in the
  second (your ruling to the planner, 2026-10-12). No agent writes
  either. The setup lines and the read line are today's, from
  `GOAL-RUN.md`.
- Blocks: the first dispatch with the script.
- Raised: 2026-10-12, by the planner

### [ ] #167: settings rules for the dispatch script
- Ticket: #167
- Session: 22ca1b72-576b-45a1-8435-30ad14e53bda
- Steps: 1. In `.claude/managers.settings.json`, add the first block's
  line to `permissions.allow`. 2. In both
  `.claude/managers.settings.json` and `.claude/builders.settings.json`,
  add the second block's lines to `permissions.deny`. 3. Optional,
  once the script has made one real dispatch: remove the allow rule
  `PowerShell(*claude.exe --bg *)` from the managers' file, so a
  builder can only be started through the script. 4. Say "commit the
  settings files" in the manager's session.

```
"PowerShell(*session-dispatch-managers-build-review\\scripts\\dispatch.ps1 *)"
```

```
"Edit(.claude/dispatch.json)", "Write(.claude/dispatch.json)",
"Edit(~/.claude/dispatch-projects.json)", "Write(~/.claude/dispatch-projects.json)"
```

- Context: waits on skills PR 46. The allow rule lets the manager run
  the script without a prompt. The deny rules keep every session from
  writing the two owner-only files.
- Blocks: the first dispatch with the script.
- Raised: 2026-10-12, by the planner

### [ ] #167: load the plugin in the manager's and builders' sessions
- Ticket: #167
- Session: 22ca1b72-576b-45a1-8435-30ad14e53bda
- Steps: 1. Add the folder in the block to the user environment
  variable `CLAUDE_CODE_PLUGIN_DIRS`, beside the owner-queue folder
  already in it. 2. Restart the sessions. 3. In the manager's session,
  invoke the session-dispatch skill for the next real ticket; the
  manager runs the dry run, then `-Apply`.

```
C:\Users\benha\claude-live\skills-plugins-hooks-agents\plugins\session-dispatch-managers-build-review
```

- Context: waits on the two entries above. The planner has not
  verified how that variable separates two folders on Windows (most
  likely a semicolon). If the second folder does not load, say so and
  the planner finds out. #167 closes on the first real dispatch
  through the script, not on the PR.
- Blocks: closing #167.
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
