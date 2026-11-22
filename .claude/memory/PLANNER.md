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

**Saved:** 2026-11-22 (see the commit time), session 65cb1676-fc95-4abf-8174-422c03a5f64e, before a compact. One Current block (Ben's button, benjamininja/skills-plugins-hooks-agents#243). Stacked history: `995f0cf` on `docs/state-2026-11-16` (PR #575, `0916977`). State branch `docs/state-2026-11-22`; the manager opens its PR.

**Done today:** #629 (PR #638) and #630 (PR #636) merged. Data PRs land again (#640, #641, #645). #614's live proof is met: run 45068959547, `[ok] 01c`, all Chains published (issuecomment-7085725374). The cause was the secret's bytes: first the `.env` line, then the PowerShell pipe. A byte-exact `cmd` redirect fixed it. PR #632 merged (`c598e3e`), and Tools pruned root. The 2026 FA keep load is in: 109 rows in `app.contract_choices`, 30 keeps (#548). The planner fixed 14 Wilson team cells in Ben's workbook at Ben's word (issuecomment-7083799790; correction in issuecomment-7084469321).

### Next (in order)

1. **#548 brief 3** (b548-ownerxwalk, building). Planner rulings on its park are at issuecomment-7085556564: function 2 returns open, passed or none; the candidate bound is not built; the CI auth stub is allowed with four limits. Count 2 (PII digit-run rows) and the `pii_token_hashes` change stay parked with the manager. When its PR opens, send the manager the `GOAL-RUN.md` After-a-schema-change line and the supabase-auditor basis (ADR-0025 Consequences), plus the `supabase-auditor.md` line (a missing `needs:` on validate is no finding). Then write the after-deadline brief (Q6; `locked_value` on an app-origin row), then brief 4 (Discord sign-in and the page; it must land before the 2027 re-sign deadline and outside 2026-12-03 to 2027-01-07).
2. **PR #647** (#643, with Ben's manual sheets-key-check workflow): it merges on green at Ben's word. Then **#648** (low): `continue-on-error` on the key step, so a bad key holds only team_manifest (F1 traces to the planner's #643 brief), plus a BOM line.
3. **The manager's order:** #623 (b623-teamcount, building), #616 (its amend Decision first), #626, #597, #633, #637 (stale root and OneDrive text; can ride with #633), #639 (medium, a shared gsis remap for every `gsis_tables()` table; not urgent), #644 (low, reproof.py Temp leak). Read each PR when asked. Memory is near its limit, so propose no extra dispatch while three builders run.
4. **#592** (held): rewrite its Change with #545's move to `ops.choice_deadline`. Then ticket #545's deadline reader move to the table.
5. **#620** waits on tools PR #242's lock text (from Tools-builder-manager).
6. **#604 and #590** at Ben's go. At the day's last save, ask Ben by button whether to prune merged worktrees (planner-589, planner-claudemd).

### Peers (queue ids)

- dff-central-builder-manager: `1a0538b1-047b-4ba3-8967-ff325369e7ab` (`session-dispatch` loaded).
- Tools-central-planner: `019c4c0b-d63a-4262-9ee1-558f1408fd4f`.
- Tools-builder-manager: `55edaa09-855e-454f-991a-371eb4875402`.
- personal-assistant: reads only, reports findings.
- After a clear: send the manager and the Tools planner the new id.

### Waiting on Ben

- His go in the manager's chat for #633, #637, #648, #604, #590.
- The 49 leftover reproof Temp folders: his hand step (#644).
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
