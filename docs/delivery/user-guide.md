# Foundation user guide

The current service supports environment verification and static analysis. It does not yet provide a refactoring product.

Follow the setup guide, open http://127.0.0.1:8000/docs, select POST /api/v1/analyze, and choose Try it out. Submit Python text in the code field. Inspect syntax_valid, findings, and error.

No model or API key is needed. Findings are limited structural heuristics and do not cover every code-quality issue. The foundation does not modify code, download a refactoring, run user tests, or start training.

The planned interface will support code input, a diff, an explanation, verification results, and user acceptance or rejection. Update this guide when that behavior is implemented and verified.
