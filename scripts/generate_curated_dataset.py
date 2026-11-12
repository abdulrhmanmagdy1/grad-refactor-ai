"""Generate and verify the authored curated refactoring dataset (FR09, NFR06).

Every record is produced from a parametric template and then verified before it
is allowed into ``data/curated.jsonl``:

1. the prompt genuinely triggers the declared smell rule (analyzer),
2. the completion is syntactically valid,
3. the declared rule is resolved in the completion,
4. behaviour is checked in the isolated sandbox:
   - ``golden`` records run auto-synthesized golden-equivalence tests that
     compare the completion against the original prompt on sampled inputs;
   - ``smoke`` records (the signature-changing parameter-object refactor) run
     an authored smoke test proving the new API works as intended;
   - ``clean-control`` records are identity pairs whose prompt has no findings;
     they teach the model not to rewrite clean code and are checked with the
     analyzer only (there is no behaviour change to execute).

Honesty (NFR06): this dataset is authored/synthetic. It is not scraped from
real repositories and not human-annotated. The manifest states this explicitly
and records exactly which verification method covered each record type.

Prompts carry no ``# example:`` provenance comment: the training renderer must
see exactly the code that inference sees. Provenance lives in ``id``,
``source_group`` and the manifest instead.

Usage:
    python scripts/generate_curated_dataset.py
"""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.ast_analyzer import analyze  # noqa: E402
from models.ast_transforms import ASTRefactoringEngine  # noqa: E402
from runner.sandbox import IsolatedRunner  # noqa: E402
from runner.test_generator import AutoTestSynthesizer  # noqa: E402

LICENSE = "CC0-1.0"

# --------------------------------------------------------------------------- #
# Type catalogue and split plan (20 train, 4 validation, 4 test per type)
# --------------------------------------------------------------------------- #
TYPES = (
    "long-function",
    "deep-nesting",
    "high-complexity",
    "async-function",
    "mutable-default-arg",
    "duplicate-code",
    "long-parameter-list",
    "broad-exception",
)

# Each split is (name, findings records per type, clean-control records per type).
# Train is 50/50 findings/no-findings in line with the accuracy plan; validation
# and test keep two clean controls per type in addition to four findings cases.
SPLIT_SPECS: list[tuple[str, int, int]] = [
    ("train", 20, 20),
    ("validation", 4, 2),
    ("test", 4, 2),
]

STYLE_COUNTS = {
    "long-function": 2,
    "deep-nesting": 2,
    "high-complexity": 2,
    "async-function": 2,
    "mutable-default-arg": 3,
    "duplicate-code": 2,
    "long-parameter-list": 3,
    "broad-exception": 3,
}

# The analyzer's rule vocabulary is the source of truth; dataset type labels
# that differ from the detector name are mapped here.
SMELL_RULE_BY_TYPE = {
    "async-function": "long-function",
    "duplicate-code": "duplicate-code-blocks",
    "broad-exception": "broad-exception-catch",
}


