"""Guard against drift between the FastAPI schemas and the web client's contract.

The web client validates every response with Zod (`frontend/src/shared/api/contract.ts`).
If the backend renames or removes a field and the client is not updated, the
interface would show a contract error at runtime — late, on a user's machine.
This script compares both sides statically and fails loudly instead.

Usage:
    python scripts/check_contract.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_FILE = ROOT / "frontend" / "src" / "shared" / "api" / "contract.ts"

sys.path.insert(0, str(ROOT / "src"))

from api.app import app  # noqa: E402  (import after sys.path setup)

# OpenAPI model name -> the Zod constant that must describe it.
MODEL_TO_SCHEMA = {
    "RunRecord": "runRecordSchema",
    "AnalysisResult": "analysisSchema",
    "ProviderInfo": "providerSchema",
    "VerificationResult": "verificationSchema",
    "ASTFinding": "astFindingSchema",
    "ASTGraph": "astGraphSchema",
    "AgentTrace": "agentTraceSchema",
}


def openapi_properties(model: str) -> set[str]:
    """Property names declared by a Pydantic model in the OpenAPI document."""
    schema = app.openapi()
    definition = schema.get("components", {}).get("schemas", {}).get(model)
    if not definition:
        return set()
    return set(definition.get("properties", {}).keys())


def zod_properties(constant: str, contract_file: Path | None = None) -> set[str]:
    """Top-level keys declared inside a ``z.object({ ... })`` in the contract file."""
    source = (contract_file or CONTRACT_FILE).read_text(encoding="utf-8")
    match = re.search(
        rf"export const {constant} = z\.object\(\{{(.*?)\n\}}\);",
        source,
        re.S,
    )
    if not match:
        return set()
    body = match.group(1)
    return set(re.findall(r"^\s{2}([A-Za-z_][A-Za-z0-9_]*):", body, re.M))


def collect_problems(contract_file: Path | None = None) -> list[str]:
    """Return the drift problems between the API models and the client contract."""
    problems: list[str] = []
    for model, constant in MODEL_TO_SCHEMA.items():
        server_fields = openapi_properties(model)
        client_fields = zod_properties(constant, contract_file)

        if not server_fields:
            problems.append(f"{model}: not present in the OpenAPI document")
            continue
        if not client_fields:
            problems.append(f"{constant}: not found in {CONTRACT_FILE.name}")
            continue

        missing_in_client = sorted(server_fields - client_fields)
        extra_in_client = sorted(client_fields - server_fields)
        for field in missing_in_client:
            problems.append(f"{model}.{field} exists on the server but is missing in {constant}")
        for field in extra_in_client:
            problems.append(f"{constant}.{field} does not exist on the server ({model})")

    return problems


def main() -> None:
    if not CONTRACT_FILE.exists():
        raise SystemExit(f"Contract file not found: {CONTRACT_FILE}")

    problems = collect_problems()
    if problems:
        print("Contract drift between the API and the web client:\n")
        for problem in problems:
            print(f"  - {problem}")
        print(
            "\nUpdate frontend/src/shared/api/contract.ts and the mirrored types, "
            "then re-run this script."
        )
        raise SystemExit(1)

    print(f"Contract OK: {len(MODEL_TO_SCHEMA)} models match the web client.")


if __name__ == "__main__":
    main()
