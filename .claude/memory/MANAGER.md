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
- **Merge (since PRs #694 and #703):** one read of
  `gh pr view <n> --json mergeStateStatus,statusCheckRollup`. Every check
  SUCCESS with no conflict is Green. Post a short Green note on the PR,
  merge squash pinned with `--match-head-commit`, then `git pull
  --ff-only` and read CI on main's new commit. `scripts/reproof.py` is
  only for chasing a failure CI shows; its review-finding lines hold row
  keys, so post counts only.
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


## CURRENT STATE (2026-11-25, fourteenth save, before a compact at Ben's word; session `4ff97ebc-bfd4-4723-997c-406160d975ba`)

- **Heads.** origin/main and the main checkout at `1fb63c5` (PR #703). The main checkout is clean apart from the untracked `.agents/` and `GEMINI.md`.
- **The rules changed today** (GOAL-RUN.md, PRs #694 and #703, on Ben's priority: "we are completing work but never completing the endless scans"):
  - Green is every CI check SUCCESS at the head with no conflict, on one read. The `checks` job (#696) runs the data-model, sources and Gate checks.
  - No local full run and no test line for a merge. A merged tree is not proved again.
  - After each merge, read CI on main. Red means a revert PR, or a fix forward for a migration. Two PRs that are each green alone can break main together.
  - The schema check is the push job plus the advisors. The full live read happens only after hand-run SQL or on Ben's word.
  - One merge word in the manager's chat may name several PRs.
  - A PR whose head predates `ab407ed` has no `checks` job: run the three scripts at the head merged with main, or have the builder merge main (planner's ruling, pull/703#issuecomment-7165536667).
  - Shared rules (tools #273, proposed): one reviewer, no advisory rounds.
  - Every ask of Ben is an AskUserQuestion pop-up with summary, pros, cons and recommendation.
- **Merged this session:**
  - #690 `8e217ed`; #689 `dc3e2fc` (Ben's hand; the late re-proof is GREEN, issues/662#issuecomment-7164344316); #692 `d53b9ab`; #696 `ab407ed`; #693 `907cf3b`; #704 `ccbef36`.
  - The planner merged #694 `7129864`, #698 `7e4ac53` and #703 `1fb63c5`.
- **Closed out:** b597, b688, b662, b686, b695, b581, b639.
- **CI on main:** `ab407ed`, `7e4ac53` and `907cf3b` are SUCCESS. `ccbef36` and `1fb63c5` `tests` were still running at this save. **Read them first.**
- **Builders running:**
  - **b700-autoload**: #700, PR #710, session `4c6c146d-928f-42b2-82ae-70ab4e900fd4`.
    - It builds the automated App roles and owner crosswalk loads through two locked definer functions.
    - Ben's Decision (issues/700#issuecomment-7165832748): the migration gate exempts only `shared.load_app_roles` and `shared.load_owner_crosswalk` by name. ADR line PR #708; the planner merges it on Ben's word.
    - Ben's word: "merge #700 when green" (issuecomment-7166200476). It merges after #708, with the supabase-auditor's review (one reviewer) and no upheld blocking finding.
    - The migration-order check applies. After the merge: the push job, plus advisors; the last proof is the scheduled run's notice showing the two counts.
  - **b699-pgfast**: #699, PR #709, session `a6adfc56-b0ed-4316-94d5-5bd6b7c22a10`.
    - storage-pg under 8 minutes with the same pg tests collected.
    - Ben's word: merge when green (issues/699#issuecomment-7165629265). One reviewer.
- **The planner's open PRs** (the planner merges, not the manager): #705 (CLAUDE.md Git sentence for the re-key exception) and #708 (the ADR-0018 line).
- **#662:** Ben's Decision was to automate the load and skip the hand run (issuecomment-7164106424). #700 does it. The App roles gid is `1489461039`. #662 closes once #700 lands.
- **#691 (data PR):** it waits for a refresh that runs with #693's remap. Its rows stay on the old id until then.
- **Tickets with no go yet:** #697 (current_gsis gap, medium, after #693), and the planner's sweep of other hand-run loads. Chain from earlier, each on Ben's go: #675, #670, #682, #663, #664, #665. Backlog: #683, #687, #676, #633, #637, #644; #592 held; #620 waits on tools #242; #563 held; #595 last.
- **Peers:**
  - dff-central-planner `9bcc0c9c-574c-4ebb-b4f4-18edc03af9aa`
  - Tools-builder-manager `dabbbcd0-2b97-445e-a2d9-4502691fb617`
  - Tools-central-planner `2c14b7ab-3b12-4984-ae56-5c6526f96566` (new after its clear)
- **Notices:**
  - The machine's GitHub login is the narrowed token (tools #204). A refused call that used to work is a finding for the Tools planner, not a retry.
  - tools #272 changed session-rules (start-up read budget, after-compact rule); a new session loads it.
- **Bot:** bot.py in a terminal tab of this session. Check it after a clear.
- **Learned:**
  - `gh pr merge --squash` without `--delete-branch` is fine: GitHub deletes the head branch on merge, and a later `git push --delete` is refused.
  - At closeout, a diff of a builder's files against main can show lines from a PR merged after the branch was cut. Compare with the squash commit before deciding anything is missing.
  - `run_pipeline.py --check-only` counts every review finding as new in a fresh checkout. Only Gate failures fail it.

## Queue entries raised

- None open. The #662 App roles tab Action is done, and Action 2 was withdrawn by Ben's Decision to automate.
