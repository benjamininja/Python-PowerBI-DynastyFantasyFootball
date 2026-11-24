# PLANNER — the planner's state

The planner (`.claude/agents/dff-central-planner.md`) writes this file and no
other in `.claude/memory/`. It has two blocks. **Current** is rewritten at
every save and holds what a new planner session needs to act. **Reference**
changes slowly. Nothing is stacked: history is in git, and the daily state
PR's diff shows what moved and what was decided. The rules are in the
`session-rules` skill, `GOAL-RUN.md` and the role file; this file is state.

Shape approved by Ben on 2026-11-14 (tools #161 issuecomment-6886175657;
design issuecomment-6886003169). The stacked items this file held until then
are in git: the last commit with them is `53104a9` on the state branch.

## Current

**Saved:** 2026-11-24 (see the commit time), session cff0e612-f08d-401c-9bb6-2a60446c1492. One Current block (Ben's button, benjamininja/skills-plugins-hooks-agents#243). Stacked history: `995f0cf` on `docs/state-2026-11-16` (PR #575, `0916977`). State branch `docs/state-2026-11-22`; the manager opens its PR.

**Done 2026-11-22/23:** #548 brief 3 merged (#646, `61aa044`); #647, #649 (#648) and #642 (#623) merged. Gap #650 (the crosswalk loader read the wrong headers) was ticketed low, and PR #652 merged it. The ADR-0025 text for `GOAL-RUN.md` After a schema change lands and for `supabase-auditor.md` was posted at #548 issuecomment-7088321713 and merged as PR #651 on Ben's buttons. Ben's sign-in check is done, with Confirm email on by his ruling (issuecomment-7102523231). The planner ruled that brief 4 adds Confirm email to ADR-0025's dashboard list and checks it against the docs (issuecomment-7102774835). Main is at `828db84`.

New tickets: #654 (owner-led grill, below); #655 (owner-led: about 53 GB of per-worktree `.venv`; the cause of closeout step 4 not removing worktrees is unknown; the tools halves are tools #250, the closeout script, high, and tools #251, the dispatch lists, medium); #658 (owner-led grill: one app for several Fantrax leagues and sports, football first, then baseball). Planner draft PR #653: `.claude/agents/supabase-look.md` from tools #247's template.

**Done 2026-11-23, after the clear:**

- **Q6 `locked_value` is ruled by the planner, option (a):** no column on the published table; the price is stored once, in `fact_salary_price_list` (#548 issuecomment-7103631284). ADR-0025 decision 10 point 1 made it the planner's; queuing it for Ben was an error. The manager removed the queue entry. Brief 4 gains a done condition: each candidate shows its locked price.
- **The #654 grill, questions 1 to 9, answered by Ben by button** (issuecomment-7103309381, -7103433632, -7103633403, -7103781615, -7103974431):
  1. Live: a role switch (lowest role first: owner, commissioner, site admin) and a read-only view-as for site admin. Act-as and phase mimic only on fake data.
  2. Live view-as is masked: access facts only, no other team's choice values before its deadline.
  3. Commissioners write in the app before and after a deadline, as an action: one team, one reason from a list, one dated note; rows carry `origin` commissioner; an append-only history keeps every version.
  4. Record-first; the database refuses an action on a team the commissioner owns.
  5. Four phases: `none`, `open`, `passed`, `final`. The `final` instant is stored in `ops.choice_deadline`; #559 reads only `final` choices.
  6. Roles in `shared.app_role`, loaded by Ben's paste; owner stays derived from the crosswalk.
  7. Staging: the role, phase and action table proven by the policy tests on every PR, and a scripted browser run on a throwaway CI stack for page PRs, with a screenshot per cell. No second Supabase project. Ben is installing Docker, so the same stack can run on his PC.
  8. Before a deadline a commissioner's action is a blind write through one database function.
  9. The app gets a domain of its own (tab-only session as the fallback). League-neutral name.
  - Planner's rulings on #654: the reason list; what a pass is; history, the `final` instant and the role table land before the first owner write; a league scope on `shared.app_role`.
- **Multi-league:** Ben chose to launch football first, built multi-league-ready, plus baseball as the second sport (#658). No league key exists in `docs/data_model.yml` today.
- **#655:** two planner worktrees removed on Ben's button (issuecomment-7102991352). Ben's eleven answers from the assistant's grill are recorded as a relay (issuecomment-7103311428), not yet checked against the assistant's chat.
- **Tools #247:** the planner answered that the builders' settings should also deny the unauthenticated Supabase plugin server (tools #247 issuecomment-7103639275). PR #656 (the consultant line) merged as `97dbebb`.

**Done 2026-11-24:**

- **PR #660 (ADR-0026) merged** as `f8b4584` at 13:07:35Z, on Ben's button asked again in the new session (PR #660 issuecomment-7132405769). #654 has its resolution pointer (issuecomment-7132410402) and the manager closed it. The PR's worktree and local branch are removed on Ben's button; the removal stopped part way once, recorded at #655 issuecomment-7132486482.
- **Planner PR #667** (branch `docs/auditor-basis-adr-0026`, head `b774bd1`): the supabase-auditor's basis follows ADR-0026 and ADR-0026's status reads accepted. Merged as `44dd334` at 13:33:17Z on Ben's button (PR #667 issuecomment-7133002512); the manager is told. Its worktree and local branch are removed on Ben's button.
- **PR #659 finding F1:** the planner's read is fix in this PR, and #626's done condition now names three Fantrax names (PR #659 issuecomment-7132497362).
- #661 and #662 carry `Profile: none`. Ben chose #597 as the manager's next dispatch; #661 follows in the next slot on his go. Ben answered #616's Decision (a).
- **The page's read path is ruled** (ADR-0026 decision 10 point 1; #548 issuecomment-7132918295), accepted by Ben's button (Record, own brief): invoker views in `app` over `shared` functions granted to `authenticated` by name; no function in `app`. The brief is **#670** (medium, `Profile: none`): the generator learns views, plus `app.choice_windows` and `app.my_teams`. The manager is told.
- **#655:** the assistant's read-only diagnosis of the 24 damaged records is recorded (issuecomment-7132935486): each lacks `HEAD`, `commondir` and `index`; links are sound; 23 keep a branch tip; the move of 2026-11-19 is the likely cause, not proven. **The plan is settled by Ben's buttons** (Judge, then remove; After first run): issuecomment-7133100125. No record is rebuilt. After the closeout script's first run, the 23 are compared with their tips, link-checked, put to Ben as a list, and removed by the manager on his button. b349-floats was read first-hand: every difference is the incoming half of a stopped merge and is on main (issuecomment-7133126900); it goes to Ben as its own line.
- **PR #669 (#616):** the planner's read is no breach (PR #669 issuecomment-7133134378). PR #668 merged as `43d053c`.
- **The assistant's token cost ledger** reached both planners (chat only; the shared rules are the Tools planner's): managers 32%, planners 23%, builders 22%; a dynasty planner start costs 1.1 to 2.2 million input-equivalent tokens. A slimmer start-up read list is the lever in dynasty's hands; no rule is decided.

### Next (in order)

1. **PR #667 is merged** (`44dd334`); nothing is left of it. Send the manager the `GOAL-RUN.md` lines when it says #661's PR is open.
2. **The briefs are posted, all medium.** Order: #661, #662, #670 (same files, so one after the other), brief 4 restated whole (#548 issuecomment-7104491120), the after-deadline copy (#548 issuecomment-7104493151), #663, #664, #665. Restate #663 to #665 against the merged code before dispatch. Of the six points ADR-0026 lists as not decided, the read path is ruled (#670); brief 4's text must say it reads `app.choice_windows` and `app.my_teams` and holds no schema change. When #670's PR opens, send the manager a `GOAL-RUN.md` line: every view in `app` has `security_invoker` on. What each brief holds (brief 4 lands outside 2026-12-03 to 2027-01-07 and before the 2027 re-sign deadline):
   - Foundations, before any owner write: the append-only history, the `final` instant (required, later than the deadline, not movable once passed), `origin` commissioner, `shared.app_role` with a league scope, the role, phase and action table and its policy tests.
   - Brief 4, the owner's page: Discord sign-in, the locked price beside each candidate, one backend fixed at build, a content security policy, the session rule of question 9, the Confirm email line for ADR-0025.
   - The after-deadline copy: idempotent, as `etl_writer`, no `changed_by`, no `locked_value`, its table on the data-PR allowlist, carrying `origin` and honouring `final`.
   - The commissioner's action (the blind-write function) and status board; then the site admin's masked view-as.
   - The scripted browser run on a throwaway CI stack, with a screenshot per cell, and the steps to run it on Ben's PC.
3. **The app's domain:** an Action for Ben with exact steps (the name, DNS, the Pages setting, the redirect addresses), written with brief 4.
4. **The owner-queue mod is no longer the dynasty planner's.** On Ben's button of 2026-11-24 (Transfer the whole mod lane), the Tools planner plans every mod ticket, tools #137, #111 and auto-close included. Handoff: tools #137 issuecomment-7132677793. Nothing is owed here; the Tools planner sends one line when the pane's behaviour changes.
5. **#655:** the assistant's second report is recorded (issuecomment-7104537108: 24 worktrees with a damaged git record, 15.7 GB, which the tools #250 script refuses; what deleted the tracked role files is unknown). The interim removal check is issuecomment-7104025813. The tools planner ruled that the script never removes those 24 (issuecomment-7104641713): the plan is settled (issuecomment-7133100125) and waits on the closeout script's first run (tools PR #252); then the list of 23 plus b349-floats goes to Ben by button. Still open: what deleted the tracked role files. Check the relayed answers against the assistant's chat. Then re-order the ticket (fix first, prune last); propose the text of dynasty's light and full setup lists for `.claude/dispatch.json` (key names `setup` and `setupFull` are tools #251's proposal, not final); propose the `GOAL-RUN.md` and manager-rule lines that answers 5, 6 and 10 change; name the proof that `pytest tests/ -q` and the pre-commit run pass from a light-venv worktree.
6. **PR #653** (supabase-look): mark it ready once tools #249 merges, tell the Tools planner, then ask Ben by button to merge. Then ask Ben about its worktree.
7. **#658** (owner-led): the multi-league grill. Its first question is whose the baseball repositories are and on what terms.
8. **The manager's order:** the crosswalk SQL waits on Ben's hand; then #616, #626, #597, #633, #637, #639, #644. The last manager session led with #633, #637, #639; the manager asks Ben which leads. Read each PR when asked.
9. **#592** (held): rewrite with #545's move to `ops.choice_deadline`; then ticket #545's reader move. **#620** waits on tools PR #242's lock text. **#604 and #590** at Ben's go.

### Peers (queue ids)

Ids as of 2026-11-24, each sent by its session; find each by name.

- dff-central-builder-manager: `695f05fc-6dff-445b-a9fd-af605c6997d9`. Builder b616-manualpublish builds; builder b626-creds has PR #659 open; the second deny line is a queued Action.
- Tools-central-planner: `2f55ae6a-00e1-46b6-9f89-e3d2d939e0de`. Tools PR #249 has not merged (it follows tools PRs #205 and #253); it sends a line when it does.
- Tools-builder-manager: `5074d20f-d5f6-4edf-b1b1-e18d5f31db19`. It sends the lock text for #620 after tools PR #242 merges. It asks Ben's go for tools #137 by button once the planner's refreshed brief is posted.
- personal-assistant: reads only, reports findings.
- After a clear: send the manager and the Tools planner the new id.

### Waiting on Ben

- Nothing of the planner's is in his queue.
- The planner's button, once its checks pass: the merge of PR #667. Coming later, with their briefs: the domain Action and the Docker and Supabase CLI steps for his PC.
- His go in the manager's chat for #633, #637, #604, #590.
- Power BI hold: #563 and #567 wait until Ben lifts it; #624 offseason.

### Rules Ben set today

- SQL that Ben pastes appears in full in the local queue entry and in Ben's chat (a fenced block with numbered steps), and never on GitHub or to other sessions.
- A secret ask names the value as the file's contents, never the `.env` line, and gives a byte-exact command with no placeholder.

### Reads and checks due

| When | What |
|---|---|
| 2026-11-28 | Publish the draft advisory if its fixes have not landed. |
| Before 2026-12-03 | The `02d` switch question to Ben, with the `minor_drift` data since 2026-11-15. |
| After 2026-12-03 | The #561 grill (the 2027-28 ledger's new events). Nothing switches between 2026-12-03 and 2027-01-07. |
| Before 2027-03-01 | Every rollover ticket on map #557 is live. |
| Before the 2027 trade deadline | The #560 grill (the 2028 ladder; Year-2 New Value is not in the data). |
| With Ben, no date | The #407 grill (point-in-time injury); the #412 grill (`review_*` tables). |
| No date | Tiers unset: #462, #463, #464, #491, #475 to #478, #506, #564. No milestone: #567, #568. |

**To confirm (no closing record found in the 2026-11-14 sweep; check the ticket first):** the Fantrax letter draft (#528 merged); #543's DROP and #521's schema half; #93 brief 5's dispatch; #454's C1 re-cite; the nflverse PFR spike and depth-chart tickets; the Materials-out-of-snapshot scoping and the `04s` recompute spike; #359 and #428 closes; the no-force-push ruleset on this repository.

## Reference

### What the planner answers for (owner, 2026-10-12)

The maps and their tickets, tiers, milestones and the Project; the role files' text; README, CONTRIBUTING and the repository's public face. The owner-queue mod is the Tools planner's since 2026-11-24 (Ben's button; tools #137 issuecomment-7132677793), replacing the lane ruling of 2026-11-09. Where the maps and `GOAL-RUN.md`'s stage table disagree, the maps win and the planner tells the manager.

### Maps

| Map | What | Status, 2026-11-14 |
|---|---|---|
| #69 | Supabase storage foundation (Stage C) | Cutover complete 2026-11-08; open tickets remain |
| #70 | In-season Fantrax flows (Stage D) | #130 closed; #93 keeps brief 5; #116, #412, #551 open |
| #66, #71 | Waiver signal; nflverse stats | Closed 2026-10-12 |
| #151 | Metadata and principles | Tickets closed; fog items unticketed |
| #162 | Session roles and plugin | Open |
| #375 | ETL flow, cadence, domains | The live working map (milestone 6) |
| #557 | Season rollover 2027 | #548, #554, #558, #559, #553, #566; grills #560, #561 |

### Milestones, Project, labels

Milestones: 1 Stage A: Ledger and cap; 2 Stage B: Seam; 3 Stage C: Postgres; 4 Stage D: Schedule; 5 Tooling and upkeep; 6 Domains and step registry. Project 2, "Dynasty FF: plan", adds tickets by itself and has no field of its own. Labels: `tier:low`, `tier:medium`, `tier:high`, `owner-led`, `backlog`, and the `wayfinder:*` set.

### Standing rulings stated to the planner (owner; the rule sources hold the rest)

- **State PRs:** one a day (2026-10-31), a fresh branch per batch (2026-11-14). Claude merges on Ben's word, head-pinned, with every check passing.
- **Never carry a prose Waiting-on-Ben list** (2026-11-14): each item is a queue entry or a pop-up as soon as it is ready, with the context to agree. An item blocked by something else says what blocks it.
- **A parked question stays parked** until Ben raises it.
- **A relayed button answer** is recorded on its ticket with the question, the exact words and the time.
- **A queue entry never carries an `Answer:` line**; a pane Note is never approval.
- **Closing a ticket is the manager's**; the two-key merge and the scoping session for a high ticket are in the rule sources.
- **Sources:** Reddit is human-only; KeepTradeCut, FantasyPros and PFF are rejected; `robots.txt` is read first; no amounts in public records; a takedown is answered in 72 hours; `fxpa` keeps running for 30 days from the letter's sending.

### Conventions

- The state worktree is the one on the current `docs/state-*` branch (`git worktree list`). Before reading and before every push: `git pull --rebase origin <branch>`. Commit with an explicit `git add` of this file; push with `git push origin HEAD:<branch>`; never force.
- A planner PR's worktree may need a `.venv` junction for the commit hooks; remove the junction before the worktree. A merged PR's local branch whose tip is behind the merged head (a second session pushed to it) is refused a delete by the hook. Leave it until tools #215's hook change lands; the closeout line is the Tools planner's to word (its advice: an object-only fetch of the PR's head, then the delete). In a planner PR's worktree, pull the branch before the merge whenever another session has pushed to it.
- Supabase is looked at only through the `supabase-dynasty` connector, read-only.
- To search for text that looks like a git command, use the search tool, not a shell grep: the git guardrail hook reads the pattern as the command.
- Push as a plain command of its own that names the branch, never a bare push inside a chained command: the guardrail hook then reads the main checkout's branch and refuses. The same hook refuses any shell command whose text holds a push line, so such text is written with the Edit or Write tool.
- Before ruling on an order of tickets, trace every blocker end to end. Before calling a ticket unblocked, read its acceptance, its merged PRs and its comments. A change asked for on a PR is checked on `main` after the merge. A rule is never cited for more than its text says.
- Before queuing a Decision for Ben, check whether an ADR already gives it to the planner, and rule what has no owner-visible stake. A question to Ben says first what an owner would see change (2026-11-23: the `locked_value` question cost him two rounds). On a safety or design question, make the broad second pass (likelihood by impact, best practice, the vendor's own guidance) before the first recommendation.
- Before removing a worktree: list junctions and links inside it and remove the link, never its target; then remove and confirm (#655). A planner PR's worktree uses a throwaway venv with a `.pth` file, never a junction.
- Time stamps come from `date -u`. Check the GitHub rate limit before a burst of calls; every session shares it.
- An issue body is edited as bytes, LF only, through a body file. A page drawn by JavaScript is read in the built-in browser. An Action for a GitHub login refresh says to run it in a real terminal.
- **Advisory detail never goes on a public ticket, a state file or a commit message** while the advisory is a draft: an unfixed gap, the command forms that use it, a trial of it. The detail goes into the draft advisory; the public record is a pointer. Before posting anything from #564's security side, ask: does this name something no rule refuses today?
- A Bash permission rule that ends in `:*` reads the colon as part of the wildcard, not as a colon (the Claude Code permission docs).
- Every push to the state branch queues a full set of checks twice (once for the push, once for the PR), and `storage-pg` takes 12 to 15 minutes. Three quick state pushes on 2026-11-15 backed the queue up for every open PR. Collect state edits and push once per seam.
- A message queued to a peer shortly before its clear can be lost. After a peer says it has cleared, check the record (the queue file, the ticket) for anything sent to its old session and send it again.
- The reset prompt is a file updated in place, and the chat gets a short pointer to it (Ben, 2026-11-15, standing; tools #217 issuecomment-6896189100). Where the file lives is open (Next, item 9); the `owner-queue` mod has no store for it yet (checked on the live clone, 2026-11-15). The committed form is below.
- The draft advisory's text is limited to 65,535 characters (62,515 on 2026-11-15) and both planners write to it. Read it again right before every save, check that the other planner's text is unchanged byte for byte, and keep a new section short.
- A check command written for Ben is run against the real files before it is sent. In PowerShell, a `$( )` inside a double-quoted string does not parse when a quoted value in it holds an unbalanced parenthesis: compute such a value into a variable first.
- In Git Bash, set `MSYS_NO_PATHCONV=1` before a `git show <ref>:<path>`, or the argument is rewritten into a Windows path.
- Dates: trade deadline 2026-11-16; re-sign deadline 2026-11-19, 23:59:59 Eastern; Close Days are Fridays; 2027-28 starts Mar 1.

### Resume prompt (the committed form; Ben's copy also names local files)

Act as the dff-central-planner of benjamininja/Python-PowerBI-DynastyFantasyFootball. Call the owner Ben or the owner and yourself Claude. Load the session-rules skill and follow the role file's read list. State: `.claude/memory/PLANNER.md` on branch `docs/state-2026-11-16` (its open state PR: `gh pr list --head docs/state-2026-11-16`); find its worktree with `git worktree list` and run `git pull --rebase origin docs/state-2026-11-16` before reading. Then read the owner's queue file in the main checkout and run `gh pr list --state open`. First send the manager and the Tools planner the new session id; the manager re-keys the planner's queue entries. Then act on the state file's Next list, in order. Advisory detail goes on no public ticket, state file or commit message.
