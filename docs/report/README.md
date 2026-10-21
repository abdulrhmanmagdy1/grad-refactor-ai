# Report materials

| File or folder | Content |
|---|---|
| [report.md](report.md) | The graduation report (draft of 2026-10-21): introduction, related work, requirements, design, implementation, data, model and fine-tuning, evaluation with the frozen test-split results, testing, limitations and ethics, conclusion and references. Edit this file directly. |
| [report.pdf](report.pdf) | The same report as a 122-page A4 PDF; links to repository files point to GitHub. Rebuild it after every change with `uv run --no-project --with markdown==3.7 python docs/report/build_pdf.py` (needs Microsoft Edge or Chrome) |
| [notes/](notes/) | Each workstream's technical notes, the sources the report was written from |
| [screenshots/](screenshots/) | Screenshots of the web interface for the report and the slides |

Every number in the report links to the repository record it comes from. The final evaluation results are in [experiments/evaluation/test-2026-10-21](../../experiments/evaluation/test-2026-10-21/), and the protocol they were measured against is in [protocol](../evaluation/protocol.md). The university report template and dates are still to be confirmed; the report's structure follows the [delivery checklist](../delivery/checklist.md).
