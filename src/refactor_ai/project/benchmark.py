"""The seeded-project benchmark of the project review (protocol project-bench-v1).

Each benchmark project is a small Python package with known problems written into it, a
manifest that says where they are, hidden tests that fail because of the seeded bugs, and a
reference fix that makes them pass. The reviewer sees only the package and its visible
tests; the hidden tests and the manifest are used afterwards to score what it found and
whether its fixes work. See docs/evaluation/project-benchmark.md.
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import math
import re
import tempfile
import time
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from refactor_ai.project import static
from refactor_ai.project.index import build_index
from refactor_ai.project.models import Category, Finding, Fix
from refactor_ai.project.review import ProjectReviewer, ReviewSettings
from refactor_ai.project.service import apply_recorded_fix
from refactor_ai.project.testrun import ProjectTestRunner, TestReport
from refactor_ai.project.workspace import IntakeError, Workspace, extract_project

# v1 froze the test split with prompt version project-v3; v2 adds the spec tests
# (project-v4) and a second, new test split; v3 adds mypy and spec-test repair (project-v5)
# with a third split.
PROTOCOL_ID = "project-bench-v3"
DATASET_ROOT = Path("datasets") / "project_bench" / "v1"
SPLITS = ("dev", "test", "test2", "test3")
# Splits that run only under a freeze record.
FROZEN_SPLITS = ("test", "test2", "test3")
MANIFEST = "manifest.json"
HIDDEN_SOURCE = Path("hidden") / "test_hidden.py"
# The hidden tests are copied to the project root under this name and run on their own,
# in a separate process from the visible tests, so neither can change the other's state.
HIDDEN_TEST_NAME = "test_zz_benchmark_hidden.py"
KEEP_PREFIX = "test_keep_"
# A finding counts as pointing at a seeded place when its lines come within this distance.
LINE_TOLERANCE = 2
SKIPPED_PARTS = frozenset({"__pycache__", ".pytest_cache", ".ruff_cache"})
READY = "proposal_ready"


# --- manifest ------------------------------------------------------------------------------


class Location(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str = Field(description="Path relative to the project folder, with forward slashes")
    lines: tuple[int, int] = Field(description="First and last line, 1-based and inclusive")

    @model_validator(mode="after")
    def _ordered(self) -> Location:
        if not 1 <= self.lines[0] <= self.lines[1]:
            raise ValueError("lines must be [start, end] with 1 <= start <= end")
        if "\\" in self.file or self.file.startswith("/"):
            raise ValueError("file must be a relative path with forward slashes")
        return self


class Issue(Location):
    id: str = Field(pattern=r"^[A-Z][0-9]{1,2}$")
    category: Literal["bug", "security", "architecture", "quality"]
    kind: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    anchor: str = Field(min_length=3, description="Exact text found inside the lines")
    symbol: str | None = Field(default=None, description="Qualified name of the function")
    modules: list[str] = Field(default_factory=list, description="Architecture issues only")
    other_locations: list[Location] = Field(default_factory=list)
    description: str = Field(min_length=10)
    fix_hint: str | None = None
    fixable_in_function: bool = False
    hidden_tests: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> Issue:
        if self.category == "architecture" and not self.modules:
            raise ValueError(f"{self.id}: an architecture issue names its modules")
        if self.fixable_in_function != bool(self.hidden_tests):
            raise ValueError(f"{self.id}: hidden_tests are given exactly for fixable issues")
        if self.fixable_in_function and not self.symbol:
            raise ValueError(f"{self.id}: a fixable issue names its function")
        for name in self.hidden_tests:
            if not name.startswith(f"test_{self.id}_"):
                raise ValueError(f"{self.id}: hidden test {name} must start with test_{self.id}_")
        return self


class Decoy(Location):
    id: str = Field(pattern=r"^D[0-9]{1,2}$")
    anchor: str = Field(min_length=3)
    why_it_is_fine: str = Field(min_length=10)


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    description: str
    author: str
    issues: list[Issue] = Field(min_length=1)
    decoys: list[Decoy] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique(self) -> Manifest:
        ids = [item.id for item in [*self.issues, *self.decoys]]
        if len(ids) != len(set(ids)):
            raise ValueError("issue and decoy ids must be unique")
        return self

    @property
    def fixable(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.fixable_in_function]


# --- projects --------------------------------------------------------------------------------


def _normalized(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


@dataclass(frozen=True)
class BenchProject:
    root: Path
    manifest: Manifest

    @classmethod
    def load(cls, root: Path) -> BenchProject:
        data = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
        manifest = Manifest.model_validate(data)
        if manifest.name != root.name:
            raise ValueError(f"{root}: manifest name {manifest.name!r} is not the folder name")
        return cls(root, manifest)

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def project_dir(self) -> Path:
        return self.root / "project"

    @property
    def reference_dir(self) -> Path:
        return self.root / "reference"

    def files(self, folder: Path | None = None) -> list[str]:
        folder = folder or self.project_dir
        if not folder.is_dir():
            return []
        return sorted(
            path.relative_to(folder).as_posix()
            for path in folder.rglob("*")
            if path.is_file() and not SKIPPED_PARTS & set(path.relative_to(folder).parts)
        )

    def zip_bytes(self) -> bytes:
        """The project as a user would upload it (line endings normalized)."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for relative in self.files():
                info = zipfile.ZipInfo(relative, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, _normalized((self.project_dir / relative).read_bytes()))
        return buffer.getvalue()

    def hidden_source(self) -> str:
        return (self.root / HIDDEN_SOURCE).read_text(encoding="utf-8").replace("\r\n", "\n")

    def reference_files(self) -> dict[str, str]:
        return {
            relative: (self.reference_dir / relative)
            .read_text(encoding="utf-8")
            .replace("\r\n", "\n")
            for relative in self.files(self.reference_dir)
        }

    def sha256(self) -> str:
        """Hash of every file of the benchmark project (manifest, code, hidden tests, fix)."""
        digest = hashlib.sha256()
        for path in sorted(p for p in self.root.rglob("*") if p.is_file()):
            relative = path.relative_to(self.root)
            if SKIPPED_PARTS & set(relative.parts):
                continue
            digest.update(relative.as_posix().encode() + b"\0")
            digest.update(hashlib.sha256(_normalized(path.read_bytes())).digest())
        return digest.hexdigest()


