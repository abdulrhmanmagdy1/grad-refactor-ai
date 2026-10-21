"""Exact and near-duplicate detection between splits and against external code.

Exact duplicates compare whitespace-normalized prompts and ast-normalized code.
Near-duplicates follow the criterion of Allamanis (2019, "The Adverse Effects of Code
Duplication in Machine Learning Models of Code"): fingerprint each function by its
identifier and literal tokens, and call two functions near-duplicates when the Jaccard
similarity of the token sets is at least 0.8 and that of the token multisets at least
0.7. Unlike that paper, small functions are not exempted (it skipped files with fewer
than 20 identifiers), which makes the check stricter for this dataset of short
functions. A difflib ratio over the full token sequence (keywords and operators
included) is reported for the most similar pairs as a second, structure-sensitive view;
it is logged, not enforced.
"""

from __future__ import annotations

import ast
import difflib
import hashlib
import io
import json
import keyword
import textwrap
import tokenize
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from refactor_ai.task_format import extract_submitted_code, parse_refactor_output
from refactor_ai.tasks import guard_clauses

SET_THRESHOLD = 0.8
BAG_THRESHOLD = 0.7
REPORT_TOP_PAIRS = 25


def normalized_code(code: str) -> str:
    return guard_clauses.normalize(code) or code


def normalized_prompt(prompt: str) -> str:
    return " ".join(prompt.split())


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_SKIP = (tokenize.NEWLINE, tokenize.NL, tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER)


def code_tokens(code: str) -> list[tuple[int, str]]:
    """(type, text) of every significant token of the normalized code."""
    text = normalized_code(code)
    try:
        return [
            (token.type, token.string)
            for token in tokenize.generate_tokens(io.StringIO(text).readline)
            if token.type not in _SKIP
        ]
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return [(tokenize.NAME, part) for part in text.split()]


def identifier_literal_tokens(code: str) -> list[str]:
    """Identifier, string and number tokens of the normalized code (Allamanis, 2019)."""
    return [
        text
        for kind, text in code_tokens(code)
        if (kind == tokenize.NAME and not keyword.iskeyword(text))
        or kind in (tokenize.STRING, tokenize.NUMBER)
    ]


STRUCTURE_SHINGLE = 4


def structure_shingles(code: str, size: int = STRUCTURE_SHINGLE) -> frozenset:
    """Shingles of the token sequence with identifiers, strings and numbers abstracted.

    This describes the code skeleton independent of the domain vocabulary. Every record
    applies the same refactoring, so similar skeletons across splits are expected; the
    measure is reported, not enforced.
    """
    abstract = []
    for kind, text in code_tokens(code):
        if kind == tokenize.NAME and not keyword.iskeyword(text):
            abstract.append("ID")
        elif kind == tokenize.STRING:
            abstract.append("STR")
        elif kind == tokenize.NUMBER:
            abstract.append("NUM")
        else:
            abstract.append(text)
    if len(abstract) < size:
        return frozenset({tuple(abstract)})
    return frozenset(tuple(abstract[i : i + size]) for i in range(len(abstract) - size + 1))


@dataclass(frozen=True)
class Fingerprint:
    label: str
    split: str
    group: str
    tokens: tuple[str, ...]
    token_set: frozenset
    token_bag: Counter
    structure: frozenset

    @classmethod
    def of(cls, label: str, split: str, group: str, code: str) -> Fingerprint:
        every = tuple(text for _, text in code_tokens(code))
        names = identifier_literal_tokens(code)
        return cls(
            label,
            split,
            group,
            every,
            frozenset(names),
            Counter(names),
            structure_shingles(code),
        )


def jaccard_set(left: frozenset, right: frozenset) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def jaccard_bag(left: Counter, right: Counter) -> float:
    union = sum((left | right).values())
    return sum((left & right).values()) / union if union else 1.0


def token_ratio(left: tuple[str, ...], right: tuple[str, ...]) -> float:
    """difflib similarity of the full token sequences (keywords and operators included)."""
    return difflib.SequenceMatcher(None, left, right, autojunk=False).ratio()


def is_near_duplicate(set_similarity: float, bag_similarity: float) -> bool:
    return set_similarity >= SET_THRESHOLD and bag_similarity >= BAG_THRESHOLD


@dataclass(frozen=True)
class PairScore:
    left: str
    right: str
    left_split: str
    right_split: str
    set_similarity: float
    bag_similarity: float
    structure_similarity: float
    token_ratio: float

    @property
    def near_duplicate(self) -> bool:
        return is_near_duplicate(self.set_similarity, self.bag_similarity)

    def as_dict(self) -> dict:
        return {
            "left": self.left,
            "right": self.right,
            "left_split": self.left_split,
            "right_split": self.right_split,
            "jaccard_set": round(self.set_similarity, 4),
            "jaccard_multiset": round(self.bag_similarity, 4),
            "structure_jaccard": round(self.structure_similarity, 4),
            "difflib_token_ratio": round(self.token_ratio, 4),
            "near_duplicate": self.near_duplicate,
        }


def score(left: Fingerprint, right: Fingerprint) -> PairScore:
    return PairScore(
        left.label,
        right.label,
        left.split,
        right.split,
        jaccard_set(left.token_set, right.token_set),
        jaccard_bag(left.token_bag, right.token_bag),
        jaccard_set(left.structure, right.structure),
        token_ratio(left.tokens, right.tokens),
    )


