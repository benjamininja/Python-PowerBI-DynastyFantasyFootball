# MANAGER — the builder manager's state

The dynasty builder manager's working copy of its state. It links to
the record on GitHub and does not replace it. **Only the newest state is
kept here.** Every earlier block is in this file's git history:
`git log -p -- .claude/memory/MANAGER.md` (trimmed 2026-11-22 on the
owner's button; the last long version is at commit `995f0cf`).

Read order at a start: the role file's list, then this file, then the
main checkout's `NEEDS-OWNER.md` (the one copy the owner's pane reads).

## Standing facts

- **Paths.** Repo root `C:\source\Github\Python-PowerBI-DynastyFantasyFootball`
  (since the tools #235 move; any OneDrive path is stale). Tools repo
  `C:\source\Github\skills-plugins-hooks-agents`. The dispatch script is
  in the session-dispatch plugin's `scripts/` folder.
- **session-dispatch** must be typed by Ben in each session before any
  dispatch, merge, resume or closeout.
- **Re-proof:** `.venv/Scripts/python.exe scripts/reproof.py <pr> <head>`
  after `git fetch origin`, run in the background. Post a summary on the
  PR with counts only: its review-finding lines hold row keys. Merge
  squash, pinned with `--match-head-commit`, then `git pull --ff-only`
  in the main checkout at once.
- **Dispatch from PowerShell without `2>&1`:** Windows PowerShell 5.1
  turns git's stderr into a stopping error, and the script fails after
  making the worktree. A re-run reuses the worktree.
- **Closeout:** `claude rm <id>` removes the worktree and the local
  branch. A squash-merged branch with more than one commit shows `+` in
  `git cherry`: check that the branch's files have no diff against main
  instead, and say so to Ben.
- **The Daily Run** is the `etl-daily` GitHub Actions workflow. Its log
  (`gh run view <id> --log`) holds each step's error tail, the same
  text the Discord summary posts.
- **The bot** runs on Ben's PC from `discord_bot`
  (`.\.botvenv\Scripts\python.exe bot.py`) in a terminal tab of the
  manager's session. A clear can close it: check and restart.
- **Ben's standing merge word, each when GREEN:** #616, #623, #597, #626.
  It never covers a parked Decision (an ADR amend, a DROP COLUMN).

## CURRENT STATE (2026-11-22 ~21:40Z, session `1a0538b1-047b-4ba3-8967-ff325369e7ab`, before a compact at Ben's word)

- **Heads.** origin/main and main checkout `ff035d7`.
- **Merged since the last save:** #636 (#630) `eebdf68`; #638 (#629)
  `dd59ac1`; #647 (#643 plus Ben's sheets-key-check workflow) `d2d267b`;
  #642 (#623) `ff035d7`. All GREEN at re-proof. Builders b629, b630,
  b643, b623 closed out. Stale data PRs #603, #618, #627, #628, #635 closed.
- **Live proofs met:** #629 (data PRs #640, #641, #645 merged); #630 and
  #614 ([ok] 01c in run 45068959547, after Ben's byte-exact re-save of
  the Sheets secret; the earlier failures were the .env line, then a
  PowerShell pipe).
- **#548 FA keeps loaded:** 109 rows in app.contract_choices (30 keeps),
  count-only check; the local SQL file is deleted.
- **In flight:**
  - b648-keyisolate (#648, session `40c1c6ac`), PR #649: local re-proof
    GREEN on `ff035d7` (3312 passed); diff read, no findings. Waits on
    storage-pg, which Ben is re-running (the runner-side cancel). Merge
    on GREEN: Ben's word. Then close out b648.
  - b548-ownerxwalk (#548 brief 3, session `938e2850`), draft PR #646.
    Count 2 = 0 (posted on #548), so the builder adds the
    pii_token_hashes() change, then marks ready. Re-proof: reproof.py,
    the migration gate (the builder's own run was refused), the
    supabase-auditor including migrate.yml and tests.yml (planner ruling
    3). The planner owes the GOAL-RUN schema line and the auditor basis
    (planner session was gone at ~21:10Z). No merge word from Ben yet.
- **CI:** every storage-pg job was cancelled at ~21:16Z (runner-side).
  Main's storage-pg has not completed since #647/#642.
- **Rules learned today:** owner hand steps carry their full content
  (root preferences). A builder's refused call is surfaced to Ben, never
  run for it. Secret saves use cmd /c with < redirection.
- **Dispatch order after, each at Ben's go:** #633, #637, #639, #616 (ADR
  amend as a Decision first), #626, #597. #563 held; #595 last; #620
  waits on tools #231. #644 (reproof temp-folder leak) is ticketed.
- **Queue:** empty.
- **Peers:** dff-central-planner and Tools-builder-manager were not
  running at ~21:10Z; personal-assistant up.
