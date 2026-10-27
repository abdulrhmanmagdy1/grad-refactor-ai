"""Static index of a project: modules, functions, the internal import graph and metrics.

Every file is only parsed with `ast`; nothing is imported or executed. Module names are
derived from the file paths: a top-level `src/` folder is treated as a source root, and a
file's dotted name is its path below the root without `.py` (packages drop `__init__`).
Imports are resolved against these names, including relative imports, so the graph holds
only the project's own modules; everything else counts as an external import.
"""

from __future__ import annotations

import ast
import hashlib
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from refactor_ai.project.workspace import Workspace
from refactor_ai.tasks import guard_clauses

_DECISIONS = (
    ast.If,
    ast.IfExp,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
    ast.Assert,
    ast.match_case,
)


@dataclass
class FunctionInfo:
    """One function or method, with the metrics the reviewers use to rank work."""

    file: str
    module: str
    qualname: str
    name: str
    line_start: int
    line_end: int
    complexity: int
    nesting: int
    parameters: int
    is_method: bool
    is_test: bool
    body_hash: str

    @property
    def lines(self) -> int:
        return self.line_end - self.line_start + 1


@dataclass
class ModuleInfo:
    file: str
    name: str
    is_package: bool
    is_test: bool
    code_lines: int = 0
    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    imports: set[str] = field(default_factory=set)
    external_imports: set[str] = field(default_factory=set)
    parse_error: str | None = None


@dataclass
class ProjectIndex:
    modules: dict[str, ModuleInfo]
    by_file: dict[str, ModuleInfo]
    cycles: list[list[str]]
    fan_in: dict[str, int]
    fan_out: dict[str, int]
    duplicates: list[list[FunctionInfo]]

    @property
    def functions(self) -> list[FunctionInfo]:
        return [f for module in self.modules.values() for f in module.functions]

    @property
    def has_tests(self) -> bool:
        return any(module.is_test for module in self.modules.values())

    def summary(self) -> dict:
        modules = list(self.modules.values())
        return {
            "python_files": len(modules),
            "code_lines": sum(m.code_lines for m in modules),
            "functions": len(self.functions),
            "classes": sum(len(m.classes) for m in modules),
            "test_files": sum(m.is_test for m in modules),
            "internal_imports": sum(len(m.imports) for m in modules),
            "import_cycles": len(self.cycles),
            "parse_errors": sum(m.parse_error is not None for m in modules),
        }


def module_names(relative: str, package_dirs: set[str]) -> tuple[str, bool, list[str]]:
    """The module's dotted name, whether it is a package's `__init__`, and its aliases.

    The name starts at the outermost folder of the file's package chain (folders with an
    `__init__.py`), so a wrapper folder, a `src/` folder or a namespace folder is not part of
    it. Aliases add each folder above that, because code may import the module either way
    (for example `core.billing` and `shop.core.billing`).
    """
    path = PurePosixPath(relative)
    parts = list(path.with_suffix("").parts)
    is_package = parts[-1] == "__init__"
    start = len(parts) - 1
    while start > 0 and PurePosixPath(*parts[:start]).as_posix() in package_dirs:
        start -= 1
    names = []
    for begin in range(start, -1, -1):
        dotted = parts[begin:-1] if is_package else parts[begin:]
        if dotted:
            names.append(".".join(dotted))
    if not names:
        names = ["__init__"]
    return names[0], is_package, names[1:]


def is_test_file(relative: str) -> bool:
    path = PurePosixPath(relative)
    return (
        path.name.startswith("test_")
        or path.name.endswith("_test.py")
        or path.name == "conftest.py"
        or any(part in ("tests", "test") for part in path.parts[:-1])
    )


def complexity(node: ast.AST) -> int:
    """McCabe cyclomatic complexity of one function, nested functions excluded."""
    score = 1

    def visit(item: ast.AST) -> None:
        nonlocal score
        for child in ast.iter_child_nodes(item):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                continue
            if isinstance(child, _DECISIONS):
                score += 1
            elif isinstance(child, ast.BoolOp):
                score += len(child.values) - 1
            elif isinstance(child, ast.comprehension):
                score += 1 + len(child.ifs)
            visit(child)

    visit(node)
    return score


