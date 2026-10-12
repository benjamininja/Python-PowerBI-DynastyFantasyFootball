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

### [ ] Fire the Fantrax runner spike again (after #230, and on other days)
- Ticket: #92, #225
- Steps: 1. On GitHub: Settings, Environments, New environment, name
  `fantrax-spike`, and limit its deployment branches to `main`. Do
  this **before the first run**: if the workflow runs first, GitHub
  makes the environment itself, with no branch rule. 2. In that
  environment add three secrets by name: `FANTRAX_EMAIL`,
  `FANTRAX_PASSWORD`, `FANTRAX_TOTP_SECRET` (the bare base32 setup
  key, no spaces). Which account is your choice; question 2 of #92
  asks about one without commissioner rights. 3. Fire the run:
  Actions tab, `fantrax-runner-spike`, Run workflow, branch `main`,
  or the block below. 4. Report in the manager's session what the
  run's summary page shows: the Login line, the read table and the
  step seconds.

```bash
gh workflow run fantrax-runner-spike.yml --ref main
```

- Context: **run 1 is done (2026-10-12): steps 1 to 4 all worked.**
  The login stopped at the second-factor code prompt, not a network
  block (34.5 s); all three secrets were set; no read was made. It
  is written on #92. What is left is steps 3 and 4 again: once
  after #230 merges, and on other days.
  Checkpoint 1 of stage D. PR #228 merged on your "merge
  228" (2026-10-12). The run prints verdicts, HTTP statuses,
  exception class names and seconds only, on a public log. Question 1
  of #92 wants several runs on different days. Until the login code
  of #230 merges a run ends at `needs_code`; you chose to fire anyway
  and again after (pane, 2026-10-12 17:19). No agent fires this or
  stores a secret. The page: `docs/research/fantrax-runner-spike.md`.
  If the runner is blocked, authed captures stay on the home PC
  (ADR-0015).
- Blocks: #92, and through it enabling the crons.
- Raised: 2026-10-12, by the builder manager

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

### [ ] Make the live clone and name both plugin folders, before the next app restart
- Ticket: #167
- Raised: 2026-10-12, by the planner
- Why: the saved `CLAUDE_CODE_PLUGIN_DIRS` names one folder, which does not exist. At the next app start neither `owner-queue` nor the dispatch plugin would load.
- Steps: 1. Make the live clone with block 1. 2. Save the variable with block 2; the two folders are joined by a semicolon. 3. Close the Claude app fully and open it again; `/reload-plugins` does not read a changed variable. 4. Check: the pane's first line reads `owner-queue 0.7.1`, and `/session-rules` is offered.
  ```
  git clone https://github.com/benjamininja/skills-plugins-hooks-agents C:\Users\benha\claude-live\skills-plugins-hooks-agents
  ```
  ```
  setx CLAUDE_CODE_PLUGIN_DIRS "C:\Users\benha\.claude\mods\owner-queue;C:\Users\benha\claude-live\skills-plugins-hooks-agents\plugins\session-dispatch-managers-build-review"
  ```
- Session: 22ca1b72-576b-45a1-8435-30ad14e53bda

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

- Context: you said "done" (2026-10-12, evening) and the manager
  sees `.claude/dispatch.json` in the main checkout, untracked. A
  second file, `.claude/dispatch-projects.json`, also sits in the
  main checkout: its place is your user `.claude` folder, where a
  copy already is, so the one in the repository can go. **One
  answer is left (step 3): is `dispatch.json` to be committed?**
  Waits on skills PR 46. The script refuses to run without
  the first file, and refuses `-Apply` in a project that is not in the
  second (your ruling to the planner, 2026-10-12). No agent writes
  either. The setup lines and the read line are today's, from
  `GOAL-RUN.md`.
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

- Context: skills PR 46 is merged (2026-10-12). Steps 1 and 2 are
  now the entry above ("Make the live clone and name both plugin
  folders"); what is left here is step 3, after that restart.
  The planner has not
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

### [ ] Cutover (later)
- Ticket: #93
- Steps: enable the crons, let the parallel week run, give the cutover go
  in chat, unregister the PC task.
- Context: checkpoint 2, after stages C and D.
- Blocks: closing #93 and maps #69, #70, #71.
- Raised: 2026-10-11, goal-run setup
