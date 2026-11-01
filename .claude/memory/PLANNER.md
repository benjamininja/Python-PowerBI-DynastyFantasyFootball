# PLANNER — state-back of the planner session

The planner (`.claude/agents/central-planner.md`) writes this file and
no other in `.claude/memory/`. It says where the plan stands, so a new
planner session can resume from the repository alone. The rules are in
`GOAL-RUN.md` and the role file; this file is state.

## START HERE (state 2026-10-31, before a compact)

Read this block first. Anything below that disagrees with it is older.
Find the manager with `ListAgents`, by name. Approved plans: this block and
`C:\Users\benha\.claude\plans\gentle-tumbling-waffle.md`.

0. **Latest (2026-10-31).** Closed or merged: #97, #201, #206, #251 (#282, #286), #287 (#288),
   #110 (#290), #273 (#295), #291 (#296), #292 (#297). **#108, the second scoping trial:** the
   result is comment 6543783313, my check 6543813162, the update after the owner's answers
   6543985668. Brief 1 merged (#293); #298 added `ipykernel`. Briefs 2, 3 and 4 are blocked by #299.
   Brief 2 carries the ADR-0018 decision 8 note. Brief 3 follows Briefs 1 and 2. Brief 4 is last,
   and its PR waits for the owner to store `SUPABASE_MIGRATE_DB_URL`. Owner's answers: `timestamptz`;
   the generator line is in `builders.settings.json`; the new secret. Docs did not settle `db push`
   and `config.toml` or file names, so Brief 3's `validate` job tests both on the service container.
   CLI pin: `setup-cli` v3.0.1 by SHA, CLI 2.122.0. Still to do on the trial: token comparison and
   judgement.
   **Tickets I wrote this stretch, all with the manager:** #299 medium, `01e` keeps any id nflverse
   drops, marked `DROPPED`, then publishes (owner's pane answer 09:33, #108 comment 6544757011);
   one PR; NotebookEdit exception for this ticket only. If the NaN pick price survives, the builder
   parks. #300 high, the re-key the owner named, waits on #299, scope first. #301 medium, gap:
   `etl_helpers.py:415` zips two separately dropna'd columns, so 0 of 614 `fact_rookie_rankings`
   ids match the true id. Waits on #299; Power BI measures and notebooks not yet searched for readers.
   **Declined, no ticket:** a -0.5 delta in `capCardHtml` prints `($0)` in the down colour.
   **Daily ETL status given to the owner:** not running; no scheduled workflow in the repo; no
   Windows task matched by name; left are #108, #135, #136, #137, #138, #111, then #93, #116, then
   the owner's crons and parallel week. The owner asked how to check the Supabase secret; answered
   with names, branch policy and a `psql` test of the URL. TOTP secret not verified; ask the
   manager to queue it before Stage D if missing.
   **State saves are batched (owner, pane, 2026-10-31 08:42):** one PR a day for planner and
   manager; the rule is in both role files. Today's branch is `docs/state-2026-10-31`. Evidence from
   the last 40 merged PRs:
   11 product, 14 state saves, 15 other chores or docs; no PR above one comment; median open about
   10 minutes; six waited 10 hours or more. So review is not the drag; bookkeeping is. Builder
   start-to-PR time was not measured. The batch must merge before any worktree cleanup.
   **Merge refusals, cause not proven.** Owner's user settings now hold an `autoMode` allow rule for
   the manager's re-proved merges, `PowerShell(gh pr merge *)`, and PowerShell denies for `--admin`
   and `--auto`. #286 and #288 merged through Bash with no refusal, mode unknown. If one is refused,
   get the mode and exact command from the manager before changing anything. Markdown cannot grant
   this: the classifier's Self-Modification rule treats written-in consent as manufactured.
   **Mine:** `cap-ledger-auditor`'s agent file lists only `capmath.py`. Builders have no clean
   notebook edit; rule-text item, no new tooling (owner). #279 part 2 waits on the owner.
   Skills-repo item 4 is held by the owner's later word. Worktree `w218` in this session's
   scratchpad has the venv for PII scans of tracker text (`workspace/_tracker/`). Ask the owner's
   yes before removing it. Earlier worktree `ps8` holds a merged branch.
   **Session ended here at the owner's word (2026-10-31), with a clear to follow.** A new planner
   starts from this block. `w218` is at `C:\Users\benha\AppData\Local\Temp\claude\C--Users-benha-OneDrive-Documents-GitHub-Python-PowerBI-DynastyFantasyFootball\b5cc7ae9-4bbb-48bd-a801-d3ccc1bd07ac\scratchpad\w218`,
   on `docs/state-2026-10-31`. This session's id is `b5cc7ae9-4bbb-48bd-a801-d3ccc1bd07ac`; a queue
   entry it raised answers back to it, so a new session re-raises any it needs. If today's state
   PR has not merged, this block is on its branch, not on main. The local branch
   `docs/planner-state-1031b` is merged and stays, as the guardrail blocks `git branch -D`.
1. **Earlier: the scoping session for #97 PR 3.** PR #269
   (#97 PR 2) merged as `5d5284e`, by the owner, before the auditor's bug was fixed: the
   `team_cap` Gate passes a null figure. The owner's word: the fix goes in the next PR. It is
   on #97 for the scoping session. Carried to #93: the first same-day `salary_remaining` run,
   same day not same instant, stale ledger, a persistent `NotComparable`. `cap_exempt` ignored
   by `stamp_cap` is on #97. The owner wants the build moving now: after the proof, no new
   tooling; go to Stage C.
2. **The owner's decision: Opus plans work down and never builds it.** A trial,
   no rule changed yet. Only high tickets get a scoping session (#97 PR 3, #108,
   #135): `dispatch.ps1` at tier high, `-TurnCap 40`, agent `stage-builder`. It
   writes no code and opens no PR; its output is one comment on the ticket: one
   brief per PR, in order, each with a low or medium tier, files, settled design,
   done condition and proof, then open design questions. It questions the planner,
   never the owner. The planner checks the briefs against the ADR and done condition,
   takes open questions to the owner, sets tiers, tells the manager. An open design
   question goes back to planning, never to a builder; an exception is the
   owner's, one at a time. The manager sends back a low or Haiku brief with
   no files or proof, and any build brief at high. The brief for #97 PR 3 is
   on #97 (comment 6525071022). #108 is the second trial.
   Then: compare token use with `b97-team-cap` from the transcripts and count parks
   and rework (rough; the tickets differ). If the trials hold: write the flow in
   `central-planner.md`, put rule text on a ticket for `GOAL-RUN.md` with #218's
   shrink, and add a Haiku tier (Haiku 5.5, medium, 15 turns; mechanical only, never
   cap, ledger, pipeline or schema) to `dispatch.ps1` with a test and to
   `session-rules`. The script refuses a Haiku tier today.
3. **That scoping session is also the #218 proof.** Two script dispatches failed
   check 3 with `Unknown skill: session-rules`. Fixes: YAML colon (skills PR 62);
   `--plugin-dir` on the start command (skills PR 66, `d193886`; the live clone is at
   it). Cause of the second, likely not proven: a `--bg` daemon's parent is
   `WmiPrvSE.exe`, so it does not inherit `CLAUDE_CODE_PLUGIN_DIRS`. `claude -p` with
   the builder's flags, without `-w` or `--bg`, loaded it, and the bare name
   resolved. `--bg` with the flag is untested. Pass: pid and own worktree; deny list by
   `--disallowedTools`; transcript (not only its report) shows `session-rules`
   loaded. On a pass: close #167 with the evidence, post the shrink text on #218
   against current `main`, open the role-file and `CLAUDE.md:57` PR. On a fail:
   stop, take what the transcript shows to the owner.
4. **Skills repo, approved in order, after the proof:** `dispatch.ps1` fetches and
   compares the live clone with `origin/main`; `-Apply` refuses when behind and prints
   the pull command; a dry run only reports; it never pulls. The planner merges on
   green, on that approval. CI does not run the mod's tests (`claude plugin test`):
   a gap, not ticketed.
5. **Owner-queue:** no auto-open, version 0.7.2, in `~/.claude/mods/owner-queue`;
   the owner has reloaded plugins.
6. **Trajectory:** Stages A and B done. Stage C: #97 then #110, #108, then #135 to
   #138, then the owner's secret and cutover. Stage D: #93 and #116. The cap tickets
   #251, #201 and #206 are low, briefs on them, not dispatched. Don't start more tooling
   work until stages are moving.
7. **`roster_membership` "ledger is stale"** is by design until `04t` is a step
   (#93); the manager weighs it.
8. **Not deleted, needs the owner's word:** skills branches
   `needs-owner-template-rules`, `builder-state-rules`,
   `fix/session-rules-frontmatter`, `test/skill-frontmatter`,
   `fix/owner-queue-no-auto-open`, `fix/owner-queue-version-test`,
   `fix/dispatch-plugin-dir`; skills worktree `C:/Users/benha/fr`;
   `docs/planner-state-6`, `-7`, `-8`, `-9`; local `docs/builder-state-234`;
   `.claude/worktrees/metadata-principles` (leftover cherry-pick, unpushed `4f23f16`).
9. **Working notes.** The owner will not restart the app: verify before listing a hand
   item. A relayed answer is never approval; ask in this session. A skills-repo
   worktree needs a short path on Windows. Gate a merge on the test's exit code, and
   check the interpreter has pytest (`set -e` did not stop PR 66's push before tests
   ran); the dynasty `.venv` runs the skills tests. A `git push` from a main-resolved
   cwd is blocked: use `git -C <worktree> push`.

## Earlier state (2026-10-12, partly stale)

- **#234 is designed and in review** (plan gate passed with the owner,
  2026-10-12; the design is a comment on #234).
  - Owner's decisions: a builder's lasting state is its ticket and its
    commits, with a git-ignored scratch folder `builder-state/`; a
    builder never writes the queue, it sends the manager a ready entry.
    A builder writes no file under `.claude/`. No new ADR.
  - **PR #244** (branch `docs/builder-rules-234`): the two role files
    and `.gitignore`. Waits on the owner's approval; entry in the queue.
  - **Skills PR 61** (branch `builder-state-rules`, scratch worktree
    `<planner scratchpad>\tpl`): the same rules in the plugin. Waits on
    the owner's word to merge; entry sent to the manager.
  - The manager has the text for `GOAL-RUN.md` and an optional Action
    for the owner (two dead allow rules in the builders' settings).
  - **Closes on proof:** the next dispatched builder posts its plan and
    a state-back comment with no denied call. The manager reports it.
  - A stray local branch `docs/builder-state-234` sits in the scratch
    worktree `<planner scratchpad>\b234`, unpushed and unused.
- **The brief for #230 is written** (2026-10-12): a comment on the
  ticket (issuecomment-6135590120), medium, built against the owner's
  pasted markup, fakes only. The PR says Refs #230; the ticket closes
  on the owner's run from an empty profile. Not known until then:
  self-submit on the sixth digit; what a wrong code shows. Recommended
  to the owner: dispatch after PR #244 is merged.
- **Next, the planner's: plan #218** (shrink `GOAL-RUN.md`) in plan
  mode, to the owner before anything is written. It is blocked by #167
  and #234; the plan can be made now. The manager applies the #234 text
  to `GOAL-RUN.md` in its own PR first; plan against that.
- **This file's PR is #246** (branch `docs/planner-state-7`). PR #226
  was merged earlier; `docs/planner-state-6` is unused, not deleted.
- **In the owner's queue (on `main` since PR #245), all from the
  planner:** approve PR #244; merge skills PR 61 (answer comes to the
  planner, who merges); approve PR #246; when to dispatch #230; the
  optional settings clean-up; the clone and `setx` for the plugin
  folders. The manager set its own id as `Session:` on the three it
  acts on (#244, #246, the #230 dispatch).
- **Skills PR 59 is merged** (by the planner on the owner's word,
  2026-10-12; merge commit `56ff4f7`): the queue-entry writing rules in
  the plugin's templates. Owner's ruling in the pane the same day: a
  pane comment (`Note:`) is never approval; recorded on #167 and in the
  `session-rules` skill.
- In the skills repository, `tests/test_git_guardrails.py` hangs on the
  owner's machine and passes in CI. Reported to the manager for #237.
- The guardrail hook blocks `git reset --hard` in any command. Do not
  route around it.
- **#167 step 2, the dispatch plugin (skills PR 46, merged; see below)**
  (branch `session-dispatch-plugin`; scratch worktree `<planner scratchpad>\sd`).
  - In it: `scripts/dispatch.ps1`, skills `session-rules` (loadable)
    and `session-dispatch` (manual only), thirteen templates, ADR 0013,
    12 tests.
  - **Owner's ruling 2026-10-12:** `-Apply` acts only in a main checkout
    named in `<user profile>/.claude/dispatch-projects.json`, which the
    owner writes. Without it, the allow rule for the script was as wide
    as a rule for any PowerShell line.
  - Owed: `/security-review` from a session rooted in the skills
    repository (the command is not available in the planner's session;
    the PR says so). Then the owner merges and pulls the live clone.
  - The owner's by-hand steps went to the manager as ready queue
    entries: the two owner-only files, the settings rules, the plugin
    folder in `CLAUDE_CODE_PLUGIN_DIRS` (separator for two folders not
    verified).
  - #167 closes on the first real dispatch through the script. Watch
    there: whether `--disallowedTools` takes path-scoped rules.
  - Still to open: a ticket under #162 for the `Tier:` line in
    `wayfinder`, after the owner's re-vendor.
- **PR #228 (#225) read: no breach.** One choice is the owner's: the
  spike prints a Fantrax error code on a public log. Entry sent to the
  manager.
- **#230** (new, Stage D, medium, child of #70): the login answers the
  TOTP code prompt. Its first step is an owner Action (report the
  prompt's field label and button text); not free to dispatch before.
- **`owner-queue` 0.7.1 is live and merged** (skills PR 39, merged by
  the planner on the owner's word "merge PR 39", 2026-10-12; merge
  commit `45e7030`). 26 tests pass. The scratch worktree
  `<planner scratchpad>\oq6` (branch `owner-queue-060`) equals it.
  - In it since 0.5.0: `Post comment` (a `Note:` line, or a typed
    `Answer: (other) ...`), sent at once; a `Time:` line on every chat
    message; every code span copied from under its field, a numbered
    field drawn one step per row; `Write in editor` (a draft file in
    the mod's own `drafts` folder, opened by the system's opener);
    `Print in chat` removed; lines between the groups.
  - Seen by the owner in the real pane: comments, the carry to the
    raising session, the `Time:` line, the editor opening. **Never
    tried there:** `Send as answer`.
  - The app's `Input` is one line and draws its own send control,
    which a mod cannot remove (labelled `Enter`). The API removes no
    file: a sent draft is emptied.
  - The trial is over; the owner marked the TEST decision done in the
    pane. The head rules for `NEEDS-OWNER.md` (the `Note:` rule, the
    `Time:` line, code marks, fenced blocks, numbered steps) went to
    the manager as text, to confirm with the owner.
  - The same rules are in the dispatch plugin's templates since
    skills PR 59.
- **A repeat of old pane answers after a compact** (manager's session,
  2026-10-12) was the app's prompt queue, not the mod: two sends made
  while the session was busy were delivered again, merged. The `Time:`
  line marks such a repeat.
- **Skills PR 46 is merged** (by the owner, 2026-10-12; merge commit
  `804ea65`). The plugin is on GitHub, not on disk: no live clone
  exists (`C:\Users\benha\claude-live` is not there), and the owner's
  checkout of the skills repository has not pulled.
- **Open, the owner's hand, in the queue through the manager:** the
  saved `CLAUDE_CODE_PLUGIN_DIRS` names only the session-dispatch
  folder, which does not exist; the next app start would load neither
  plugin. The entry gives the clone command and a `setx` with both
  folders joined by a semicolon (`~/.claude/mods/owner-queue` first),
  then a full restart. The planner changes no system setting.
- **Lesson repeated by the owner, 2026-10-12:** open points for the
  owner go to the manager as ready queue entries in the same turn,
  never chat alone ("why aren't the questions in the ledger").
- **#167 after that:** `.claude/dispatch.json` exists in the main
  checkout (the manager's report); it closes on the first real
  dispatch through the script.
- **#237** (the manager's standing cleanup ticket): `wayfinder:task`,
  `tier:low`, "Tooling and upkeep", no parent. Auto-add to the Project
  worked.
- **#234** (new, child of #162, "Tooling and upkeep", tier none): the
  planner designs a move of the builders' state files out of
  `.claude/`, by the owner's answer of 2026-10-12 as the manager
  recorded it on #166 (the planner did not see the line itself). Plan
  gate with the owner first. The stopgap holds until then. #218 waits
  on it.
- **#167, checked 2026-10-12 after the owner ticked three entries:**
  `~/.claude/dispatch-projects.json` exists and lists the main
  checkout; the settings rules are in both settings files
  (uncommitted, the manager's to commit on the owner's word);
  `.claude/dispatch.json` is missing; skills PR 46 is open, so the
  plugin is not in the live clone
  (`C:\Users\benha\claude-live\skills-plugins-hooks-agents`) and
  `CLAUDE_CODE_PLUGIN_DIRS` names only the `owner-queue` folder. The
  manager kept the three entries open.
  - `/security-review` now loads in the planner's session but reviews
    the session's own branch only; it found nothing here and did not
    cover PR 46. Still owed from a session in the skills repository.
- **Then:** #218 (shrink `GOAL-RUN.md`), blocked by #167.
- **Out with the manager:** the brief for #225 (the part of #92 an
  agent may do: the spike workflow, ready for the owner to fire). The
  owner reads the workflow before the merge. Nothing of #110 is free:
  PRs #145 to #148 did four parts, `scorer_id` moved to #97, the
  `roster_slot` rename waits on #97.
- **Milestones (owner, 2026-10-12):** every open ticket and map has
  one. A map carries the stage it finishes in (#69 Stage C, #70 Stage
  D). Work outside the stages is "Tooling and upkeep" (#151, #162,
  #167, #218, #130, #211).
- **The GitHub Project** (project 2, "Dynasty FF: plan") is finished
  (read through the API 2026-10-12): "By stage" grouped by Milestone,
  "By map" by Parent issue, "Auto-add to project" on. Check that the
  next new ticket lands there by itself; if not,
  `gh project item-add 2 --owner benjamininja --url <url>`.
- **`owner-queue` 0.5.0 is proven live** (2026-10-12): an answer
  pressed in the manager's pane arrived in the planner's chat, once,
  and not in the manager's. Not seen: the id line in the system prompt
  (use `/owner id`); mouse selection of a "Print in chat" notice.
- **#166 is closed** (PR #219 put the owner's settings edits on
  `main`).
- Stage C waits on the owner's `04t` capture, after Wednesday
  2026-10-14, 8:00 am.

## What the planner answers for (owner, 2026-10-12)

| Matter | Ruling |
|---|---|
| The plan | The wayfinder maps and their tickets, all of them. The stage table in `GOAL-RUN.md` is the manager's, derived from the maps; where they disagree the maps win and the planner says so |
| Stages | Each stage is a milestone on its tickets, kept by the planner |
| Project | One GitHub Project as a derived view: labels, state, parent map, milestone. No field of its own. Private. A ticket that waits on the owner's own hand carries the label `owner-led` |
| Wiki | None for now; owner-facing pages are a fog item on map #151 |
| A found gap | A ticket with evidence, tier and done condition. The planner fixes gaps in documents it owns; code, tests, data and notebooks go to the manager. The manager gets all it needs to disposition, and the planner stays on the gap until it is closed |
| Live builds | The planner reads a builder's PR when the manager asks |
| Sweeps | When the owner asks |
| `owner-queue` (2026-10-12, night) | The planner owns the tool with the owner: the mod's code and tests, the entry format of `NEEDS-OWNER.md`, the upstream copy (PR 39 of the skills repository) and where it goes next. Managers still write the queue entries and send the planner what they need from the tool |
| Merging | The manager merges the planner's PRs after the owner's approval. One PR per check-in, one commit per topic |

## Maps

| Map | What it is | Open |
|---|---|---|
| #69 | Supabase storage foundation | #108, #110, #111, #135 to #138 (stage C) |
| #66 | trade-bud waiver-activity signal | closed 2026-10-12 (sweep 1); its one gap is #200 on map #70 |
| #70 | In-season Fantrax league flows | #211 (owner, upkeep); #97, #201 (stage C); #225, #230, #92, #93, #116 (stage D); #206 (stage C, after #97); #130 owner-led. #200 merged (PR #204) |
| #71 | nflverse in-season stats and injuries | closed 2026-10-12 (sweep 1) |
| #151 | Metadata and principles | all tickets closed; fog items not ticketed |
| #162 | Managing-session roles and plugin | #167, #234, #218 (after #167 and #234) |

#140 was placed as blocked by nothing; one clause of its acceptance
needed #97 (see "Lessons").

## Milestones

One per stage of the table in `GOAL-RUN.md`: "Stage A: Ledger and cap",
"Stage B: Seam", "Stage C: Postgres", "Stage D: Schedule", and
"Tooling and upkeep" for work outside the stages. A ticket
moves between stages by the planner on the manager's word.

## Sweeps

A sweep checks, read-only: each closed ticket's done condition against
`main`; each ADR against the code it describes; each map's pointer
lines against its closed tickets; `Tier:` lines and labels; milestones
against the stage table; README, CONTRIBUTING and `docs/` claims
against `main`. Raw payloads go through the `fantrax-payload-analyst`
subagent, cap and ledger logic through `cap-ledger-auditor`. A finding
without a command and its output, or a file and line, is left out.

| Sweep | Scope | Result |
|---|---|---|
| 1 | Stages A and B | 2026-10-12, `main` at 383d22f. All six closed tickets hold; `pytest tests` 776 pass. Six gaps, in "Gaps". Maps #66 and #71 closed; maps #69, #70 and #162 and `PLAN.md` corrected |

## Gaps

Each row: ticket, where found, disposition, healed (the evidence re-run
after the fix).

| Ticket | Found | Disposition | Healed |
|---|---|---|---|
| #140 | Power BI prices Dead Money from `Status = "Cut"`; no `fact_dead_money` in the model (`_Measures.tmdl:680-810`) | single brief, now | healed 2026-10-12 (PR #207): `Fact_DeadMoney` is in the model on `main` and no measure reads `Status = "Cut"`. Not opened in Power BI Desktop: #211 |
| #200 | the page draws no waiver or free-agency line (`index.html:511`) | single brief, now | healed 2026-10-12 (PR #204): `index.html` on `main` names both signals |
| #201 | a defaulted contract at a drop is printed, not queued (`02d:1709`); no reversed-drop test | stage C, after #97 PR 1 | open |
| #97 (comment) | `02e:169` sums Dead Money over every season in the roster table | the rewrite of `02e` in #97 | open |
| none | `05a:163-166` counts stat rows as games | dropped by the owner; recorded on map #71 | not healed, by ruling |
| manager's | `project-fantasy-football.md:399` lists the nflverse tables as not built | the manager's next memory PR | healed 2026-10-12 (PR #202) |

To re-run when a row's PR merges: the file and line named in the row.

## Asked by the manager

| PR | Asked | Read |
|---|---|---|
| #207 (#140) | 2026-10-12: three places past the ticket | No breach; posted on the PR. One acceptance clause needed `fact_team_cap` (#97 PR 2). The owner reworded it: prove with the parity formula of #96 now, the table comparison moved to #97 |

## Decided since (owner, 2026-10-12, late)

- **One anchor for this season**: the season on the roster table, for
  every consumer; nothing takes it from the calendar. Built in #97
  PR 2; written on #97 and #206.
- **IR-slot salary is cap-exempt** in the cap module too (#97), as in
  the Power BI measures (#140).
- **`owner-queue` 0.4.0** (plan approved, built): a press is staged and
  nothing is written until Submit; a copy button per `code` span;
  `/owner show` prints entries into the transcript; the pane shows its
  version and says when it is not reading the main checkout. Live in
  the owner's mods folder; upstream commit 359a15a on PR 39 of the
  skills repository. A session started before an update keeps its old
  copy, and a copy older than 0.3.0 writes to its own worktree's queue.
- **#206** (from the #140 audit): tier low, stage C, after #97.
- **`owner-queue` 0.4.1 to 0.5.0** (owner, 2026-10-12, each on the
  owner's word): 0.4.1 options drawn as text with a Choose button and
  copy buttons beside them, "Print in chat"; 0.4.2 a fenced block in
  an entry is one copy chunk, and an entry with a block gets no span
  buttons; 0.5.0 message back by the `Session:` field. Live in the
  owner's mods folder, 20 tests; upstream commit 851aedc on PR 39.
  Backups of each earlier version are in the session's scratchpad
  only. Staging and Submit were proven live by the owner at 0.4.0.
- **Proof-command rule** is in `GOAL-RUN.md` (PR #215).
- **Label `owner-led`** marks a ticket that waits on the owner's hand.

## Decided before this file (pointers)

- #164, #165, #166: roles, dispatch from the CLI, tiers, the relay.
  The decisions are on the tickets.
- `owner-queue` 0.3.0 (2026-10-12): a decision is answered by a button;
  one queue, the main checkout's `NEEDS-OWNER.md`; only the pane writes
  an `Answer:` line. Upstream: PR 39 of the skills repository.
- Two-key merge (owner, 2026-10-12, given in the manager's session and
  confirmed there): a builder opens its PR, the manager re-proves Green
  and merges; no owner approval per builder PR.
- #186 merged (PR #195): `scripts/compare_tables.py` and `--raw-dir` on
  `02d` are the proof commands for stage C briefs. A brief says
  "identical or equal": after `02d` four tables are frame-equal with
  different bytes.

## Lessons

- Before a ticket is called blocked by nothing, its acceptance is read
  for a table or a rule another open ticket builds. #140 was placed
  free while its acceptance compared with `fact_team_cap` of #97.
- A `grep` of the `04t` script is denied to the planner (the Fantrax
  deny rules). Ask the manager for a fact about it.

- A sweep's subagent report is checked against the file before it goes
  to the owner; what was not checked is said so on the ticket.

- Before a ticket is called free for dispatch, its merged PRs and
  comments are read, not only its body and its blockers. #110 was
  offered with four parts open that PRs #145 to #148 had done.
- A skill that tells a session to start sessions or to merge is
  manual only by the skills repo's ADR-0006; keep rules and acts in
  separate skills.
- A pane feature is not done until the owner has used it: tests passed
  on 0.4.0 while the copy buttons sat out of sight and one span per
  button was the wrong unit. Say what was not seen in a real pane.
- `gh auth refresh` must run in a real terminal and wait for
  "Authentication complete"; the app's terminal panel drops it.
- The Projects API cannot set a view's grouping or the auto-add
  workflow; those are by the owner's hand.

- A by-hand item left only in chat is lost. It goes to the manager as
  a ready queue entry, every time.
- Tracker text is checked with `scripts/check_pii.py` from a file
  inside the worktree (`workspace/_tracker/`), then the folder goes.
- In Git Bash `origin/main:path` is mangled; use PowerShell for
  `git show`.
- A brief's prompt holds no double quote; a ticket's PR needs a closing
  keyword; a builder's scratch files live under `workspace/`.
