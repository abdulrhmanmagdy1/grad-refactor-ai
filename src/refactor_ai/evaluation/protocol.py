"""Evaluation protocol eval-v1 (draft): arms, budgets, generation settings, test guard.

docs/evaluation/protocol.md is the human-readable protocol; this module is its
executable part. The protocol is frozen only by the record
experiments/evaluation/protocol-freeze.json (status "frozen"), written after the
validation baseline and before any test-split run. Without that record, and without an
explicit confirmation flag, the harness refuses to run on the frozen test split.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from refactor_ai.contracts import GenerationConfig, Role, WorkflowMode, WorkflowSettings

PROTOCOL_VERSION = "eval-v1"
PROTOCOL_DOC = "docs/evaluation/protocol.md"
PROTOCOL_FREEZE_PATH = Path("experiments/evaluation/protocol-freeze.json")
TEST_FREEZE_PATH = Path("experiments/data/test-split-freeze.json")
ARMS = ("A", "B", "C", "D")
RUN_TIMEOUT_S = 600.0
CALL_TIMEOUT_S = 120.0
GENERATION_SEED = 42
MAX_NEW_TOKENS = {Role.ANALYSIS: 384, Role.REFACTOR: 768, Role.REVIEW: 384}


@dataclass(frozen=True)
class ArmSpec:
    arm: str
    mode: WorkflowMode
    refactor_use_adapter: bool
    max_calls: int
    max_corrections: int
    description: str


ARM_SPECS = {
    "A": ArmSpec(
        "A", WorkflowMode.SINGLE_ROLE, False, 1, 0, "original model, one refactoring role"
    ),
    "B": ArmSpec(
        "B",
        WorkflowMode.MULTI_ROLE,
        False,
        5,
        1,
        "original model, analysis, refactoring and review roles, at most one correction",
    ),
    "C": ArmSpec(
        "C", WorkflowMode.SINGLE_ROLE, True, 1, 0, "LoRA-adapted refactoring role, one role"
    ),
    "D": ArmSpec(
        "D",
        WorkflowMode.MULTI_ROLE,
        True,
        5,
        1,
        "LoRA-adapted refactoring role; analysis and review on the original model",
    ),
}


def generation_settings() -> dict[Role, GenerationConfig]:
    """Identical for every arm: greedy decoding, fixed seed, bounded tokens and time."""
    return {
        role: GenerationConfig(
            max_new_tokens=tokens,
            temperature=0.0,
            top_p=1.0,
            seed=GENERATION_SEED,
            max_input_tokens=2048,
            timeout_s=CALL_TIMEOUT_S,
        )
        for role, tokens in MAX_NEW_TOKENS.items()
    }


def arm_settings(arm: str) -> WorkflowSettings:
    if arm not in ARM_SPECS:
        raise ValueError(f"unknown arm {arm!r}; expected one of {', '.join(ARMS)}")
    spec = ARM_SPECS[arm]
    return WorkflowSettings(
        mode=spec.mode,
        refactor_use_adapter=spec.refactor_use_adapter,
        max_calls=spec.max_calls,
        max_corrections=spec.max_corrections,
        run_timeout_s=RUN_TIMEOUT_S,
        generation=generation_settings(),
    )


def parse_arms(text: str) -> list[str]:
    arms = [part.strip().upper() for part in text.split(",") if part.strip()]
    unknown = [arm for arm in arms if arm not in ARM_SPECS]
    if unknown or not arms:
        raise ValueError(f"arms must be a comma-separated subset of {','.join(ARMS)}")
    return list(dict.fromkeys(arms))


def protocol_state(root: Path) -> dict:
    """The protocol version and whether a freeze record marks it frozen."""
    path = root / PROTOCOL_FREEZE_PATH
    if not path.exists():
        return {"version": PROTOCOL_VERSION, "status": "draft", "freeze_record": None}
    record = json.loads(path.read_text(encoding="utf-8"))
    frozen = record.get("status") == "frozen" and record.get("protocol_version") == PROTOCOL_VERSION
    return {
        "version": PROTOCOL_VERSION,
        "status": "frozen" if frozen else "draft",
        "freeze_record": PROTOCOL_FREEZE_PATH.as_posix(),
    }


class TestSplitRefused(RuntimeError):
    """The harness will not touch the frozen test split under these conditions."""

    __test__ = False  # not a pytest test class


def split_sha256(records_path: Path, split: str) -> str:
    """Same definition as the dataset manifest: the split's JSON lines, LF-terminated."""
    text = records_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    lines = [
        line for line in text.split("\n") if line.strip() and json.loads(line)["split"] == split
    ]
    return hashlib.sha256("".join(line + "\n" for line in lines).encode("utf-8")).hexdigest()