# --------------------------------------------------------------------------- #
# Template builders: return (prompt, completion, verification_kind, smoke_test)
# --------------------------------------------------------------------------- #
def build_long_function(variant: int, slug: str, style: int) -> tuple[str, str, str, None]:
    if style == 1:
        first_steps = "\n".join(f"    total += sum(cleaned) * {k}" for k in range(2, 17))
        second_steps = "\n".join(f"    total += sum(cleaned) * {k}" for k in range(17, 34))
        all_steps = "\n".join(f"    total += sum(cleaned) * {k}" for k in range(2, 34))
        prompt = (
            f"def collect_{slug}(values):\n"
            f"    cleaned = [abs(value) for value in values if value is not None]\n"
            f"    total = 0\n"
            f"{all_steps}\n"
            f"    return total\n"
        )
        completion = (
            f"def _clean_values_{slug}(values):\n"
            f"    return [abs(value) for value in values if value is not None]\n\n"
            f"def _score_first_{slug}(cleaned):\n"
            f"    total = 0\n{first_steps}\n    return total\n\n"
            f"def _score_second_{slug}(cleaned, total):\n"
            f"{second_steps}\n    return total\n\n"
            f"def collect_{slug}(values):\n"
            f'    """Split cleaning and scoring into cohesive helpers (behaviour preserved)."""\n'
            f"    cleaned = _clean_values_{slug}(values)\n"
            f"    return _score_second_{slug}(cleaned, _score_first_{slug}(cleaned))\n"
        )
        return prompt, completion, "golden", None

    steps = [f"    total_{variant} = total_{variant} * {k} + {k}" for k in range(1, 33)]
    prompt = (
        f"def aggregate_{slug}(seed):\n"
        f"    total_{variant} = seed\n" + "\n".join(steps) + f"\n    return total_{variant}\n"
    )
    first_steps = "\n".join(f"    total = total * {k} + {k}" for k in range(1, 17))
    second_steps = "\n".join(f"    total = total * {k} + {k}" for k in range(17, 33))
    completion = (
        f"def _aggregate_{slug}_first(seed):\n"
        f"    total = seed\n{first_steps}\n    return total\n\n"
        f"def _aggregate_{slug}_second(total):\n"
        f"{second_steps}\n    return total\n\n"
        f"def aggregate_{slug}(seed):\n"
        f'    """Split the chained fold into two cohesive helpers (behaviour preserved)."""\n'
        f"    return _aggregate_{slug}_second(_aggregate_{slug}_first(seed))\n"
    )
    return prompt, completion, "golden", None


def build_deep_nesting(variant: int, slug: str, style: int) -> tuple[str, str, str, None]:
    if style == 1:
        prompt = (
            f"def summarize_{slug}(groups, minimum, include_zero):\n"
            f"    total = 0\n"
            f"    if groups:\n"
            f"        for group in groups:\n"
            f"            if group:\n"
            f"                for value in group:\n"
            f"                    if value >= minimum:\n"
            f"                        if include_zero or value != 0:\n"
            f"                            total += value\n"
            f"    return total\n"
        )
        completion = (
            f"def summarize_{slug}(groups, minimum, include_zero):\n"
            f'    """Flatten the nested loops with guard clauses (behaviour preserved)."""\n'
            f"    total = 0\n"
            f"    for group in groups or []:\n"
            f"        for value in group or []:\n"
            f"            if value < minimum:\n"
            f"                continue\n"
            f"            if not include_zero and value == 0:\n"
            f"                continue\n"
            f"            total += value\n"
            f"    return total\n"
        )
        return prompt, completion, "golden", None

    threshold = 10 + variant
    prompt = (
        f"def evaluate_{slug}(user, score, level, active):\n"
        f"    if user:\n"
        f"        if score > {threshold}:\n"
        f"            if level:\n"
        f"                if active:\n"
        f"                    return user + score + level\n"
        f"    return 0\n"
    )
    completion, _steps = ASTRefactoringEngine().transform(prompt, analyze(prompt).findings)
    return prompt, completion, "golden", None


def build_high_complexity(variant: int, slug: str, style: int) -> tuple[str, str, str, None]:
    if style == 1:
        bands = (
            (95, "A+"),
            (90, "A"),
            (85, "A-"),
            (80, "B+"),
            (75, "B"),
            (70, "B-"),
            (65, "C+"),
            (60, "C"),
            (55, "C-"),
            (50, "D+"),
            (45, "D"),
            (40, "D-"),
        )
        branches = "\n".join(
            ("    if " if index == 0 else "    elif ")
            + f"score >= {threshold}:\n        return {grade!r}"
            for index, (threshold, grade) in enumerate(bands)
        )
        prompt = f"def classify_{slug}(score):\n{branches}\n    return 'F'\n"
        table = "\n".join(f"    ({threshold}, {grade!r})," for threshold, grade in bands)
        completion = (
            f"_GRADE_BANDS_{slug.upper()} = (\n{table}\n)\n\n"
            f"def classify_{slug}(score):\n"
            f'    """Replace the decision chain with a data table (behaviour preserved)."""\n'
            f"    for threshold, grade in _GRADE_BANDS_{slug.upper()}:\n"
            f"        if score >= threshold:\n"
            f"            return grade\n"
            f"    return 'F'\n"
        )
        return prompt, completion, "golden", None

    codes = [f"'{slug.upper()}{index:02d}'" for index in range(1, 12)]
    values = [index * 10 for index in range(1, 12)]
    branches = "\n".join(
        ("    if event_code == " if index == 0 else "    elif event_code == ")
        + f"{code}:\n        return {value}"
        for index, (code, value) in enumerate(zip(codes, values, strict=False))
    )
    prompt = f"def route_{slug}(event_code):\n{branches}\n    return 0\n"
    table = "\n".join(f"    {code}: {value}," for code, value in zip(codes, values, strict=False))
    completion = (
        f"_ROUTES_{slug.upper()} = {{\n{table}\n}}\n\n"
        f"def route_{slug}(event_code):\n"
        f'    """Replace the decision chain with table-driven dispatch (behaviour preserved)."""\n'
        f"    return _ROUTES_{slug.upper()}.get(event_code, 0)\n"
    )
    return prompt, completion, "golden", None


