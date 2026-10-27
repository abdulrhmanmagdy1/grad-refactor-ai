"""The project review coordinator: index, static scan, agents, fixes and verification.

Stages, in order, with a budget of model calls and a time limit for the whole run:

1. index the project and run the static scan (always; no model is needed);
2. with a model: the architecture reviewer (one call), the bug finder on the riskiest
   functions, and the quality and security reviewer on the riskiest file windows; every model
   finding must quote its line (otherwise it is dropped) and is then judged by the finding
   checker, and only findings judged real are kept;
3. fixes, one per function with fixable findings, riskiest first: the deterministic
   guard-clause rewrite for a refactoring finding alone, otherwise the fixer agent; each fix
   gets the syntax check, the static re-check, the project's tests (when enabled) and the fix
   reviewer, and a disposition in the order of the function mode.

Without a model (fake mode), the run stops after the static scan and the deterministic
fixes; the summary says so. Model calls and their raw outputs are recorded.
"""

from __future__ import annotations

import ast
import re
import sys
import textwrap
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from refactor_ai.contracts import (
    ChatMessage,
    Disposition,
    GenerationConfig,
    GenerationRequest,
    ModelReference,
    ProviderMode,
    Role,
)
from refactor_ai.project import agents, fixes, static, typecheck
from refactor_ai.project.index import (
    FunctionInfo,
    ProjectIndex,
    build_index,
    module_level_imports,
    project_map,
    reaches,
    related_api,
)
from refactor_ai.project.models import (
    SEVERITY_ORDER,
    AgentCall,
    Category,
    Finding,
    Fix,
    FixCheck,
    ProjectStatus,
    Severity,
    StageTime,
)
from refactor_ai.project.testrun import ProjectTestRunner, TestReport, compare
from refactor_ai.project.workspace import Workspace
from refactor_ai.tasks import guard_clauses

CATEGORY_ORDER = {
    Category.BUG: 0,
    Category.SECURITY: 1,
    Category.ARCHITECTURE: 2,
    Category.QUALITY: 3,
    Category.REFACTORING: 4,
}
MAX_RAW_OUTPUT = 4000

# Plain-language advice for the most common static rules.
RULE_ADVICE = {
    "B006": "Use None as the default and create the list or dict inside the function.",
    "B008": "Compute the default inside the function instead of in the signature.",
    "B023": "Bind the loop variable as a default argument (lambda x, level=level: ...).",
    "B012": "Do not return or break inside finally; it hides exceptions.",
    "B020": "Use a different name for the loop variable than for the iterable.",
    "F821": "Define the name or import it before it is used.",
    "F841": "Remove the unused variable or use its value.",
    "F401": "Remove the unused import.",
    "F811": "Remove or rename the duplicate definition.",
    "E722": "Catch the specific exception you expect instead of a bare except.",
    "S307": "Use ast.literal_eval for literals, or parse the input explicitly; never eval it.",
    "S102": "Remove exec; call the code directly.",
    "S602": "Pass a list of arguments to subprocess without shell=True.",
    "S605": "Use subprocess.run with a list of arguments instead of a shell command.",
    "S608": "Use query parameters instead of building SQL with string formatting.",
    "S301": "Do not unpickle untrusted data; use JSON or another safe format.",
    "S324": "Use hashlib.sha256 (or better) instead of MD5 or SHA-1.",
    "S105": "Read secrets from the environment or a secrets store, not from the code.",
    "S110": "Handle or log the exception instead of passing silently.",
    "PLW0603": "Pass the value as an argument or keep it in an object instead of a global.",
    "PLW2901": "Use a new name instead of reassigning the loop variable.",
    "RET503": "Return a value explicitly on every path.",
    "ARG001": "Remove the unused argument or use it.",
}
RULE_ADVICE_PROJECT = {
    "iterated-list-mutated": "Iterate over a copy (for x in list(items)) or build a new list.",
    "identity-comparison-of-computed-value": "Compare values with == instead of is.",
    "value-never-used": "Remove the computation or use its result.",
}


@dataclass
class ReviewSettings:
    max_calls: int = 110
    time_limit_s: float = 45 * 60
    bug_functions: int = 12
    quality_windows: int = 6
    window_lines: int = 160
    max_fixes: int = 20
    max_findings_checked: int = 30
    fix_steps: int = 4
    run_tests: bool = False
    finder_tokens: int = 512
    architecture_tokens: int = 700
    checker_tokens: int = 160
    fixer_tokens: int = 1200
    reviewer_tokens: int = 256
    # Spec tests: functions whose documented behavior the tester checks, and its budget.
    spec_functions: int = 8
    spec_tokens: int = 700
    spec_checks: int = 2
    max_input_tokens: int = 6000
    call_timeout_s: float = 240.0
    seed: int = 42


@dataclass
class ReviewOutcome:
    summary: dict = field(default_factory=dict)
    architecture: dict = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    fixes: list[Fix] = field(default_factory=list)
    calls: list[AgentCall] = field(default_factory=list)
    stage_times: list[StageTime] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    baseline_tests: dict | None = None
    model: ModelReference | None = None
    # Model findings that were not kept, with the reason (for evaluation; not stored).
    dropped: list[dict] = field(default_factory=list)


ProgressCallback = Callable[[ProjectStatus, str], None]


@dataclass
class _Current:
    """The file text and the function's span as the accepted fix steps have left them."""

    source: str
    span: fixes.Span


