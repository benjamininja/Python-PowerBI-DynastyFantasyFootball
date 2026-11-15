---
name: mrp-dff-code-review
description: Dynasty's code-review ruleset for the reviewer at re-proof. Load it only when a reviewer packet names it as the Ruleset, never on a general review request.
---

# mrp-dff-code-review

Dynasty's ruleset for the shared `pr-code-reviewer`. The packet, the
effort, the finding format and the one round are in `session-rules`,
`references/code-review.md`. This file says what to read, what blocks, and
what to check. Tools ADR-0015 holds the reason for the design.

## 1. What the reviewer reads

A code PR: anything under `notebooks/`, `scripts/`, `discord_bot/`,
`mouserat_trade-bud/`, `supabase/`, `pbi/mouserat2/`, `tests/`,
`.github/workflows/`, `docs/data_model.yml` (it generates the DDL), and
both `requirements.txt` files. P7 checks the requirements files; the
workflows hold the runner's permissions and secrets.

A docs-only or memory-only PR gets no full review. A PR that changes only
rule or skill text gets the light review in section 5.

The reviewer reads the diff and the code each hunk calls, not only the
changed lines: most of the bugs below sat one call away from the edit.

## 2. Blocking and advisory

- **Blocking:** a finding that can make the pipeline, the bot, trade-bud
  or Power BI show a wrong number, or lose, duplicate or mis-key rows
  without failing; or that breaks the storage seam, the identity FK or the
  EAV grain; or that leaks a value or secret. It names the input that
  triggers it. A finding with no concrete trigger is advisory.
- **Advisory:** everything else a rule below names (a test that can pass
  vacuously, a display edge case, a copied helper with no wrong output
  yet).
- **Not a finding:** style, naming the linters already cover, anything CI
  already gates (`check_pii.py`, `tests/test_storage_guard.py`, the UA
  guard test, `check_data_model.py --check`, `check_sources.py --check`),
  and design the ticket settled.

## 3. Bug patterns this project has fixed

| # | Pattern | From | Check on the diff | Class |
|---|---|---|---|---|
| P1 | Implicit row choice | #347, #295, #309 | Where a dedupe keeps one row per key (`subset=`, `keep=`, `groupby().first()/last()`, `iloc[0]` after a filter), it follows a stable sort on a total order with a named tie-break. Ask whether two rows can tie, or one player can have rows in two Conferences, or a DROPPED and a live row. A full-row `drop_duplicates` of exact duplicates needs no sort. | Blocking |
| P2 | Non-ordinal sort key | #441, #308 | A latest-row pick sorts on a typed, ordinal key. Text weeks (`PRE`, `DRAFT`, `08`), `m/d` dates and mixed formats need an explicit rank, and an unknown value raises. | Blocking |
| P3 | Null semantics in joins and compares | #368, #275, #307 | A `merge` on a nullable key drops nulls on the key side first. A Gate comparison (`>`, `!=`, `abs() >`) ORs in `isna()` on both sides. Never `zip` or `dict` two columns that were filtered separately. | Blocking |
| P4 | Identity resolution skipped | #438, #369, #309, #307 | gsis_ids are compared only after `etl.current_gsis` / `dim_gsis_link`. A reference scan covers every column with the `gsis` stem. A pfr-to-gsis lookup prefers the live row. | Blocking |
| P5 | Missing pipeline dependency | #456 | For a step added to or moved in `scripts/run_pipeline.py`: list the tables it reads, and check that every step writing one of them is in its `needs`. The step tests check only that the graph is acyclic. | Blocking |
| P6 | Silent fallback | #308, #353, #337, #296 | No `return raw` / `return df` on a mismatch branch, no store-as-is on a parse miss, no `except ImportError: pass`, no parametrized test over a list that can be empty (`assert files`). | Blocking for data; advisory for tests |
| P7 | Behaviour CI does not reproduce | #351, #260, #298 | A new import has its line in the right `requirements.txt`. Explicit dtype after `map`, `concat` or an empty frame; the empty case tested. A database read does not depend on session settings (binary reads). | A missing `requirements.txt` line: blocking everywhere. Dtype and empty frame: blocking in the seam, advisory elsewhere |
| P8 | Unbounded wait or race in the seam | #450, #337, #353 | Every write transaction sets a bounded `lock_timeout`, never `0`. A check-then-act runs in the same transaction under the lock. A stale-run count excludes runs still in flight. | Blocking |
| P9 | Grain not filled or asserted | #145 | Rows written to the EAV fact fill every grain column, and the writer asserts non-null and unique on the grain. | Blocking |
| P10 | Values or secrets in error text; weak test-DB guard | #337, #363, #353 | An exception or warn line does not interpolate a cell value, a URL with a token, or `{exc}` text that carries one. A throwaway-DB guard parses every host (`conninfo_to_dict`), not only the URL hostname. | Blocking |
| P11 | Outbound HTTP identity | #460, #436, #363 | Every request goes through `etl._make_session()` or the shared helper with `ETL_USER_AGENT`; no hard-coded browser string or copied header dict. | Advisory (a guard test exists) |
| P12 | Display of sign, NaN and inf | #295 | Money and number formatters handle negatives, NaN, `pd.NA`, inf and `-0`; a per-player card loops over every row. | Advisory |

