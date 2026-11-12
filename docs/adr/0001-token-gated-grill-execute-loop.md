# Token-gated grill/execute loop with deferred Phase-0 consolidation

We run long agentic builds as a repeating loop —
`grill/plan → (Phase 0: consolidate) → compact → execute stage → compact → … → grill/plan` —
because context quality degrades and unplanned compaction risk rises well
before the window fills, so we proactively compact at a fixed token budget
rather than coasting to the limit. PLAN.md is the durable thread anchor that
survives every compaction; cost buckets and stage boundaries on it tell us where
each compact falls.

## Key parameters

- **Compact budget**: **~125K–150K tokens**, as an absolute range — supersedes
  the earlier "~35% of context window on Opus" framing (updated 2026-07-18 to
  match root `token-gating-loop.md`; that framing was model-specific and never
  actually re-tuned per model in practice). The original "slog past ~40%"
  lived signal doesn't have a clean direct token-count analog, so it's
  dropped rather than guessed at — re-add an equivalent empirical note here
  if a lived signal at the new range emerges.
- **Step cost buckets** (coarse, not exact counts — mid-run token use is
  unmeasurable and false precision is its own waste): `cheap` <2K · `med`
  2–10K · `heavy` 10K+ (whole-notebook JSON read, `/code-review`,
  pipeline-wide scan, a grill-with-docs session).
- **Stage** = the steps packed up to the budget that we commit to running
  before one compact. Steps are grouped into stages, not gated one-per-compact.

## Seam ritual (what we write before each compact)

- **PLAN.md = heartbeat**: updated at *every* seam (next stage + buckets +
  boundary markers on plan seams; done/in-progress/blockers on execute seams).
  Cheap, always-on.
- **Memory / ADR / CONTEXT = on real signal only**: consolidation is *deferred
  and batched* into **Phase 0**, which fires at a planning seam only when a
  chunk of work completed since the last consolidation. Hindsight at chunk-end
  beats guessing which lessons are durable per-execute-seam, and it keeps
  execute seams cheap.
- **Phase-0 ordering = plan → consolidate → compact**, all in one hot window:
  the just-completed chunk's full context is still live, so we plan against it
  *and* flush its durable lessons to memory/ADR/CONTEXT *before* the compact
  wipes the window. Consolidating after a compact would plan/consolidate
  against a colder window.

## Considered alternatives (rejected)

- **Coast to the context limit, rely on auto-compaction** — rejected: lossy,
  unplanned, and quality already degraded by the time it triggers (we ate one
  this session).
- **Exact per-step token estimates** — rejected: unmeasurable mid-run, false
  precision; coarse buckets are enough to place a stage boundary.
- **Consolidate inline at every execute seam** — rejected: per-seam cost +
  memory sprawl + worse signal than batched chunk-end hindsight.

## Consequences

- Don't run an execution stage in the same window as a grill session — grill
  loads docs + carries the grill/caveman skill defs, dead weight during
  execution. The grill→compact→execute seam also sheds that planning-only
  overhead.
- CLAUDE.md carries the one-line pointer to this discipline; PLAN.md carries
  the live buckets/stages/⟂ markers.

## Amendment 2026-11-12: a hard ceiling for a tracked session's clear prep (tools #148)

Ben's ruling (tools #148, issuecomment-6825758719): keep the compact budget, add a ceiling.

- **The compact budget is unchanged**: ~125K to 150K tokens is still the seam a stage aims for.
- **A new hard ceiling, about 255K tokens**, for a *tracked* session: a session started with a main-agent role (the planners, the builder manager, the consultants). By then it must prep its clear boundary: finish the current step, record, state-back, flush memory on real signal, then write its reset prompt. Stage builders are not tracked; they keep their own push-and-comment rule.
- The budget is a target; the ceiling is the latest point. A session that missed the budget does not coast past the ceiling.
- **The session does not count for itself.** The owner-queue mod measures context size and idle time and sends the prep instruction (tools #161). The other two triggers are idle 45 minutes, and Ben's ask.
- What the prep does and what a reset prompt holds live in the `session-rules` skill (tools #148, issuecomment-6825487690), not here.