@dataclass
class ComparisonReport:
    pairs_examined: int
    flagged: list[PairScore]
    top: list[PairScore]
    top_structure: list[PairScore]
    max_similarity: dict[str, float]
    max_structure: dict[str, float]

    def as_dict(self) -> dict:
        return {
            "pairs_examined": self.pairs_examined,
            "flagged": [pair.as_dict() for pair in self.flagged],
            "top_pairs_by_set_similarity": [pair.as_dict() for pair in self.top],
            "top_pairs_by_structure": [pair.as_dict() for pair in self.top_structure],
        }


def compare(
    lefts: list[Fingerprint],
    rights: list[Fingerprint],
    *,
    skip_same_split: bool = True,
    top: int = REPORT_TOP_PAIRS,
) -> ComparisonReport:
    """Score every left/right pair (different splits only, by default)."""
    examined = 0
    flagged: list[PairScore] = []
    by_names: list[tuple[float, float, str, str, Fingerprint, Fingerprint]] = []
    by_structure: list[tuple[float, float, str, str, Fingerprint, Fingerprint]] = []
    max_similarity: dict[str, float] = {}
    max_structure: dict[str, float] = {}
    for left in lefts:
        for right in rights:
            if left.label == right.label:
                continue
            if skip_same_split and left.split == right.split:
                continue
            examined += 1
            set_sim = jaccard_set(left.token_set, right.token_set)
            structure_sim = jaccard_set(left.structure, right.structure)
            for label in (left.label, right.label):
                max_similarity[label] = max(max_similarity.get(label, 0.0), set_sim)
                max_structure[label] = max(max_structure.get(label, 0.0), structure_sim)
            bag_sim = jaccard_bag(left.token_bag, right.token_bag)
            if is_near_duplicate(set_sim, bag_sim):
                flagged.append(score(left, right))
            by_names.append((set_sim, bag_sim, left.label, right.label, left, right))
            by_structure.append((structure_sim, set_sim, left.label, right.label, left, right))
    by_names.sort(key=lambda item: (-item[0], -item[1], item[2], item[3]))
    by_structure.sort(key=lambda item: (-item[0], -item[1], item[2], item[3]))
    top_pairs = [score(item[4], item[5]) for item in by_names[:top]]
    top_structure = [score(item[4], item[5]) for item in by_structure[:top]]
    flagged.sort(key=lambda pair: (pair.left, pair.right))
    return ComparisonReport(
        examined, flagged, top_pairs, top_structure, max_similarity, max_structure
    )


_CODE_KEYS = ("original_code", "target_code", "reference_code", "code", "source")


def _codes_from_json(value: object, label: str, out: list[tuple[str, str]]) -> None:
    if isinstance(value, dict):
        for key in sorted(value):
            item = value[key]
            if isinstance(item, str):
                if key in _CODE_KEYS:
                    out.append((f"{label}.{key}", item))
                elif key == "prompt":
                    code = extract_submitted_code(item)
                    if code:
                        out.append((f"{label}.prompt", code))
                elif key == "completion":
                    parsed = parse_refactor_output(item)
                    if parsed.code:
                        out.append((f"{label}.completion", parsed.code))
            else:
                _codes_from_json(item, f"{label}.{key}", out)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _codes_from_json(item, f"{label}[{index}]", out)


_FIXTURE_SUFFIXES = (".py", ".json", ".jsonl")


def _codes_from_python(text: str, label: str, out: list[tuple[str, str]]) -> None:
    """Functions in a Python fixture module: string constants that hold a single function
    (fixtures are usually kept as strings) and the module's own top-level functions."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "def " in node.value:
            candidate = textwrap.dedent(node.value).strip("\n") + "\n"
            func, _ = guard_clauses.parse_function(candidate)
            if func is not None:
                out.append((f"{label}:{node.lineno}:string", candidate))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            segment = ast.get_source_segment(text, node)
            if segment:
                out.append((f"{label}:{node.lineno}:def", segment + "\n"))


def external_code(paths: list[Path], root: Path) -> tuple[list[tuple[str, str]], list[dict]]:
    """Function code found in external fixture files, plus a file inventory with hashes."""
    found: list[tuple[str, str]] = []
    inventory: list[dict] = []
    files: list[Path] = []
    for base in paths:
        if base.is_file():
            files.append(base)
        elif base.is_dir():
            files += [p for p in base.rglob("*") if p.is_file()]
    files = [p for p in files if p.suffix in _FIXTURE_SUFFIXES and "__pycache__" not in p.parts]
    for path in sorted(set(files)):
        relative = path.relative_to(root).as_posix() if path.is_relative_to(root) else path.name
        data = path.read_bytes()
        # Hash with LF line endings so a Windows checkout (CRLF) gives the same value.
        normalized = data.replace(b"\r\n", b"\n")
        inventory.append({"path": relative, "sha256": hashlib.sha256(normalized).hexdigest()})
        text = data.decode("utf-8", errors="replace").replace("\r\n", "\n")
        if path.suffix == ".py":
            _codes_from_python(text, relative, found)
        elif path.suffix == ".jsonl":
            for number, line in enumerate(text.splitlines(), 1):
                if line.strip():
                    try:
                        _codes_from_json(json.loads(line), f"{relative}:{number}", found)
                    except json.JSONDecodeError:
                        continue
        elif path.suffix == ".json":
            try:
                _codes_from_json(json.loads(text), relative, found)
            except json.JSONDecodeError:
                continue
    usable = [(label, code) for label, code in found if guard_clauses.normalize(code)]
    return usable, inventory