def load_split(split: str, root: Path = DATASET_ROOT) -> list[BenchProject]:
    folder = root / split
    if not folder.is_dir():
        return []
    return [
        BenchProject.load(path)
        for path in sorted(folder.iterdir())
        if path.is_dir() and (path / MANIFEST).is_file()
    ]


# --- tests -----------------------------------------------------------------------------------


def short_name(full: str) -> str:
    """'tests.test_x::TestA::test_b[1]' -> 'test_b'."""
    return full.rsplit("::", 1)[-1].split("[", 1)[0]


@dataclass
class TestOutcome:
    __test__ = False  # not a pytest test class

    status: str
    hidden_passed: set[str] = field(default_factory=set)
    hidden_failed: set[str] = field(default_factory=set)
    visible_passed: set[str] = field(default_factory=set)
    visible_failed: set[str] = field(default_factory=set)
    detail: str = ""

    @classmethod
    def from_reports(cls, visible: TestReport, hidden: TestReport) -> TestOutcome:
        """A project without visible tests counts as a run with none."""
        ran = hidden.status == "ran" and visible.status in ("ran", "no_tests")
        details = [
            f"{label}: {r.status} {r.detail}".strip()
            for label, r in (("visible", visible), ("hidden", hidden))
            if r.status not in ("ran", "no_tests")
        ]
        outcome = cls(status="ran" if ran else "error", detail="; ".join(details))
        outcome.visible_passed = set(visible.passed)
        outcome.visible_failed = visible.failed | visible.errors
        outcome.hidden_passed = {short_name(full) for full in hidden.passed}
        outcome.hidden_failed = {short_name(full) for full in hidden.failed | hidden.errors}
        # A parametrized test passes only when every case passes.
        outcome.hidden_passed -= outcome.hidden_failed
        return outcome

    @property
    def keep_passed(self) -> set[str]:
        return {name for name in self.hidden_passed if name.startswith(KEEP_PREFIX)}


