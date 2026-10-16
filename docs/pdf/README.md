# Download the project documents

1. [Complete project documentation](01-project-documentation.pdf): the proposal, requirements, architecture, development environment, data and training plans, evaluation, risks, supervisor reviews, and delivery checklist.
2. [Team delivery plan](02-team-delivery-plan.pdf): one clear main workstream per member, expected outputs in every phase, component handoffs, and the named GitHub task allocation.

Version 0.3 is a planning edition. The trained model, final evaluation, and complete product are not delivered yet. PDF bookmarks support navigation, and source links open the editable documents on GitHub.

The PDFs explain the plan. GitHub Issues and the Project board show current execution. Sources remain under docs/ and should be updated before regenerating the PDFs. Each task has one owner; second-person approval is not required. Supervisor reviews remain scheduled after each phase.

This edition uses a 21-day delivery plan. The optional agent execution folder is maintained separately under [docs/agent-execution](../agent-execution/README.md).

## Regenerate the PDFs

From the repository root, use a separate tool environment so PDF tooling does not change the core lockfile:

```bash
uv run --no-project --with reportlab==4.4.9 --with pypdf==6.10.0 python scripts/export_docs_pdf.py
```

Render every resulting page with Poppler and inspect layout before publication. The exporter refreshes page counts, source hashes and file hashes in manifest.json. Its edition label must be updated deliberately for future editions.
