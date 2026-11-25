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

**Saved:** 2026-11-25 (see the commit time), session 9bcc0c9c-574c-4ebb-b4f4-18edc03af9aa. State branch `docs/state-2026-11-22` (PR #634; the manager opens its PR). This block holds open items only (#711, the start-up read budget of tools #261): a done item is on its ticket or PR, and the last commit that carried the done lists is `8ba13fe` on this branch.

### Next (in order)

0. **The owner's priority, 2026-11-25:** the checks were overdesigned; keep them simple. No new check-line list on any ticket; a schema ticket carries tests. The rule set is merged (PRs #694, #696, #703): CI is the test proof, the `checks` job runs the three scripts, one merge word. A PR opened before PR #696 has no `checks` job: ruling on PR #703 issuecomment-7165536667. No planner PR is open.
1. **Merge on Green.** The owner chose it with gate exceptions for the shared rules (tools #273 issuecomment-7165533423; review rounds issuecomment-7164630571). Read the shared-rule PR when the Tools planner sends its link. Until it merges, the merge-word rule stands. Then one question to the owner by button: which checks are required on `main` (`storage-pg` and `checks` are not required today).
2. **#700** (medium, the scheduled run loads the role table and the owner crosswalk): dispatched as b700-autoload. Its rules are merged: PR #698 (ADR-0026 decision 2) and PR #708 (ADR-0018 decision 12, the gate exempts the two functions by name). Read its PR when the manager asks.
3. **CI time (first in line, the owner's word 2026-11-25):** PR #709 (#699) merges first on the owner's word to the manager (planner reads: no breach at `bb05185`, PR #709 issuecomment-7167121220; 404 pg tests, 6m58s at the head before it), then #713 dispatches. Ruling on #697 issuecomment-7167121907: #697 and the app chain are not dispatched until PR #709 merges; the tools repository's stop (tools #187) holds nothing else here. Earlier: #581 (PR #704, one run per head, a text-only PR skips the heavy jobs) is the manager's; #699 (medium, the 17-minute pg tests) follows it. **#713** (low, `storage-pg` skips a PR that changes only `pbi/`, trade-bud, the bot or the docs site; filed on the owner's word 2026-11-25) dispatches after PR #709 merges, on the owner's go to the manager: same file. **#697** (medium, the `current_gsis` gap) has no go yet.
4. **Data PR #691** stays unmerged until a refresh runs with PR #693's fix (merged as `907cf3b`).
5. **The app chain,** on the owner's go to the manager: #670, then #675 before #663 (never side by side), then #682 (brief 4 of #548). Restate #663 to #665 and #676 against merged code before each dispatches. Carry into the restated #663: only grants keep the table owner from changing a history row; the owner write policies wrap `auth.uid()` as `(select auth.uid())` (#661 issuecomment-7137103517). #670's tests cover that every view in `app` has `security_invoker` on. #682's wording must not promise that only the last version of a choice is shown; its domain Action for the owner is written with it. The after-deadline copy brief (#548 issuecomment-7104493151) has no ticket: file it when it is next. Two scope calls in #675 are open for the owner to overturn (#675 issuecomment-7163128887). #682 and the copy land outside 2026-12-03 to 2027-01-07.
6. **#655:** 24 worktrees with a damaged record wait on the closeout script's first run (tools PR #252); the plan is issuecomment-7133100125; then the list goes to the owner by button. Tell the personal-assistant when the real run has happened (its prediction: issuecomment-7163874200).
7. **PR #653** (supabase-look): ready once tools #249 merges; then the owner's button.
8. **#658's map:** #673 waits on the owner and the partner signing; then a planner PR adds one sentence to the licence file. #676 after #675; #678 waits on #673; #677 to #681 backlog.
9. **Waiting, no date:** gap tickets #683 (low) and #687 (low, backlog) on the owner's go to the manager. #592 held (rewrite with #545's move to `ops.choice_deadline`). #620 waits on tools PR #242's lock text. #604 and #590 at the owner's go.
10. **#711:** the Current block, the reset prompt and the role file's read list are slimmed (PR #712 merged as `2ba4932`, 2026-11-25 15:17 UTC). Still owed: after the next clear, measure the start with the method on tools #258 and post the number on #711.
11. **The stored GitHub login is the narrowed token** (tools #204): a refused call that worked before is reported to the Tools planner, not retried.

### Peers (queue ids)

Ids as of 2026-11-25; find each by name. After a clear, send the manager and the Tools planner the new id.

- dff-central-builder-manager: `4ff97ebc-bfd4-4723-997c-406160d975ba`
- Tools-central-planner: `2c14b7ab-3b12-4984-ae56-5c6526f96566`
- Tools-builder-manager: `dabbbcd0-2b97-445e-a2d9-4502691fb617`
- personal-assistant: reads only, reports findings.

### Waiting on Ben

- Nothing of the planner's is in his queue.
- #673: the owner and the partner sign the private agreement; a line on #673 when it is signed.
- His go in the manager's chat for dispatches; his merge words are the manager's.
- Power BI hold: #563 and #567 wait until he lifts it; #624 offseason.

### Reads and checks due

| When | What |
|---|---|
| 2026-11-28 | Publish the draft advisory if its fixes have not landed. |
| Before 2026-12-03 | The `02d` switch question to the owner, with the `minor_drift` data since 2026-11-15. |
| After 2026-12-03 | The #561 grill (the 2027-28 ledger's new events). Nothing switches between 2026-12-03 and 2027-01-07. |
| Before 2027-03-01 | Every rollover ticket on map #557 is live. |
| Before the 2027 trade deadline | The #560 grill (the 2028 ladder; Year-2 New Value is not in the data). |
| With the owner, no date | The #407 grill (point-in-time injury); the #412 grill (`review_*` tables). |
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