def authorize_split(
    split: str,
    *,
    records_path: Path,
    root: Path,
    confirm_frozen_test: bool,
    protocol_version: str | None,
    provider_mode: str,
) -> dict | None:
    """Return the freeze evidence for a test run, or raise TestSplitRefused.

    Validation and train runs need no authorization. A test run needs all of: the
    explicit confirmation flag, the protocol version, a frozen protocol of exactly that
    version, the real local model (never the fake provider), and a test split whose hash
    equals the recorded freeze.
    """
    if split != "test":
        return None
    if not confirm_frozen_test:
        raise TestSplitRefused(
            "The test split is frozen for the final comparison. Pass --i-confirm-frozen-test "
            "and --protocol-version only for the final run under a frozen protocol."
        )
    if not protocol_version:
        raise TestSplitRefused("A test run needs --protocol-version naming the frozen protocol.")
    if protocol_version != PROTOCOL_VERSION:
        raise TestSplitRefused(
            f"Protocol version {protocol_version!r} is not the implemented {PROTOCOL_VERSION!r}."
        )
    state = protocol_state(root)
    if state["status"] != "frozen":
        raise TestSplitRefused(
            f"Protocol {PROTOCOL_VERSION} is not frozen ({PROTOCOL_FREEZE_PATH.as_posix()} with "
            "status 'frozen' is required; it is written after the validation baseline and "
            "the numerical targets)."
        )
    if provider_mode != "local_model":
        raise TestSplitRefused("The test split is evaluated only with the local model provider.")
    freeze_path = root / TEST_FREEZE_PATH
    if not freeze_path.exists():
        raise TestSplitRefused(f"No test-split freeze record at {TEST_FREEZE_PATH.as_posix()}.")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    actual = split_sha256(records_path, "test")
    if actual != freeze["split_sha256"]:
        raise TestSplitRefused(
            f"The test split hash {actual} differs from the frozen {freeze['split_sha256']}."
        )
    if "content_sha256" in freeze:
        from refactor_ai.data import content

        rows = content.records_from_text(records_path.read_text(encoding="utf-8"))
        if content.content_sha256(rows, "test") != freeze["content_sha256"]:
            raise TestSplitRefused("The test split case content differs from the frozen content.")
    protocol_freeze = json.loads((root / PROTOCOL_FREEZE_PATH).read_text(encoding="utf-8"))
    return {"test_freeze": freeze, "protocol_freeze": protocol_freeze}


FROZEN_MODEL_KEYS = ("model_id", "model_revision", "adapter_id", "adapter_sha256")


def check_test_options(
    split: str, *, limit: int | None, case_ids: list[str] | None, runner_mode: str
) -> None:
    """The one test-split run covers every test case with the reference runner enabled."""
    if split != "test":
        return
    if limit is not None or case_ids:
        raise TestSplitRefused(
            "The test split is run once, on every test case: --limit and --case-ids are not "
            "allowed (try the plumbing on the validation split)."
        )
    if runner_mode == "disabled":
        raise TestSplitRefused(
            "The test split needs the reference runner: --runner disabled is not allowed."
        )


def check_test_readiness(warmup: dict, authorization: dict) -> None:
    """Refuse a test run before its first attempt if the runner or the model is unusable.

    Every attempt of the single test run counts, so the run stops here when the runner's
    isolation checks did not enable it, when a warm-up call failed (for example a missing
    adapter), or when a warm-up call reports a model identity other than the "model"
    object (model_id, model_revision, adapter_id, adapter_sha256) of the protocol freeze
    record. The adapter fields are compared for adapter calls only.
    """
    problems = []
    runner = warmup.get("runner") or {}
    if not runner.get("enabled"):
        reason = runner.get("reason") or "no runner"
        problems.append(f"the reference runner is not enabled ({reason})")
    frozen = (authorization.get("protocol_freeze") or {}).get("model")
    if not isinstance(frozen, dict) or not all(frozen.get(key) for key in FROZEN_MODEL_KEYS[:2]):
        problems.append(
            "the protocol freeze record names no model identity (a 'model' object with "
            + ", ".join(FROZEN_MODEL_KEYS)
            + ")"
        )
        frozen = None
    for call in warmup.get("provider_calls") or []:
        state = f"use_adapter={str(call['use_adapter']).lower()}"
        if call.get("error"):
            detail = call.get("error_message") or call["error"]
            problems.append(f"the warm-up call with {state} failed ({call['error']}: {detail})")
            continue
        model = call.get("model")
        if not model:
            problems.append(f"the warm-up call with {state} reported no model identity")
            continue
        if model.get("use_adapter") != call["use_adapter"]:
            reported = str(model.get("use_adapter")).lower()
            problems.append(f"the warm-up call with {state} reported use_adapter={reported}")
        if frozen is not None:
            keys = FROZEN_MODEL_KEYS if call["use_adapter"] else FROZEN_MODEL_KEYS[:2]
            for key in keys:
                if model.get(key) != frozen.get(key):
                    problems.append(
                        f"the warm-up call with {state} reported {key}={model.get(key)!r}, "
                        f"the protocol freeze record has {frozen.get(key)!r}"
                    )
    if problems:
        raise TestSplitRefused(
            "The test run was stopped before its first attempt: " + "; ".join(problems) + "."
        )
