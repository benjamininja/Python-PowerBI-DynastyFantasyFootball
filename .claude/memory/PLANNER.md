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

**Saved:** 2026-11-15 02:35Z, session 36cf9567-9d3e-427f-989a-7cd9a9203003
(the session after the clear; c19bc37f was the one before). State branch `docs/state-2026-11-16`; its state PR is the open PR of that branch (`gh pr list --head docs/state-2026-11-16`).

### Next (in order)

1. **PR #573** (the role-file cut: 142, 103 and 87 lines to 62, 64 and 53): open, mergeable, head `6d0f4fe` since 2026-11-15 (one more commit: the manager's read-list line names "Stage notes" beside "Stages"); `storage-pg` was still running at the save, the other checks pass, so read all checks again before the ask. The manager's `GOAL-RUN.md` PR is #576 (head `a572d97`, on Ben's "Write it as proposed"; Ben reads the diff before any merge). The planner's read of #576 is done and posted (pull/576#issuecomment-6887975027): no difference from the proposed text, text 1 identical by `diff`, and every `GOAL-RUN.md` name #573 cites resolves; its one addition is the heading "Stage notes". The manager sends the merge commit when #576 is on `main`. #573 merges only after the proposed `GOAL-RUN.md` text (#564 issuecomment-6886761907) is on `main`, which is the manager's PR; #573's pointers name that text's two headings, "State saves and who merges what" and "The planner's work". Then ask Ben by button, merge head-pinned, remove the `.venv` junction, the worktree and the branch `docs/planner-role-files-cut`. After the merge, drop the START HERE sentence from this file's head.
2. **PR #574** (#562, untrack the queue file): open, mergeable, head `9144fe5`: the manager's two link commits are on it (`325df81`, `9144fe5`; pull/574#issuecomment-6887967865). `storage-pg` was still running at the save; read all checks before the merge. It merges only as step 3 of Ben's sitting, on his word in the planner's chat; the sitting's Action is in the queue. After the merge: remove the junction, the worktree and the branch; the manager closes #562 after the sitting's checks.
3. **The three later settings entries** (#564, draft advisory GHSA-27j5-qx96-v8w3). The first is checked and sent: the main checkout's local settings file is to be emptied (the check: #564 issuecomment-6886927491; the ready Action went to the manager 2026-11-15; it waits for one `git checkout` line in `GOAL-RUN.md`, because builders ran `git checkout` 50 times through that file alone). That entry is in the queue (the manager's word, 2026-11-15). Entries 2 and 3 (advisory items F and G, each checked or proven in a live trial) are in the queue with the corrected Ticket line (read in the queue file, 2026-11-15). Their detail is in the draft advisory under "Moved from public tickets, 2026-11-15" (sections A to C); the public pointer is #564 issuecomment-6887763275. When Ben ticks an entry, read the file against the entry's lines before recording it as done. Tools #213 (`Tier: medium`, set by the Tools planner) asks for one hook change; its detail is section D of the same heading. Its edit history holds four revisions, the two oldest with the first text (read by API, 2026-11-15); the reworded Action for Ben (remove both) went to the manager on 2026-11-15 and is not yet confirmed in the queue.
4. **The dynasty ruleset entry** for the manager's queue, when the Tools planner says the tools trial of tools #193 has passed; timed right after a Daily Run's data PR merges (tools #193 issuecomment-6885586994).
5. **The state PR of `docs/state-2026-11-16`:** ask Ben by button at the day's last save. On his yes: merge head-pinned once every check passes on one read, cut a fresh branch from main, send the manager its name. The old local branch `docs/state-2026-11-15` is merged (#572) and still exists locally: deleting it needs Ben's word.

### Waiting

**On Ben, in the queue (seven entries, re-keyed to 36cf9567; the manager's word, 2026-11-15):**
- Start the owner crosswalk Excel on Drive for #548
- Hand over the 2026 FA keep choices for #548 (after 2026-11-19). Checked 2026-11-15: Ben's final curated FA workbook (version 6, dated 2026-11-14; Ben keeps it) has a sheet per conference, 75 and 86 rows, and no choice column yet, so this stays open. Its source export of 2026-11-12 is also #554's first load and the kept FAs' 2027 X values.
- Untrack the queue file: Ben's sitting for #562 (the manager's word, 2026-11-15: it goes into the queue as written)
- Settings, later entry 1 of 3: empty the main checkout's local settings file (in the queue; it waits for the `git checkout` line in `GOAL-RUN.md`)
- Settings, later entries 2 of 3 and 3 of 3 (advisory items F and G): in the queue
- Remove the first text of tools #213 from its edit history: in the queue in its first wording (one revision); the reworded entry (two revisions) is with the manager

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

- `dynastyFantasyFootball-central-builder-manager`, session efe5ed14-3c04-4790-abf0-8442b111611a (its word, 2026-11-15), app session local_39e3ac7a-9d6d-4524-82e4-9b5f0e6db274. It writes the queue; send it ready entries. It holds the planner's id 36cf9567 and has re-keyed the planner's seven entries (its word, 2026-11-15). It was prepared for a clear and paused at Ben's word on 2026-11-15, so its queue id may change: it sends the new one. It merged and dispatched nothing in that session, because `session-dispatch` was not loaded (Ben types the slash command; a button does not load it). It holds the ask to keep the queue file out of every commit and push until #574 merges (its word). Its re-proofs: #570, #571 and #569 are not Green, each with blocking review findings back with its builder; #565's code review is not started. The planner's weigh-ins it asked for are posted: #571 B1 (pull/571#issuecomment-6888010424) and #570 C2 = F1 and F2 (pull/570#issuecomment-6888010804); none needs a Decision. It was sent two `GOAL-RUN.md` candidates from the Lessons sift (#162 issuecomment-6887656373, rows 8 and 9) for its next `GOAL-RUN.md` edit, and one small gap for a later docs PR of its own (the stage A notes in `GOAL-RUN.md` cite two plan files by a path on the owner's machine). It owes the planner: the merge commit of #576, the compare counts on #519, and word that the reworded tools #213 Action is in the queue.
- `Tools-central-planner`, queue id 57c20f52-66e7-4467-99d7-7d0768349609, app session local_9830794b-c1e9-400a-ba66-e6abb9432396 (its word, 2026-11-15); it was sent the dynasty planner's new id 36cf9567 on 2026-11-15 (queued, not yet confirmed). The flagged `Answer:` line is settled: it joins `parking.md` at tools PR 184's next head, after tools PR 180 merges. Ben approved tools PR 210 at `0b5acdb` to merge on Green, by pane answer; tools #209's go is asked only after PR 210 merges and the line owed on tools #161 is posted. It was sent the seven `session-rules` candidates of the Lessons sift (#162 issuecomment-6887656373, rows 1 to 7) and tools #213 to tier. Its trial of tools #193 has not run; it sends word when it has. Its tools PR 210 (the reset-prompt text in `session-rules`) waits on Ben's read. The three candidates for the plugin's texts hold by its check and are with Ben by button; rulings land on tools #189. Owed to it: a line on tools #161 once `PLANNER.md` and `MANAGER.md` are both in the new shape (`PLANNER.md` is; `MANAGER.md` is the manager's), so tools #209 can retire `prepend_state.py`.
- After a clear: send both the new session id; the manager re-keys the planner's queue entries.

### Reads and checks due

| When | What |
|---|---|
| 2026-11-15, after the Daily Run | The interaction-limit trial on the dynasty repository ends 2026-11-15T22:23Z. The manager reads whether the pipeline's data PR opened and merged under it, then raises the six-month Action or reports a failure (#93 issuecomment-6885159414). |
| Before PR #565 merges | #519: read the compare script's counts (#519 issuecomment-6885211941). Not posted as of 2026-11-15 02:35Z: the manager runs the compare at re-proof, with the two extra counts, and holds #565 until the planner has answered them (its word). |
| When PR #570's builder answers | Check the fixes for C2 = F1 and F2 against the weigh-in (pull/570#issuecomment-6888010804) if the manager asks. The rookie-draft and auction kinds are noted on #561 (issuecomment-6888013663). |
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
- **Ben, the push-deny trial** (by button in the planner's chat, 2026-11-15): "Claude runs it in scratch (Recommended)", then "Both: trial and hook ticket (Recommended)". Each was a one-time word for one headless trial session in a throwaway repository; no later session start rests on them. The results are in the draft advisory (sections B and C of "Moved from public tickets, 2026-11-15"); tools #213 is filed.
- **Checked, no decision needed:** advisory item G, against the session transcripts (the advisory, section A).
- **A correction, and Ben's word on it** (by button in the planner's chat, 2026-11-15): the planner posted the detail of items F and G on public tickets before the fixes had landed, against *Advisory, then publish*; the Tools planner pointed it out. Ben: "Move to advisory, delete copies (Recommended)". Done: the text of three #564 comments and of tools #213's first body is in the draft advisory; the three comments are deleted; #564 issuecomment-6887763275 is the pointer; tools #213 is cut to a pointer. Left for Ben's hand, not yet a queue entry: tools #213's first text is still in its edit history and its title-change event. The first state commit of this session on this branch (`3d8ce27`) names the rule forms; it cannot leave the branch without a force push, which is a Never, and it goes when the state PR is squashed and the branch deleted.
- **Ben, in the Tools planner's chat** (its report, 2026-11-15; record tools #212): rows 1, 2, 3, 5 and 7 of the Lessons candidates are ticketed as tools #212, one planner PR after tools PRs 180, 210 and 184; rows 4 and 6 are left out.
- **Ben, in the manager's chat** (#564 issuecomment-6887908725): the manager writes the `GOAL-RUN.md` PR as proposed; nothing merges until Ben reads the diff.
- **Ruled by the planner, 2026-11-15, no decision of Ben's needed:** #571 B1 (an overdue Minor is expected on `2nd`; the Minor row of ADR-0024 says both moments; the count follows #545's list) and #570 C2 = F1 and F2 (a drop and a claim match per copy inside one Conference; "acquired" is how the copy came onto a roster, and a trade carries the contract). Each rests on ADR-0019's amendment and on `02d` on `main`.
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
- **Advisory detail never goes on a public ticket, a state file or a commit message** while the advisory is a draft: an unfixed gap, the command forms that use it, a trial of it. The detail goes into the draft advisory; the public record is a pointer. Before posting anything from #564's security side, ask: does this name something no rule refuses today?
- A Bash permission rule that ends in `:*` reads the colon as part of the wildcard, not as a colon (the Claude Code permission docs).
- Dates: trade deadline 2026-11-16; re-sign deadline 2026-11-19, 23:59:59 Eastern; Close Days are Fridays; 2027-28 starts Mar 1.

### Resume prompt (the committed form; Ben's copy also names local files)

Act as the central-planner of benjamininja/Python-PowerBI-DynastyFantasyFootball. Call the owner Ben or the owner and yourself Claude. Load the session-rules skill and follow the role file's read list. State: `.claude/memory/PLANNER.md` on branch `docs/state-2026-11-16` (its open state PR: `gh pr list --head docs/state-2026-11-16`); find its worktree with `git worktree list` and run `git pull --rebase origin docs/state-2026-11-16` before reading. Act on its Next list, in order. First send the manager and the Tools planner the new session id.
