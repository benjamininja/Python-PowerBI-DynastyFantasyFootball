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
until the role-file PR (Next, item 1) changes the wording.

## Current

**Saved:** 2026-11-15 02:11Z, session c19bc37f-d5c9-4e25-af7e-36bff3f31a00
(it replaced 15250d47 at a clear). State branch `docs/state-2026-11-16`; its state PR is the open PR of that branch (`gh pr list --head docs/state-2026-11-16`).

### Next (in order)

1. **PR #573** (the role-file cut: 142, 103 and 87 lines to 62, 64 and 53): open, mergeable, all checks passing at `e82611f` (read 2026-11-15 01:50Z). The manager's `GOAL-RUN.md` PR is not open yet; it asks Ben by button and sends the number. It merges only after the proposed `GOAL-RUN.md` text (#564 issuecomment-6886761907) is on `main`, which is the manager's PR; #573's pointers name that text's two headings, "State saves and who merges what" and "The planner's work". Then ask Ben by button, merge head-pinned, remove the `.venv` junction, the worktree and the branch `docs/planner-role-files-cut`. After the merge, drop the START HERE sentence from this file's head.
2. **PR #574** (#562, untrack the queue file): open, mergeable, all checks passing at `72ac8d8`. It merges only as step 3 of Ben's sitting, on his word in the planner's chat; the sitting's Action went to the manager on 2026-11-15. Before the sitting the manager owes two commits on the branch `docs/planner-562-untrack-queue` (`MEMORY.md` line 25, `RESUME.md` line 432). After the merge: remove the junction, the worktree and the branch; the manager closes #562 after the sitting's checks.
3. **The three later settings entries** (#564, draft advisory GHSA-27j5-qx96-v8w3). The first is checked and sent: the main checkout's local settings file is to be emptied (the check: #564 issuecomment-6886927491; the ready Action went to the manager 2026-11-15; it waits for one `git checkout` line in `GOAL-RUN.md`, because builders ran `git checkout` 50 times through that file alone). That entry is in the queue (the manager's word, 2026-11-15). Entry 2 (seven push denies, each proven in a live trial: #564 issuecomment-6887662942 and issuecomment-6887760014) and entry 3 (five denies for the `research` profile: #564 issuecomment-6887572642) went to the manager as ready Actions on 2026-11-15: confirm both are in the queue. When Ben ticks an entry, read the file against the entry's lines before recording it as done. The empty-source refspec also has a hook ticket, tools #213 (`Tier: unset`, the Tools planner's).
4. **The dynasty ruleset entry** for the manager's queue, when the Tools planner says the tools trial of tools #193 has passed; timed right after a Daily Run's data PR merges (tools #193 issuecomment-6885586994).
5. **The state PR of `docs/state-2026-11-16`:** ask Ben by button at the day's last save. On his yes: merge head-pinned once every check passes on one read, cut a fresh branch from main, send the manager its name. The old local branch `docs/state-2026-11-15` is merged (#572) and still exists locally: deleting it needs Ben's word.

### Waiting

**On Ben, in the queue (keyed to c19bc37f; the manager's word, 2026-11-15):**
- Start the owner crosswalk Excel on Drive for #548
- Hand over the 2026 FA keep choices for #548 (after 2026-11-19). Checked 2026-11-15: Ben's final curated FA workbook (version 6, dated 2026-11-14; Ben keeps it) has a sheet per conference, 75 and 86 rows, and no choice column yet, so this stays open. Its source export of 2026-11-12 is also #554's first load and the kept FAs' 2027 X values.
- Untrack the queue file: Ben's sitting for #562 (the manager's word, 2026-11-15: it goes into the queue as written)
- Settings, later entry 1 of 3: empty the main checkout's local settings file (in the queue; it waits for the `git checkout` line in `GOAL-RUN.md`)
- Settings, later entry 2 of 3 (seven push denies) and entry 3 of 3 (the `research` profile's five denies): sent to the manager 2026-11-15, not yet confirmed in the queue

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

- `dynastyFantasyFootball-central-builder-manager`, session efe5ed14-3c04-4790-abf0-8442b111611a (its word, 2026-11-15), app session local_39e3ac7a-9d6d-4524-82e4-9b5f0e6db274. It writes the queue; send it ready entries. It holds the planner's id c19bc37f. It is re-proving #570, then #569, #571 and #565, one at a time. It was sent two `GOAL-RUN.md` candidates from the Lessons sift (#162 issuecomment-6887656373, rows 8 and 9), which do not hold its owed PR. It owes, each after asking Ben by button: the `GOAL-RUN.md` PR (#564 issuecomment-6886761907, plus the `git checkout` line of issuecomment-6886927491), and two link commits on `docs/planner-562-untrack-queue`; it sends the PR number. It was sent the fresh state branch's name, `docs/state-2026-11-16`, on 2026-11-15.
- `Tools-central-planner`, queue id 57c20f52-66e7-4467-99d7-7d0768349609, app session local_9830794b-c1e9-400a-ba66-e6abb9432396 (its word, 2026-11-15); it holds the dynasty planner's id c19bc37f (its word, 2026-11-15). The flagged `Answer:` line is settled: it joins `parking.md` at tools PR 184's next head, after tools PR 180 merges. Ben approved tools PR 210 at `0b5acdb` to merge on Green, by pane answer; tools #209's go is asked only after PR 210 merges and the line owed on tools #161 is posted. It was sent the seven `session-rules` candidates of the Lessons sift (#162 issuecomment-6887656373, rows 1 to 7) and tools #213 to tier. Its trial of tools #193 has not run; it sends word when it has. Its tools PR 210 (the reset-prompt text in `session-rules`) waits on Ben's read. The three candidates for the plugin's texts hold by its check and are with Ben by button; rulings land on tools #189. Owed to it: a line on tools #161 once `PLANNER.md` and `MANAGER.md` are both in the new shape (`PLANNER.md` is; `MANAGER.md` is the manager's), so tools #209 can retire `prepend_state.py`.
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

### Decided since the last merged state PR (#572, `49aece9`)

- **Ben, state PR #572:** "Merge when checks pass (Recommended)" (pull/572#issuecomment-6887438579). Merged 2026-11-15 as `49aece9`, all eight checks passing on one read, pinned to `6f2f312`. The fresh state branch is `docs/state-2026-11-16`.
- **Ben, the three plugin-text candidates** (by button in the Tools planner's chat, reported by it; record #564 issuecomment-6887450272): the flagged `Answer:` line joins `parking.md` in tools PR 184; the Status block gets no plugin change, so dynasty names its contents in `GOAL-RUN.md` (already in the text proposed to the manager, #564 issuecomment-6886761907, finding 1); the tier table leaves both role templates under tools #189. The manager was told on 2026-11-15.
- **Ben, the push-deny trial** (by button in the planner's chat, 2026-11-15): "Claude runs it in scratch (Recommended)", then "Both: trial and hook ticket (Recommended)". Each was a one-time word for one headless trial session in a throwaway repository; no later session start rests on them. Result: seven denies proven, `Bash(git push* :*)` does not match and `Bash(git push* :**)` does (#564 issuecomment-6887662942, issuecomment-6887760014); tools #213 filed.
- **Checked, no decision needed:** the 7 `gh issue comment --repo` calls of 2026-11-07 were three tools builders with no profile; the one `research` dispatch ever run used no form the proposed denies refuse (#564 issuecomment-6887572642).
- **The old Lessons lists are sifted** (#162 issuecomment-6887656373): 53 lessons, 19 already in a rule source, 14 candidate rows. Rows 1 to 7 went to the Tools planner and 8 and 9 to the manager, as candidates; rows 10 to 14 are in Conventions below.
- Everything decided on 2026-11-14 and 2026-11-15 before that merge is in #572's diff and on its tickets: #505 (pull/505), the settings edits and the local settings check (#564), the role-file check and PR #573 (#564), #562's two answers and PR #574 (#562).

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
- Push as a plain command of its own that names the branch, never a bare push inside a chained command: the guardrail hook then reads the main checkout's branch and refuses. The same hook refuses any shell command whose text holds a push line, so such text is written with the Edit or Write tool.
- Before ruling on an order of tickets, trace every blocker end to end. Before calling a ticket unblocked, read its acceptance, its merged PRs and its comments. A change asked for on a PR is checked on `main` after the merge. A rule is never cited for more than its text says.
- Time stamps come from `date -u`. Check the GitHub rate limit before a burst of calls; every session shares it.
- An issue body is edited as bytes, LF only, through a body file. A page drawn by JavaScript is read in the built-in browser. An Action for a GitHub login refresh says to run it in a real terminal.
- A Bash permission rule that ends in `:*` reads the colon as part of the wildcard, not as a colon; `:**` keeps the colon (#564 issuecomment-6887760014).
- Dates: trade deadline 2026-11-16; re-sign deadline 2026-11-19, 23:59:59 Eastern; Close Days are Fridays; 2027-28 starts Mar 1.

### Resume prompt (the committed form; Ben's copy also names local files)

Act as the central-planner of benjamininja/Python-PowerBI-DynastyFantasyFootball. Call the owner Ben or the owner and yourself Claude. Load the session-rules skill and follow the role file's read list. State: `.claude/memory/PLANNER.md` on branch `docs/state-2026-11-16` (its open state PR: `gh pr list --head docs/state-2026-11-16`); find its worktree with `git worktree list` and run `git pull --rebase origin docs/state-2026-11-16` before reading. Act on its Next list, in order. First send the manager and the Tools planner the new session id.