def build_async_function(variant: int, slug: str, style: int) -> tuple[str, str, str, None]:
    if style == 1:
        prompt_steps = "\n".join(
            f"    total = total + await transform_{slug}(item) * {k}" for k in range(2, 33)
        )
        prompt = (
            f"async def transform_{slug}(item):\n    return item * 3\n\n\n"
            f"async def handle_{slug}(item):\n"
            f"    total = await transform_{slug}(item)\n"
            f"{prompt_steps}\n"
            f"    return total\n"
        )
        first_steps = "\n".join(
            f"    total = total + await transform_{slug}(item) * {k}" for k in range(2, 17)
        )
        second_steps = "\n".join(
            f"    total = total + await transform_{slug}(item) * {k}" for k in range(17, 33)
        )
        completion = (
            f"async def transform_{slug}(item):\n    return item * 3\n\n\n"
            f"async def _handle_first_{slug}(item):\n"
            f"    total = await transform_{slug}(item)\n"
            f"{first_steps}\n    return total\n\n\n"
            f"async def _handle_second_{slug}(item):\n"
            f"    total = 0\n{second_steps}\n    return total\n\n\n"
            f"async def handle_{slug}(item):\n"
            f'    """Split the await sequence into two cohesive helpers (order preserved)."""\n'
            f"    return await _handle_first_{slug}(item) + await _handle_second_{slug}(item)\n"
        )
        return prompt, completion, "golden", None

    prompt_steps = "\n".join(
        f"    total_{variant} += await process_{slug}(items[0]) * {k}" for k in range(2, 32)
    )
    prompt = (
        f"async def process_{slug}(item):\n    return item\n\n\n"
        f"async def handle_batch_{slug}(items):\n"
        f"    total_{variant} = await process_{slug}(items[0]) * 1\n"
        f"{prompt_steps}\n"
        f"    return total_{variant}\n"
    )
    first_steps = "\n".join(
        f"    total += await process_{slug}(items[0]) * {k}" for k in range(2, 17)
    )
    second_steps = "\n".join(
        f"    total += await process_{slug}(items[0]) * {k}" for k in range(17, 32)
    )
    completion = (
        f"async def process_{slug}(item):\n    return item\n\n\n"
        f"async def _handle_batch_{slug}_first(items):\n"
        f"    total = await process_{slug}(items[0]) * 1\n"
        f"{first_steps}\n    return total\n\n\n"
        f"async def _handle_batch_{slug}_second(items):\n"
        f"    total = 0\n{second_steps}\n    return total\n\n\n"
        f"async def handle_batch_{slug}(items):\n"
        f'    """Split the sequential awaits into two cohesive helpers (order preserved)."""\n'
        f"    return await _handle_batch_{slug}_first(items) + await"
        f" _handle_batch_{slug}_second(items)\n"
    )
    return prompt, completion, "golden", None


