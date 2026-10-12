# PLANNER — state-back of the planner session

The planner (`.claude/agents/central-planner.md`) writes this file and
no other in `.claude/memory/`. It says where the plan stands, so a new
planner session can resume from the repository alone. The rules are in
`GOAL-RUN.md` and the role file; this file is state.

## START HERE (state 2026-10-12, night)

- **Done:** sweep 1 of stages A and B (see "Sweeps" and "Gaps").
- **Next:** `owner-queue`. The owner's live trial of 0.3.0 is the first
  input; the planner owns the tool from here (see the table below).
- **Then:** the GitHub Project, once the owner has turned Projects on
  and given the token the `project` scope (in the owner's queue).
- **Then:** plan #167 with the owner (the upstream plugin
  `session-dispatch-managers-build-review`; it takes `owner-queue`
  0.3.0 or later as a dependency; the wayfinder template gains a
  `Tier:` line).
- **Open on map #162:** #166 closes when `.claude/builders.settings.json`
  is on `main` and matches the text on the ticket.
- Nothing is running. Stage C waits on the owner's `04t` capture after
  2026-10-15.

## What the planner answers for (owner, 2026-10-12)

| Matter | Ruling |
|---|---|
| The plan | The wayfinder maps and their tickets, all of them. The stage table in `GOAL-RUN.md` is the manager's, derived from the maps; where they disagree the maps win and the planner says so |
| Stages | Each stage is a milestone on its tickets, kept by the planner |
| Project | One GitHub Project as a derived view: labels, state, parent map, milestone. No field of its own |
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
| #70 | In-season Fantrax league flows | #97, #201 (stage C); #92, #93, #116 (stage D); #140, #200 (no stage, single briefs); #130 owner-led |
| #71 | nflverse in-season stats and injuries | closed 2026-10-12 (sweep 1) |
| #151 | Metadata and principles | all tickets closed; fog items not ticketed |
| #162 | Managing-session roles and plugin | #166, #167 |

#140 and #200 sit in no stage: each is proposed to the manager as a
single brief, and nothing blocks either.

## Milestones

One per stage of the table in `GOAL-RUN.md`: "Stage A: Ledger and cap",
"Stage B: Seam", "Stage C: Postgres", "Stage D: Schedule". A ticket
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
| #140 | Power BI prices Dead Money from `Status = "Cut"`; no `fact_dead_money` in the model (`_Measures.tmdl:680-810`) | single brief, now | open |
| #200 | the page draws no waiver or free-agency line (`index.html:511`) | single brief, now | open |
| #201 | a defaulted contract at a drop is printed, not queued (`02d:1709`); no reversed-drop test | stage C, after #97 PR 1 | open |
| #97 (comment) | `02e:169` sums Dead Money over every season in the roster table | the rewrite of `02e` in #97 | open |
| none | `05a:163-166` counts stat rows as games | dropped by the owner; recorded on map #71 | not healed, by ruling |
| manager's | `project-fantasy-football.md:399` lists the nflverse tables as not built | the manager's next memory PR | open |

To re-run when a row's PR merges: the file and line named in the row.

## Asked by the manager

No PR read asked yet.

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

- A sweep's subagent report is checked against the file before it goes
  to the owner; what was not checked is said so on the ticket.

- A by-hand item left only in chat is lost. It goes to the manager as
  a ready queue entry, every time.
- Tracker text is checked with `scripts/check_pii.py` from a file
  inside the worktree (`workspace/_tracker/`), then the folder goes.
- In Git Bash `origin/main:path` is mangled; use PowerShell for
  `git show`.
- A brief's prompt holds no double quote; a ticket's PR needs a closing
  keyword; a builder's scratch files live under `workspace/`.
