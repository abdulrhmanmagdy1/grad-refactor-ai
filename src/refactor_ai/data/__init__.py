"""Dataset curation for the guard_clauses task (data and evaluation workstream).

The package builds datasets/guard_clauses/v1 reproducibly: team-authored template
families and qualifying functions from licensed datasets are filtered with the shared
task definition, given trusted reference tests by a curation-only executor, split by
source group, checked for duplicates and written with a hashed manifest. The entry point
is scripts/curate_dataset.py; refactor_ai.data.curate holds the pipeline.
"""
