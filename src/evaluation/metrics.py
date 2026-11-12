"""Academic evaluation metrics for the refactoring benchmark (FR09, Phase 5).

Implemented from their published definitions:

- ``codebleu_score`` follows the CodeBLEU formulation (Ren et al., 2020,
  "CodeBLEU: a Method for Automatic Evaluation of Code Synthesis"): the
  weighted blend of n-gram match, keyword-weighted n-gram match, AST syntax
  match, and data-flow match.  We apply it Python-to-Python with the original
  equal weights (0.25 each) and add-1 n-gram smoothing so partial refactors
  are not clipped to zero.

- ``ast_similarity_score`` is a lightweight normalized AST node-sequence
  similarity (LCS ratio over annotated preorder nodes).  It is an
  interpretable structural indicator, not a tree-edit distance.

- ``mi_improvement`` / ``complexity_reduction_pct`` are computed by the caller
  from real analyzer snapshots (see ``evaluation.harness``).
"""

import ast
import io
import keyword
import tokenize
from collections import Counter
from difflib import SequenceMatcher

_KEYWORD_WEIGHT = 5.0
_KEYWORD_NAMES = set(keyword.kwlist) | {
    "True",
    "False",
    "None",
    "self",
    "return",
}
_CODEBLEU_COMPONENT_WEIGHTS = (0.25, 0.25, 0.25, 0.25)
_MAX_NGRAM = 4


# --------------------------------------------------------------------------- #
# Tokenization
# --------------------------------------------------------------------------- #
def _code_tokens(code: str) -> list[str] | None:
    """Tokenize code into NAME/OP/NUMBER/STRING tokens (identifiers preserved)."""
    tokens: list[str] = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(code).readline):
            if token.type in (tokenize.NAME, tokenize.OP, tokenize.NUMBER, tokenize.STRING):
                tokens.append(token.string)
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        return None
    return tokens


def _ngram_counts(tokens: list[str], n: int) -> Counter:
    return Counter(tuple(tokens[index : index + n]) for index in range(len(tokens) - n + 1))


def _weighted_match(reference: list[str], candidate: list[str], n: int, weighted: bool) -> float:
    ref_counts = _ngram_counts(reference, n)
    cand_counts = _ngram_counts(candidate, n)
    if not cand_counts:
        return 0.0

    def gram_weight(gram: tuple[str, ...]) -> float:
        if not weighted:
            return 1.0
        return max(_KEYWORD_WEIGHT if token in _KEYWORD_NAMES else 1.0 for token in gram)

    matched = 0.0
    total = 0.0
    for gram, count in cand_counts.items():
        total += count * gram_weight(gram)
        matched += min(count, ref_counts.get(gram, 0)) * gram_weight(gram)
    return matched / total if total else 0.0


def _bleu_like(reference: list[str], candidate: list[str], weighted: bool) -> float:
    """BLEU-style combined n-gram precision (n=1..4) with add-1 smoothing."""
    if not candidate or not reference:
        return 0.0
    scores = []
    for n in range(1, _MAX_NGRAM + 1):
        numerator = _weighted_match(reference, candidate, n, weighted)
        # Add-1 smoothing keeps the geometric mean informative for short
        # candidates where high-order n-grams have no match.
        scores.append((numerator * len(candidate) + 1.0) / (len(candidate) + 1.0))
    geometric = 1.0
    for score in scores:
        geometric *= max(score, 1e-12)
    geometric **= 1.0 / len(scores)
    brevity = min(1.0, len(candidate) / max(len(reference), 1)) ** 0.5
    return geometric * brevity


# --------------------------------------------------------------------------- #
# AST components
# --------------------------------------------------------------------------- #
def _ast_node_sequence(code: str) -> list[tuple[str, str]] | None:
    """Annotated preorder node sequence: (node type, normalized value)."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return None
    sequence: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        kind = type(node).__name__
        value = ""
        if isinstance(node, ast.Name):
            value = node.id
        elif isinstance(node, ast.Constant):
            value = repr(node.value)
        elif isinstance(node, ast.Attribute):
            value = node.attr
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            value = node.name
        sequence.append((kind, value))
    return sequence


def _syntax_match(reference: str, candidate: str) -> float:
    ref_seq = _ast_node_sequence(reference)
    cand_seq = _ast_node_sequence(candidate)
    if not ref_seq or not cand_seq:
        return 0.0
    return SequenceMatcher(None, ref_seq, cand_seq, autojunk=False).ratio()


def _dataflow_pairs(code: str) -> set[tuple[str, str]] | None:
    """Variable definition/use pairs used by the data-flow match component."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return None
    pairs: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            pairs.add((node.id, "defined" if isinstance(node.ctx, ast.Store) else "used"))
        elif isinstance(node, ast.Attribute):
            pairs.add((node.attr, "attribute"))
    return pairs


def _dataflow_match(reference: str, candidate: str) -> float:
    ref_pairs = _dataflow_pairs(reference)
    cand_pairs = _dataflow_pairs(candidate)
    if not ref_pairs or not cand_pairs:
        return 0.0
    intersection = len(ref_pairs & cand_pairs)
    return 2.0 * intersection / (len(ref_pairs) + len(cand_pairs))


# --------------------------------------------------------------------------- #
# Public metrics
# --------------------------------------------------------------------------- #
def codebleu_score(reference: str, candidate: str) -> float:
    """CodeBLEU(ref -> candidate) in the 0..1 range (Python variant)."""
    ref_tokens = _code_tokens(reference)
    cand_tokens = _code_tokens(candidate)
    if not ref_tokens or not cand_tokens:
        return 0.0

    ngram = _bleu_like(ref_tokens, cand_tokens, weighted=False)
    weighted = _bleu_like(ref_tokens, cand_tokens, weighted=True)
    syntax = _syntax_match(reference, candidate)
    dataflow = _dataflow_match(reference, candidate)

    weights = _CODEBLEU_COMPONENT_WEIGHTS
    return round(
        weights[0] * ngram + weights[1] * weighted + weights[2] * syntax + weights[3] * dataflow,
        4,
    )


def codebleu_components(reference: str, candidate: str) -> dict[str, float]:
    """Per-component breakdown (useful for the published evaluation table)."""
    ref_tokens = _code_tokens(reference)
    cand_tokens = _code_tokens(candidate)
    if not ref_tokens or not cand_tokens:
        return {"ngram": 0.0, "weighted_ngram": 0.0, "syntax": 0.0, "dataflow": 0.0}
    return {
        "ngram": round(_bleu_like(ref_tokens, cand_tokens, weighted=False), 4),
        "weighted_ngram": round(_bleu_like(ref_tokens, cand_tokens, weighted=True), 4),
        "syntax": round(_syntax_match(reference, candidate), 4),
        "dataflow": round(_dataflow_match(reference, candidate), 4),
    }


def ast_similarity_score(reference: str, candidate: str) -> float:
    """Normalized LCS similarity of annotated AST node sequences (0..1)."""
    return round(_syntax_match(reference, candidate), 4)