## 4. The repo's rules the reviewer checks against

From `CLAUDE.md`:

- **Storage seam:** a table is read and written by name through
  `etl.read_table` / `etl.write_table`, never `read_parquet` /
  `to_parquet`; P7, P8 and P10 are its internals. A seam change also goes
  to the supabase-auditor, as now.
- **`etl_helpers` reuse:** logic needed by more than one notebook lives in
  `etl_helpers.py`; a copy with slight variation is a finding (#438 ruled
  no copy of the resolver; #460 removed six copied UA strings). Advisory
  unless the copy already differs in output, then blocking.
- **Transformer tables:** a new raw position or school value is a
  `dim_position` / `dim_school` row, never an if/else downstream. No fix
  since 2026-10-09 touched this rule; it stays as a check.
- **Dynasty EAV and FD rules:** new sources or metrics add rows, never
  columns; each `metric_key` maps to one `source_name`; P9 for the grain.
- **TMDL fidelity and rename cascade:** `lineageTag` / `sourceLineageTag`
  and non-AI annotations kept; a rename touches the declaration, DAX refs,
  relationships, cultures and the report (#480 is the latest miss, in the
  report half). No fix PR in the window came from a TMDL bug; #480 is the
  reason to keep it.
- **Trade-bud:** the exporter calls the router functions, and endpoint
  logic is never reimplemented in the exporter or in JS. Generated JSON
  turns non-finite floats into `null` and is dumped with
  `allow_nan=False`.
- **Bot:** no writes to GitHub. Replies go through the shared delivery
  helpers (the ones that route a reply to an ephemeral message, a DM or a
  public post), private by default; no new delivery path. Embeds are built
  against `len(discord.Embed)` and the field limits. Rendering is
  `pd.isna`-aware (P12, and P3 outside the bot).

## 5. Light review: rule and skill text only

A builder PR that changes only `CLAUDE.md`, `.claude/memory/GOAL-RUN.md`,
`CONTRIBUTING.md`, `.claude/agents/`, `.claude/skills/` or `skills/` gets
a light, low-effort review. State-backs (`PLANNER.md`, `MANAGER.md`,
`RESUME.md`) and the pipeline's data PRs get none. The reviewer checks two
things only and does not run code-review. They come from tools #113's
ruleset, its P10 and P2, which are not this skill's P2 and P10 in
section 3.

- **L1, contradiction:** text that contradicts or quietly loosens another
  rule file. Compare against `CLAUDE.md`, `GOAL-RUN.md`, `CONTRIBUTING.md`,
  `docs/PRINCIPLES.md`, the role files in `.claude/agents/` and the
  `session-rules` skill. A deleted or softened Never or denied-call line
  is blocking, with the line it loosens as the trigger, unless the PR
  cites the owner's decision on its ticket; anything else is advisory.
- **L2, tool not given:** a body asks for a tool, skill or command the
  session is not given. Compare with the role's `tools:` line and the
  builders' allow rules. Advisory for a missing tool. A tool *added* to
  `tools:` or an allow rule is blocking until the PR names the ticket line
  that asks for it.

## 6. Updating this ruleset

When a review catches the same pattern on two PRs, the manager drafts a
one-line `CLAUDE.md` rule for it, the planner reads it, and it lands like
any ruleset update. The first version of this skill added no `CLAUDE.md`
rule beyond the line naming it.