class Budget:
    def __init__(self, calls: int, seconds: float, clock: Callable[[], float]) -> None:
        self.calls_left = calls
        self.deadline = clock() + seconds
        self.clock = clock

    def can_call(self) -> bool:
        return self.calls_left > 0 and self.clock() < self.deadline

    def remaining_s(self) -> float:
        return max(0.0, self.deadline - self.clock())


class ProjectReviewer:
    def __init__(
        self,
        workspace: Workspace,
        provider=None,
        settings: ReviewSettings | None = None,
        *,
        test_runner: ProjectTestRunner | None = None,
        on_progress: ProgressCallback | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.workspace = workspace
        self.provider = provider
        self.settings = settings or ReviewSettings()
        self.test_runner = test_runner
        self.on_progress = on_progress or (lambda status, text: None)
        self.clock = clock
        self.outcome = ReviewOutcome()
        self.budget = Budget(self.settings.max_calls, self.settings.time_limit_s, clock)
        self.lines: dict[str, list[str]] = {}
        self.index: ProjectIndex | None = None
        self._readme: str | None = None
        # Spec test files kept for the run (name -> code): passing tests and failing tests
        # the spec checker blamed on the code. They join every test run of the fixes.
        self.spec_files: dict[str, str] = {}

    # --- helpers -------------------------------------------------------------------------

    @property
    def uses_model(self) -> bool:
        return self.provider is not None and self.provider.mode is ProviderMode.LOCAL_MODEL

    def _lines(self, file: str) -> list[str]:
        if file not in self.lines:
            self.lines[file] = self.workspace.read(file).splitlines()
        return self.lines[file]

    def _description(self) -> str | None:
        """The project's README (the shallowest one), which says what the code should do."""
        if self._readme is None:
            readmes = sorted(
                (f for f in self.workspace.files if PurePosixPath(f).stem.lower() == "readme"),
                key=lambda f: (f.count("/"), f),
            )
            self._readme = self.workspace.read(readmes[0]) if readmes else ""
        return self._readme or None

    def _import_cycle(self, file: str, before: str, after: str) -> str | None:
        """Why a fix step's new module-level import closes an import cycle, or None."""
        module = self.index.by_file.get(file) if self.index else None
        if module is None:
            return None
        names = self.index.modules
        added = module_level_imports(after, module, names) - module_level_imports(
            before, module, names
        )
        for target in sorted(added):
            if reaches(self.index, target, module.name):
                return (
                    f"The fix imports {target} when the module loads, and {target} imports "
                    f"{module.name} back: an import cycle that can fail at import time."
                )
        return None

    def _stage(self, name: str, started: float) -> None:
        self.outcome.stage_times.append(
            StageTime(stage=name, seconds=round(self.clock() - started, 3))
        )

    def _call(
        self, agent: str, target: str, role: Role, messages: list[ChatMessage], max_tokens: int
    ) -> str | None:
        """One model call, recorded; None when the budget is spent or the call failed."""
        if not self.budget.can_call():
            return None
        self.budget.calls_left -= 1
        config = GenerationConfig(
            max_new_tokens=max_tokens,
            max_input_tokens=self.settings.max_input_tokens,
            temperature=0.0,
            top_p=1.0,
            seed=self.settings.seed,
            timeout_s=min(self.settings.call_timeout_s, max(1.0, self.budget.remaining_s())),
        )
        request = GenerationRequest(role=role, messages=messages, config=config, use_adapter=False)
        started = self.clock()
        result = self.provider.generate(request)
        error = result.error
        self.outcome.calls.append(
            AgentCall(
                role=agent,
                target=target,
                status="error" if error else "ok",
                elapsed_s=round(self.clock() - started, 3),
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                finish_reason=result.finish_reason,
                error=f"{error.code}: {error.message}" if error else None,
                raw_output=(result.text or "")[:MAX_RAW_OUTPUT] or None,
            )
        )
        if error:
            return None
        if self.outcome.model is None and result.model is not None:
            self.outcome.model = result.model
        return result.text or ""

    # --- the run -------------------------------------------------------------------------

    def run(self) -> ReviewOutcome:
        started = self.clock()
        self.on_progress(ProjectStatus.INDEXING, "Reading the project")
        index = build_index(self.workspace)
        self.index = index
        self._stage("index", started)

        started = self.clock()
        self.on_progress(ProjectStatus.SCANNING, "Running the static checks")
        findings, warnings = static.scan(self.workspace, index)
        self.outcome.warnings.extend(warnings)
        for finding in findings:
            finding.recommendation = finding.recommendation or self._advice(finding)
        self._stage("static", started)

        model_counts = {"reported": 0, "dropped_unquoted": 0, "dropped_by_checker": 0, "kept": 0}
        if self.uses_model:
            started = self.clock()
            self.on_progress(ProjectStatus.REVIEWING, "Agents are reviewing the architecture")
            findings.extend(self._architecture(index, findings))
            self.on_progress(ProjectStatus.REVIEWING, "Agents are looking for bugs")
            candidates = self._bugs(index, findings, model_counts)
            self.on_progress(ProjectStatus.REVIEWING, "Agents are reviewing quality and security")
            candidates.extend(self._quality(index, findings, model_counts))
            findings.extend(self._checked(candidates, model_counts))
            if self.settings.run_tests and self.test_runner is not None:
                self.on_progress(ProjectStatus.REVIEWING, "Agents are testing documented behavior")
                findings.extend(self._spec_findings(index, model_counts))
            self._stage("agents", started)
        else:
            self.outcome.warnings.append(
                "No language model is configured: the review used the static checks only."
            )

        findings = self._merge(findings)
        self._assign_ids(findings)
        self.outcome.findings = findings

        started = self.clock()
        baseline = self._baseline(index)
        self.on_progress(ProjectStatus.FIXING, "Proposing and checking fixes")
        self.outcome.fixes = self._fixes(index, findings, baseline)
        self._stage("fixes", started)

        self.outcome.summary = self._summary(index, findings, model_counts)
        if not self.budget.can_call() and self.uses_model:
            self.outcome.warnings.append(
                "The model-call budget or the time limit was reached; some functions were not "
                "reviewed by the agents."
            )
        return self.outcome

    # --- static helpers ------------------------------------------------------------------

    def _advice(self, finding: Finding) -> str | None:
        if finding.source.startswith("static:ruff:"):
            return RULE_ADVICE.get(finding.source.removeprefix("static:ruff:"))
        if finding.source.startswith("static:rule:"):
            return RULE_ADVICE_PROJECT.get(finding.source.removeprefix("static:rule:"))
        return None

    # --- agents --------------------------------------------------------------------------

    def _architecture(self, index: ProjectIndex, findings: list[Finding]) -> list[Finding]:
        """The architecture reviewer's issues that name real modules and that the checker
        judges real. An import cycle that the index already found is merged into it."""
        static_arch = [f for f in findings if f.category is Category.ARCHITECTURE]
        known = [f.title + (f": {f.symbol}" if f.symbol else "") for f in static_arch]
        text_map = project_map(index)
        text = self._call(
            "architecture",
            "project",
            Role.ANALYSIS,
            agents.architecture_messages(text_map, known),
            self.settings.architecture_tokens,
        )
        if text is None:
            return []
        parsed = agents.parse_architecture(text)
        if parsed.error:
            self.outcome.warnings.append("The architecture reviewer's answer could not be read.")
            return []
        self.outcome.architecture["agent_summary"] = parsed.extra.get("summary")
        names = set(index.modules)
        cycles = [set(cycle) for cycle in index.cycles]
        cycle_findings = [f for f in static_arch if f.source == "static:index:import-cycle"]
        found = []
        for issue in parsed.items:
            modules = [m for m in issue["modules"] if m in names]
            if not modules:
                continue
            if "cycle" in issue["title"].lower() or "circular" in issue["problem"].lower():
                twins = [
                    f
                    for f, cycle in zip(cycle_findings, cycles, strict=False)
                    if set(modules) <= cycle
                ]
                if twins:
                    twins[0].also_reported_by.append("agent:architecture")
                    continue
            if self._about_standard_library(issue, modules, index):
                self.outcome.architecture.setdefault("dropped_agent_issues", []).append(
                    issue["title"]
                )
                continue
            verdict_text = self._call(
                "architecture_checker",
                ", ".join(modules),
                Role.REVIEW,
                agents.architecture_check_messages(issue["title"], issue["problem"], text_map),
                self.settings.checker_tokens,
            )
            verdict = None
            if verdict_text is not None:
                checked = agents.parse_verdict(verdict_text, ("real", "not_a_problem", "unsure"))
                verdict = None if checked.error else checked.extra["verdict"]
            if verdict != "real":
                self.outcome.architecture.setdefault("dropped_agent_issues", []).append(
                    issue["title"]
                )
                continue
            first = index.modules[modules[0]]
            found.append(
                Finding(
                    id="",
                    category=Category.ARCHITECTURE,
                    severity=Severity.LOW,  # a model opinion without static evidence
                    source="agent:architecture",
                    file=first.file,
                    symbol=", ".join(modules),
                    title=issue["title"],
                    explanation=issue["problem"],
                    recommendation=issue["recommendation"],
                    evidence="architecture reviewer, from the project map",
                    also_reported_by=["agent:architecture_checker"],
                )
            )
        return found

    def _risk(self, function: FunctionInfo, static_counts: Counter) -> tuple:
        return (
            -static_counts[(function.file, function.qualname)],
            -function.complexity,
            -function.lines,
            function.file,
            function.line_start,
        )

    def _known_for(self, findings: list[Finding], file: str, start: int, end: int) -> list[str]:
        return [
            f"line {f.line_start}: {f.title}"
            for f in findings
            if f.file == file and f.line_start and start <= f.line_start <= end
        ][:12]

    def _bugs(self, index: ProjectIndex, findings: list[Finding], counts: dict) -> list[Finding]:
        static_counts = Counter((f.file, f.symbol) for f in findings)
        functions = [f for f in index.functions if not f.is_test and f.lines >= 3]
        functions.sort(key=lambda f: self._risk(f, static_counts))
        candidates = []
        for function in functions[: self.settings.bug_functions]:
            lines = self._lines(function.file)
            code = "\n".join(lines[function.line_start - 1 : function.line_end])
            known = self._known_for(findings, function.file, function.line_start, function.line_end)
            text = self._call(
                "bug_finder",
                f"{function.file}:{function.qualname}",
                Role.ANALYSIS,
                agents.bug_messages(
                    function.qualname, code, function.line_start, known, self._description()
                ),
                self.settings.finder_tokens,
            )
            if text is None:
                continue
            parsed = agents.parse_findings(text)
            for item in parsed.items:
                counts["reported"] += 1
                line = agents.quote_matches(item["code"], lines, item["line"])
                if line is None or not function.line_start <= line <= function.line_end:
                    counts["dropped_unquoted"] += 1
                    self.outcome.dropped.append(
                        {"agent": "bug_finder", "target": function.file, "item": item}
                    )
                    continue
                candidates.append(
                    Finding(
                        id="",
                        category=Category.BUG,
                        severity=Severity(item["severity"]),
                        source="agent:bug_finder",
                        file=function.file,
                        line_start=line,
                        line_end=line,
                        symbol=function.qualname,
                        title=item["problem"][:120],
                        explanation=item["problem"],
                        evidence=f"line {line}: {lines[line - 1].strip()}",
                        recommendation=item.get("recommendation"),
                        fixable=True,
                    )
                )
        return candidates

    def _windows(self, index: ProjectIndex, findings: list[Finding]) -> list[tuple[str, int, int]]:
        """File windows of at most window_lines lines, cut between top-level statements."""
        per_file = Counter(f.file for f in findings if f.file)
        modules = [m for m in index.modules.values() if not m.is_test and not m.parse_error]
        modules.sort(key=lambda m: (-per_file[m.file], -m.code_lines, m.file))
        windows = []
        for module in modules:
            lines = self._lines(module.file)
            if not lines:
                continue
            tree = ast.parse("\n".join(lines))
            starts = [node.lineno for node in tree.body] + [len(lines) + 1]
            begin = 1
            for stop in starts[1:]:
                if stop - begin > self.settings.window_lines and stop - 1 > begin:
                    windows.append(
                        (module.file, begin, min(stop - 1, begin + self.settings.window_lines - 1))
                    )
                    begin = stop
            if begin <= len(lines):
                windows.append(
                    (module.file, begin, min(len(lines), begin + self.settings.window_lines - 1))
                )
        return windows[: self.settings.quality_windows]

    def _quality(self, index: ProjectIndex, findings: list[Finding], counts: dict) -> list[Finding]:
        candidates = []
        for file, begin, end in self._windows(index, findings):
            lines = self._lines(file)
            code = "\n".join(lines[begin - 1 : end])
            if not code.strip():
                continue
            text = self._call(
                "quality_security",
                f"{file}:{begin}-{end}",
                Role.ANALYSIS,
                agents.quality_messages(
                    file,
                    code,
                    begin,
                    self._known_for(findings, file, begin, end),
                    self._description(),
                ),
                self.settings.finder_tokens,
            )
            if text is None:
                continue
            parsed = agents.parse_findings(text, categories=("security", "quality"))
            for item in parsed.items:
                counts["reported"] += 1
                line = agents.quote_matches(item["code"], lines, item["line"])
                if line is None or not begin <= line <= end:
                    counts["dropped_unquoted"] += 1
                    self.outcome.dropped.append(
                        {"agent": "quality_security", "target": file, "item": item}
                    )
                    continue
                function = static.enclosing_function(index, file, line)
                candidates.append(
                    Finding(
                        id="",
                        category=Category(item["category"]),
                        severity=Severity(item["severity"]),
                        source="agent:quality_security",
                        file=file,
                        line_start=line,
                        line_end=line,
                        symbol=function.qualname if function else index.by_file[file].name,
                        title=item["problem"][:120],
                        explanation=item["problem"],
                        recommendation=item.get("recommendation"),
                        evidence=f"line {line}: {lines[line - 1].strip()}",
                        fixable=function is not None,
                    )
                )
        return candidates

    def _checked(self, candidates: list[Finding], counts: dict) -> list[Finding]:
        """Keep the model findings that the finding checker judges real."""
        kept = []
        candidates.sort(key=lambda f: (SEVERITY_ORDER[f.severity], f.file or "", f.line_start or 0))
        for finding in candidates[: self.settings.max_findings_checked]:
            lines = self._lines(finding.file)
            begin = max(1, finding.line_start - 8)
            end = min(len(lines), finding.line_start + 8)
            text = self._call(
                "finding_checker",
                f"{finding.file}:{finding.line_start}",
                Role.REVIEW,
                agents.check_messages(
                    finding.title, finding.explanation, "\n".join(lines[begin - 1 : end]), begin
                ),
                self.settings.checker_tokens,
            )
            verdict = None
            if text is not None:
                parsed = agents.parse_verdict(text, ("real", "not_a_problem", "unsure"))
                verdict = None if parsed.error else parsed.extra["verdict"]
            if verdict == "real":
                finding.also_reported_by.append("agent:finding_checker")
                kept.append(finding)
            else:
                counts["dropped_by_checker"] += 1
                self.outcome.dropped.append(
                    {"finding": finding.model_dump(mode="json"), "reason": f"checker:{verdict}"}
                )
        for finding in candidates[self.settings.max_findings_checked :]:
            counts["dropped_by_checker"] += 1
            self.outcome.dropped.append(
                {"finding": finding.model_dump(mode="json"), "reason": "not_checked"}
            )
        counts["kept"] = len(kept)
        return kept

    def _mypy_recheck(self, typed: list[Finding], function: FunctionInfo, state) -> FixCheck:
        """mypy on the project with the fix: the fixed type errors are gone from the
        function and no new one appears there."""
        files = typecheck.checked_files(self.index)
        before, _ = typecheck.run_mypy(self.workspace.root, files)
        after, problem = typecheck.run_mypy(
            self.workspace.root, files, {function.file: state.source}
        )
        if problem:
            return FixCheck(status="error", detail=problem)
        old = typecheck.in_span(before, function.file, function.line_start, function.line_end)
        new = typecheck.in_span(after, function.file, state.span.def_line, state.span.end_line)
        left = sorted({e["code"] for e in new} & {f.source.rsplit(":", 1)[1] for f in typed})
        added = sorted({e["code"] for e in new} - {e["code"] for e in old})
        if left or added:
            detail = "; ".join(
                part
                for part in (
                    f"Still reported by mypy: {', '.join(left)}." if left else "",
                    f"New mypy errors: {', '.join(added)}." if added else "",
                )
                if part
            )
            return FixCheck(status="fail", detail=detail)
        return FixCheck(status="pass", detail="mypy no longer reports the fixed errors.")

    # --- spec tests ----------------------------------------------------------------------

    def _spec_targets(self, index: ProjectIndex) -> list[FunctionInfo]:
        """Documented functions, the riskiest first: their docstring says what to test."""
        functions = [
            f
            for f in index.functions
            if not f.is_test
            and f.lines >= 3
            and not (f.name.startswith("__") and f.name != "__init__")
        ]
        functions.sort(key=lambda f: self._risk(f, Counter()))
        targets = []
        for function in functions:
            lines = self._lines(function.file)
            code = textwrap.dedent("\n".join(lines[function.line_start - 1 : function.line_end]))
            try:
                node = ast.parse(code).body[0]
            except (SyntaxError, ValueError, IndexError):
                continue
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and ast.get_docstring(
                node
            ):
                targets.append(function)
        return targets[: self.settings.spec_functions]

    def _spec_repair(self, function: FunctionInfo, name: str, code: str, report, counts: dict):
        """One more try when the tests did not run or failed by calling the code wrongly:
        the tester sees the errors and fixes how its tests call the code. Returns the new
        (code, report), or None when no repair was needed or it did not help."""
        broken = sorted(report.errors) + [
            f for f in sorted(report.failed) if agents.misuse(report.messages.get(f, ""))
        ]
        if report.status == "ran" and not broken:
            return None
        if report.status != "ran":
            failures = report.detail or report.status
        else:
            failures = "\n".join(
                f"{full.rsplit('::', 1)[-1]}: {report.messages.get(full, '')[:300]}"
                for full in broken[:3]
            )
        text = self._call(
            "spec_tester",
            f"{function.file}:{function.qualname}:repair",
            Role.ANALYSIS,
            agents.spec_repair_messages(function.qualname, code, failures),
            self.settings.spec_tokens,
        )
        if text is None:
            return None
        parsed = agents.parse_spec_tests(text)
        if parsed.error:
            return None
        counts["spec_repaired"] = counts.get("spec_repaired", 0) + 1
        again = self.test_runner.run(self.workspace.root, {name: parsed.extra["code"]}, (name,))
        return parsed.extra["code"], again

    def _spec_findings(self, index: ProjectIndex, counts: dict) -> list[Finding]:
        """Bugs shown by tests written from the documentation.

        The tester writes tests of what each documented function promises; they run in the
        sandbox on the unchanged project. Each failing test goes to the spec checker, which
        says whether the code or the test is wrong. Tests that pass, and failing tests
        blamed on the code, are kept and run with every fix: a fix that makes a blamed test
        pass has a test that fails before it and passes after it.
        """
        found = []
        for number, function in enumerate(self._spec_targets(index), 1):
            module = index.by_file[function.file].name
            text = self._call(
                "spec_tester",
                f"{function.file}:{function.qualname}",
                Role.ANALYSIS,
                agents.spec_test_messages(
                    module,
                    function.qualname,
                    self.workspace.read(function.file),
                    self._description(),
                    related_api(index, self.workspace, module),
                ),
                self.settings.spec_tokens,
            )
            if text is None:
                continue
            parsed = agents.parse_spec_tests(text)
            if parsed.error:
                counts["spec_unreadable"] = counts.get("spec_unreadable", 0) + 1
                continue
            name, code = f"test_zz_spec_{number:02d}.py", parsed.extra["code"]
            report = self.test_runner.run(self.workspace.root, {name: code}, (name,))
            counts["spec_tests"] = counts.get("spec_tests", 0) + len(parsed.extra["tests"])
            repaired = self._spec_repair(function, name, code, report, counts)
            if repaired is not None:
                code, report = repaired
                parsed.extra["tests"] = agents.parse_spec_tests(f"```python\n{code}```").extra.get(
                    "tests", parsed.extra["tests"]
                )
            if report.status != "ran":
                continue
            short = {full: full.rsplit("::", 1)[-1].split("[", 1)[0] for full in report.passed}
            keep = set(short.values())
            lines = self._lines(function.file)
            body = "\n".join(lines[function.line_start - 1 : function.line_end])
            blamed = []
            failing = sorted(report.failed)  # errors are broken tests, not evidence
            counts["spec_failing"] = counts.get("spec_failing", 0) + len(failing)
            # A test that fails by calling the code wrongly shows nothing about the code.
            misused = [f for f in failing if agents.misuse(report.messages.get(f, ""))]
            counts["spec_misused"] = counts.get("spec_misused", 0) + len(misused)
            failing = [f for f in failing if f not in misused]
            for full in failing[: self.settings.spec_checks]:
                test = full.rsplit("::", 1)[-1].split("[", 1)[0]
                message = report.messages.get(full, "")
                answer = self._call(
                    "spec_checker",
                    f"{function.file}:{function.qualname}:{test}",
                    Role.REVIEW,
                    agents.spec_check_messages(
                        function.qualname,
                        agents.spec_test_source(code, test),
                        message,
                        body,
                        function.line_start,
                        self._description(),
                    ),
                    self.settings.checker_tokens,
                )
                verdict, reason = None, ""
                if answer is not None:
                    checked = agents.parse_verdict(answer, ("code_wrong", "test_wrong", "unsure"))
                    if not checked.error:
                        verdict = checked.extra["verdict"]
                        reason = " ".join(checked.extra["reasons"])
                if verdict == "code_wrong":
                    keep.add(test)
                    blamed.append((test, reason, message))
                else:
                    self.outcome.dropped.append(
                        {
                            "spec_test": test,
                            "file": function.file,
                            "symbol": function.qualname,
                            "reason": f"spec_checker:{verdict}",
                        }
                    )
            if keep:
                self.spec_files[name] = agents.drop_tests(code, set(parsed.extra["tests"]) - keep)
            if not blamed:
                continue
            counts["spec_blamed_on_code"] = counts.get("spec_blamed_on_code", 0) + len(blamed)
            test, reason, message = blamed[0]
            source = agents.spec_test_source(code, test)
            found.append(
                Finding(
                    id="",
                    category=Category.BUG,
                    severity=Severity.HIGH,
                    source="agent:spec_tester",
                    file=function.file,
                    line_start=function.line_start,
                    line_end=function.line_end,
                    symbol=function.qualname,
                    title=f"{function.qualname} does not do what its documentation says"[:120],
                    explanation=(
                        f"{reason} The test {test}, written from the documentation, fails: "
                        f"{message[:300]} Test: {source[:600]}"
                    ).strip(),
                    evidence=f"failing test {test} (written from the documentation)",
                    recommendation=(
                        "Change the function so that it does what its documentation says and "
                        "the test passes."
                    ),
                    fixable=True,
                    also_reported_by=["agent:spec_checker"],
                )
            )
        return found

    # --- merging and ids -----------------------------------------------------------------

    @staticmethod
    def _about_standard_library(issue: dict, modules: list[str], index: ProjectIndex) -> bool:
        """An issue about external or third-party imports when every external import of the
        named modules is part of the standard library."""
        text = f"{issue['title']} {issue['problem']}".lower()
        if not any(word in text for word in ("external", "third-party", "third party")):
            return False
        imported = {name for m in modules for name in index.modules[m].external_imports}
        return imported <= set(sys.stdlib_module_names)

    def _merge(self, findings: list[Finding]) -> list[Finding]:
        """One finding per place: a model finding on a line that a static rule already
        reports is merged into the static finding (its source is listed there)."""
        static_at = {}
        for finding in findings:
            if not finding.source.startswith("agent:") and finding.line_start:
                static_at.setdefault((finding.file, finding.line_start), finding)
        merged, agent_at = [], {}
        for finding in findings:
            # A spec test finding covers the whole function and keeps its own place.
            spec = finding.source == "agent:spec_tester"
            if finding.source.startswith("agent:") and finding.line_start and not spec:
                key = (finding.file, finding.line_start)
                twin = static_at.get(key) or agent_at.get(key)
                if twin is not None:
                    if finding.source not in twin.also_reported_by:
                        twin.also_reported_by.append(finding.source)
                    continue
                agent_at[key] = finding
            merged.append(finding)
        return merged

    def _assign_ids(self, findings: list[Finding]) -> None:
        findings.sort(
            key=lambda f: (
                SEVERITY_ORDER[f.severity],
                CATEGORY_ORDER[f.category],
                f.file or "",
                f.line_start or 0,
                f.source,
            )
        )
        for number, finding in enumerate(findings, 1):
            finding.id = f"F{number:03d}"

    # --- fixes ---------------------------------------------------------------------------

    def _baseline(self, index: ProjectIndex) -> TestReport | None:
        if not self.settings.run_tests:
            return None
        if self.test_runner is None or not index.has_tests:
            self.outcome.baseline_tests = {"status": "not_available", "detail": "No tests found."}
            return None
        self.on_progress(ProjectStatus.FIXING, "Running the project's tests before any fix")
        report = self.test_runner.run(self.workspace.root, dict(self.spec_files))
        self.outcome.baseline_tests = report.summary()
        return report if report.status == "ran" else None

    def _fixes(
        self, index: ProjectIndex, findings: list[Finding], baseline: TestReport | None
    ) -> list[Fix]:
        groups: dict[tuple[str, str], list[Finding]] = defaultdict(list)
        for finding in findings:
            if finding.fixable and finding.file and finding.symbol and finding.line_start:
                function = static.enclosing_function(index, finding.file, finding.line_start)
                if function is not None:
                    groups[(function.file, function.qualname)].append(finding)
        functions = {(f.file, f.qualname): f for f in index.functions}
        ordered = sorted(
            groups.items(),
            key=lambda item: (
                min(SEVERITY_ORDER[f.severity] for f in item[1]),
                min(CATEGORY_ORDER[f.category] for f in item[1]),
                item[0],
            ),
        )
        made = []
        for key, group in ordered[: self.settings.max_fixes]:
            fix = self._fix(functions[key], group, baseline)
            if fix is not None:
                made.append(fix)
        for number, fix in enumerate(made, 1):
            fix.id = f"X{number:03d}"
        return made

    def _fix(
        self, function: FunctionInfo, group: list[Finding], baseline: TestReport | None
    ) -> Fix | None:
        """One fix per function. Problems are fixed one at a time, each step building on the
        previous one and kept only if the file still parses and no new static finding
        appears; the result is then checked as a whole."""
        source = self.workspace.read(function.file)
        span = fixes.function_span(source, function.name, function.line_end)
        if span is None:
            return None
        original = fixes.function_text(source, span)
        actionable = sorted(
            (f for f in group if f.category is not Category.REFACTORING),
            key=lambda f: (SEVERITY_ORDER[f.severity], f.line_start or 0),
        )[: self.settings.fix_steps]
        if not actionable:
            produced_by = "deterministic:guard_clauses"
            rewritten = guard_clauses.to_guard_clauses(original)
            steps = [(group, rewritten, "Nested conditionals replaced with guard clauses.")]
        elif self.uses_model:
            produced_by = "agent:fixer"
            steps = None
        else:
            return None  # without a model only the deterministic rewrite can propose a fix
        fix = Fix(
            id="",
            finding_ids=[],
            file=function.file,
            symbol=function.qualname,
            line_start=span.def_line,
            line_end=span.end_line,
            original=original,
            produced_by=produced_by,
            syntax=FixCheck(status="not_run"),
            static_recheck=FixCheck(status="not_run"),
            tests=FixCheck(status="not_run"),
            review=FixCheck(status="not_run"),
            disposition=Disposition.FAILED,
        )
        state = _Current(source, span)
        fixed: list[Finding] = []
        notes: list[str] = []
        failures: dict[str, list[str]] = {"syntax": [], "static": []}
        imports: list[str] = []
        explanations: list[str] = []
        for finding_group, proposed, explanation in steps or self._fixer_steps(
            function, actionable, state
        ):
            if proposed is None:
                notes.append(explanation)
                continue
            try:
                proposal = fixes.check_proposal(proposed, function.name)
                applied = fixes.apply_fix(state.source, function.file, state.span, proposal)
                ast.parse(applied.patched)
            except (fixes.FixError, SyntaxError, ValueError) as exc:
                note = f"{finding_group[0].id}: {str(exc)[:200]}"
                notes.append(note)
                failures["syntax"].append(note)
                continue
            step = fixes.static_recheck(
                finding_group, function.file, state.source, state.span, applied
            )
            cycle = self._import_cycle(function.file, state.source, applied.patched)
            if step.status not in ("pass", "partial") or cycle:
                note = f"{finding_group[0].id}: {cycle or step.detail}"
                notes.append(note)
                failures["static"].append(note)
                continue
            state.source, state.span = applied.patched, applied.span_after
            fixed.extend(finding_group)
            imports.extend(line for line in proposal.imports if line not in imports)
            if explanation:
                explanations.append(explanation)
        if not fixed:
            fix.finding_ids = [f.id for f in (actionable or group)]
            if failures["syntax"]:
                fix.syntax = FixCheck(status="fail", detail="; ".join(failures["syntax"])[:300])
            if failures["static"]:
                fix.static_recheck = FixCheck(
                    status="fail", detail="; ".join(failures["static"])[:300]
                )
            if failures["syntax"] or failures["static"]:
                return self._dispose(fix)
            fix.disposition_reasons = [
                "no_proposal: " + ("; ".join(notes) or "No fix was produced.")
            ]
            return fix
        fix.finding_ids = [f.id for f in fixed]
        fix.proposed = fixes.function_text(state.source, state.span)
        fix.imports = imports
        fix.diff = fixes.unified_diff(source, state.source, function.file)
        fix.explanation = " ".join(explanations) or None
        fix.syntax = FixCheck(status="pass", detail="The patched file parses.")
        total = fixes.AppliedFix(state.source, state.span, fix.diff)
        fix.static_recheck = fixes.static_recheck(fixed, function.file, source, span, total)
        typed = [f for f in fixed if f.source.startswith("static:mypy:")]
        if typed and fix.static_recheck.status in ("pass", "partial"):
            fix.static_recheck = self._mypy_recheck(typed, function, state)
        if notes:
            fix.static_recheck.detail = (fix.static_recheck.detail or "") + (
                " Not fixed: " + "; ".join(notes)
            )[:400]
        fix.tests, newly_passing = self._tests(
            function.file, state.source, baseline, function.name, self.index
        )
        if produced_by == "agent:fixer":
            fix.review, fix.review_reasons = self._review(fixed, fix.diff)
        else:
            fix.review = FixCheck(
                status="not_run", detail="Deterministic rewrite; no model review."
            )
        # A fix is ready only with machine evidence that it was needed: every problem it fixes
        # is a static finding that is now gone, or a test fails before it and passes after.
        evidence = newly_passing > 0 or all(not f.source.startswith("agent:") for f in fixed)
        return self._dispose(fix, evidence)

    def _fixer_steps(self, function: FunctionInfo, actionable: list[Finding], state: _Current):
        """Yield ([finding], proposed function or None, explanation) for each problem; the
        prompt shows the function as the previous accepted steps left it."""
        for finding in actionable:
            code = fixes.function_text(state.source, state.span)
            text = self._call(
                "fixer",
                f"{function.file}:{function.qualname}:{finding.id}",
                Role.REFACTOR,
                agents.fix_messages(
                    finding.title,
                    finding.explanation
                    + (
                        f" Suggested fix: {finding.recommendation}"
                        if finding.recommendation
                        else ""
                    ),
                    finding.line_start,
                    code,
                ),
                self.settings.fixer_tokens,
            )
            if text is None:
                yield [finding], None, f"{finding.id}: the fixer was not called or failed."
                continue
            parsed = agents.parse_fix(text)
            if parsed.error:
                yield (
                    [finding],
                    None,
                    f"{finding.id}: the fixer's answer had no code ({parsed.error}).",
                )
                continue
            yield [finding], parsed.extra["code"], parsed.extra["explanation"]

    def _tests(
        self, file: str, patched: str, baseline: TestReport | None, name: str, index: ProjectIndex
    ) -> tuple[FixCheck, int]:
        """The project's tests before and after the fix, and how many tests fail before it and
        pass after it. Passing tests count as evidence only when some test file refers to the
        function by name; otherwise they only show that nothing else broke."""
        if not self.settings.run_tests:
            return FixCheck(
                status="not_run", detail="Running the project's tests is turned off."
            ), 0
        if baseline is None:
            detail = (self.outcome.baseline_tests or {}).get("detail") or "No usable test run."
            return FixCheck(status="not_available", detail=detail), 0
        after = self.test_runner.run(self.workspace.root, {**self.spec_files, file: patched})
        status, detail = compare(baseline, after)
        newly = len(after.passed - baseline.passed) if after.status == "ran" else 0
        if status == "pass" and not self._tested(name, index):
            return FixCheck(
                status="not_available",
                detail=f"{detail} No test refers to {name}(), so the tests do not check this fix.",
            ), newly
        return FixCheck(status=status, detail=detail), newly

    def _tested(self, name: str, index: ProjectIndex) -> bool:
        pattern = re.compile(r"\b" + re.escape(name) + r"\b")
        return any(
            pattern.search(self.workspace.read(module.file))
            for module in index.modules.values()
            if module.is_test
        ) or any(pattern.search(code) for code in self.spec_files.values())

    def _review(self, targets: list[Finding], diff: str) -> tuple[FixCheck, list[str]]:
        problem = "; ".join(f"line {f.line_start}: {f.title}" for f in targets)
        text = self._call(
            "fix_reviewer",
            targets[0].file or "",
            Role.REVIEW,
            agents.fix_review_messages(f"{len(targets)} problem(s)", problem, diff),
            self.settings.reviewer_tokens,
        )
        if text is None:
            return FixCheck(
                status="not_run", detail="No review (model call failed or budget spent)."
            ), []
        parsed = agents.parse_verdict(text, ("accept", "reject", "uncertain"))
        if parsed.error:
            return FixCheck(status="error", detail="The review could not be read."), []
        return FixCheck(status=parsed.extra["verdict"]), parsed.extra["reasons"]

    def _dispose(self, fix: Fix, evidence: bool = True) -> Fix:
        """The fix's disposition from its checks. `evidence` is False when the fixed problems
        were found by the agents only and no test fails before the fix and passes after it."""
        reasons = []
        deterministic = fix.produced_by.startswith("deterministic")
        if fix.syntax.status == "fail":
            reasons.append("syntax_fail: The fix does not produce valid Python.")
        if fix.static_recheck.status == "fail":
            reasons.append(f"static_fail: {fix.static_recheck.detail}")
        if fix.tests.status == "fail":
            reasons.append(f"tests_fail: {fix.tests.detail}")
        if fix.review.status == "reject":
            reasons.append("review_reject: The fix reviewer rejected the change.")
        if reasons:
            fix.disposition, fix.disposition_reasons = Disposition.REJECTED, reasons
            return fix
        if fix.tests.status != "pass":
            reasons.append(f"tests_{fix.tests.status}: {fix.tests.detail or 'Tests did not pass.'}")
        if fix.static_recheck.status != "pass":
            reasons.append(f"static_{fix.static_recheck.status}: {fix.static_recheck.detail}")
        if not deterministic and fix.review.status != "accept":
            reasons.append(f"review_{fix.review.status}: The fix reviewer did not accept it.")
        if not evidence:
            reasons.append(
                "model_only: Only the AI agents say this problem exists, and no test fails "
                "before the fix and passes after it, so nothing checks that the change is "
                "needed. Read the diff before accepting it."
            )
        if reasons:
            fix.disposition, fix.disposition_reasons = Disposition.UNCERTAIN, reasons
            return fix
        fix.disposition = Disposition.PROPOSAL_READY
        fix.disposition_reasons = [
            "ready: Syntax, the static re-check and the project's tests passed"
            + ("" if deterministic else " and the fix reviewer accepted it")
            + ". Passing tests do not prove equal behavior for every input."
        ]
        return fix

    # --- summary -------------------------------------------------------------------------

    def _summary(self, index: ProjectIndex, findings: list[Finding], model_counts: dict) -> dict:
        by_category = Counter(f.category.value for f in findings)
        by_severity = Counter(f.severity.value for f in findings)
        dispositions = Counter(fix.disposition.value for fix in self.outcome.fixes)
        self.outcome.architecture.update(
            {
                "modules": len(index.modules),
                "cycles": index.cycles,
                "most_imported": sorted(index.fan_in.items(), key=lambda i: (-i[1], i[0]))[:5],
                "most_dependent": sorted(index.fan_out.items(), key=lambda i: (-i[1], i[0]))[:5],
            }
        )
        return {
            **index.summary(),
            "findings": len(findings),
            "by_category": dict(by_category),
            "by_severity": dict(by_severity),
            "fixes": len(self.outcome.fixes),
            "fix_dispositions": dict(dispositions),
            "model_calls": len(self.outcome.calls),
            "model_findings": model_counts if self.uses_model else None,
            "used_model": self.uses_model,
        }
