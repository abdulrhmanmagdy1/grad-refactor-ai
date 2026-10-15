# Working together

Start from the assigned Issue and confirm its dependencies and acceptance criteria. Each member owns a main workstream and normally keeps one primary implementation task active.

## Publish work

```bash
git switch main
git pull --ff-only
git switch -c feat/123-short-description
```

Keep the change focused, run the relevant checks, and update its documentation. Open a linked pull request using Closes #123 so the team can see the output and automated checks. A second-person approval is not required; the task owner checks the result and merges it when ready. Do not force-push main.

Research and meeting tasks can be completed with a linked record instead of code. Uploading a file alone is not completion: the result must meet the stated acceptance criteria. Training work includes versions, settings, artifacts, and actual results.

## Status

Backlog is planned work. Ready means dependencies allow it to start. In Progress means work has begun. In Review is optional for a result awaiting a decision or supervisor feedback; it does not create a peer-review assignment. Done means the owner has completed the acceptance checks and published the output.

Record blockers and the help needed in the Issue. The Project helps update status automatically, but owners keep it accurate. Every phase ends with a supervisor review and recorded decisions.

## Data and execution

Do not commit credentials, private contact details, unlicensed data, or large model weights. Record small sanitized experiment logs and checksums. The API must not execute submitted code. Enable a separate runner only after completing its isolation checks on trusted examples.
