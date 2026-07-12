# ADR-0009: First subagent roster (subagent-audit outcome)

**Status:** proposed (files written 2026-07-12, not yet committed — repo's
"commit only when asked" rule)

**Context:** First run of the `subagent-audit` skill (authored in
`skills-plugins-hooks-agents`, PR #22) against this repo as its acceptance
test. The skill scans six categories with a hard hook-vs-skill-vs-subagent
boundary and caps the roster at 3–5. This ADR records both the accepted
candidates and the rejected-with-reason ones, so later sessions don't
re-propose them.

## Decision — two subagents, defined in `.claude/agents/`

1. **`fantrax-payload-analyst`** (categories A + C, merged): context
   firewall and schema analyst for `data/raw/` external payloads.
   Evidence: `fantrax_playerstats_2025_YTD.json` is **31.7MB** and
   `fantrax_draftranks_2026_wkPRE.json` **16.5MB** — a single direct read
   floods any context window, yet their shape governs the parsers in
   `04a`/`04w`/`03c`/`04z` and `etl_helpers.py`, and drift is a live risk
   (the `dim_fantrax_crosswalk`/`04z` universe fix was exactly a shape
   mismatch). A merged the two categories: the same agent that samples the
   payload is best placed to emit the typed model and drift notes.
   Read-only tools; `model: haiku` (sampling + schema transcription, not
   deep judgment); background by default, foreground when the main agent
   is blocked on the shape.

2. **`cap-ledger-auditor`** (category B): adversarial auditor for
   cap/contract/ledger logic (`capmath.py`, `cap.py`, `roster.py`, `02d`,
   `02e`, dead-money measures), grounded in `CONTEXT.md`, ADR-0003/0004/
   0006/0008 and `.claude/memory/data-model.md`. Evidence for builder
   bias being a real failure mode here: `capmath.py` silently escaped
   `offline_smoke.py`'s `fetch_parquet` monkeypatch and made real GitHub
   calls with a fake token until the ADR-0008 retrofit caught it.
   Read-only; `model: sonnet` (needs real judgment); foreground pre-merge
   (its result gates the merge).

## Rejected candidates (with reasons — don't re-propose without new evidence)

- **D, MCP wrapper:** no MCP server is project-configured (no `.mcp.json`);
  Microsoft Learn MCP is read-only docs (no wrapping value); FabricIQ is
  unauthenticated here; Fabric REST operations are already governed by the
  `powerbi-report-management` skill's scoped `az rest` patterns. No live
  broad-access surface to firewall today.
- **E, background docs/test writer:** the deterministic layer already
  exists and is active (pre-commit: pytest per ADR-0008, `check_sources.py`
  per ADR-0007, `check-in-hygiene`); test *authorship* belongs in the main
  thread via the `tdd` skill at agreed seams. A background writer would
  also collide with the single-author-notebook workflow.
- **F, parallel dispatch:** the notebook pipeline is stage-ordered
  (`01* → 02* → 03* → 04* → 05*`) with a shared `etl_helpers.py` seam —
  not zero-shared-state — and no identical cross-file fix is pending.
- **`en-US.tmdl` firewall (A):** the 947KB culture file is generated; the
  correct control is "never read it", a one-line CLAUDE.md guardrail, not
  an agent.
- **Notebook-output extractor (A):** measured, not assumed — the largest
  `.ipynb` is 87KB; partial reads suffice.
- **`skills/Instructions-PowerBI-Visuals-Deneb-HTML.md`:** an orphan
  project-local skill doc, not a subagent candidate — flagged to the
  central catalog's "orphan project-skill detection" backlog instead.

## Consequences

- First `.claude/agents/` content in any of this user's repos; the central
  catalog repo will use this as the exemplar for whether it grows an
  `agents/` directory.
- Both agents are read-only by design; neither can conflict with files the
  main agent is editing, so the background-edit-collision guardrail is
  satisfied structurally.