def build_mutable_default(variant: int, slug: str, style: int) -> tuple[str, str, str, None]:
    if style == 1:
        prompt = (
            f"def register_{slug}(name, cache={{}}):\n"
            f"    cache[name] = cache.get(name, 0) + 1\n"
            f"    return cache\n"
        )
    elif style == 2:
        prompt = f"def track_{slug}(name, seen=set()):\n    seen.add(name)\n    return len(seen)\n"
    else:
        prompt = f"def tag_{slug}(name, labels=[]):\n    labels.append(name)\n    return labels\n"
    completion, _steps = ASTRefactoringEngine().transform(prompt, analyze(prompt).findings)
    return prompt, completion, "golden", None


def build_duplicate_code(variant: int, slug: str, style: int) -> tuple[str, str, str, None]:
    if style == 1:
        body = (
            "    parts = raw.split(',')\n"
            "    result = {}\n"
            "    for part in parts:\n"
            "        if '=' in part:\n"
            "            key, value = part.split('=', 1)\n"
            "            result[key.strip()] = value.strip()\n"
            "    return result\n"
        )
        prompt = f"def parse_{slug}_left(raw):\n{body}\n\ndef parse_{slug}_right(raw):\n{body}"
        completion = (
            f"def _parse_pairs_{slug}(raw):\n{body}\n\n"
            f"def parse_{slug}_left(raw):\n"
            f"    return _parse_pairs_{slug}(raw)\n\n"
            f"def parse_{slug}_right(raw):\n"
            f"    return _parse_pairs_{slug}(raw)\n"
        )
        return prompt, completion, "golden", None

    body = (
        "    total = 0\n"
        "    for record in records:\n"
        "        if record > 0:\n"
        "            total += record\n"
        "    return total\n"
    )
    prompt = f"def summarize_{slug}_a(records):\n{body}\n\ndef summarize_{slug}_b(records):\n{body}"
    completion = (
        f"def _sum_positive_{slug}(records):\n{body}\n\n"
        f"def summarize_{slug}_a(records):\n"
        f"    return _sum_positive_{slug}(records)\n\n"
        f"def summarize_{slug}_b(records):\n"
        f"    return _sum_positive_{slug}(records)\n"
    )
    return prompt, completion, "golden", None


def _build_parameter_object(
    slug: str,
    function_name: str,
    class_name: str,
    fields: tuple[tuple[str, str], ...],
    values: dict[str, str],
) -> tuple[str, str, str, str]:
    names = [name for name, _type_name in fields]
    prompt = (
        f"def {function_name}({', '.join(names)}):\n"
        "    return {\n" + "\n".join(f"        {name!r}: {name}," for name in names) + "\n    }\n"
    )
    dataclass_fields = "\n".join(f"    {name}: {type_name}" for name, type_name in fields)
    completion = (
        "from dataclasses import dataclass\n\n\n"
        f"@dataclass\nclass {class_name}:\n{dataclass_fields}\n\n\n"
        f"def {function_name}(request: {class_name}):\n"
        f'    """Build the payload from one cohesive request object."""\n'
        "    return {\n"
        + "\n".join(f"        {name!r}: request.{name}," for name in names)
        + "\n    }\n"
    )
    arguments = ",\n        ".join(f"{name}={values[name]}" for name in names)
    expected = "\n".join(f"        {name!r}: {values[name]}," for name in names)
    smoke_test = (
        f"from solution import {class_name}, {function_name}\n\n\n"
        "def test_parameter_object_round_trip():\n"
        f"    request = {class_name}(\n        {arguments}\n    )\n"
        f"    assert {function_name}(request) == {{\n{expected}\n    }}\n"
    )
    return prompt, completion, "smoke", smoke_test


