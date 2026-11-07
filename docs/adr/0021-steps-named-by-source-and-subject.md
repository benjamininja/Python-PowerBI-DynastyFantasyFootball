# Steps are named by source and subject, grouped in domain folders, and described by one registry

- Status: accepted. Decided in the owner grill on map [#375](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/375) of 2026-11-07 (questions 1 to 35); not yet built.
- Date: 2026-11-07
- Amends: [ADR-0020](0020-daily-runs-weekly-finals.md) decision 3 (a step's cadence is declared in the registry, with more values). No decision is reversed.
- Scope:
  - the names and folders of pipeline steps
  - `docs/steps.yml`, the registry of every flow
  - how Run Tier, Chain and Source are shown
  - `CONTEXT.md` (Domain, Source, Depends On, Run Tier, Cadence)

## Context

- The `01` to `04` prefixes encoded order, table type and subject all at once. Each change to one of them forced renames across notebooks, docs and the run order. That is the sprawl.
- Order is not a property of a name. It is what a flow depends on.
- Facts about a flow (its sources, cadence, login, chain) lived in several places and drifted.

## Decision

1. **Step names are `<source>_<subject>`, with no numbers.**
2. **A folder per Domain.** The Domains are League, Rosters, Players, Rookies and Apps.
3. **`docs/steps.yml` is the single source of truth for every flow.** Per flow it records: domain, sources, chain, cadence and window, depends_on, login, and the reason for any manual step.
4. **Run Tier is computed from Depends On and never typed.** It is 0 for a flow that depends on nothing, otherwise one more than the highest tier it depends on.
5. **Chain stays the internal publish unit and is hidden in apps. Source is shown.**
6. **Cadence values are Daily, Close Day, Annual and Manual,** optionally within a season window. Annual runs on a named league event, not a calendar date. Manual is on demand by design, with the reason recorded.

## Alternatives considered

- **Keep the numbers.** Rejected: they are the source of the renames and say nothing about what a step reads.
- **Put the tier or cadence in names.** Rejected: both change without the step changing, so each change would rename it again. Both are registry facts.
- **Type the Run Tier in the registry.** Rejected: a typed tier can disagree with Depends On. Computed, it cannot.

## Consequences

- Renaming existing steps, creating `docs/steps.yml` and moving files into Domain folders are separate tickets. This ADR changes no code.
- A new flow is one registry entry and one folder placement; nothing else encodes its order.
- Owners see Source, never Chain, in apps.