def run_with_hidden(
    runner: ProjectTestRunner, root: Path, project: BenchProject, changed: dict[str, str]
) -> TestOutcome:
    """The visible tests, then the hidden tests alone, on copies of `root` with `changed`."""
    visible = runner.run(root, changed)
    hidden = runner.run(
        root, {**changed, HIDDEN_TEST_NAME: project.hidden_source()}, (HIDDEN_TEST_NAME,)
    )
    return TestOutcome.from_reports(visible, hidden)


def resolved_issues(project: BenchProject, outcome: TestOutcome) -> set[str]:
    """Fixable issues whose hidden tests all pass."""
    return {
        issue.id
        for issue in project.manifest.fixable
        if set(issue.hidden_tests) <= outcome.hidden_passed
    }


def broken_tests(baseline: TestOutcome, after: TestOutcome) -> list[str]:
    """Keep tests and visible tests that passed before and do not pass now."""
    if after.status != "ran":
        return [f"(the tests could not run: {after.status} {after.detail})".strip()]
    lost = (baseline.keep_passed - after.hidden_passed) | (
        baseline.visible_passed - after.visible_passed
    )
    return sorted(lost)


# --- validation ------------------------------------------------------------------------------


def function_sources(source: str) -> dict[str, str]:
    """Qualified name -> source text of every function and method."""
    tree = ast.parse(source)
    found: dict[str, str] = {}

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{prefix}{child.name}"
                found[name] = ast.get_source_segment(source, child) or ""
                visit(child, f"{name}.")
            elif isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}.")

    visit(tree, "")
    return found


def _region(lines: list[str], location: Location) -> str | None:
    start, end = location.lines
    if end > len(lines):
        return None
    return "\n".join(lines[start - 1 : end])


@dataclass
class Validation:
    project: str
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def validate(
    project: BenchProject, runner: ProjectTestRunner | None = None, *, run_tests: bool = True
) -> Validation:
    """Check a benchmark project: places, hidden tests, reference fix, static findings."""
    result = Validation(project.name)
    problems = result.problems
    manifest = project.manifest
    with tempfile.TemporaryDirectory(prefix="bench-validate-") as temp:
        try:
            workspace = extract_project(project.zip_bytes(), Path(temp) / "project")
        except IntakeError as exc:
            problems.append(f"the project is not accepted for upload: {exc}")
            return result
        index = build_index(workspace)
        functions = {(f.file, f.qualname): f for f in index.functions}
        texts = {file: workspace.read(file).splitlines() for file in workspace.files}

        for item in [*manifest.issues, *manifest.decoys]:
            places = [item, *getattr(item, "other_locations", [])]
            for place in places:
                if place.file not in texts:
                    problems.append(f"{item.id}: {place.file} is not in the project")
                elif _region(texts[place.file], place) is None:
                    problems.append(f"{item.id}: lines {list(place.lines)} are past the end")
            if item.file in texts:
                region = _region(texts[item.file], item)
                if region is not None and item.anchor not in region:
                    problems.append(
                        f"{item.id}: anchor {item.anchor!r} is not in lines {item.lines}"
                    )
        for issue in manifest.issues:
            if issue.symbol:
                function = functions.get((issue.file, issue.symbol))
                if function is None:
                    problems.append(f"{issue.id}: no function {issue.symbol} in {issue.file}")
                elif (
                    not function.line_start <= issue.lines[0] <= issue.lines[1] <= function.line_end
                ):
                    problems.append(
                        f"{issue.id}: lines {list(issue.lines)} are not in {issue.symbol}"
                    )
            for module in issue.modules:
                if module not in index.modules:
                    problems.append(f"{issue.id}: module {module} is not in the project")

        _check_hidden(project, problems)
        _check_reference(project, workspace, problems)
        _check_static(project, workspace, index, result)

        if run_tests:
            _check_tests(project, workspace, runner or ProjectTestRunner(), result)
    return result