def build_long_parameter_list(variant: int, slug: str, style: int) -> tuple[str, str, str, str]:
    if style == 1:
        return _build_parameter_object(
            slug,
            f"build_profile_{slug}",
            f"ProfileRequest_{slug}",
            (
                ("username", "str"),
                ("email", "str"),
                ("age", "int"),
                ("country", "str"),
                ("plan", "str"),
                ("active", "bool"),
            ),
            {
                "username": "'alice'",
                "email": "'a@example.com'",
                "age": "30",
                "country": "'EG'",
                "plan": "'pro'",
                "active": "True",
            },
        )
    if style == 2:
        return _build_parameter_object(
            slug,
            f"make_order_{slug}",
            f"OrderRequest_{slug}",
            (
                ("order_id", "int"),
                ("customer", "str"),
                ("item", "str"),
                ("quantity", "int"),
                ("price", "float"),
                ("currency", "str"),
            ),
            {
                "order_id": "7",
                "customer": "'bob'",
                "item": "'book'",
                "quantity": "2",
                "price": "9.5",
                "currency": "'USD'",
            },
        )
    return _build_parameter_object(
        slug,
        f"create_report_{slug}",
        f"ReportRequest_{slug}",
        (
            ("title", "str"),
            ("author", "str"),
            ("date", "str"),
            ("category", "str"),
            ("priority", "int"),
            ("tags", "list"),
        ),
        {
            "title": "'t'",
            "author": "'a'",
            "date": "'d'",
            "category": "'c'",
            "priority": "1",
            "tags": "['x']",
        },
    )


def build_broad_exception(variant: int, slug: str, style: int) -> tuple[str, str, str, None]:
    if style == 1:
        prompt = (
            "import json\n\n\n"
            f"def parse_payload_{slug}(raw):\n"
            f"    try:\n"
            f"        return json.loads(raw)\n"
            f"    except Exception:\n"
            f"        return {{}}\n"
        )
        completion = (
            "import json\n\n\n"
            f"def parse_payload_{slug}(raw):\n"
            f"    try:\n"
            f"        return json.loads(raw)\n"
            f"    except (TypeError, ValueError):\n"
            f"        return {{}}\n"
        )
        return prompt, completion, "golden", None
    if style == 2:
        prompt = (
            f"def safe_ratio_{slug}(numerator, denominator):\n"
            f"    try:\n"
            f"        return numerator / denominator\n"
            f"    except Exception:\n"
            f"        return 0\n"
        )
        completion = (
            f"def safe_ratio_{slug}(numerator, denominator):\n"
            f"    try:\n"
            f"        return numerator / denominator\n"
            f"    except (TypeError, ZeroDivisionError):\n"
            f"        return 0\n"
        )
        return prompt, completion, "golden", None
    prompt = (
        f"def read_number_{slug}(raw):\n"
        f"    try:\n"
        f"        return int(raw.strip())\n"
        f"    except Exception:\n"
        f"        return 0\n"
    )
    completion = (
        f"def read_number_{slug}(raw):\n"
        f"    try:\n"
        f"        return int(raw.strip())\n"
        f"    except (TypeError, ValueError):\n"
        f"        return 0\n"
    )
    return prompt, completion, "golden", None


BUILDERS = {
    "long-function": build_long_function,
    "deep-nesting": build_deep_nesting,
    "high-complexity": build_high_complexity,
    "async-function": build_async_function,
    "mutable-default-arg": build_mutable_default,
    "duplicate-code": build_duplicate_code,
    "long-parameter-list": build_long_parameter_list,
    "broad-exception": build_broad_exception,
}

# Rules that only one specific type must resolve; everything else is checked
# generically ("the declared rule must disappear from the completion").
_SKIPPED_EQUIVALENCE = {
    "long-parameter-list": (
        "The parameter-object refactor intentionally changes the call surface "
        "(one request object instead of six scalars); golden equivalence against "
        "the old signature is therefore not applicable. Verified by the authored "
        "smoke test instead."
    )
}


