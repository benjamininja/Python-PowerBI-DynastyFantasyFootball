# Running the pipeline

!!! note "Stub"
    This page will explain how the scheduled run works, which steps stay
    manual and how to run the checks. Until it is written, see the
    [README](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball#running-the-pipeline)
    and
    [notebooks/README.md](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/blob/main/notebooks/README.md).

What will be here:

- What `scripts/run_pipeline.py` does: it runs the scheduled steps in
  dependency order, checks each group of tables before publishing it, and
  lands only the groups that passed.
- Which steps stay manual by design: the live draft, the rankings that arrive
  as Excel files, and the review of uncertain player matches.
- How to run the checks without running any step.