def _check_hidden(project: BenchProject, problems: list[str]) -> None:
    path = project.root / HIDDEN_SOURCE
    if not path.is_file():
        problems.append(f"{HIDDEN_SOURCE.as_posix()} is missing")
        return
    tree = ast.parse(project.hidden_source())
    names = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test")
    }
    if any(isinstance(node, ast.ClassDef) for node in tree.body):
        problems.append("hidden tests must be top-level functions")
    listed = {name for issue in project.manifest.issues for name in issue.hidden_tests}
    for name in sorted(listed - names):
        problems.append(f"hidden test {name} is listed but not defined")
    for name in sorted(names - listed):
        if not name.startswith(KEEP_PREFIX):
            problems.append(f"hidden test {name} is neither listed nor a {KEEP_PREFIX}* test")
    if not any(name.startswith(KEEP_PREFIX) for name in names):
        problems.append(f"there is no {KEEP_PREFIX}* test")


def _check_reference(project: BenchProject, workspace: Workspace, problems: list[str]) -> None:
    reference = project.reference_files()
    fixable_files = {issue.file for issue in project.manifest.fixable}
    for file in sorted(fixable_files - set(reference)):
        problems.append(f"the reference fix does not change {file}")
    for file, text in reference.items():
        if file not in workspace.files:
            problems.append(f"the reference changes {file}, which is not in the project")
            continue
        try:
            fixed = function_sources(text)
        except SyntaxError as exc:
            problems.append(f"the reference {file} does not parse: {exc}")
            continue
        allowed = {i.symbol for i in project.manifest.fixable if i.file == file}
        original = function_sources(workspace.read(file))
        for name, body in original.items():
            inside = any(name == a or name.startswith(f"{a}.") for a in allowed if a)
            if inside:
                if name in allowed and name not in fixed:
                    problems.append(f"the reference removes {file}:{name}")
                continue
            if fixed.get(name) != body:
                problems.append(f"the reference changes {file}:{name}, which no issue names")


def _check_static(project: BenchProject, workspace: Workspace, index, result: Validation) -> None:
    findings, warnings = static.scan(workspace, index)
    for warning in warnings:
        result.problems.append(f"static scan warning: {warning}")
    matching = match_findings(findings, project.manifest)
    for finding in findings:
        key = _finding_key(finding)
        if not matching["finding_issues"].get(key) and not matching["finding_decoys"].get(key):
            where = f"{finding.file}:{finding.line_start}" if finding.line_start else finding.file
            # mypy joined the static checks after the first splits were written; its findings
            # outside the seeded places are reported, not held against those projects.
            if finding.source.startswith("static:mypy:"):
                result.notes.append(f"mypy outside the seeded places: {where} {finding.title}")
                continue
            result.problems.append(
                f"static finding outside every seeded place: {where} {finding.source} "
                f"{finding.title}"
            )
    detected = sorted(issue for issue, keys in matching["detected"].items() if keys)
    result.notes.append(f"static checks find: {', '.join(detected) or 'none'}")


def _check_tests(
    project: BenchProject, workspace: Workspace, runner: ProjectTestRunner, result: Validation
) -> None:
    problems = result.problems
    before = run_with_hidden(runner, workspace.root, project, {})
    if before.status != "ran":
        problems.append(f"the tests do not run on the project: {before.status} {before.detail}")
        return
    if not before.visible_passed:
        problems.append("the project has no passing visible test")
    for name in sorted(before.visible_failed):
        problems.append(f"visible test fails on the project: {name}")
    for issue in project.manifest.fixable:
        for name in issue.hidden_tests:
            if name not in before.hidden_failed:
                problems.append(f"{issue.id}: hidden test {name} does not fail on the project")
    for name in sorted(n for n in before.hidden_failed if n.startswith(KEEP_PREFIX)):
        problems.append(f"keep test {name} fails on the project")
    after = run_with_hidden(runner, workspace.root, project, project.reference_files())
    if after.status != "ran":
        problems.append(f"the tests do not run with the reference fix: {after.status}")
        return
    for name in sorted(after.hidden_failed | after.visible_failed):
        problems.append(f"test fails with the reference fix: {name}")
    result.notes.append(
        f"tests: {len(before.visible_passed)} visible, "
        f"{len(before.hidden_passed) + len(before.hidden_failed)} hidden"
    )


# --- matching findings to seeded places ------------------------------------------------------


