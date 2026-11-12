"""The web client validates every response with Zod; these tests prove the drift
guard actually detects a mismatch instead of passing silently.
"""

import importlib.util
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_contract.py"
CONTRACT = ROOT / "frontend" / "src" / "shared" / "api" / "contract.ts"


def _load():
    spec = importlib.util.spec_from_file_location("check_contract", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_contract_matches_the_api():
    module = _load()
    assert module.collect_problems() == []


def test_drift_is_detected_when_a_field_is_removed(tmp_path):
    module = _load()
    mutated = tmp_path / "contract.ts"
    shutil.copy(CONTRACT, mutated)
    source = mutated.read_text(encoding="utf-8")
    source = source.replace("  refactoring_type: z.string().nullable(),\n", "", 1)
    mutated.write_text(source, encoding="utf-8")

    problems = module.collect_problems(mutated)
    assert any("refactoring_type" in problem for problem in problems)


def test_drift_is_detected_when_the_client_invents_a_field(tmp_path):
    module = _load()
    mutated = tmp_path / "contract.ts"
    shutil.copy(CONTRACT, mutated)
    source = mutated.read_text(encoding="utf-8")
    source = source.replace(
        "export const providerSchema = z.object({\n",
        "export const providerSchema = z.object({\n  invented_field: z.string();\n",
        1,
    )
    mutated.write_text(source, encoding="utf-8")

    problems = module.collect_problems(mutated)
    assert any("invented_field" in problem for problem in problems)
