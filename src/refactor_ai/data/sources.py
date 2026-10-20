"""Licensed real-code sources: pinned downloads, licenses and function extraction.

Raw files are downloaded once into the Git-ignored data/raw/ directory from URLs pinned
to a commit, and their SHA-256 is checked before use. Licenses were checked on the
official pages on 2026-10-20 (see docs/data-and-training/data-plan.md):

- MBPP (Austin et al., 2021): the Hugging Face dataset card google-research-datasets/mbpp
  declares CC-BY-4.0. The file used here is the identical release in
  google-research/google-research (an Apache-2.0 repository with no data-specific
  statement in the mbpp/ README). Attribution is kept in the dataset NOTICE.
- HumanEval (Chen et al., 2021): MIT License, Copyright (c) OpenAI, in openai/human-eval
  and on the Hugging Face card openai/openai_humaneval. The MIT notice must accompany
  copies of the code.

Most functions in these sources are outside the task scope; the pipeline records why.
"""

from __future__ import annotations

import ast
import gzip
import hashlib
import json
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SourceFile:
    name: str
    url: str
    relative_path: str
    sha256: str
    license: str
    license_url: str
    citation: str
    item_url_template: str


MBPP = SourceFile(
    name="mbpp",
    url=(
        "https://raw.githubusercontent.com/google-research/google-research/"
        "f82046ba5aabbbb427dbfd38a254d26bff08b533/mbpp/mbpp.jsonl"
    ),
    relative_path="mbpp/mbpp.jsonl",
    sha256="ccf64ceae9c5403bf50a044cb6d505bfd2a2963ee58338ba268fd65beab92a9f",
    license="CC-BY-4.0",
    license_url="https://huggingface.co/datasets/google-research-datasets/mbpp",
    citation=(
        "Austin, J., Odena, A., Nye, M., Bosma, M., Michalewski, H., Dohan, D., Jiang, E., "
        "Cai, C., Terry, M., Le, Q. and Sutton, C. (2021). Program Synthesis with Large "
        "Language Models. arXiv:2108.07732."
    ),
    item_url_template=(
        "https://github.com/google-research/google-research/blob/"
        "f82046ba5aabbbb427dbfd38a254d26bff08b533/mbpp/mbpp.jsonl#task_id={item}"
    ),
)

HUMANEVAL = SourceFile(
    name="humaneval",
    url=(
        "https://raw.githubusercontent.com/openai/human-eval/"
        "463c980b59e818ace59f6f9803cd92c749ceae61/data/HumanEval.jsonl.gz"
    ),
    relative_path="humaneval/HumanEval.jsonl.gz",
    sha256="b796127e635a67f93fb35c04f4cb03cf06f38c8072ee7cee8833d7bee06979ef",
    license="MIT",
    license_url="https://github.com/openai/human-eval/blob/master/LICENSE",
    citation=(
        "Chen, M., Tworek, J., Jun, H., Yuan, Q., Pinto, H. P. de O., Kaplan, J., et al. "
        "(2021). Evaluating Large Language Models Trained on Code. arXiv:2107.03374."
    ),
    item_url_template=(
        "https://github.com/openai/human-eval/blob/"
        "463c980b59e818ace59f6f9803cd92c749ceae61/data/HumanEval.jsonl.gz#{item}"
    ),
)

SOURCES = {MBPP.name: MBPP, HUMANEVAL.name: HUMANEVAL}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ensure_source(source: SourceFile, raw_dir: Path, *, allow_download: bool) -> Path:
    """Return the verified local copy, downloading it first when allowed."""
    path = raw_dir / source.relative_path
    if not path.exists():
        if not allow_download:
            raise FileNotFoundError(f"{path} is missing; rerun with downloads enabled")
        path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(source.url, headers={"User-Agent": "grad-refactor-ai"})
        with urllib.request.urlopen(request, timeout=120) as response:  # pinned https URL
            path.write_bytes(response.read())
    digest = sha256_file(path)
    if digest != source.sha256:
        raise ValueError(f"{path} has SHA-256 {digest}, expected {source.sha256}")
    return path


@dataclass
class RealFunction:
    """One function from a licensed source with the calls its own tests make."""

    source: str
    item_id: str
    function_name: str
    code: str
    seed_calls: list[tuple[str, str]] = field(default_factory=list)
    raw_code: str = ""