def _finding_key(finding: Finding) -> str:
    """Findings are keyed by id; before ids are assigned, by place and title."""
    return finding.id or f"{finding.source}|{finding.file}|{finding.line_start}|{finding.title}"


def _overlaps(finding: Finding, place: Location, tolerance: int = LINE_TOLERANCE) -> bool:
    if finding.file != place.file or finding.line_start is None:
        return False
    end = finding.line_end or finding.line_start
    return finding.line_start <= place.lines[1] + tolerance and end >= place.lines[0] - tolerance


def _mentions(text: str, module: str) -> bool:
    return re.search(rf"(?<![\w.]){re.escape(module)}(?!\w|\.\w)", text) is not None


def matches(finding: Finding, issue: Issue) -> bool:
    """Whether a finding points at a seeded issue (the rule fixed by the protocol)."""
    places = [issue, *issue.other_locations]
    if any(_overlaps(finding, place) for place in places):
        return True
    if issue.category != "architecture" or finding.category is not Category.ARCHITECTURE:
        return False
    text = " ".join(
        part
        for part in (finding.symbol, finding.title, finding.explanation, finding.evidence)
        if part
    )
    named = sum(_mentions(text, module) for module in issue.modules)
    if named >= min(2, len(issue.modules)):
        return True
    return finding.line_start is None and any(place.file == finding.file for place in places)


def match_findings(findings: list[Finding], manifest: Manifest) -> dict:
    finding_issues: dict[str, list[str]] = {}
    finding_decoys: dict[str, list[str]] = {}
    detected: dict[str, list[str]] = {issue.id: [] for issue in manifest.issues}
    right_category: dict[str, bool] = {issue.id: False for issue in manifest.issues}
    decoys_hit: dict[str, list[str]] = {decoy.id: [] for decoy in manifest.decoys}
    for finding in findings:
        key = _finding_key(finding)
        hit = [issue for issue in manifest.issues if matches(finding, issue)]
        finding_issues[key] = [issue.id for issue in hit]
        for issue in hit:
            detected[issue.id].append(key)
            if finding.category.value == issue.category:
                right_category[issue.id] = True
        if hit:
            continue
        on_decoy = [decoy.id for decoy in manifest.decoys if _overlaps(finding, decoy)]
        finding_decoys[key] = on_decoy
        for decoy in on_decoy:
            decoys_hit[decoy].append(key)
    return {
        "finding_issues": finding_issues,
        "finding_decoys": finding_decoys,
        "detected": detected,
        "right_category": right_category,
        "decoys_hit": decoys_hit,
    }


# --- fixes -----------------------------------------------------------------------------------


def evaluate_fixes(
    project: BenchProject, root: Path, fixes: list[Fix], runner: ProjectTestRunner
) -> dict:
    """Apply each fix alone, then every ready fix together, and run all tests each time."""
    baseline = run_with_hidden(runner, root, project, {})
    if baseline.status != "ran":
        return {"error": f"the tests do not run on the project: {baseline.status}"}
    before = resolved_issues(project, baseline)
    per_fix = []
    for fix in fixes:
        entry = {"fix": fix.id, "disposition": fix.disposition.value, "file": fix.file}
        entry["symbol"] = fix.symbol
        if not fix.proposed:
            per_fix.append({**entry, "outcome": "no_proposal"})
            continue
        try:
            patched = apply_recorded_fix((root / fix.file).read_text(encoding="utf-8"), fix)
        except LookupError as exc:
            per_fix.append({**entry, "outcome": "not_applicable", "detail": str(exc)})
            continue
        after = run_with_hidden(runner, root, project, {fix.file: patched})
        broken = broken_tests(baseline, after)
        resolved = sorted(resolved_issues(project, after) - before) if after.status == "ran" else []
        outcome = "harmful" if broken else "resolves" if resolved else "no_effect"
        per_fix.append({**entry, "outcome": outcome, "resolved": resolved, "broken": broken})

    ready = [fix for fix in fixes if fix.disposition.value == READY and fix.proposed]
    combined: dict = {"fixes": [fix.id for fix in ready], "resolved": [], "broken": []}
    if ready:
        changed: dict[str, str] = {}
        try:
            for fix in ready:
                source = changed.get(fix.file) or (root / fix.file).read_text(encoding="utf-8")
                changed[fix.file] = apply_recorded_fix(source, fix)
        except LookupError as exc:
            combined["error"] = str(exc)
        else:
            after = run_with_hidden(runner, root, project, changed)
            combined["broken"] = broken_tests(baseline, after)
            if after.status == "ran":
                combined["resolved"] = sorted(resolved_issues(project, after) - before)
    return {"per_fix": per_fix, "ready_together": combined}


