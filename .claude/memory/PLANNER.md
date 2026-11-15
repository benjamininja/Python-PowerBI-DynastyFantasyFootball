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

## Current

**Saved:** 2026-11-15 13:15Z, session df8ce212-d05c-4e0e-abee-55ee8a799b78
(36cf9567 was the one before, until its clear). State branch `docs/state-2026-11-16`; its state PR is the open PR of that branch (`gh pr list --head docs/state-2026-11-16`).

### Next (in order)

1. **PR #574's leftovers** (#562 is done and closed: merged as `ba99faa`, the sitting's record is #562 issuecomment-6894613437). Nothing is left of it locally: the junction, the worktree and both local branches are removed (Decided, below). Two candidates went to the Tools planner on 2026-11-15 and are its to place: tools #215 (the hook's branch-delete test, with a closeout line for `session-dispatch`) and the queue-format line from the sitting (an Action whose steps cross between Ben and a session stops at the hand-over, or puts the wait in the step of the command it gates).
1a. **PR #565 (#519): read the compare run's counts on #519 before it merges.** Read so far: 23 rostered multi-code rows and 6,611 of 6,611 player names holding a comma (#519 issuecomment-6894734502), so F1 and F2 are both blocking and with the builder. Still owed: the compare run (rows whose resolved position changes must be 0) and the two counts for the 8 ids missing from the capture. The manager does not run the script as written (it reads the environment file and may open the store); the planner's answer is a snapshot mode on the published parquet (#519 issuecomment-6894833074), or Ben's hand for this PR if the round cannot carry it.
1b. **#577 item 1** (a floor for a short `fact_minor_eligibility` capture): the planner's to rule, in a comment on #577, from the capture-by-capture row counts. Held out of #577's build (Tier: low, items 2 to 4, dispatch after PR #570 merges).
2. **The three later settings entries** (#564, draft advisory GHSA-27j5-qx96-v8w3). The first is checked and sent: the main checkout's local settings file is to be emptied (the check: #564 issuecomment-6886927491; the ready Action went to the manager 2026-11-15). That entry is in the queue, and its step 1 is met: the `git checkout` line is on `main` at `GOAL-RUN.md` line 110 since PR #576 merged as `29e38ab` (checked on `main`, 2026-11-15). Entries 2 and 3 (advisory items F and G, each checked or proven in a live trial) are in the queue with the corrected Ticket line (read in the queue file, 2026-11-15). Their detail is in the draft advisory under "Moved from public tickets, 2026-11-15" (sections A to C); the public pointer is #564 issuecomment-6887763275. When Ben ticks an entry, read the file against the entry's lines before recording it as done. Tools #213 (`Tier: medium`, set by the Tools planner) asks for one hook change; its detail is section D of the same heading. Its edit history holds four revisions, the two oldest with the first text (read by API, 2026-11-15); the reworded Action for Ben (remove both) is in the queue (the manager's word, and read in the queue file, 2026-11-15).
3. **The dynasty ruleset entry** for the manager's queue, when the Tools planner says the tools trial of tools #193 has passed. Ben did the hand part on 2026-11-15: the tools ruleset reads as specified by API (active, no bypass, all branches, only the no-force-push rule) and the throwaway branch is deleted; whether the refused force push's output reached the Tools planner is not known, and that session was not up. Still its word to give; timed right after a Daily Run's data PR merges (tools #193 issuecomment-6885586994).
4. **The state PR of `docs/state-2026-11-16`:** ask Ben by button at the day's last save. On his yes: merge head-pinned once every check passes on one read, cut a fresh branch from main, send the manager its name.
### Waiting

**On Ben, in the queue (re-keyed to df8ce212; the manager's word, 2026-11-15). Read against the files on 2026-11-15 13:15Z, after Ben ticked all three settings entries: entry 1 is done (the local allow list is empty) and entry 3 is done (the research profile's deny list is the entry's seven lines, exactly). **Entry 2 is half done: the research file holds the seven lines (51 denies), the builders' file does not (43, done is 50); Ben was given its step 3 again in chat.** The tools #213 entry is not done (all four revisions still in the history):**
- Start the owner crosswalk Excel on Drive for #548
- Hand over the 2026 FA keep choices for #548 (after 2026-11-19). Checked 2026-11-15: Ben's final curated FA workbook (version 6, dated 2026-11-14; Ben keeps it) has a sheet per conference, 75 and 86 rows, and no choice column yet, so this stays open. Its source export of 2026-11-12 is also #554's first load and the kept FAs' 2027 X values.
- Settings, later entry 1 of 3: empty the main checkout's local settings file (in the queue; the `git checkout` line it waited for is on `main`)
- Settings, later entries 2 of 3 and 3 of 3 (advisory items F and G): in the queue
- Remove the two oldest revisions of tools #213 from its edit history: in the queue, in the reworded form

**On Ben, his go or his word (not yet a queue entry; each becomes one when it is next in line):**
- #520: dispatch at Ben's go, not during periods 13 to 17.
- tools #137 (Bring to Chat): Ben's go; when it merges, send the Tools planner the plugin.json version; tools #142 follows. tools #111 (Ask planner, high): go and timing are Ben's.
- OLB and DE rows in `dim_position`: parked until Ben raises it, then a low ticket.
- Three sweep gaps, ticketed only on Ben's word: `CLAUDE.md`'s stale `_deliver_text` and `_deliver_embeds` names; map #69's Not-yet-specified list names done tickets; map #375's line on which board Contending reads.

**On something else:**
- #559 waits for #548's table, #554 and #558; #553 comes after #559 and before the first 2027-28 move, and since 2026-11-15 also carries the contract lists' Minor matcher (PR #570's F2). #566 waits for #561's grill.
- #567 waits for PR #563, and both wait for Ben to lift his hold on all Power BI work (by button in the manager's chat, 2026-11-15; pull/563#issuecomment-6886523623). #563 stays open at `44ce6ca`; its Desktop-check Decision is out of the queue.
- #522 and #523 wait for #473 briefs 2 to 4. #523 also needs another source for `is_rookie` before `04a` is retired (#523 issuecomment-6885227380).
- #524 stays open until the Fantrax match and `04v`'s retirement are met; #529 (backlog) follows it.
- #484 and #485 wait for #413 plus a Close Day run; #459 B9 sits behind #413.
- #398 and #399 are rewritten after #407's grill.
- tools #185 is built after tools #161's PR #197 merges, and after tools #202 is read.
- #473's later briefs: one batched allow-rule Action before brief 4; the CollegeFootballData key Action before the rookie brief; brief 12 after #485; brief 13 is unblocked (#480 is closed); brief 14's DraftSharks-list question at its dispatch, after the 2026 final week.

### Peers

- **Newest first, 2026-11-15 13:15Z:** the manager cleared and is on session d7ab8b3f-533b-4fb0-811f-e822752a1e02 (its word; b48f0cf3 was the one before; same app session). Ben typed `session-dispatch` in it, so it may merge and dispatch. It holds the planner's id df8ce212 and has re-keyed the planner's entries. It closed #562 and removed the ticked sitting entry. It keeps the three ticked Tools entries (tools #195, #193, #204) whole until the Tools planner has read them. It has read the planner's two weigh-ins (#570: pull/570#issuecomment-6894656644; #565: pull/565#issuecomment-6894664701). Its order: the re-proof of #571 at `292f15f`, the ruling on #570 F2, #569, then #565 back to its builder; it sends each merge commit as it lands. Since then (its word, about 13:10Z): PR #571 merged as `8c58e60`; #570's F2 is ruled closed on the planner's weigh-in and its builder brings `main` in (both PRs edit ADR-0019); #569 merges after #570; #565 is back with its builder. The Tools planner came up at about 13:05Z and was sent the planner's new id, the read of Ben's three ticked Tools entries with the #204 output (no token text), tools #215 and the two candidates. **Owed by it: its queue id, and its word on the tools #193 trial.**
- `dynastyFantasyFootball-central-builder-manager`, session b48f0cf3-5d6b-449b-aadd-f7d0ac81d267 since its clear of 2026-11-15 (its word; efe5ed14 was the one before), app session local_39e3ac7a-9d6d-4524-82e4-9b5f0e6db274. On 2026-11-15, later, it said it is preparing for another clear at Ben's word, so a newer id follows: ask for it. `session-dispatch` was loaded there (Ben typed it), so it could merge and dispatch again; it is asking Ben by button for #576's merge word and resumes the builders of #571 and #570 with the planner's weigh-ins. The sentences below about its pause and the unloaded skill describe the session before that clear. It writes the queue; send it ready entries. It holds the planner's id 36cf9567 and has re-keyed the planner's seven entries (its word, 2026-11-15). It was prepared for a clear and paused at Ben's word on 2026-11-15, so its queue id may change: it sends the new one. It merged and dispatched nothing in that session, because `session-dispatch` was not loaded (Ben types the slash command; a button does not load it). It holds the ask to keep the queue file out of every commit and push until #574 merges (its word). Its re-proofs: #570, #571 and #569 are not Green, each with blocking review findings back with its builder; #565's code review is not started. The planner's weigh-ins it asked for are posted: #571 B1 (pull/571#issuecomment-6888010424) and #570 C2 = F1 and F2 (pull/570#issuecomment-6888010804); none needs a Decision. It was sent two `GOAL-RUN.md` candidates from the Lessons sift (#162 issuecomment-6887656373, rows 8 and 9) for its next `GOAL-RUN.md` edit, and one small gap for a later docs PR of its own (the stage A notes in `GOAL-RUN.md` cite two plan files by a path on the owner's machine). It was told of #573's merge on 2026-11-15. It owes the planner: the compare counts on #519. It waits for the planner's weigh-in on PR #570's narrowed F2 before it rules on it.
- `Tools-central-planner`, queue id 57c20f52-66e7-4467-99d7-7d0768349609, app session local_9830794b-c1e9-400a-ba66-e6abb9432396 (its word, 2026-11-15); it holds the dynasty planner's new id 36cf9567 (its word, 2026-11-15). Ben's go for tools #213, by button in its chat: "Go, after #200 merges (Recommended)" (tools #213 issuecomment-6887956636). Ben asked it to prepare for a clear on 2026-11-15: its app session id stays, and a new queue id follows (its word). Its report of 2026-11-15: the tools-side copies of the advisory detail are in the draft advisory (sections E to H) and deleted from tools #200 and tools #213, on Ben's button answer there; pointers are tools #200 issuecomment-6887955810 and tools #213 issuecomment-6887956636; tools #213 is `Tier: medium`, `Profile: none`. The flagged `Answer:` line is settled: it joins `parking.md` at tools PR 184's next head, after tools PR 180 merges. Ben approved tools PR 210 at `0b5acdb` to merge on Green, by pane answer; tools #209's go is asked only after PR 210 merges and the line owed on tools #161 is posted. It was sent the seven `session-rules` candidates of the Lessons sift (#162 issuecomment-6887656373, rows 1 to 7) and tools #213 to tier. Its trial of tools #193 has not run; it sends word when it has. Its tools PR 210 (the reset-prompt text in `session-rules`) waits on Ben's read. The three candidates for the plugin's texts hold by its check and are with Ben by button; rulings land on tools #189. Owed to it: a line on tools #161 once `PLANNER.md` and `MANAGER.md` are both in the new shape (`PLANNER.md` is; `MANAGER.md` is the manager's), so tools #209 can retire `prepend_state.py`.
- After a clear: send both the new session id; the manager re-keys the planner's queue entries.

### Reads and checks due

| When | What |
|---|---|
| 2026-11-15, after the Daily Run | The interaction-limit trial on the dynasty repository ends 2026-11-15T22:23Z. The manager reads whether the pipeline's data PR opened and merged under it, then raises the six-month Action or reports a failure (#93 issuecomment-6885159414). |
| Before PR #565 merges | #519: read the compare script's counts (#519 issuecomment-6885211941). Not posted as of 2026-11-15 13:00Z: the manager's next session runs the compare, with the two extra counts and the comma count, and holds #565 until the planner has answered them (its word). After the F1 weigh-in the count of rows whose resolved position changes must be 0. |
| If the manager asks | PR #565 after its builder's answer: `apply_player_ids` overlays name and NFL team only, a test holds a `DL,LB` row unchanged, and F3 and F4 drop out (the weigh-in, pull/565#issuecomment-6894664701). PR #570: the follow-up ticket for advisories 1 to 4 needs a tier when the manager sends its number. |
| When PR #570's and PR #571's builders have answered | On 2026-11-15 the fresh auditor accepted #571's B1 and A1 to A5 (pull/571#issuecomment-6888382610; a re-proof at `292f15f` and the merge are the manager's) and #570's C1 to C7 (pull/570#issuecomment-6888386272; the reviewer's half was still running). |
| If the manager asks | Check the fixes on PR #570 (head `103ee13`) for C2 = F1 and F2 against the weigh-in (pull/570#issuecomment-6888010804), and on PR #571 (head `292f15f`) for B1 (pull/571#issuecomment-6888010424). #569 is at `e9cf33c`, with its re-check and re-proof owed by the manager. The rookie-draft and auction kinds are noted on #561 (issuecomment-6888013663). |
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

- **Ben, PR #574 and the #562 sitting** (by button in the planner's chat, 2026-11-15): "Merge #574 now (Recommended)". Merged as `ba99faa`, pinned to `9144fe5`, all eight checks passing on one read. Ben had run the sitting's delete and pull before the merge, so the pane had no file for about a quarter of an hour; the copy was whole and nothing was lost. Ben then ran the pull, the copy-back and the two checks. Record: #562 issuecomment-6894613437; the manager closed #562.
- **Ben's hand items, read on 2026-11-15:** tools #195 is done (the user-level plugin variable names the live clone's two folders; owner-queue there is 0.11.0). Tools #193: the ruleset is in place as specified and the throwaway branch is deleted. Tools #204: 8 of 9 read calls ran and passed, the Green read among them; step 8 was not run; no token is left at user level. All three are the Tools planner's to record.
- **Weighed in by the planner, 2026-11-15, no decision of Ben's needed:**
  - **PR #570, F2 as narrowed, goes to #553** (pull/570#issuecomment-6894656644). The matcher's one-season scope is the same assumption as `02d`'s carry; the right boundary is bylaws 12.5's whole season unrostered, which is #553's scope item 1, so the two change together. #553's body now holds scope item 5, three matcher tests, the two files and a done line.
  - **PR #565, F1 stands; `position_raw` keeps the league's codes** (pull/565#issuecomment-6894664701; #519 issuecomment-6894664979; #523 issuecomment-6894665278). Counted on the published snapshot: 2,478 crosswalk rows, all in the league's seven codes; 100 multi-code (83 `DL,LB`); 620 on a current roster, 23 of them multi-code. `getPlayerIds` carries the NFL position in 23 other codes, a different fact. The overlay takes name and NFL team only. #519's done condition is narrowed a second time; #523 gains the line that league eligibility needs another source before `04a` goes (first to test: `getLeagueInfo`'s `playerInfo.eligiblePos`). The `OLB` and `DE` question stays parked with Ben and is not answered by this.
- **Ben, PR #574's leftovers** (by button in the planner's chat, 2026-11-15): "Remove both (Recommended)". Removed: the `.venv` junction, the PR's worktree, the local branch `docs/state-2026-11-15`. The hook refused the delete of `docs/planner-562-untrack-queue`: its test is that the local tip equals a merged PR's head, and the tip was two commits behind it, because the manager had pushed to the branch from its own checkout. The call was not retried.
- **Ben, the mechanism for that** (by button, 2026-11-15, after asking for the cause): "Both, clear it now (Recommended)". Done: the branch was fast-forwarded from `refs/pull/574/head` by a plain refspec (git refuses that unless nothing is unmerged), then deleted; tools #215 is filed, `Tier: unset`, for the hook to accept an ancestor of a merged head, with the closeout line as a candidate.
- **Set by the planner, 2026-11-15:** #577 (the four advisories left by PR #570's review) is `Tier: low` for items 2 to 4; item 1 is held out for a planner ruling.
- **A correction to the settings check:** the main checkout's local settings file holds 146 allow rules (112 Bash, 34 PowerShell), not the 84 in the queue entry's Context; its only key is `permissions.allow`, and the entry's replacement is unchanged.

- **Ben, state PR #572:** "Merge when checks pass (Recommended)" (pull/572#issuecomment-6887438579). Merged 2026-11-15 as `49aece9`, all eight checks passing on one read, pinned to `6f2f312`. The fresh state branch is `docs/state-2026-11-16`.
- **Ben, the three plugin-text candidates** (by button in the Tools planner's chat, reported by it; record #564 issuecomment-6887450272): the flagged `Answer:` line joins `parking.md` in tools PR 184; the Status block gets no plugin change, so dynasty names its contents in `GOAL-RUN.md` (already in the text proposed to the manager, #564 issuecomment-6886761907, finding 1); the tier table leaves both role templates under tools #189. The manager was told on 2026-11-15.
- **Ben, the push-deny trial** (by button in the planner's chat, 2026-11-15): "Claude runs it in scratch (Recommended)", then "Both: trial and hook ticket (Recommended)". Each was a one-time word for one headless trial session in a throwaway repository; no later session start rests on them. The results are in the draft advisory (sections B and C of "Moved from public tickets, 2026-11-15"); tools #213 is filed.
- **Checked, no decision needed:** advisory item G, against the session transcripts (the advisory, section A).
- **A correction, and Ben's word on it** (by button in the planner's chat, 2026-11-15): the planner posted the detail of items F and G on public tickets before the fixes had landed, against *Advisory, then publish*; the Tools planner pointed it out. Ben: "Move to advisory, delete copies (Recommended)". Done: the text of three #564 comments and of tools #213's first body is in the draft advisory; the three comments are deleted; #564 issuecomment-6887763275 is the pointer; tools #213 is cut to a pointer. Left for Ben's hand, not yet a queue entry: tools #213's first text is still in its edit history and its title-change event. The first state commit of this session on this branch (`3d8ce27`) names the rule forms; it cannot leave the branch without a force push, which is a Never, and it goes when the state PR is squashed and the branch deleted.
- **Ben, in the Tools planner's chat** (its report, 2026-11-15; record tools #212): rows 1, 2, 3, 5 and 7 of the Lessons candidates are ticketed as tools #212, one planner PR after tools PRs 180, 210 and 184; rows 4 and 6 are left out.
- **Ben, in the manager's chat** (#564 issuecomment-6887908725): the manager writes the `GOAL-RUN.md` PR as proposed; nothing merges until Ben reads the diff.
- **Ben, PR #573** (by button in the planner's chat, 2026-11-15; record pull/573#issuecomment-6888293040): "Merge and clean up (Recommended)". Merged as `ed993cc`, pinned to `6d0f4fe`, all eight checks passing on one read, after PR #576 was on `main` at `29e38ab` (the manager merged it on Ben's button word, pull/576#issuecomment-6888087860). The worktree and the branch `docs/planner-role-files-cut` are removed. The role files on `main` are the short form; the planner's read list now ends with the queue file and the issue and PR lists.
- **Ben, the `session-dispatch` skill invoked in the planner's chat** (by button, 2026-11-15): "Meant for the manager (Recommended)". Nothing was done under it; the planner's merges stay on Ben's word per PR.
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
- A planner PR's worktree may need a `.venv` junction for the commit hooks; remove the junction before the worktree. Before deleting a merged PR's local branch, fast-forward it with `git fetch origin pull/<n>/head:<branch>` (a plain refspec): the hook passes only when the local tip is the merged head, and a second session may have pushed to the branch.
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
- The reset prompt goes to Ben in the chat, in one copy block: the `owner-queue` mod has no store for it yet (checked on the live clone, 2026-11-15). The committed form is below.
- In Git Bash, set `MSYS_NO_PATHCONV=1` before a `git show <ref>:<path>`, or the argument is rewritten into a Windows path.
- Dates: trade deadline 2026-11-16; re-sign deadline 2026-11-19, 23:59:59 Eastern; Close Days are Fridays; 2027-28 starts Mar 1.

### Resume prompt (the committed form; Ben's copy also names local files)

Act as the central-planner of benjamininja/Python-PowerBI-DynastyFantasyFootball. Call the owner Ben or the owner and yourself Claude. Load the session-rules skill and follow the role file's read list. State: `.claude/memory/PLANNER.md` on branch `docs/state-2026-11-16` (its open state PR: `gh pr list --head docs/state-2026-11-16`); find its worktree with `git worktree list` and run `git pull --rebase origin docs/state-2026-11-16` before reading. Act on its Next list, in order. First send the manager and the Tools planner the new session id.
