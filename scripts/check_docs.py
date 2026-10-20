"""Check local Markdown link targets; external URLs and heading anchors are excluded."""

import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
errors = []
for file in root.rglob("*.md"):
    parts = file.relative_to(root).parts
    if any(part.startswith(".") or part in {"node_modules", "dist"} for part in parts):
        continue
    for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", file.read_text(encoding="utf-8")):
        path = target.split("#", 1)[0]
        if not path or "://" in path or path.startswith("mailto:"):
            continue
        if not (file.parent / path).exists():
            errors.append(f"{file.relative_to(root)}: {target}")
if errors:
    raise SystemExit("Broken local links:\n" + "\n".join(errors))
print("Local Markdown links OK")
