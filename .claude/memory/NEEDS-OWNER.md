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
- a `- Note:` line is the owner's comment, written by the
  owner-queue pane. No agent writes, edits or removes a `Note:`
  line. An entry may hold several; they leave with the entry
  (owner-queue 0.7.1, as are the four lines below);
- a pane message in chat carries a `Time:` line. Act on a pane
  answer only while its entry is still in this file; a message with
  an old time is a repeat;
- anything the owner types or pastes by hand goes in code marks, one
  value per mark, with no prose inside the marks. The pane draws a
  Copy button for each;
- a command the owner runs goes in a fenced block, which the pane
  copies whole;
- steps are numbered `1.`, `2.`, `3.` inside the Steps field. The
  pane draws one step per row with that step's Copy buttons under
  it;
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

### [ ] Fire the Fantrax runner spike again: #230 is merged, the login now types the code
- Ticket: #230, #92
- Steps: 1. In the repository's `fantrax-spike` environment, confirm
  the three secrets exist by name: `FANTRAX_EMAIL`,
  `FANTRAX_PASSWORD`, `FANTRAX_TOTP_SECRET` (the bare base32 setup
  key, no spaces). They were all set for run 1. 2. Fire the run from
  `main`: Actions tab, `fantrax-runner-spike`, Run workflow, or the
  block below. It starts from an empty profile every run. 3. Report
  in the manager's session the Login line (`passed`, `needs_code`,
  `challenged` or `failed`), the class name after `Login step
  raised:` if any (`TotpCodeRefused`, `TotpSecretMissing`), the read
  table and the step seconds. 4. If you can tell: did the form submit
  by itself on the sixth digit, and what did a wrong or expired code
  look like?

```bash
gh workflow run fantrax-runner-spike.yml --ref main
```

- Context: PR #249 (merged 2026-10-14) makes the one login path type
  the current code from `FANTRAX_TOTP_SECRET`. No agent has logged
  in; it is proven on a fake page only, so your run is the first
  sight of the real page. A refusal is detected as the code field
  still showing 10 s after the submit; the PR body lists the
  assumptions. Run 1 (2026-10-12) stopped at the code prompt, not a
  network block. #92 question 1 wants several runs on different days,
  so fire it again on later days too. The run prints verdicts, HTTP
  statuses, exception class names and seconds only, on a public log.
  No agent fires this or stores a secret. If the runner is blocked,
  authed captures stay on the home PC (ADR-0015).
- Blocks: closing #230; #92's runner login, and with it the scheduled
  capture of ADR-0015 and enabling the crons.
- Raised: stage-builder (#230), 2026-10-14; merged into the builder
  manager's entry of 2026-10-12

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

### [ ] Remove two dead allow rules from the builders' settings file
- Ticket: #234
- Steps: 1. Open `.claude/builders.settings.json` in the main checkout. 2. In the `allow` list, delete the line `"Edit(.claude/memory/**)",` and the line `"Write(.claude/memory/**)"`. 3. Remove the comma that now ends the line above them, the `02d_fact_roster_transactions.py --raw-dir` rule, so the list stays valid JSON. 4. Commit it on a branch and tell the manager.
- Context: In a builder's mode a write under `.claude/` is refused before any allow rule is read, so the two rules never take effect and only mislead a reader. Optional; nothing breaks if they stay.
- Blocks: nothing
- Raised: central-planner, 2026-10-12
- Session: 22ca1b72-576b-45a1-8435-30ad14e53bda

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
