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

## CURRENT STATE (2026-11-24, twelfth save, before a clear at Ben's word; session `c2116a9a-72a7-4688-89d3-26574767e13b`)

- **Heads.** origin/main and the main checkout at `86e4d00` (PR #685). The main checkout is clean (only `.agents/` and `GEMINI.md` untracked).
- **session-dispatch** was typed by Ben in session `c2116a9a`. After the clear, Ben types it again before any dispatch, merge or closeout. Closeout words are per builder.
- **Done this session:**
  - PR #685 (#661) re-proved GREEN on base `1eda32b` (3529 passed, 0 Gate failures) and merged as `86e4d00`. The merged tree equals the re-proved tree.
  - The first migration applied on merge. Ben dispatched `migrate.yml` for the held `final_at` drop: SUCCESS.
  - The After a schema change lands check holds every line (issues/661#issuecomment-7137075042, -7137669797). #661 is closed, and b661 is closed out (recorded on #661 and #655).
  - Ben accepted two security advisor findings as by design: INFO `shared.owner_crosswalk` RLS with no policy, and WARN Auth leaked-password protection (issues/661#issuecomment-7137326774). Later checks skip them, as they skip `shared.owner`.
  - The planner ruled no action on the performance advisories, except `auth_rls_initplan`, which goes into the restated #663 (issuecomment-7137103517).
  - #662 dispatched as b662-approles. #688 dispatched as b688-migorder on Ben's go.
- **PR #684 (#597, b597-teamabbr, session `4a1fed88-8d24-4502-83c3-25eaf5bf18b3`), head `1be8dbcdebc9b1b3593ed862bb9b21d57927148b`.**
  - Restamped on Ben's word (issues/597#issuecomment-7136939338): the migration is now `20261124155956_registry_update.sql`, after main's newest. The manager checked the order.
  - Code review: no findings (pull/684#issuecomment-7136414266). Audit: F1, the Power BI column, closed as settled by #624; F2 and F3 advisory (issuecomment-7136372003). The review and audit stand for the code after the restamp.
  - Ben: merge when green (issues/597#issuecomment-7135711716).
  - **Next:** take the test line after tools #210 (start and end notices); re-prove at the head; read CI once (storage-pg was pending at the builder's read); merge pinned; pull.
  - Then give Ben the `migrate.yml` dispatch Action for the held DROP COLUMN (he chose apply after merge, issuecomment-7135625750), and run the After a schema change lands check.
  - Then dispatch #686 (go: issues/686#issuecomment-7135826055). Ask Ben for b597's closeout word.
- **PR #690 (#688, b688-migorder, session `ee0a7309-35fe-46b4-b1f3-cbbec6eec8fb`), head `8d3b1807a20dbe7d604088f038e02d978d281df8`.**
  - Code review: no findings. Audit: no blocking; F3 and F4 closed by the manager, F5 to F7 advisory (pull/690#issuecomment-7137805673, -7137791128).
  - Planner: no breach (issuecomment-7137847468).
  - **Next:** re-prove after #684 on the test line. Read `scripts/check_migration_order.py`, then run it (the builder's mode refused it). Read CI once; storage-pg was pending. Then merge.
  - It has no merge word from Ben yet: ask him by button before merging. Closeout of b688 needs his word.
- **PR #689 (#662, b662-approles, session `cad4e1c1-5c27-4f2f-8371-056a362856ed`), head `1263c4853be9fe8bb4b3238146a0b9ef8249f255`.**
  - The builder reports it green.
  - **Next:** code review (Tier medium: full, high) and supabase-auditor (it touches migrations, the generator and the registry; tell it to read only); ask the planner's read; re-prove; merge.
  - Note for the review: `tests/test_registry_keys.py` is outside the ticket's file list (one line, which the suite needs). Answers to the ticket's question are in the builder's plan comment (issues/662#issuecomment-7137065714).
  - Owner Action 1 (the App roles tab) is queued. Action 2 (loader run, `scripts/load_app_roles.py --gid <gid> --out <file outside every repo>`, then a paste into the SQL editor) is queued after the merge and the schema check.
  - #662's go covers the dispatch; ask Ben by button about the merge, unless the ticket records a merge word.
  - Tell the planner when #670's PR opens.
- **Migration order:** #684 (`20261124155956`) and #689 (`20261124160456`) are in stamp order. Merge #684 before #689, or check the order by eye again before re-proving #689. #690 adds no migration.
- **Chain after #662**, each after the one before merges: #670, then #682 (merge outside 2026-12-03 to 2027-01-07), then #663, #664, #665 (the last three need the planner's restated brief). Separately: #684 then #686. Backlog, no go: #683, #687, #675, #676, #633, #637, #639, #644; #592 held; #620 waits on tools #242; #563 held; #595 last.
- **Test line (shared with tools):** tools #210 holds it (started about 16:20 UTC, about 61 minutes). Order: tools #210, then dynasty #684, then dynasty #690 and #689. Ask Tools-builder-manager after the clear.
- **Bot:** running (`bot.py`, discord_bot `.botvenv`).
- **Builders running:** b597-teamabbr (done, waiting), b662-approles and b688-migorder (waiting on the manager).
- **Peers:** dff-central-planner (clearing; it sends its new id), Tools-builder-manager `e7026592-a1b4-4ccd-afea-61d5cf451e9f`, Tools-central-planner `2f55ae6a-00e1-46b6-9f89-e3d2d939e0de`.
- **Learned this session:**
  - `information_schema.role_table_grants` hides grants from the connector's role. Read privileges with `has_table_privilege` and `has_column_privilege`.
  - A held destructive migration makes the push job fail at its last step by design.
  - A new committed script is not on the builders' allow list, so the manager runs it at re-proof.

## Queue entries raised

- #662: add the App roles tab (Action, 2026-11-24). Open.
