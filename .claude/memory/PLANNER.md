# PLANNER — the planner's state

The planner (`.claude/agents/central-planner.md`) writes this file and no
other in `.claude/memory/`. It has two blocks. **Current** is rewritten at
every save and holds what a new planner session needs to act. **Reference**
changes slowly. Nothing is stacked: history is in git, and the daily state
PR's diff shows what moved and what was decided. The rules are in the
`session-rules` skill, `GOAL-RUN.md` and the role file; this file is state.

Shape approved by Ben on 2026-11-14 (tools #161 issuecomment-6886175657;
design issuecomment-6886003169). The stacked items this file held until then
are in git: the last commit with them is `53104a9` on the state branch.
Where the role file or an older prompt says START HERE, it means Current,
until the role-file PR (Next, item 2) changes the wording.

## Current

**Saved:** 2026-11-15 01:20Z, session 15250d47-4582-4cdc-b6c4-ea935b34c75e,
at a seam (two PRs opened). State branch `docs/state-2026-11-15`, state PR #572.

### Next (in order)

1. **PR #573** (the role-file cut: 142, 103 and 87 lines to 62, 64 and 53): open, checks to read. It merges only after the proposed `GOAL-RUN.md` text (#564 issuecomment-6886761907) is on `main`, which is the manager's PR; #573's pointers name that text's two headings, "State saves and who merges what" and "The planner's work". Then ask Ben by button, merge head-pinned, remove the `.venv` junction, the worktree and the branch `docs/planner-role-files-cut`. After the merge, drop the START HERE sentence from this file's head.
2. **PR #574** (#562, untrack the queue file): open. It merges only as step 3 of Ben's sitting, on his word in the planner's chat; the sitting's Action went to the manager on 2026-11-15. Before the sitting the manager owes two commits on the branch `docs/planner-562-untrack-queue` (`MEMORY.md` line 25, `RESUME.md` line 432). After the merge: remove the junction, the worktree and the branch; the manager closes #562 after the sitting's checks.
3. **The three later settings entries** (#564, draft advisory GHSA-27j5-qx96-v8w3). The first is checked and sent: the main checkout's local settings file is to be emptied (the check: #564 issuecomment-6886927491; the ready Action went to the manager 2026-11-15; it waits for one `git checkout` line in `GOAL-RUN.md`, because builders ran `git checkout` 50 times through that file alone). Confirm the entry is in the queue. Next the push denies, after a live trial of the `+` pattern, in the builders' and the research file in one edit; then the `research` profile's denies, after checking which profile the 7 `gh issue comment --repo` calls of 2026-11-07 ran under.
4. **The dynasty ruleset entry** for the manager's queue, when the Tools planner says the tools trial of tools #193 has passed; timed right after a Daily Run's data PR merges (tools #193 issuecomment-6885586994).
5. **Sift the old Lessons lists** (in `53104a9`'s copy of this file) for rules worth a place in a rule source; send candidates to the Tools planner or the manager. One candidate is already sent to the manager and owed to the Tools planner: an `Answer:` line the pane flags as not written by the pane is not the owner's (for `references/parking.md`).
6. **State PR #572:** ask Ben by button at the day's last save. On his yes: pause the manager's state pushes, merge head-pinned, cut a fresh branch from main, send the manager its name.

### Waiting

**On Ben, in the queue (keyed to 15250d47; the manager re-keyed them on 2026-11-15):**
- Start the owner crosswalk Excel on Drive for #548
- Hand over the 2026 FA keep choices for #548 (after 2026-11-19). Checked 2026-11-15: Ben's final curated FA workbook (version 6, dated 2026-11-14; Ben keeps it) has a sheet per conference, 75 and 86 rows, and no choice column yet, so this stays open. Its source export of 2026-11-12 is also #554's first load and the kept FAs' 2027 X values.
- Untrack the queue file: Ben's sitting for #562 (sent to the manager 2026-11-15; confirm it is in the queue)
- Settings, later entry 1 of 3: empty the main checkout's local settings file (sent to the manager 2026-11-15; confirm it is in the queue)
- Settings 1 of 5 to 5 of 5 are applied and their entries are to leave the queue (the manager was told; confirm).

**On Ben, his go or his word (not yet a queue entry; each becomes one when it is next in line):**
- #520: dispatch at Ben's go, not during periods 13 to 17.
- tools #137 (Bring to Chat): Ben's go; when it merges, send the Tools planner the plugin.json version; tools #142 follows. tools #111 (Ask planner, high): go and timing are Ben's.
- OLB and DE rows in `dim_position`: parked until Ben raises it, then a low ticket.
- Three sweep gaps, ticketed only on Ben's word: `CLAUDE.md`'s stale `_deliver_text` and `_deliver_embeds` names; map #69's Not-yet-specified list names done tickets; map #375's line on which board Contending reads.

**On something else:**
- #559 waits for #548's table, #554 and #558; #553 comes after #559 and before the first 2027-28 move. #566 waits for #561's grill.
- #567 waits for PR #563, and both wait for Ben to lift his hold on all Power BI work (by button in the manager's chat, 2026-11-15; pull/563#issuecomment-6886523623). #563 stays open at `44ce6ca`; its Desktop-check Decision is out of the queue.
- #522 and #523 wait for #473 briefs 2 to 4. #523 also needs another source for `is_rookie` before `04a` is retired (#523 issuecomment-6885227380).
- #524 stays open until the Fantrax match and `04v`'s retirement are met; #529 (backlog) follows it.
- #484 and #485 wait for #413 plus a Close Day run; #459 B9 sits behind #413.
- #398 and #399 are rewritten after #407's grill.
- tools #185 is built after tools #161's PR #197 merges, and after tools #202 is read.
- #473's later briefs: one batched allow-rule Action before brief 4; the CollegeFootballData key Action before the rookie brief; brief 12 after #485; brief 13 is unblocked (#480 is closed); brief 14's DraftSharks-list question at its dispatch, after the 2026 final week.

### Peers

- `dynastyFantasyFootball-central-builder-manager`, session 6d478b2d-32fa-4453-9c0d-ede04a08401d until its clear (still that id at 2026-11-15 00:30Z, paused for the clear at Ben's word); find it by name and take its new id from its first message. It writes the queue; send it ready entries. Five messages of 2026-11-15 wait in its inbox: the settings edits, #505 merged, PR #573 and the `GOAL-RUN.md` text, PR #574 and the sitting's entry, the `git checkout` line and the local-settings entry.
- `Tools-central-planner`, queue id b5e85b86-f217-4a16-94e3-bc154bfd9e2f (its word, 2026-11-15); it holds the dynasty planner's new id. Its trial of tools #193 has not run; it sends word when it has. Its tools PR 210 (the reset-prompt text in `session-rules`) waits on Ben's read. Owed to it: a line on tools #161 once `PLANNER.md` and `MANAGER.md` are both in the new shape (`PLANNER.md` is; `MANAGER.md` is the manager's), so tools #209 can retire `prepend_state.py`. It owns skills-plugins-hooks-agents except the owner-queue mod, which is the dynasty planner's.
- After a clear: send both the new session id; the manager re-keys the planner's queue entries.

### Reads and checks due

| When | What |
|---|---|
| 2026-11-15, after the Daily Run | The interaction-limit trial on the dynasty repository ends 2026-11-15T22:23Z. The manager reads whether the pipeline's data PR opened and merged under it, then raises the six-month Action or reports a failure (#93 issuecomment-6885159414). |
| Before PR #565 merges | #519: read the compare script's counts (#519 issuecomment-6885211941). |
| When #548's PR 2 is in review | Write the brief for the after-deadline publish step (Q6). |
| When #548's PR 3 opens | Send the manager the `GOAL-RUN.md` replacement line and the supabase-auditor's new basis as queue entries. The same edit adds the long-owed line to `supabase-auditor.md`: a missing `needs:` on validate is no finding. |
| When #548's deadline table is live | Ticket moving #545's deadline reader to it. |
| 2026-11-21 | #408 folds into #391's PR, or is dispatched alone if #391 has slipped. |
| 2026-11-28 | Publish the draft advisory if its fixes have not landed. Rule #548's Q4 again if #554 has not merged. |
| Before 2026-12-03 | The `02d` switch question to Ben, with about a week of `minor_drift` data from 2026-11-15. |
| After 2026-12-03 | The #561 grill (the 2027-28 ledger's new events). Nothing switches between 2026-12-03 and 2027-01-07. |
| After #93 brief 5 | Check #551's scoping briefs. |
| Before 2027-03-01 | #548's ADR (number 0025) lands; every rollover ticket on map #557 is live. |
| Before the 2027 trade deadline | The #560 grill (the 2028 ladder). Its list: whether a first-year `Tag` may be tagged again (bylaws 11.4.1); what follows `X`; the Year-2 "New Value" is not in the data; bylaws 12.2 names the trade deadline where 12.3 and the code use the re-sign deadline. |
| With Ben, no date | The #407 grill (point-in-time injury status); the #412 grill (`review_*` tables; also the fix for the `stintless_drop` label, #412 issuecomment-6883548655). |
| No date | Tiers unset: #462, #463, #464, #491, #475 to #478, #506, #564. No milestone: #567, #568. tools #188's 19 findings have no follow-up yet. #506 stays open for the next failure's text. #511 and #512 are backlog. |

**To confirm (the 2026-11-14 sweep found no closing record; check the ticket before acting):**
- The Fantrax letter: Claude drafts it for Ben once #517 merged (it has, as #528); private, kept in the private repository. No record that it was drafted.
- The first Weekly Final check, Fri 2026-11-20.
- #543's DROP was held until Ben runs `migrate.yml` by hand; #521's schema half at Ben's go. Not known to be queued.
- #93 brief 5 dispatches when #525 merges; #525 is closed, and no dispatch is recorded here.
- #454: the C1 re-cite brief, owed after the source run (the run is done).
- The nflverse PFR spike and the depth-chart ticket: asked of Ben, not filed until he answers.
- The Materials-out-of-snapshot scoping (high) and the `04s` recompute spike: listed to ticket, not among the filed tickets.
- #359 closes after one more agreeing `04v` pull. #428 closes when #429 settles.
- Owner-side leftovers: the DLF Action (in the queue); dotclaude PR #5, then `~/.claude` back on main; the pbiprune profile removal; #279 part 2.
- From 2026-10-12: a security review of tools PR 46, and a `Tier:`-line ticket under #162.

### Decided since the last merged state PR (#542, `a0885f4`)

- **Ben, tools #185's three questions:** "Ben sets a name (Recommended)", "Id written in the file (Recommended)", "The set name alone (Recommended)" (tools #185 issuecomment-6885472513).
- **Ben, on the queue pane:** "I don't see anything for tools app at all." Ticketed as tools #202 (medium), before tools #185.
- **Ben, the resume-prompt redesign:** "Approve, history to git (Recommended)" (tools #161 issuecomment-6886175657).
- **Ben, #505:** "Merge when checks pass (Recommended)" (pull/505#issuecomment-6886176133). Merged 2026-11-15 00:27Z as `c665d70`, all eight checks passing on one read; on Ben's "Approve both (Recommended)" the worktree and the local branch were removed (the remote branch was already gone). The worktree record `p490` is left half-removed in the main checkout's git folder; `git worktree prune --dry-run` lists it with five other stale records, and nothing was pruned.
- **Ben, the settings hand items:** asked which of six file-edit Actions Claude makes as a one-time exception to the Never line, Ben answered "Settings 1 to 5 plus tools rules". Applied and proved (#564 issuecomment-6886574638); the tools repository's builders' file got its two allow rules on the same word. The exception covers those entries only.
- **Ben, #562's two questions:** "Leave history (Recommended)" and "Nothing extra (Recommended)" (#562 issuecomment-6886869542).
- **Planner, PR #573's read lists:** the planner's and the manager's now end with the queue file and the open issue and PR lists (commit `e82611f`), to match tools PR 210, where Ben ruled by button in the Tools planner's chat that the read list stands in the role file, or in the project rules file where a role has no role file. `CLAUDE.md` is left out of the lists: it loads by itself.
- **Planner, the role files:** every line checked against the rule sources; a dozen rules stood only in a role file and are proposed as `GOAL-RUN.md` text, with two findings: the Status block a builder must print is defined only in `session-dispatch`, and `MANAGER.md` was not in the manager's read list (#564 issuecomment-6886761907).
- **Planner, Verify first:** done for the top five settings fixes (#564 issuecomment-6885943927; a Verification section on the draft advisory). The planner and the manager run in auto mode, where a classifier decides almost every call; the main checkout's local settings file reaches dynasty builders; the managers' two script rules never matched a call; a deny added to the builders' file must also go into the research file (`dispatch.ps1` line 193).
- **Planner, #570:** no plan breach; "0 new Review findings" reads as no new finding from any check that already exists on `main`; one wording fix wanted (pull/570#issuecomment-6885894132). The fix is read at `fa759db` and holds; the manager's re-proof is next.
- **Planner, the bylaws difference parked by the #558 builder:** #557 decisions 2 and 3 stand; ADR-0024 needs no amendment (#557 issuecomment-6885895208).
- **Planner, #566:** tier medium, on map #557, blocked by #561's grill.
- **Planner, #562's rehearsal:** the ticket's step 3 is wrong; the corrected sequence is copy aside, merge, delete and pull, copy back (#562 issuecomment-6886033417).
- **Planner, tools #193:** nothing in the dynasty repository rewrites a pushed branch (tools #193 issuecomment-6885586994).

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
- A planner PR's worktree may need a `.venv` junction for the commit hooks; remove the junction before the worktree.
- Supabase is looked at only through the `supabase-dynasty` connector, read-only.
- To search for text that looks like a git command, use the search tool, not a shell grep: the git guardrail hook reads the pattern as the command.
- Dates: trade deadline 2026-11-16; re-sign deadline 2026-11-19, 23:59:59 Eastern; Close Days are Fridays; 2027-28 starts Mar 1.

### Resume prompt (the committed form; Ben's copy also names local files)

Act as the central-planner of benjamininja/Python-PowerBI-DynastyFantasyFootball. Call the owner Ben or the owner and yourself Claude. Load the session-rules skill and follow the role file's read list. State: `.claude/memory/PLANNER.md` on branch `docs/state-2026-11-15` (PR #572); find its worktree with `git worktree list`. Act on its Next list.
