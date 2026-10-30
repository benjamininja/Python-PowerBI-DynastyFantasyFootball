# PLANNER — state-back of the planner session

The planner (`.claude/agents/central-planner.md`) writes this file and
no other in `.claude/memory/`. It says where the plan stands, so a new
planner session can resume from the repository alone. The rules are in
`GOAL-RUN.md` and the role file; this file is state.

## START HERE (state 2026-10-30, before a compact)

Read this block first. Anything below that disagrees with it is older.
No PR is open in this repository. Find the manager with `ListAgents`, by
name. CI is green: #259 merged (PR #260, `bdd3d84`), and `main` passes on
pandas 3.1.0 and pyarrow 26.0.0, 882 tests.

1. **#218 is approved and gated; the proof is the next event.** The first
   script dispatch (b254) passed two checks and failed the third:
   `Unknown skill: session-rules`. Cause: an unquoted colon broke that
   skill's YAML frontmatter. Fixed in skills PR 62 (`70e8504`); the live
   clone is pulled to it. The manager's hold is lifted and its next builder
   through the script is the proof, reported to the planner by name. Pass:
   pid and own worktree; deny list by `--disallowedTools`; transcript shows
   `session-rules` loaded. A `--bg` session with the fix is untested.
   On a pass: close #167 with the evidence, post the shrink text on #218
   against the merged #234 edits (PR #261, `41354e2`; the fold in the plan is
   dropped), open the role-file and `CLAUDE.md:57` PR. On a fail: stop, take
   the cause to the owner. The owner's two files are in (PR #262). The owner
   will not restart the app: new processes read the plugin without it.
2. **Skills repo plan, approved by the owner in order.**
   Part 1 done: PR 63 (`e5c5a94`), every tracked SKILL.md's frontmatter is
   tested. Part 2 not started and held until the proof passes: `dispatch.ps1`
   fetches and compares the live clone with `origin/main`; `-Apply` refuses
   when it is behind and prints the pull command; a dry run only reports; it
   never pulls. The planner merges on green, on that approval.
3. **Owner-queue no longer opens by itself:** PR 64 (`8aee46a`) and PR 65
   (`a898308`), version 0.7.2, copied to `~/.claude/mods/owner-queue`, 27
   tests pass there. A session gets it at its next launch or plugin reload.
   CI does not run the mod's tests (`claude plugin test`): a gap, not
   ticketed. PR 64 merged with one test failing for that reason.
4. **Spike:** #92 and #230 closed. The owner fired one more manual run
   (41063510308, login passed, four reads 200) and the workflow was then
   `active`, so check whether its schedule is still on. The manager runs the
   removal (b254). Stage D's stale lines in `GOAL-RUN.md`: the owner said
   yes here; the manager needs that word in its own session.
5. **`roster_membership` "ledger is stale"** is by design until `04t` is a
   step (#93); the manager weighs it.
6. **#97:** PR 1 merged; PR 2 is `fact_team_cap`, writer `02h`. Three planner
   notes may not have reached the builder, so they go in that brief: the
   player card prints stored `cap_hit` while `/roster` and `/cap` charge IR
   until PR 3 (ADR-0016's Consequences misses it); the out-of-season fallback
   reads as added at build; `02g` in the settled design is taken.
7. **#251:** tier low, Stage C, brief on it, not dispatched.
8. **Not deleted, needs the owner's word:** skills branches
   `needs-owner-template-rules`, `builder-state-rules`,
   `fix/session-rules-frontmatter`, `test/skill-frontmatter`,
   `fix/owner-queue-no-auto-open`, `fix/owner-queue-version-test`; skills
   worktree `C:/Users/benha/fr`; `docs/planner-state-6`, `-7`, `-8`; local
   `docs/builder-state-234`; `.claude/worktrees/metadata-principles` (leftover
   cherry-pick, unpushed `4f23f16`).
9. **Working notes.** A long temp path breaks a skills-repo worktree on
   Windows: use a short one. Chain with `set -e`, and never pipe a test run
   through `tail` before a merge: that hid a failure on PR 64.

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