def normalize_source_code(code: str) -> str:
    """Line endings to LF, trailing spaces removed when that keeps the syntax tree."""
    text = code.replace("\r\n", "\n").replace("\r", "\n").strip("\n") + "\n"
    stripped = "\n".join(line.rstrip() for line in text.split("\n"))
    try:
        if ast.dump(ast.parse(stripped)) == ast.dump(ast.parse(text)):
            return stripped
    except SyntaxError:
        return text
    return text


def _calls_to(tree: ast.AST, name: str) -> list[tuple[str, str]]:
    """Literal (args, kwargs) of calls to ``name`` in a test snippet; others are skipped."""
    calls = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        if node.func.id != name:
            continue
        try:
            args = [ast.literal_eval(arg) for arg in node.args]
            kwargs = {kw.arg: ast.literal_eval(kw.value) for kw in node.keywords if kw.arg}
        except (ValueError, SyntaxError, TypeError):
            continue
        if any(kw.arg is None for kw in node.keywords) or _contains_set([args, kwargs]):
            continue
        calls.append((repr(args), repr(kwargs)))
    return list(dict.fromkeys(calls))


def _contains_set(value: object) -> bool:
    """Set literals print in hash-seed-dependent order, so calls using them are skipped."""
    if isinstance(value, (set, frozenset)):
        return True
    if isinstance(value, (list, tuple)):
        return any(_contains_set(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_set(k) or _contains_set(v) for k, v in value.items())
    return False


def _parse_or_none(text: str) -> ast.AST | None:
    try:
        return ast.parse(text)
    except SyntaxError:
        return None


def load_mbpp(path: Path) -> list[RealFunction]:
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        code = normalize_source_code(row["code"])
        tree = _parse_or_none(code)
        name = ""
        if tree is not None:
            defs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
            name = defs[0].name if len(defs) == 1 else ""
        calls: list[tuple[str, str]] = []
        for snippet in list(row.get("test_list") or []) + list(
            row.get("challenge_test_list") or []
        ):
            test_tree = _parse_or_none(snippet)
            if test_tree is not None and name:
                calls += _calls_to(test_tree, name)
        items.append(
            RealFunction(
                source=MBPP.name,
                item_id=str(row["task_id"]),
                function_name=name,
                code=code,
                seed_calls=list(dict.fromkeys(calls)),
                raw_code=row["code"],
            )
        )
    return items


def load_humaneval(path: Path) -> list[RealFunction]:
    items = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            raw = row["prompt"] + row["canonical_solution"]
            code = normalize_source_code(raw)
            test_tree = _parse_or_none(row["test"])
            calls = _calls_to(test_tree, "candidate") if test_tree is not None else []
            items.append(
                RealFunction(
                    source=HUMANEVAL.name,
                    item_id=row["task_id"],
                    function_name=row["entry_point"],
                    code=code,
                    seed_calls=calls,
                    raw_code=raw,
                )
            )
    return items


def derived_calls(seed_calls: list[tuple[str, str]], limit: int = 300) -> list[tuple[str, str]]:
    """Type-directed variations of a source's own test inputs (one argument at a time).

    They exist only to reach branches the source's tests miss; expected outcomes still
    come from executing the licensed original.
    """
    derived: list[tuple[str, str]] = []
    for args_src, kwargs_src in seed_calls:
        args = ast.literal_eval(args_src)
        for position, value in enumerate(args):
            for variant in _variants(value):
                changed = list(args)
                changed[position] = variant
                derived.append((repr(changed), kwargs_src))
        for left in range(len(args)):
            for right in range(len(args)):
                if left != right and type(args[left]) is type(args[right]):
                    changed = list(args)
                    changed[right] = args[left]
                    derived.append((repr(changed), kwargs_src))
    seeds = set(seed_calls)
    unique = [call for call in dict.fromkeys(derived) if call not in seeds]
    return unique[:limit]


def _variants(value: object) -> list[object]:
    if isinstance(value, bool):
        return [not value]
    if isinstance(value, int):
        return [value - 1, value + 1, 0, -value, value * 2, value + 5]
    if isinstance(value, float):
        return [value - 1.0, value + 1.0, 0.0, -value, value * 2]
    if isinstance(value, str):
        options = ["", value.upper(), value.lower(), " " + value, value[::-1], "+" + value]
        return options + ["-" + value, value[:1], "0", "12", "+12", "-7", "a1"]
    if isinstance(value, list):
        return [[], value[:1], value[::-1], value + value[:1]]
    if isinstance(value, tuple):
        return [(), value[:1], value[::-1]]
    if isinstance(value, dict):
        return [{}, dict(list(value.items())[:1])]
    return []
