# Data preparation plan

## Record format

Each record contains id, source_group, split, prompt, completion, license, and refactoring_type. The prompt includes the task and original code. The completion is a reviewed reference output. A separate manifest records source URLs, commits, and reference tests.

## Collection and curation

Use sources with terms compatible with the intended training and distribution. Record the license for each source; public availability on GitHub is not a substitute for a license review.

Check Python syntax before and after each change. Exclude functional changes, ambiguous examples, credentials, and personal data. Manually prepared teaching examples or controlled transformations are possible if reviewed. Correctness and source diversity matter more than an untested volume target.

## Splitting and leakage checks

Begin with a candidate 80/10/10 train/validation/test split by repository or example family, not by randomly distributing rows. Review the ratio against the available sample size. A source_group must not cross splits.

Check duplicate prompts and targets and investigate near-duplicates. The current validation script detects normalized exact duplicates and overlapping groups; it does not detect semantic similarity. A stronger near-duplicate check remains a data task.

Use validation data for selection. Freeze test data before final model and prompt choices. Save dataset hashes and split manifests. Do not reuse test examples as prompt demonstrations while tuning.

## Data acceptance

Require clear provenance and licensing, a recorded sample review, complete fields, valid reference code, source-separated splits, a curation log, and reference tests for behavior-preservation measurements. Final dataset size depends on the sources and feasibility results.

## GitHub storage

Small permitted examples and manifests may be committed. Larger permitted data requires a Releases or LFS quota check. If the free allowance is insufficient, reduce the dataset or agree on reproducible source-download scripts. No paid storage or additional external storage service has been approved.
