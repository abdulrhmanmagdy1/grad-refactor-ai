"""Evaluation protocol eval-v1: arms, budgets, generation settings, test guard.

docs/evaluation/protocol.md is the human-readable protocol; this module is its
executable part. The protocol is frozen by the record
experiments/evaluation/protocol-freeze.json (status "frozen"), written on 2026-10-21
after the validation baseline and before any test-split run. The harness runs on the
frozen test split only with an explicit confirmation flag and only when that record is
exactly consistent with what would run: the protocol version, the per-arm settings, the
dataset and test-split hashes, a complete model identity, and the SHA-256 of every file
of the frozen workflow, scoring and generation code (check_protocol_freeze).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import refactor_ai
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
# The code whose behavior the frozen protocol fixes: the role workflow and its prompts and
# parsers, the task rubric, verification, the harness and report, the shared contracts and
# the local model provider's generation path. Paths are relative to the repository root
# of the running code (code_root()); hashes are over UTF-8 bytes with CRLF read as LF.
FROZEN_CODE_PATTERNS = (
    "scripts/evaluate.py",
    "scripts/report_evaluation.py",
    "src/refactor_ai/agents/*.py",
    "src/refactor_ai/contracts.py",
    "src/refactor_ai/evaluation/*.py",
    "src/refactor_ai/providers/local.py",
    "src/refactor_ai/providers/model_worker.py",
    "src/refactor_ai/task_format.py",
    "src/refactor_ai/tasks/*.py",
    "src/refactor_ai/verification/*.py",
)
MODEL_KEYS_REQUIRED = ("model_id", "model_revision", "adapter_id", "adapter_sha256")


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


def code_root() -> Path:
    """Repository root of the running code (the source checkout or the Kaggle bundle)."""
    return Path(refactor_ai.__file__).resolve().parents[2]


def lf_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def frozen_code_sha256(root: Path | None = None) -> dict[str, str]:
    """SHA-256 of every file matched by FROZEN_CODE_PATTERNS, by repository-relative path."""
    base = root or code_root()
    files = {}
    for pattern in FROZEN_CODE_PATTERNS:
        for path in base.glob(pattern):
            if path.is_file():
                files[path.relative_to(base).as_posix()] = lf_sha256(path)
    return dict(sorted(files.items()))


def frozen_arm_settings() -> dict[str, dict]:
    """The per-arm WorkflowSettings as JSON, exactly as the freeze record stores them."""
    return {arm: json.loads(json.dumps(arm_settings(arm).model_dump(mode="json"))) for arm in ARMS}


def _is_sha256(text: object) -> bool:
    return (
        isinstance(text, str)
        and len(text) == 64
        and all(char in "0123456789abcdef" for char in text)
    )


def check_protocol_freeze(
    freeze: dict, *, records_path: Path, test_freeze: dict | None, code: dict[str, str]
) -> list[str]:
    """Every way the freeze record differs from what a test run would use (empty: none).

    code is frozen_code_sha256() of the running code. The test-split freeze record
    (experiments/data/test-split-freeze.json) is optional here because the protocol
    freeze repeats its hashes; when it is present, both must agree.
    """
    from refactor_ai.data import content
    from refactor_ai.evaluation import cases

    problems = []
    if freeze.get("protocol_version") != PROTOCOL_VERSION:
        problems.append(
            f"protocol_version is {freeze.get('protocol_version')!r}, not {PROTOCOL_VERSION!r}"
        )
    if freeze.get("status") != "frozen":
        problems.append(f"status is {freeze.get('status')!r}, not 'frozen'")
    arms = freeze.get("arms")
    expected_arms = frozen_arm_settings()
    if not isinstance(arms, dict) or sorted(arms) != sorted(expected_arms):
        problems.append(f"the record must give the settings of exactly the arms {', '.join(ARMS)}")
    else:
        problems += [
            f"arm {arm}: the frozen settings differ from the harness settings"
            for arm in ARMS
            if arms[arm] != expected_arms[arm]
        ]
    model = freeze.get("model")
    if not isinstance(model, dict):
        problems.append("the record has no 'model' object")
    else:
        problems += [
            f"model.{key} is missing"
            for key in MODEL_KEYS_REQUIRED
            if not isinstance(model.get(key), str) or not model.get(key)
        ]
        if model.get("adapter_sha256") and not _is_sha256(model["adapter_sha256"]):
            problems.append("model.adapter_sha256 is not a SHA-256")
    data = freeze.get("data") or {}
    frozen_split = data.get("test_split") or {}
    rows = content.records_from_text(records_path.read_text(encoding="utf-8"))
    try:
        content_hash = content.content_sha256(rows, "test")
    except (KeyError, ValueError) as exc:  # a record without the case-content fields
        content_hash = f"not computable ({type(exc).__name__}: {exc})"
    actual = {
        "dataset_sha256": cases.dataset_sha256(records_path),
        "split_sha256": split_sha256(records_path, "test"),
        "content_sha256": content_hash,
        "count": sum(1 for row in rows if row["split"] == "test"),
    }
    if data.get("dataset_sha256") != actual["dataset_sha256"]:
        problems.append(
            f"the dataset hash {actual['dataset_sha256']} differs from the frozen "
            f"{data.get('dataset_sha256')}"
        )
    for key in ("split_sha256", "content_sha256", "count"):
        if frozen_split.get(key) != actual[key]:
            problems.append(
                f"the test split {key} {actual[key]} differs from the frozen "
                f"{frozen_split.get(key)}"
            )
    if test_freeze is not None:
        for key in ("split_sha256", "content_sha256"):
            if test_freeze.get(key) != frozen_split.get(key):
                problems.append(
                    f"{TEST_FREEZE_PATH.as_posix()} has {key} {test_freeze.get(key)}, the "
                    f"protocol freeze record has {frozen_split.get(key)}"
                )
    frozen_code = (freeze.get("frozen_code") or {}).get("files")
    if not isinstance(frozen_code, dict) or not frozen_code:
        problems.append("the record lists no frozen code (frozen_code.files)")
    else:
        changed = sorted(p for p in frozen_code if p in code and code[p] != frozen_code[p])
        missing = sorted(p for p in frozen_code if p not in code)
        added = sorted(p for p in code if p not in frozen_code)
        for label, paths in (("changed", changed), ("missing", missing), ("new", added)):
            if paths:
                problems.append(f"frozen code {label} since the freeze: {', '.join(paths)}")
    return problems


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
    version, the real local model (never the fake provider), and a protocol freeze
    record that check_protocol_freeze() finds consistent with the dataset, the harness
    settings and the running code.
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
    freeze = json.loads((root / PROTOCOL_FREEZE_PATH).read_text(encoding="utf-8"))
    test_freeze_path = root / TEST_FREEZE_PATH
    test_freeze = (
        json.loads(test_freeze_path.read_text(encoding="utf-8"))
        if test_freeze_path.exists()
        else None
    )
    problems = check_protocol_freeze(
        freeze, records_path=records_path, test_freeze=test_freeze, code=frozen_code_sha256()
    )
    if problems:
        raise TestSplitRefused(
            f"The protocol freeze record {PROTOCOL_FREEZE_PATH.as_posix()} does not match this "
            "run: " + "; ".join(problems) + ". A change after the freeze needs a new protocol "
            "version, or a documented re-freeze before any test-split run."
        )
    return {"test_freeze": test_freeze, "protocol_freeze": freeze}


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
