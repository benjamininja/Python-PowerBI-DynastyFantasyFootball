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

**Saved:** 2026-11-23 (see the commit time), session e0f49660-15b2-44b9-8430-e04f2e6b243b, before a clear. One Current block (Ben's button, benjamininja/skills-plugins-hooks-agents#243). Stacked history: `995f0cf` on `docs/state-2026-11-16` (PR #575, `0916977`). State branch `docs/state-2026-11-22`; the manager opens its PR.

**Done 2026-11-22/23:** #548 brief 3 merged (#646, `61aa044`); #647, #649 (#648) and #642 (#623) merged. Gap #650 (the crosswalk loader read the wrong headers) was ticketed low, and PR #652 merged it. The ADR-0025 text for `GOAL-RUN.md` After a schema change lands and for `supabase-auditor.md` was posted at #548 issuecomment-7088321713 and merged as PR #651 on Ben's buttons. Ben's sign-in check is done, with Confirm email on by his ruling (issuecomment-7102523231). The planner ruled that brief 4 adds Confirm email to ADR-0025's dashboard list and checks it against the docs (issuecomment-7102774835). Main is at `828db84`.

New tickets: #654 (owner-led grill: app roles, a site-admin impersonation role and season phases for regression walk-throughs, from Ben's pane Note; record issuecomment-7102641828); #655 (owner-led: about 53 GB of per-worktree `.venv`; the cause of closeout step 4 not removing worktrees is unknown, issuecomment-7102787917; the tools half is tools #250). Planner draft PR #653: `.claude/agents/supabase-look.md` from tools #247's template.

### Next (in order)

1. **Q6 `locked_value` Decision** (in Ben's queue; record #548 issuecomment-7102450894; the planner recommends (a), no column, join `fact_salary_price_list`). On his answer, write the after-deadline brief: an idempotent copy as `etl_writer`, no `changed_by`, its table on the data-PR allowlist.
2. **Offer Ben the #654 grill** before brief 4 is written. Then brief 4: Discord sign-in and the page, plus the Confirm email line. It must land before the 2027 re-sign deadline and outside 2026-12-03 to 2027-01-07.
3. **#655:** put Ben the `dispatch.json` light-venv choice (item 3) by button, with exact paste text. The manager prunes (item 1; Ben's word per builder). The cause of step 4 must be found first.
4. **PR #653** (supabase-look): mark it ready once tools #249 merges (after tools #205), then ask Ben by button to merge. The consultant line for `GOAL-RUN.md` and the builder-reach test are in Ben's queue; the reach result goes on tools #247.
5. **The manager's order:** the crosswalk load (Ben chose to run it; first on the next manager session's list), #616 (its amend Decision first), #626, #597, #633, #637, #639, #644. Read each PR when asked.
6. **#592** (held): rewrite with #545's move to `ops.choice_deadline`; then ticket #545's reader move.
7. **#620** waits on tools PR #242's lock text. **#604 and #590** at Ben's go. Ask Ben by button whether to prune the planner's merged worktrees (planner-589, planner-claudemd, and planner-supabase-look after #653).

### Peers (queue ids)

- dff-central-builder-manager: a new session after its 2026-11-23 clear (the last app id seen: `local_102f2ba0-b400-4be8-a986-c12c63f83f34`); it sends its new id. Find it by name.
- Tools-central-planner: `019c4c0b-d63a-4262-9ee1-558f1408fd4f`.
- Tools-builder-manager: `55edaa09-855e-454f-991a-371eb4875402`.
- personal-assistant: reads only, reports findings.
- After a clear: send the manager and the Tools planner the new id.

### Waiting on Ben

- In his queue: the Q6 `locked_value` Decision, the consultant-line Action, the builder-reach Decision.
- The planner's buttons: the #655 light-venv choice and the #654 grill offer.
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

The maps and their tickets, tiers, milestones and the Project; the role files' text; README, CONTRIBUTING and the repository's public face; the owner-queue mod, with the owner (lane ruling, 2026-11-09: the dynasty planner plans the mod, the Tools planner keeps the rest of that repository). Where the maps and `GOAL-RUN.md`'s stage table disagree, the maps win and the planner tells the manager.

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