# --------------------------------------------------------------------------- #
# Verification
# --------------------------------------------------------------------------- #
class _Verifier:
    def __init__(self) -> None:
        self.synthesizer = AutoTestSynthesizer()
        self.runner = IsolatedRunner(timeout_seconds=30.0)

    def verify(
        self,
        prompt: str,
        completion: str,
        rule: str,
        kind: str,
        smoke_test: str | None,
    ) -> dict:
        prompt_analysis = analyze(prompt)
        if not prompt_analysis.syntax_valid:
            raise ValueError(f"prompt does not parse: {prompt_analysis.error}")
        prompt_rules = {finding.rule for finding in prompt_analysis.findings}
        if rule not in prompt_rules:
            raise ValueError(
                f"prompt does not trigger declared rule '{rule}' (found {prompt_rules})"
            )

        completion_analysis = analyze(completion)
        if not completion_analysis.syntax_valid:
            raise ValueError(f"completion does not parse: {completion_analysis.error}")
        completion_rules = {finding.rule for finding in completion_analysis.findings}
        if rule in completion_rules:
            raise ValueError(f"completion still triggers rule '{rule}'")

        if kind == "golden":
            tests, meta = self.synthesizer.synthesize(prompt)
            if tests is None:
                raise ValueError(
                    f"no samplable functions for golden equivalence ({meta.get('skipped')})"
                )
            result = self.runner.run_test(completion, tests, reference_code=prompt, timeout=30.0)
            if not result.success:
                excerpt = (result.stdout + result.stderr)[-600:]
                raise ValueError(f"golden equivalence failed:\n{excerpt}")
            return {
                "method": "golden-equivalence",
                "verified": True,
                "sampled_cases": meta["cases"],
                "functions_tested": meta["functions_tested"],
            }

        if kind == "smoke":
            if smoke_test is None:
                raise ValueError("smoke verification requires a smoke test")
            result = self.runner.run_test(completion, smoke_test, timeout=30.0)
            if not result.success:
                excerpt = (result.stdout + result.stderr)[-600:]
                raise ValueError(f"smoke test failed:\n{excerpt}")
            return {
                "method": "authored-smoke-test",
                "verified": True,
                "note": _SKIPPED_EQUIVALENCE.get(rule, ""),
            }

        raise ValueError(f"unknown verification kind: {kind}")

    def verify_clean(self, clean_code: str) -> dict:
        analysis = analyze(clean_code)
        if not analysis.syntax_valid:
            raise ValueError(f"clean control does not parse: {analysis.error}")
        if analysis.findings:
            rules = sorted({finding.rule for finding in analysis.findings})
            raise ValueError(f"clean control still has findings: {rules}")
        return {
            "method": "clean-control",
            "verified": True,
            "note": (
                "Identity pair: the prompt has no findings and the completion is the "
                "same module, teaching the model not to rewrite clean code."
            ),
        }


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #
def generate(verify: bool = True, verbose: bool = True) -> tuple[list[dict], dict]:
    verifier = _Verifier() if verify else None
    records: list[dict] = []
    per_type_variant: dict[str, int] = {rule: 0 for rule in TYPES}
    findings_counts: dict[str, int] = {}
    clean_counts: dict[str, int] = {}
    method_counts: dict[str, int] = {}

    for split, findings_count, clean_count in SPLIT_SPECS:
        for rule in TYPES:
            style_count = STYLE_COUNTS[rule]
            for index in range(1, findings_count + 1):
                per_type_variant[rule] += 1
                variant = per_type_variant[rule]
                style = (variant - 1) % style_count
                slug = f"{rule.replace('-', '_')}_{variant:02d}"
                builder = BUILDERS[rule]
                prompt, completion, kind, smoke_test = builder(variant, slug, style)

                smell_rule = SMELL_RULE_BY_TYPE.get(rule, rule)
                if verifier is not None:
                    try:
                        verification = verifier.verify(
                            prompt, completion, smell_rule, kind, smoke_test
                        )
                    except ValueError as exc:
                        raise ValueError(
                            f"{rule}-{split}-{index:02d} (style {style}): {exc}"
                        ) from exc
                else:
                    verification = {"method": "unverified", "verified": False}
                method_counts[verification["method"]] = (
                    method_counts.get(verification["method"], 0) + 1
                )
                findings_counts[rule] = findings_counts.get(rule, 0) + 1

                records.append(
                    {
                        "id": f"{rule}-{split}-{index:02d}",
                        "source_group": f"authored-{rule}-{split}",
                        "split": split,
                        "prompt": prompt,
                        "completion": completion,
                        "license": LICENSE,
                        "refactoring_type": rule,
                        "smell_rule": smell_rule,
                        "variant": "findings",
                        "template_style": style,
                        "verification": verification,
                    }
                )

                if index <= clean_count:
                    if verifier is not None:
                        try:
                            clean_verification = verifier.verify_clean(completion)
                        except ValueError as exc:
                            raise ValueError(
                                f"{rule}-clean-{split}-{index:02d} (style {style}): {exc}"
                            ) from exc
                    else:
                        clean_verification = {"method": "unverified", "verified": False}
                    method_counts[clean_verification["method"]] = (
                        method_counts.get(clean_verification["method"], 0) + 1
                    )
                    clean_counts[rule] = clean_counts.get(rule, 0) + 1
                    records.append(
                        {
                            "id": f"{rule}-clean-{split}-{index:02d}",
                            "source_group": f"authored-{rule}-clean-{split}",
                            "split": split,
                            "prompt": completion,
                            "completion": completion,
                            "license": LICENSE,
                            "refactoring_type": rule,
                            "smell_rule": None,
                            "variant": "clean-control",
                            "template_style": style,
                            "verification": clean_verification,
                        }
                    )

                if verbose and len(records) % 25 == 0:
                    print(f"  verified {len(records):>3} records")

    manifest = {
        "dataset": "data/curated.jsonl",
        "name": "Curated Python refactoring dataset (authored)",
        "license": LICENSE,
        "provenance": (
            "Authored/synthetic: generated by scripts/generate_curated_dataset.py from "
            "parametric templates. Not scraped from real repositories and not "
            "human-annotated. Suitable for pipeline validation and LoRA training "
            "smoke tests; conclusions must not be presented as real-world dataset "
            "evidence (NFR06). Clean-control records are identity pairs and are "
            "labelled as such."
        ),
        "records": len(records),
        "splits": {
            split: sum(record["split"] == split for record in records)
            for split, _findings, _clean in SPLIT_SPECS
        },
        "refactoring_types": list(TYPES),
        "smell_rule_by_type": SMELL_RULE_BY_TYPE,
        "records_per_type": {
            rule: findings_counts.get(rule, 0) + clean_counts.get(rule, 0) for rule in TYPES
        },
        "findings_records_per_type": {rule: findings_counts.get(rule, 0) for rule in TYPES},
        "clean_records_per_type": {rule: clean_counts.get(rule, 0) for rule in TYPES},
        "variant_counts": {
            "findings": sum(findings_counts.values()),
            "clean-control": sum(clean_counts.values()),
        },
        "template_styles": STYLE_COUNTS,
        "verification_methods": method_counts,
        "verification_policy": {
            "golden-equivalence": (
                "Auto-synthesized golden tests compare completion vs prompt behaviour "
                "on sampled inputs inside the isolated sandbox (NFR01/NFR02)."
            ),
            "authored-smoke-test": (
                "Signature-changing parameter-object refactors are verified by an "
                "authored smoke test proving the new API works as intended."
            ),
            "clean-control": (
                "Identity pairs whose prompt the analyzer reports as finding-free; "
                "the completion is the same module. No code is executed because "
                "there is no behavioural change to compare."
            ),
        },
        "equivalence_not_applicable": _SKIPPED_EQUIVALENCE,
        "prompt_marker": (
            "No provenance comment is embedded in prompts: training and inference "
            "must see the same code. Provenance lives in id/source_group and this "
            "manifest."
        ),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "generator": "scripts/generate_curated_dataset.py",
    }
    return records, manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/curated.jsonl"))
    parser.add_argument("--manifest", type=Path, default=Path("data/manifest.json"))
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip sandbox verification (development only; records are marked unverified).",
    )
    args = parser.parse_args()

    print("Generating curated dataset (verification enabled by default)...")
    records, manifest = generate(verify=not args.no_verify)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    with open(args.output, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)

    manifest["sha256"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    with open(args.manifest, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

    print(f"Wrote {len(records)} records to {args.output}")
    print(f"Wrote manifest to {args.manifest}")
    print(json.dumps(manifest["splits"], indent=2))


if __name__ == "__main__":
    main()