def _body_hash(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Hash of the function's syntax tree without its name, docstring and positions."""
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        if isinstance(body[0].value.value, str):
            body = body[1:]
    shape = ast.dump(ast.Module(body=body, type_ignores=[]), include_attributes=False)
    arguments = ast.dump(node.args, include_attributes=False)
    return hashlib.sha256((arguments + shape).encode("utf-8")).hexdigest()


def _collect_functions(tree: ast.Module, file: str, module: str, test: bool) -> list[FunctionInfo]:
    found: list[FunctionInfo] = []

    def visit(node: ast.AST, prefix: str, in_class: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualname = f"{prefix}{child.name}"
                found.append(
                    FunctionInfo(
                        file=file,
                        module=module,
                        qualname=qualname,
                        name=child.name,
                        line_start=min([child.lineno, *(d.lineno for d in child.decorator_list)]),
                        line_end=child.end_lineno or child.lineno,
                        complexity=complexity(child),
                        nesting=guard_clauses.nesting_depth(child),
                        parameters=len(child.args.posonlyargs)
                        + len(child.args.args)
                        + len(child.args.kwonlyargs),
                        is_method=in_class,
                        is_test=test or child.name.startswith("test_"),
                        body_hash=_body_hash(child),
                    )
                )
                visit(child, f"{qualname}.<locals>.", False)
            elif isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}.", True)
            elif not isinstance(child, ast.Lambda):
                visit(child, prefix, in_class)

    visit(tree, "", False)
    return found


def _resolve_relative(module: str, is_package: bool, level: int, target: str | None) -> str:
    package = module.split(".") if is_package else module.split(".")[:-1]
    if level > 1:
        package = package[: len(package) - (level - 1)] if level - 1 <= len(package) else []
    base = ".".join(package)
    if target:
        return f"{base}.{target}" if base else target
    return base


def _type_checking_block(node: ast.AST) -> bool:
    test = getattr(node, "test", None) if isinstance(node, ast.If) else None
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def module_level_imports(source: str, info: ModuleInfo, modules: Iterable[str]) -> set[str]:
    """Project modules that a module imports when it is loaded: imports outside functions and
    outside `if TYPE_CHECKING:` blocks."""
    known = set(modules)
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return set()
    found: set[str] = set()
    stack: list[ast.AST] = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if _type_checking_block(node):
            stack.extend(node.orelse)
            continue
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = (
                _resolve_relative(info.name, info.is_package, node.level, node.module)
                if node.level
                else node.module or ""
            )
            names = [base, *(f"{base}.{alias.name}" for alias in node.names)]
        else:
            stack.extend(ast.iter_child_nodes(node))
            continue
        for name in names:
            parts = name.split(".")
            for end in range(len(parts), 0, -1):
                candidate = ".".join(parts[:end])
                if candidate in known:
                    if candidate != info.name:
                        found.add(candidate)
                    break
    return found


def reaches(index: ProjectIndex, start: str, target: str) -> bool:
    """Whether module `start` imports `target`, directly or through other project modules."""
    seen, stack = {start}, [start]
    while stack:
        module = index.modules.get(stack.pop())
        if module is None:
            continue
        for name in module.imports:
            if name == target:
                return True
            if name not in seen:
                seen.add(name)
                stack.append(name)
    return False


def _imports(tree: ast.Module, info: ModuleInfo, known: dict[str, str]) -> None:
    """Record the project modules (by name) and the external packages a module imports.

    `known` maps every module name and alias to the module's name.
    """

    def internal(name: str) -> str | None:
        """The longest project module that `name` refers to, or None."""
        parts = name.split(".")
        for end in range(len(parts), 0, -1):
            candidate = ".".join(parts[:end])
            if candidate in known:
                return known[candidate]
        return None

    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = _resolve_relative(info.name, info.is_package, node.level, node.module)
            else:
                base = node.module or ""
            names = [f"{base}.{alias.name}" if base else alias.name for alias in node.names]
            names.append(base)
        for name in names:
            if not name:
                continue
            target = internal(name)
            if target is None:
                if not (isinstance(node, ast.ImportFrom) and node.level):
                    info.external_imports.add(name.split(".")[0])
            elif target != info.name:
                info.imports.add(target)


def _cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Strongly connected components with more than one module (Tarjan), sorted."""
    index_of: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []
    counter = 0

    def strongconnect(node: str) -> None:
        nonlocal counter
        work = [(node, iter(sorted(graph.get(node, ()))))]
        index_of[node] = low[node] = counter
        counter += 1
        stack.append(node)
        on_stack.add(node)
        while work:
            current, children = work[-1]
            advanced = False
            for child in children:
                if child not in index_of:
                    index_of[child] = low[child] = counter
                    counter += 1
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, iter(sorted(graph.get(child, ())))))
                    advanced = True
                    break
                if child in on_stack:
                    low[current] = min(low[current], index_of[child])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[current])
            if low[current] == index_of[current]:
                component = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == current:
                        break
                if len(component) > 1:
                    components.append(sorted(component))

    for node in sorted(graph):
        if node not in index_of:
            strongconnect(node)
    return sorted(components)


def build_index(workspace: Workspace) -> ProjectIndex:
    modules: dict[str, ModuleInfo] = {}
    trees: dict[str, ast.Module] = {}
    package_dirs = {
        PurePosixPath(file).parent.as_posix()
        for file in workspace.python_files
        if PurePosixPath(file).name == "__init__.py"
    }
    aliases: dict[str, set[str]] = defaultdict(set)
    for file in workspace.python_files:
        name, is_package, extra = module_names(file, package_dirs)
        if name in modules:  # two roots map to one name; keep the path to disambiguate
            name = file.removesuffix(".py").replace("/", ".")
        info = ModuleInfo(file=file, name=name, is_package=is_package, is_test=is_test_file(file))
        source = workspace.read(file)
        info.code_lines = sum(
            1 for line in source.splitlines() if line.strip() and not line.strip().startswith("#")
        )
        try:
            tree = ast.parse(source, filename=file)
        except (SyntaxError, ValueError, RecursionError) as exc:
            info.parse_error = f"{type(exc).__name__}: {exc}"
        else:
            trees[name] = tree
            info.classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
            info.functions = _collect_functions(tree, file, name, info.is_test)
        modules[name] = info
        for alias in extra:
            aliases[alias].add(name)
    known = {name: name for name in modules}
    for alias, owners in aliases.items():
        if alias not in known and len(owners) == 1:  # ambiguous aliases are dropped
            known[alias] = next(iter(owners))
    for name, tree in trees.items():
        _imports(tree, modules[name], known)
    graph = {name: set(info.imports) for name, info in modules.items()}
    fan_in: dict[str, int] = defaultdict(int)
    for targets in graph.values():
        for target in targets:
            fan_in[target] += 1
    groups: dict[str, list[FunctionInfo]] = defaultdict(list)
    for module in modules.values():
        for function in module.functions:
            if function.lines >= 6 and not function.is_test:
                groups[function.body_hash].append(function)
    duplicates = sorted(
        (
            sorted(group, key=lambda f: (f.file, f.line_start))
            for group in groups.values()
            if len(group) > 1
        ),
        key=lambda group: (group[0].file, group[0].line_start),
    )
    return ProjectIndex(
        modules=modules,
        by_file={info.file: info for info in modules.values()},
        cycles=_cycles(graph),
        fan_in={name: fan_in.get(name, 0) for name in modules},
        fan_out={name: len(targets) for name, targets in graph.items()},
        duplicates=duplicates,
    )


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    keyword = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"{keyword} {node.name}({ast.unparse(node.args)}){returns}: ..."


def api_stub(source: str) -> str:
    """A module's public shape: classes with their fields and method signatures, functions
    with their signatures and constants, without bodies."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return ""
    lines: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lines += [line for line in (*_decorators(node), _signature(node))]
        elif isinstance(node, ast.ClassDef):
            bases = ", ".join(ast.unparse(base) for base in node.bases)
            lines += [
                *_decorators(node),
                f"class {node.name}({bases}):" if bases else f"class {node.name}:",
            ]
            for item in node.body:
                if isinstance(item, ast.AnnAssign | ast.Assign):
                    lines.append("    " + ast.unparse(item))
                elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    lines += ["    " + d for d in _decorators(item)] + ["    " + _signature(item)]
        elif isinstance(node, ast.AnnAssign | ast.Assign) and len(ast.unparse(node)) <= 120:
            lines.append(ast.unparse(node))
    return "\n".join(lines)


def _decorators(node) -> list[str]:
    return [f"@{ast.unparse(d)}" for d in node.decorator_list]


def related_api(index: ProjectIndex, workspace: Workspace, module: str, limit: int = 3000) -> str:
    """The public shape of the project modules that `module` imports, for writing code that
    uses them correctly."""
    info = index.modules.get(module)
    if info is None:
        return ""
    parts = []
    for name in sorted(info.imports):
        other = index.modules.get(name)
        if other is None or other.is_test or other.parse_error:
            continue
        stub = api_stub(workspace.read(other.file))
        if stub:
            parts.append(f"# {name}\n{stub}")
    return "\n\n".join(parts)[:limit]


def project_map(index: ProjectIndex, max_modules: int = 60) -> str:
    """A compact text description of the project for the architecture agent."""
    summary = index.summary()
    lines = [
        f"Project: {summary['python_files']} Python files, {summary['code_lines']} code lines, "
        f"{summary['functions']} functions, {summary['classes']} classes, "
        f"{summary['test_files']} test files.",
        "Modules (code lines, functions, classes, imported by N project modules, imports N):",
    ]
    ranked = sorted(index.modules.values(), key=lambda m: (-m.code_lines, m.name))[:max_modules]
    for module in ranked:
        role = " [test]" if module.is_test else ""
        lines.append(
            f"- {module.name}{role}: {module.code_lines} lines, {len(module.functions)} functions, "
            f"{len(module.classes)} classes, in {index.fan_in[module.name]}, "
            f"out {index.fan_out[module.name]}"
        )
        if module.imports:
            lines.append(f"  imports: {', '.join(sorted(module.imports))}")
    if len(index.modules) > max_modules:
        lines.append(f"... and {len(index.modules) - max_modules} smaller modules.")
    lines.append(
        "Import cycles: "
        + ("; ".join(" -> ".join(cycle) for cycle in index.cycles) if index.cycles else "none")
    )
    hotspots = sorted(index.functions, key=lambda f: (-f.complexity, -f.lines))[:10]
    lines.append("Most complex functions (complexity, lines, nesting):")
    lines.extend(
        f"- {f.module}.{f.qualname}: {f.complexity}, {f.lines}, {f.nesting}" for f in hotspots
    )
    external = sorted({name for m in index.modules.values() for name in m.external_imports})
    lines.append("External imports: " + (", ".join(external[:40]) if external else "none"))
    return "\n".join(lines)
