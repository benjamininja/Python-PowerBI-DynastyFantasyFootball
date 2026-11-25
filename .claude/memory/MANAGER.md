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
- **The reset prompt** is a local file in the owner's profile, outside
  every repository, one per repo and role (tools #217). A new session
  told to read it, with none in its chat, looks there before it rebuilds
  from this file.
- **The queue is edited with the owner-queue command line** (add, remove,
  prune), never by hand for a whole entry. A pane Note is recorded on the
  entry's ticket word for word before the entry is removed.
- **A pane Note is not approval,** even when its words approve. Bring it
  to Ben by button in chat, then act. A tick is not approval of a merge
  either: an entry that asks for a merge is a Decision, so the pane
  writes an Answer, and it never offers the tick as a way to approve.
- **An owner's settings edit** is made by Ben in the main checkout. On
  his word the manager copies the file unchanged to a branch and a PR.
  After that PR merges, restore the main checkout's copy and pull at
  once: git refuses a pull over the same edit left uncommitted.

## CURRENT STATE (2026-11-25, thirteenth save, before a compact at Ben's word; session `4ff97ebc-bfd4-4723-997c-406160d975ba`)

- **Heads.** origin/main and the main checkout at `8e217ed` (PR #690). The main checkout is clean (only `.agents/` and `GEMINI.md` untracked).
- **session-dispatch** was typed by Ben in session `4ff97ebc`. A compact keeps it; a clear needs it typed again.
- **Done this session:**
  - PR #684 (#597) re-proved GREEN on base `86e4d00` (3529 passed) and merged as `3544eb0`. Ben dispatched `migrate.yml` for the held drop (run 45615491025): SUCCESS. The schema check holds every line (issues/597#issuecomment-7162996556). #597 closed; b597 closed out.
  - PR #690 (#688) re-proved GREEN on base `3544eb0` (3534 passed) and merged as `8e217ed` on Ben's button word. b688 closed out (issues/688#issuecomment-7162912346). #688 stays open for the planner's GOAL-RUN.md check-lines PR.
  - #686 dispatched as b686-dropload (session `17c21010-6d47-4c03-b1c5-0bdea138ca41`); #639 dispatched as b639-gsisremap (session `f9b3cf43-e574-451b-851d-5e14ac8dbf62`), both medium, profile none, on Ben's go.
  - Bot restarted after the clear (terminal tab of this session).
- **PR #689 (#662, b662-approles, session `cad4e1c1-5c27-4f2f-8371-056a362856ed`), head `a19a5b32059465b2e1a1ef66f62dde7d80b6893d`.**
  - Resumed on Ben's word (issues/662#issuecomment-7162720212): main merged, migration regenerated as `20261125124252_app_role_and_checks.sql`, F1 to F3 fixed. Builder reports CI green.
  - Review round closed, no blocking finding (pull/689#issuecomment-7163211816). Audit F2 to F4 advisory, open. Planner: no breach at a19a5b3 (issuecomment-7162949880). Migration order OK (manager ran the script).
  - Ben: merge when green (issues/662#issuecomment-7163217152).
  - **Next:** on Tools-builder-manager's end notice for tools #267, take the test line; `reproof.py 689 a19a5b32059465b2e1a1ef66f62dde7d80b6893d`; one CI read; merge pinned; pull; check the merged tree; end notice (tools takes it for #259).
  - Then: the migration has no destructive statement, so the push run should apply it; run the After a schema change lands check with #661's lines (issues/661#issuecomment-7135889563) and #662's (issues/662#issuecomment-7162418443): the functions of `shared` now number four. The expected advisor lint on `shared.app_role` goes to Ben as a Decision (the planner has not accepted it).
  - Then: send the planner the merge commit (it writes the GOAL-RUN.md check-lines PR, with #688's line, and checks #670's and #675's bodies). Queue Owner Action 2 (loader run) once Ben has posted the gid. Ask Ben for b662's closeout word.
- **PR #692 (#686, b686-dropload).** `tests` failed on `tests/test_pg_marker.py`; fixed locally at 5018d9c. Its push `git push origin <branch>` was refused (allowed forms: `git push`, `git push -u origin *`); told to use `git push` (issues/686#issuecomment-7163228435). Waits on its green report; then review (full, high) and supabase-auditor (storage seam), re-proof.
- **#639 (b639-gsisremap).** Building. It blocks data PR #691 (fails `test_gsis_current`: one old gsis_id in `dim_fantrax_crosswalk` and `fact_fantrax_adp`; pull/691#issuecomment-7162641975). Last proof after merge: the next scheduled data PR's tests check.
- **Chain after #662**, each on Ben's go and the planner's last body check: #675 (before #663; never beside #670 or #663), #670, #682 (merge outside 2026-12-03 to 2027-01-07), #663, #664, #665. Backlog, no go: #683, #687, #676, #633, #637, #644; #592 held; #620 waits on tools #242; #563 held; #595 last.
- **Test line:** tools #267 holds it (started about 12:45 UTC, 26 to 58 minutes). Next: dynasty #689, then tools #259.
- **Builders running:** b662-approles (waiting), b686-dropload, b639-gsisremap.
- **Peers:** dff-central-planner `9bcc0c9c-574c-4ebb-b4f4-18edc03af9aa`, Tools-builder-manager `dabbbcd0-2b97-445e-a2d9-4502691fb617`, Tools-central-planner `ad857488-55b0-4c62-90d5-3ee43f4e0c99`.
- **Learned this session:**
  - A builder's push form matters: only `git push` and `git push -u origin *` are allowed.
  - A push run on a later merge (here #690 touching `migrate.yml`) holds nothing once the owner's dispatch has applied the held migration.

## Queue entries raised

- #662: add the App roles tab (Action, 2026-11-24). Open. Session line `4ff97ebc-bfd4-4723-997c-406160d975ba`.
