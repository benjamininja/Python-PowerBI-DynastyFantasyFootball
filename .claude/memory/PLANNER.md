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

**Saved:** 2026-11-15 14:15Z, session 6116cb2f-15c9-406a-aa61-05abfe1c941a, before a clear at Ben's word (df8ce212 was the one before). State branch `docs/state-2026-11-16`; its state PR is the open PR of that branch (`gh pr list --head docs/state-2026-11-16`).

### Next (in order)

0. **First: the planner's read of PR #579 (Closes #577, head `0013a49` when asked), which the manager asked for at about 14:15Z, on one point. Post the read on the PR.** Item 3 of #577 asked that the step's `needs` name every table it reads, and its builder did that: step `02k_contract_moves` in `scripts/run_pipeline.py` now needs `02e_derive`, `04v_minor_contracts`, `02d_ledger`, `01e_dim_nfl_players` and `02j_minor_eligibility`. So a failed `02j` or `01e` now skips `02k` for that run, where the step's comment from PR #570 said an nflverse failure does not hold this Chain (`02k` reads `01e`'s names and `02j`'s games as reference columns). The manager's question: no breach as built, or should `02k` keep running on stale reference columns, with `needs` limited to the Fantrax inputs and the other reads documented? To read first: the PR's diff and body, #577's item 3 and its done line (the planner wrote that done line), the step's comment on `main`, ADR-0008's amendment (decisions 2 and 3, the Chain as the publish unit) and how `run_pipeline.py` treats a `needs` across Chains. The code review is posted (pull/579#issuecomment-6895831988): no blocking finding, two advisories. Its F1 sharpens the question: `run_steps` skips `02k` on a failed `01e` or `02j`, and `plan_publish` counts a skipped step against its own Chain, so an nflverse failure would fail `fantrax_core` and withhold every table of that Chain for the run, not only `fact_contract_move`. F2: the header of `notebooks/02k_fact_contract_move.py` still says an nflverse failure does not hold this Chain. The builder is not asked to answer until the planner's read is on the PR; the ruling on item 3 (keep the five needs, or cut `01e` and `02j` back out and document the two reads) is the planner's.
1. **The advisory's section I: two settings Actions are in the queue for Ben's hands** (#564 issuecomment-6895276896 and issuecomment-6895520198; the detail is only in the draft advisory GHSA-27j5-qx96-v8w3, sections I5 and I7, and goes on no public record, state file or commit message). Done on 2026-11-15: the count from the session transcripts, the first Action, a second live trial on Ben's one-time word, and a second Action from what it proved. Both are in the queue with the correction to the first (the manager's word, about 14:20Z). **Next step: when Ben marks each done,** read the file against the entry's lines and its check output, and record it on #564. The first entry follows later entry 2 of 3; the second follows the first. The Tools planner has both results; the tools side is the advisory's section I6 and its Action is the Tools planner's.
2. **Settings later entry 2 of 3 is half done.** The research file holds the seven lines (51 denies); the builders' file does not (43 at 2026-11-15 13:55Z; done is 50). Ben has its step 3 in the queue entry, and the manager keeps the entry until its own check prints builders 50, research 51, missing 0. When it does, read the file against the entry's lines and record it on #564. Entries 1 and 3 are done and recorded (#564 issuecomment-6894855445).
3. **PR #565 (#519): read the compare run's counts on #519 before it merges.** Read so far: 23 rostered multi-code rows and 6,611 of 6,611 player names holding a comma (#519 issuecomment-6894734502), so F1 and F2 were both blocking; the builder answered and the fresh re-check accepted all seven findings (pull/565#issuecomment-6894958005). The compare run is Ben's Action in the queue (four commands, counts only), not run as of 14:00Z; its counts go on #519. Still to read there: rows whose resolved position changes (must be 0), the two counts for the 8 ids missing from the capture, and `name_kept`. Ruled 2026-11-15: the 55 suffix names stay as they are in this PR, and #523 holds the rule owed before `04a` goes (#519 issuecomment-6895009760). The manager's re-proof of #565 runs on `c278305`. **Open for the planner:** whether the compare script's snapshot mode is worth a follow-up ticket, since `04z` reads two tables that are not in the published snapshot; decide when the run's counts are in.
4. **#577 is built as PR #579, dispatched on Ben's button word (#577 issuecomment-6895431560; the read owed is item 0); #578 waits for Ben's dispatch word in the manager's chat.** #578 (`Tier: low`, `Profile: none`) is the follow-up of the ruling on #577 item 1; #577 items 2 to 4 are `Tier: low`. Neither touches the other's files. Nothing is owed by the planner until a PR read is asked.
5. **The dynasty ruleset: in the queue, waits on Ben and on the day's data PR** (tools #193 issuecomment-6894885083). It asks no test push on dynasty. **When Ben marks it done: read the ruleset back by API** (`gh api repos/<owner>/<repo>/rulesets`, then the one by id) and compare it with the tools repository's: active, no bypass actor, include `~ALL`, one rule `non_fast_forward`. The manager reads the next Daily Run's data PR.
6. **The state PR of `docs/state-2026-11-16`:** ask Ben by button at the day's last save. On his yes: merge head-pinned once every check passes on one read, cut a fresh branch from main, send the manager its name.
7. **Two findings from the personal-assistant session, to check and ticket if real** (its report of 2026-11-15, about 14:15Z; not urgent; a report, not Ben's approval of a fix). (a) 84 of 89 worktree folders hold their own copy of the queue file, left from before PR #574 untracked it; the pane reads only the main checkout's file, but a search for the file's name finds the copies. To settle: whether anything removes them before each worktree is deleted. (b) `.claude/memory/MEMORY.md` does not list `PLANNER.md`, though `CLAUDE.md`'s memory layout does; `MEMORY.md` is not the planner's file, so a fix is a ticket. Its two process questions were answered at 14:15Z. Its wider report is tools #217, filed by the Tools planner for both planners; its section C names dynasty's role files as customised copies of the templates.
8. **Two owner-queue mod changes Ben asked for, which the dynasty planner plans** (Ben's ruling by button in the Tools planner's chat, as it reported at about 14:30Z: "Dynasty planner (Recommended)"; find the quote in the record before acting on it). The records, each with Ben's words and a reading of tools PR #197's branch at `b7ef918`: a tab per project at the top of the pane (tools #185 issuecomment-6895986248); a Sessions tab for session health, the clear instruction at 245,000 tokens in place of 255,000, and a stored prompt dropped once its session has reset (tools #161 issuecomment-6895988934, which also holds Ben's two other button answers and a proposed split). **Next step: read both comments, then tier the split:** the 245,000 constant right after tools PR #197 merges; the Sessions tab; the project tabs after tools #185's own build. One writer at a time on `register.tsx`. The rule text stays the Tools planner's: one `session-rules` PR after tools PR #210 merges, before the mod's constant changes.

### Waiting

**On Ben, in the queue (the planner's entries are keyed to 6116cb2f; read in the queue file 2026-11-15 14:12Z):**
- The two settings Actions of the advisory's section I (Next, item 1)
- Settings, later entry 2 of 3: its step 3, the builders' file (Next, item 2)
- Add the no-force-push ruleset to the dynasty repository, after the day's data PR has merged
- Run the compare for PR #565 on the saved capture (the manager's entry)
- Remove the two oldest revisions of tools #213 from its edit history: not done (all four revisions were still in the history at 13:00Z)
- Start the owner crosswalk Excel on Drive for #548
- Hand over the 2026 FA keep choices for #548 (after 2026-11-19). Checked 2026-11-15: Ben's final curated FA workbook (version 6, dated 2026-11-14; Ben keeps it) has a sheet per conference, 75 and 86 rows, and no choice column yet, so this stays open. Its source export of 2026-11-12 is also #554's first load and the kept FAs' 2027 X values.
- The three ticked Tools entries (tools #195, #193, #204) are the Tools planner's; the manager keeps them until it has read them.

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

- `dynastyFantasyFootball-central-builder-manager`: session 0f450e2b-06cb-4be5-834d-e80757dbdf8d since its clear of 2026-11-15, about 13:40Z (its word; d7ab8b3f is closed), app session local_39e3ac7a-9d6d-4524-82e4-9b5f0e6db274. It holds the planner's id 6116cb2f and has re-keyed the planner's five entries (its word). It writes the queue; send it ready entries. `session-dispatch` is loaded there only when Ben types it. Its reports of 2026-11-15: PR #570 merged as `c278305` (pinned to `3275c56`, 13:52Z); its builder brings `main` into #569 and regenerates its migration; the #565 re-proof runs on `c278305`; #577 is dispatched only on Ben's word; the schema check for #570 and #569 runs once after #569 lands (the planner agreed, with #570's alone if #569 does not land the same day). Its report of about 14:15Z: the #565 re-proof is GREEN on `c278305` (pull/565#issuecomment-6895488032) and still waits on Ben's compare run; `migrate`'s push job for `c278305` failed at the held `pff_id` drop (#515; record #545 issuecomment-6895496917), Ben chose by button to run `migrate` by hand, the Action is in the queue, and the schema check for #570 follows his run. It owes the planner: the compare counts on #519 after Ben's run, and #569's merge commit. It has the draft advisory's size limit and the Tools planner's new queue id. At about 14:20Z it said Ben has asked it to prepare for a clear, so its queue id changes again and its new session sends it. The planner is clearing at Ben's word: the next planner session sends both peers its new id. Still with it from earlier: two `GOAL-RUN.md` candidates from the Lessons sift (#162 issuecomment-6887656373, rows 8 and 9), and a small docs gap (the stage A notes in `GOAL-RUN.md` cite two plan files by a path on the owner's machine).
- `Tools-central-planner`: queue id bae0af50-ba4f-42e1-9ae2-e271f84ce2a1 since its clear of 2026-11-15 (its word; 209a059f was the one before), app session local_9830794b-c1e9-400a-ba66-e6abb9432396. It was sent the dynasty planner's id 6116cb2f at 13:40Z. From Ben's answers in its chat, as it reported on 2026-11-15: tools #215 goes after tools #213 merges (tools #215 issuecomment-6894950231), `Tier: medium`, `Profile: none`; the queue-format line is row 8 of tools #212 (issuecomment-6894952102); the flagged `Answer:` line joins `parking.md` at tools PR 184's next head; tools #213 has Ben's go after tools #200 merges (tools #213 issuecomment-6887956636). At about 14:30Z it said it is at a clear on Ben's word, so its queue id changes again and its next session sends the new one. It wrote the advisory's section I6 (the tools side) and holds Ben's button answer for its own tools-side Action. Owed to it: a line on tools #161 once `PLANNER.md` and `MANAGER.md` are both in the new shape (`PLANNER.md` is; `MANAGER.md` is the manager's), so tools #209 can retire `prepend_state.py`.
- `personal-assistant`, app session local_a8a11097-9b58-4198-82a6-7c1355a4f11d: a cross-project role Ben set up on 2026-11-15 (its word). It reads only, writes nothing in a repository, messages the two planners only, sweeps only on Ben's word, and sends findings to the owning planner to ticket. Its role file is being drafted for the Tools planner's review. It was told where the planner's live state is and the form a finding should take (one batched report per sweep, each item shaped like a gap ticket).
- After a clear: send the manager and the Tools planner the new session id; the manager re-keys the planner's queue entries.

### Reads and checks due

| When | What |
|---|---|
| 2026-11-15, after the Daily Run | The interaction-limit trial on the dynasty repository ends 2026-11-15T22:23Z. The manager reads whether the pipeline's data PR opened and merged under it, then raises the six-month Action or reports a failure (#93 issuecomment-6885159414). |
| Before PR #565 merges | #519: read the compare script's counts (#519 issuecomment-6885211941). Not posted as of 2026-11-15 14:00Z: the run is Ben's Action in the queue, with the two extra counts and the comma count, and the manager holds #565 until the planner has answered them (its word). After the F1 weigh-in the count of rows whose resolved position changes must be 0. |
| If the manager asks | PR #565 after its builder's answer: `apply_player_ids` overlays name and NFL team only, a test holds a `DL,LB` row unchanged, and F3 and F4 drop out (the weigh-in, pull/565#issuecomment-6894664701). PR #569 after `main` is merged in: its re-check and re-proof are the manager's. A PR for #577 or #578 against its ticket's done condition. The rookie-draft and auction kinds are noted on #561 (issuecomment-6888013663). |
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

- **Ben, the second trial for the advisory's section I** (by button in the planner's chat, 2026-11-15): "Full trial in scratch (Recommended)". A one-time word for one headless trial session in a throwaway repository; no later session start rests on it. The question, the method and the results are in the draft advisory, section I7; the public pointer is #564 issuecomment-6895520198.
- **Checked and sent by the planner, 2026-11-15:** the count owed for the advisory's section I (section I5; pointer #564 issuecomment-6895276896), and two settings Actions as ready entries to the manager, the second after the trial.
- **Ruled by the planner, 2026-11-15, no decision of Ben's needed: #577 item 1** (#577 issuecomment-6895340770). A floor is wanted, at the pull and not in `02k`: `04v` compares each filter's pages fetched and rows parsed with the server's own totals and raises before the write. No percent floor: the table has four captures (5,513; 3,180; 3,171; 3,171) and the one large change is real. It rests on ADR-0008's amendment (decisions 2, 3 and 6) and on `04a`'s short-pull stop. The follow-up is #578, `Tier: low`, `Profile: none`, milestone Stage D.
- **Merged by the manager, 2026-11-15:** PR #570 as `c278305`, pinned to `3275c56`.
- **Ben, the trial for the advisory's section I** (by button in the planner's chat, 2026-11-15): "Full trial in scratch (Recommended)". A one-time word for one headless trial session in a throwaway repository; no later session start rests on it. The question, the method and the results are in the draft advisory, section I4; the public pointer is #564 issuecomment-6894992883.
- **Sent by the planner, 2026-11-15:** the dynasty ruleset Action, as a ready entry to the manager, after the Tools planner's word that the tools #193 trial passed (tools #193 issuecomment-6894885083). The closeout tip the planner gave on tools #215 is withdrawn as rule text, on the Tools planner's advice.

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
- The reset prompt goes to Ben in the chat, in one copy block: the `owner-queue` mod has no store for it yet (checked on the live clone, 2026-11-15). The committed form is below.
- The draft advisory's text is limited to 65,535 characters (62,515 on 2026-11-15) and both planners write to it. Read it again right before every save, check that the other planner's text is unchanged byte for byte, and keep a new section short.
- A check command written for Ben is run against the real files before it is sent. In PowerShell, a `$( )` inside a double-quoted string does not parse when a quoted value in it holds an unbalanced parenthesis: compute such a value into a variable first.
- In Git Bash, set `MSYS_NO_PATHCONV=1` before a `git show <ref>:<path>`, or the argument is rewritten into a Windows path.
- Dates: trade deadline 2026-11-16; re-sign deadline 2026-11-19, 23:59:59 Eastern; Close Days are Fridays; 2027-28 starts Mar 1.

### Resume prompt (the committed form; Ben's copy also names local files)

Act as the central-planner of benjamininja/Python-PowerBI-DynastyFantasyFootball. Call the owner Ben or the owner and yourself Claude. Load the session-rules skill and follow the role file's read list. State: `.claude/memory/PLANNER.md` on branch `docs/state-2026-11-16` (its open state PR: `gh pr list --head docs/state-2026-11-16`); find its worktree with `git worktree list` and run `git pull --rebase origin docs/state-2026-11-16` before reading. Then read the owner's queue file in the main checkout and run `gh pr list --state open`. First send the manager and the Tools planner the new session id; the manager re-keys the planner's queue entries. Then act on the state file's Next list, in order. Advisory detail goes on no public ticket, state file or commit message.