# --- one review ------------------------------------------------------------------------------


def review_project(
    project: BenchProject,
    provider,
    settings: ReviewSettings,
    runner: ProjectTestRunner,
    work_dir: Path,
    arm: str,
) -> dict:
    """Review one benchmark project as an upload, then score the findings and fixes."""
    workspace = extract_project(project.zip_bytes(), work_dir / project.name)
    reviewer = ProjectReviewer(workspace, provider, settings, test_runner=runner)
    started = time.monotonic()
    outcome = reviewer.run()
    elapsed = round(time.monotonic() - started, 2)
    scored_started = time.monotonic()
    matching = match_findings(outcome.findings, project.manifest)
    dropped = [
        {**entry, "issues": [i.id for i in project.manifest.issues if matches(entry_finding, i)]}
        for entry, entry_finding in (
            (item, Finding.model_validate(item["finding"]))
            for item in outcome.dropped
            if "finding" in item
        )
    ]
    fix_scores = evaluate_fixes(project, workspace.root, outcome.fixes, runner)
    return {
        "protocol": PROTOCOL_ID,
        "arm": arm,
        "project": project.name,
        "project_sha256": project.sha256(),
        "review_s": elapsed,
        "scoring_s": round(time.monotonic() - scored_started, 2),
        "summary": outcome.summary,
        "architecture": outcome.architecture,
        "findings": [f.model_dump(mode="json") for f in outcome.findings],
        "fixes": [f.model_dump(mode="json") for f in outcome.fixes],
        "calls": [c.model_dump(mode="json") for c in outcome.calls],
        "stage_times": [s.model_dump(mode="json") for s in outcome.stage_times],
        "warnings": outcome.warnings,
        "baseline_tests": outcome.baseline_tests,
        "model": outcome.model.model_dump(mode="json") if outcome.model else None,
        "dropped": dropped,
        "dropped_unquoted": [item for item in outcome.dropped if "finding" not in item],
        "matching": matching,
        "fix_scores": fix_scores,
    }


# --- metrics ---------------------------------------------------------------------------------


def wilson(successes: int, total: int, z: float = 1.959964) -> tuple[float, float] | None:
    """95% Wilson score interval of a proportion."""
    if total == 0:
        return None
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)


def mcnemar_exact(only_a: int, only_b: int) -> float:
    """Two-sided exact McNemar p-value from the discordant pair counts."""
    n = only_a + only_b
    if n == 0:
        return 1.0
    k = min(only_a, only_b)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * tail)


def _rate(successes: int, total: int) -> dict:
    return {
        "count": successes,
        "total": total,
        "rate": round(successes / total, 4) if total else None,
        "ci95": wilson(successes, total),
    }


# --- adjudication ----------------------------------------------------------------------------

# A finding that lands on a seeded place may still be about something else ("this function is
# complex" next to an off-by-one bug). Every (issue, finding) pair that the location rule
# matched is therefore judged once, blind to the arm, with these instructions.
JUDGE_INSTRUCTIONS = (
    "Each item pairs a known problem in a Python project with a finding that an automated "
    "review reported at the same place. Decide whether the finding identifies this problem. "
    "Answer same=true when it names the same defect or its direct consequence, even in other "
    "words or with a different suggested fix. Answer same=false when it is about something "
    "else at that place, is wrong, or is too vague to show the problem was understood (for "
    "example 'this function is complex' for an off-by-one bug). For a quality or architecture "
    "problem, a finding that describes the same structural issue counts (nested conditions "
    "for a deep-nesting problem, a cycle between the same modules, the same duplicated logic). "
    "Judge each item on its own, from its text only."
)


