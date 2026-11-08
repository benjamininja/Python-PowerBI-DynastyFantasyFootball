"""Retired (#431). Do not run.

This script typed a decision into DECISIONS and wrote the crosswalk and
fact_fantrax_adp directly, so the next 04z rebuild dropped any fix that was not
also in the old CSV. Its 33 decisions are in ops.dim_fantrax_crosswalk_override,
which 04z reads first.

A new override is recorded from GitHub: Actions, "Record a crosswalk override",
Run workflow, on main. It writes one row through the storage seam
(scripts/record_crosswalk_override.py).
"""
raise SystemExit(
    "retired: record a crosswalk override from GitHub (Actions, Record a crosswalk override)")
