"""Tests for the release manifest builder and verification script (delivery checklist)."""

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import make_release  # noqa: E402
import verify_release  # noqa: E402


def _make_tree(root: Path) -> Path:
    (root / "data").mkdir(parents=True)
    (root / "data" / "curated.jsonl").write_text('{"id": "r1"}\n', encoding="utf-8")
    (root / "data" / "manifest.json").write_text('{"records": 1}\n', encoding="utf-8")
    (root / "experiments").mkdir()
    (root / "experiments" / "results.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (root / "experiments" / "summary.json").write_text("{}\n", encoding="utf-8")
    review = root / "experiments" / "review"
    review.mkdir()
    (review / "review_summary.json").write_text("{}\n", encoding="utf-8")
    assets = root / "frontend" / "dist" / "assets"
    assets.mkdir(parents=True)
    (root / "frontend" / "dist" / "index.html").write_text("<html></html>\n", encoding="utf-8")
    (assets / "app.js").write_text("console.log(1);\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "9.9.9"\n', encoding="utf-8"
    )
    return root


def test_collect_artifacts_covers_groups_and_excludes_review_inputs(tmp_path):
    root = _make_tree(tmp_path)
    artifacts = make_release.collect_artifacts(root)

    assert artifacts == {
        "data/curated.jsonl": "dataset",
        "data/manifest.json": "dataset",
        "experiments/results.csv": "experiments",
        "experiments/summary.json": "experiments",
        "frontend/dist/assets/app.js": "frontend_dist",
        "frontend/dist/index.html": "frontend_dist",
    }
    # Review-packet inputs (review/ subdirectory) are deliberately not release artifacts.
    assert not any(path.startswith("experiments/review/") for path in artifacts)


def test_manifest_is_deterministic_and_verifies_clean(tmp_path):
    root = _make_tree(tmp_path)
    first = make_release.build_manifest(root, "9.9.9")
    second = make_release.build_manifest(root, "9.9.9")

    assert first["aggregate_sha256"] == second["aggregate_sha256"]
    assert first["groups"] == second["groups"]
    assert first["artifact_count"] == 6
    assert verify_release.verify(root, first) == []


def test_verify_reports_changed_missing_and_extra_files(tmp_path):
    root = _make_tree(tmp_path)
    manifest = make_release.build_manifest(root, "9.9.9")

    (root / "data" / "curated.jsonl").write_text('{"id": "tampered"}\n', encoding="utf-8")
    (root / "experiments" / "summary.json").unlink()
    (root / "frontend" / "dist" / "stray.css").write_text("body{}", encoding="utf-8")

    problems = verify_release.verify(root, manifest)
    assert any(p.startswith("changed: data/curated.jsonl") for p in problems)
    assert "missing: experiments/summary.json" in problems
    assert any(p.startswith("extra: frontend/dist/stray.css") for p in problems)
    assert any(p.startswith("group digest mismatch: dataset") for p in problems)
    assert "aggregate digest mismatch" in problems


def test_verify_cli_passes_on_clean_tree_and_fails_after_tamper(tmp_path, monkeypatch):
    root = _make_tree(tmp_path)
    manifest_path = root / "RELEASE_MANIFEST.json"
    manifest_path.write_text(
        json.dumps(make_release.build_manifest(root, "9.9.9"), indent=2), encoding="utf-8"
    )

    argv = [
        "verify_release.py",
        "--root",
        str(root),
        "--manifest",
        str(manifest_path),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    verify_release.main()  # clean tree: returns without raising

    (root / "experiments" / "results.csv").write_text("a,b\n9,9\n", encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        verify_release.main()
    assert excinfo.value.code == 1


def test_make_release_cli_writes_manifest_and_markdown_block(tmp_path, monkeypatch, capsys):
    root = _make_tree(tmp_path)
    output = root / "RELEASE_MANIFEST.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["make_release.py", "--root", str(root), "--output", str(output)],
    )
    make_release.main()

    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["version"] == "9.9.9"
    assert manifest["artifact_count"] == 6
    assert manifest["groups"]["frontend_dist"]["artifact_count"] == 2

    printed = capsys.readouterr().out
    assert "| `dataset` | 2 |" in printed
    assert manifest["aggregate_sha256"] in printed