def pair_id(project: str, issue_id: str, finding: dict) -> str:
    """Stable id of an (issue, finding) pair; the same finding in two arms gets one id."""
    parts = [project, issue_id, finding.get("source"), finding.get("file")]
    parts += [finding.get("line_start"), finding.get("title"), finding.get("explanation")]
    return hashlib.sha256(json.dumps(parts).encode("utf-8")).hexdigest()[:16]


def adjudication_pairs(records: list[dict], projects: dict[str, BenchProject]) -> list[dict]:
    """Every located (issue, finding) pair across the runs, once, without the arm or the
    finding's source, in an order that does not depend on the arm."""
    pairs: dict[str, dict] = {}
    for record in records:
        project = projects[record["project"]]
        issues = {issue.id: issue for issue in project.manifest.issues}
        for finding in record["findings"]:
            for issue_id in record["matching"]["finding_issues"].get(finding["id"], []):
                issue = issues[issue_id]
                lines = (project.project_dir / issue.file).read_text(encoding="utf-8")
                start, end = issue.lines
                pairs[pair_id(project.name, issue_id, finding)] = {
                    "pair": pair_id(project.name, issue_id, finding),
                    "problem": {
                        "file": issue.file,
                        "lines": list(issue.lines),
                        "category": issue.category,
                        "description": issue.description,
                        "code": "\n".join(lines.splitlines()[start - 1 : end][:20]),
                    },
                    "finding": {
                        "file": finding.get("file"),
                        "line": finding.get("line_start"),
                        "category": finding.get("category"),
                        "title": finding.get("title"),
                        "explanation": finding.get("explanation"),
                        "evidence": finding.get("evidence"),
                        "recommendation": finding.get("recommendation"),
                    },
                }
    return [pairs[key] for key in sorted(pairs)]


def confirmed(record: dict, labels: dict[str, dict]) -> dict[str, bool | None]:
    """Per issue: found by a finding the judge called the same problem (True), found only by
    findings judged different (False, also when nothing was located), or located but not
    judged yet (None)."""
    by_id = {finding["id"]: finding for finding in record["findings"]}
    result: dict[str, bool | None] = {}
    for issue_id, keys in record["matching"]["detected"].items():
        verdicts = [
            labels.get(pair_id(record["project"], issue_id, by_id[key]), {}).get("same")
            for key in keys
            if key in by_id
        ]
        if any(verdict is True for verdict in verdicts):
            result[issue_id] = True
        elif any(verdict is None for verdict in verdicts):
            result[issue_id] = None
        else:
            result[issue_id] = False
    return result


