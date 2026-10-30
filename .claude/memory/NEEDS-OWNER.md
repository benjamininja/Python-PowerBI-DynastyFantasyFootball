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

### [ ] Remove the spike schedule (#254, #92): approve its small PR when due
- Ticket: #254, #92
- Due: when #92 is answered, or seven days after the #254 merge
  (2026-10-21), whichever is first.
- Step: the manager opens one small PR that deletes the `schedule`
  trigger from `fantrax-runner-spike.yml` and the header line about
  it. You approve it like #254 (a workflow trigger change).
- Context: PR #256 (merged 2026-10-14, `b436823`) fires the spike
  daily at 14:17 UTC; no one fires it by hand now. The manager reads
  each run's summary (the `Code sent by:` word included) and records
  it on #92 and #230.
- Raised: the planner, 2026-10-14 (ready entry), written by the
  builder manager
- Session: 56063cf0-bc0e-400b-bb12-5b1aeb644f85

### [x] Make the live clone and name both plugin folders, before the next app restart
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
- Note: this is what i received when attempting the first command in terminal: fatal: destination path 'C:\Users\benha\claude-live\skills-plugins-hooks-agents' already exists and is not an empty directory. | pane, 2026-10-14 18:58:45, session 56063cf0-bc0e-400b-bb12-5b1aeb644f85

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
- Note: check if this is done | pane, 2026-10-30 08:15:56, session a3f025ae-a21b-4f55-ab21-a8465c8c59b4

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
