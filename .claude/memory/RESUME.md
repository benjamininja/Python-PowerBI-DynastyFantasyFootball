# RESUME — trade-bud post-merge walkthrough (2026-08-03, session 2)

**Files touched this session**: `mouserat_trade-bud/frontend/index.html`
(uncommitted, local `main`), `.claude/memory/mouserat-trade-bud.md`,
`PLAN.md`.

**Next task**: Ask Ben which exact screen/player showed the "$0 minor league
contract" and whether a hard browser refresh (Ctrl+Shift+R) resolves it —
every layer checked on disk (source data, exported JSON, served HTML) is
already correct, so the report is unexplained, not yet fixed.

## Code changed this session (all in `index.html`, uncommitted)

1. Removed the Counterparty "No reliable data signal" helper panel
   (`renderProfile`) — confidence chips already convey it.
2. Fixed `onTeamChange`: now clears `state.give` when `myTeam` changes and
   `state.receive` when `cpTeam` changes (previously stale basket assets
   lingered after a team swap and still counted in cap math).

Both fixes are **not yet reflected in the served `_site/` build** — run
`python export_static.py` from `mouserat_trade-bud/` then restart
`python -m http.server --directory _site 8500` before asking Ben to
re-verify.

## Open, unresolved (investigate first, don't re-fix blind)

"Minor league contracts are $0 again" — checked:
- `data_access.roster_with_cap_hit()`: Minors rows have real non-zero
  `contract_value` (e.g. `9,703,000`).
- `_site/data/assets/A10.json`: same, correct on disk.
- `_site/index.html`: Salary column already reads `a.contract_value`, not
  `cap_hit`.
- Running `http.server` (was PID 49992) confirmed serving the right
  directory (`mouserat_trade-bud/_site`).

Nothing found explains the report. Do not assume "already fixed" — ask Ben
for the exact screen/player and try a hard refresh before further code
changes.

## Test / verify command

```
cd mouserat_trade-bud
../.venv/Scripts/python.exe export_static.py
../.venv/Scripts/python.exe -m http.server --directory _site 8500
```
Then open `http://127.0.0.1:8500/` and re-run the walkthrough.