def summarize_arm(
    records: list[dict], manifests: dict[str, Manifest], labels: dict[str, dict] | None = None
) -> dict:
    """Detection, false alarms, fixes and cost of one arm over its records."""
    by_category: dict[str, list[int]] = {}
    judged: dict[str, list[int]] = {}
    unjudged = 0
    right = Counter()
    findings_total = Counter()
    sources = Counter()
    decoys = [0, 0]
    fixable = [0, 0, 0]  # total, resolved by ready fixes together, resolved by some single fix
    fix_table: Counter = Counter()
    ready_harmful: list[str] = []
    checker_wrongly_dropped = 0
    checker_dropped = 0
    for record in records:
        manifest = manifests[record["project"]]
        matching = record["matching"]
        verdicts = confirmed(record, labels) if labels is not None else {}
        for issue in manifest.issues:
            counts = by_category.setdefault(issue.category, [0, 0])
            counts[1] += 1
            if matching["detected"][issue.id]:
                counts[0] += 1
                right[issue.category] += bool(matching["right_category"][issue.id])
            if labels is not None:
                judged_counts = judged.setdefault(issue.category, [0, 0])
                judged_counts[1] += 1
                judged_counts[0] += verdicts[issue.id] is True
                unjudged += verdicts[issue.id] is None
        for finding in record["findings"]:
            key = finding["id"]
            kind = (
                "on_issue"
                if matching["finding_issues"].get(key)
                else "on_decoy"
                if matching["finding_decoys"].get(key)
                else "unlabelled"
            )
            findings_total[kind] += 1
            origin = "agent" if finding["source"].startswith("agent:") else "static"
            sources[(origin, kind)] += 1
        decoys[0] += sum(1 for keys in matching["decoys_hit"].values() if keys)
        decoys[1] += len(manifest.decoys)
        scores = record["fix_scores"]
        resolved_single = {
            issue for entry in scores.get("per_fix", []) for issue in entry.get("resolved", [])
        }
        together = set(scores.get("ready_together", {}).get("resolved", []))
        fixable[0] += len(manifest.fixable)
        fixable[1] += len(together)
        fixable[2] += len(resolved_single)
        for entry in scores.get("per_fix", []):
            fix_table[(entry["disposition"], entry["outcome"])] += 1
            if entry["disposition"] == READY and entry["outcome"] == "harmful":
                ready_harmful.append(f"{record['project']}:{entry['fix']}")
        for entry in record.get("dropped", []):
            checker_dropped += 1
            checker_wrongly_dropped += bool(entry["issues"])
    issues_total = sum(total for _, total in by_category.values())
    issues_found = sum(found for found, _ in by_category.values())
    all_findings = sum(findings_total.values())
    ready_fixes = sum(n for (disposition, _), n in fix_table.items() if disposition == READY)
    times = sorted(record["review_s"] for record in records)
    confirmed_summary = None
    if labels is not None:
        confirmed_summary = {
            "issues": _rate(
                sum(found for found, _ in judged.values()), sum(t for _, t in judged.values())
            ),
            "by_category": {
                category: _rate(found, total) for category, (found, total) in sorted(judged.items())
            },
            "issues_located_but_not_judged": unjudged,
        }
    return {
        "projects": len(records),
        "issues": _rate(issues_found, issues_total),
        "issues_by_category": {
            category: {**_rate(found, total), "right_category": right[category]}
            for category, (found, total) in sorted(by_category.items())
        },
        "confirmed": confirmed_summary,
        "findings": {
            "total": all_findings,
            **dict(findings_total),
            "on_issue_share": _rate(findings_total["on_issue"], all_findings),
            "by_origin": {f"{o}:{k}": n for (o, k), n in sorted(sources.items())},
        },
        "decoys_hit": _rate(decoys[0], decoys[1]),
        "fixable_issues": {
            "total": fixable[0],
            "resolved_by_ready_fixes": _rate(fixable[1], fixable[0]),
            "resolved_by_some_fix": _rate(fixable[2], fixable[0]),
        },
        "fixes": {f"{d}/{o}": n for (d, o), n in sorted(fix_table.items())},
        "ready_fixes": ready_fixes,
        "ready_harmful": ready_harmful,
        "checker": {"dropped": checker_dropped, "dropped_on_seeded_issue": checker_wrongly_dropped},
        "review_s": {
            "median": times[len(times) // 2] if times else None,
            "max": times[-1] if times else None,
        },
        "model_calls": sum(len(record["calls"]) for record in records),
    }


def compare_detection(
    first: list[dict],
    second: list[dict],
    manifests: dict[str, Manifest],
    labels: dict[str, dict] | None = None,
) -> dict:
    """Paired detection of the same issues by two arms (exact McNemar test); with labels,
    an issue counts as found only when the judge confirmed it."""

    def found(record: dict) -> dict[str, bool]:
        if labels is None:
            return {issue: bool(keys) for issue, keys in record["matching"]["detected"].items()}
        return {issue: verdict is True for issue, verdict in confirmed(record, labels).items()}

    a = {r["project"]: found(r) for r in first}
    b = {r["project"]: found(r) for r in second}
    both = only_first = only_second = neither = 0
    for project in sorted(set(a) & set(b)):
        for issue in manifests[project].issues:
            found_a, found_b = a[project][issue.id], b[project][issue.id]
            both += found_a and found_b
            only_first += found_a and not found_b
            only_second += found_b and not found_a
            neither += not found_a and not found_b
    return {
        "both": both,
        "only_first": only_first,
        "only_second": only_second,
        "neither": neither,
        "mcnemar_p": round(mcnemar_exact(only_first, only_second), 6),
    }
