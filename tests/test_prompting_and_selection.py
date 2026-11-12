"""Tests for the shared prompt contract and AST-only candidate selection."""

from core.candidate_selection import score_candidate, select_best_candidate
from core.schemas import ASTFinding
from models.prompting import (
    REFACTORING_SYSTEM_PROMPT,
    assistant_end_token,
    build_user_prompt,
    extract_refactored_code,
)


def finding(rule: str = "deep-nesting") -> ASTFinding:
    return ASTFinding(
        rule=rule,
        line=1,
        end_line=4,
        node_type="If",
        message="Nested conditionals should be flattened.",
        rationale="Lower nesting improves readability.",
    )


def test_user_prompt_carries_findings_and_code_without_training_markers():
    code = "def f(x):\n    return x\n"
    prompt = build_user_prompt(code, [finding()])
    assert "- deep-nesting: Nested conditionals should be flattened." in prompt
    assert "```python\ndef f(x):" in prompt
    assert "# example:" not in prompt
    assert REFACTORING_SYSTEM_PROMPT.startswith("You are the Refactoring Agent")


def test_extract_refactored_code_removes_fences_and_chat_markers():
    raw = "Here is the refactored code:\n```python\ndef f(x):\n    return x + 1\n```\n<|im_end|>"
    assert extract_refactored_code(raw) == "def f(x):\n    return x + 1\n"


def test_assistant_end_token_prefers_chat_turn_marker():
    class Tokenizer:
        unk_token_id = 0
        eos_token = "<eos>"
        eos_token_id = 2

        def convert_tokens_to_ids(self, token):
            return {"<|im_end|>": 7, "<|eot_id|>": 0, "</s>": 0}[token]

    assert assistant_end_token(Tokenizer()) == ("<|im_end|>", 7)


DEEPLY_NESTED = (
    "def process(items):\n"
    "    if items:\n"
    "        if len(items) > 1:\n"
    "            if items[0]:\n"
    "                if items[0] > 0:\n"
    "                    return items[0]\n"
    "    return 0\n"
)

FLATTENED = (
    "def process(items):\n"
    "    if items and len(items) > 1 and items[0] and items[0] > 0:\n"
    "        return items[0]\n"
    "    return 0\n"
)


def test_candidate_scoring_prefers_a_resolving_rewrite():
    scores = score_candidate(DEEPLY_NESTED, FLATTENED, [finding()])
    assert scores["syntax_valid"] is True
    assert scores["preserved_symbols"] is True
    assert scores["resolved_rules"] == ["deep-nesting"]
    assert scores["score"] > 0


def test_candidate_selection_skips_invalid_and_no_op_candidates():
    invalid = "def process(items):\n    return (\n"
    no_op = DEEPLY_NESTED
    good = FLATTENED
    best, index, scores = select_best_candidate(DEEPLY_NESTED, [invalid, no_op, good], [finding()])
    assert best == good
    assert index == 2
    assert scores[0]["syntax_valid"] is False
    assert scores[1]["resolved_rules"] == []


def test_candidate_selection_rejects_missing_symbols():
    dropped = "def other(items):\n    if items and items[0]:\n        return items[0]\n"
    result = score_candidate(DEEPLY_NESTED, dropped, [finding()])
    assert result["preserved_symbols"] is False
    assert result["missing_symbols"] == ["process"]
