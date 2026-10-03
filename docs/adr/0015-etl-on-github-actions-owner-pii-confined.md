# The ETL runs on GitHub Actions; Owner PII is confined to one table

- Status: accepted. Designed through HITL grilling on 2026-09-27 ([#87](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/87)); not yet built.
- Date: 2026-09-27
- Amends: [ADR-0014](0014-supabase-system-of-record-static-serving.md). Its rejection of "a GitHub Actions `select 1` keep-alive" was reasoned on keeping DB credentials out of Actions secrets. A remote ETL has to hold those credentials somewhere, so that reason no longer stands. The rest of ADR-0014 stands.
- Scope:
  - `scripts/run_pipeline.py` and a new Linux entrypoint
  - `.github/workflows/` (daily run, Change Poll, PII check)
  - `supabase/migrations/` (`change_poll_state`, `review_*`, `shared.owner`, `etl_run_log`)
  - the Supabase Storage `raw/` bucket

## Context

- Today the pipeline is one Windows Task Scheduler job on the owner's home PC, weekly Thursday 06:00. The owner does not want the long-term path to depend on that PC being on.
- The in-season design (#87) needs a **daily run** plus a **Change Poll** every 10 minutes in season. Both must run year-round, because the daily run's `etl_run_log` write is what keeps the Supabase Free project from pausing (ADR-0014).
- The authed Fantrax steps (`04a`/`04s`/`04t`) log in with a headless Playwright browser from `FANTRAX_EMAIL`/`FANTRAX_PASSWORD`. The code already warns about a Cloudflare/captcha gate, which is more likely from a datacenter IP.
- The repo is **public**: Actions minutes are free, and `GITHUB_TOKEN` can commit the snapshot to `main` natively.
- GitHub disables scheduled workflows in a public repo after **60 days without repository activity**. A quiet off-season with change-detected commits can reach that.
- The owner scoped confidentiality to one thing: **Owner PII** (human names, emails, Fantrax usernames). Everything else is league data. At decision time 24 manager emails were found in a tracked notebook's saved outputs, and the owner sheet is link-readable with its ID committed.

## Decision

1. **Host: GitHub Actions `schedule`.**
   - Daily run: `17 11 * * *` UTC (≈06:17 CDT / 05:17 CST, after late games go final, off the top of the hour).
   - Change Poll: every 10 min in INSEASON/PRESEASON (`3,13,…,53`), hourly in OFFSEASON; the phase check is inside the run.
   - Both share `concurrency: group: etl`, `cancel-in-progress: false`. Actions queues them, so runs never overlap.
   - **Gated by a spike**: a headless Fantrax login from a runner. If a runner is challenged, every datacenter host fails the same way; the fallback is a residential host. No CAPTCHA workarounds.
2. **The home PC is the test and fallback runner.** Both runners call one Linux-capable `run_pipeline.py` entrypoint. The Thursday task stays until cutover, then a one-week parallel run, then it is unregistered.
3. **Reliability requirements.**
   - A **dead-man's switch**: each successful run pings an external check; a missed ping (~26 h) alerts.
   - The daily run **re-enables its own workflows** via the Actions API (`PUT …/actions/workflows/{id}/enable`, `actions: write`), so the 60-day timer never fires. No filler commits, no third-party keepalive action.
   - `workflow_dispatch` on every workflow, for manual re-runs.
4. **Security requirements.**
   - **Owner PII lives only in `shared.owner`** (`owner_id`, `team_key`, `human_name`, `email`, `fantrax_username`). RLS on; no grant to any read or anon role; never exported to the snapshot or to raw storage. Team names, abbreviations and Fantrax team ids are public identity.
   - A **CI PII check** (and pre-commit hook) fails any commit containing an email pattern or a known `human_name`/`fantrax_username`. It runs inside the data-commit job *before* the push, and on every PR.
   - The ETL uses a **least-privilege Postgres writer role**, never the `service_role` key.
   - Actions hygiene: secrets in a `main`-only environment, per-job `permissions:`, third-party actions pinned by SHA, no `pull_request_target`.
5. **State that used to be local disk moves to Supabase.**
   - `change_poll_state` (per-team roster hash + debounce state).
   - Review queues as `review_*` tables, resolved rows marked `resolved_at`.
   - Raw payloads to a private Storage bucket `raw/`, gzipped: dailies 14 days, period-closing pulls and failed runs kept. Owner PII is stripped at capture, before upload.

## Alternatives considered

- **Keep the home PC as the host.** Rejected: the owner wants the pipeline independent of the PC.
- **Railway cron beside the bot.** Rejected: usage cost, a separate PAT for the push, and the same datacenter-IP login risk. More precise timing is not needed at a 10-minute poll.
- **A self-managed VPS.** Rejected: maintenance burden for no gain at this scale.
- **Actions artifacts for raw payloads and review queues.** Rejected: artifacts on a public repo are readable by any signed-in GitHub user, expire within 90 days, and give review resolutions no path back.
- **A weekly keep-alive job.** Rejected: a 7-day cadence against Supabase's 7-day pause has no margin, and the job would itself be disabled at GitHub's 60 days.
- **Treating any string containing an owner's name as PII.** Rejected: it would force hashing team names out of the snapshot and break the bot and app.

## Consequences

- ADR-0014's "DB credentials stay out of Actions secrets" no longer holds. The credentials live in a `main`-only environment instead.
- Map #69 gains `change_poll_state`, `review_*`, `shared.owner` and the `raw/` bucket. `01c` stops reading manager emails from the sheet; owners are maintained in `shared.owner`.
- Discord posts only on events (failure, period close, drift, poll-triggered run). Silence means success, which is why the dead-man's switch is required. *[ADR-0008's amendment](0008-regression-testing-standard.md#amendment-2026-10-03-publish-gate-post-run-checks-ci-88) (decision 12) adds one daily-digest line: counts of new Review findings, only when there are any.*
- Freshness is bounded by the poll (10 min + a one-poll debounce) plus ~2 min for publishing.
- Docs and commits refer to people by role, not by name.
