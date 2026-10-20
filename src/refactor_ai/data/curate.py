"""Reproducible curation of datasets/guard_clauses/v1.

Pipeline (all steps deterministic for a fixed seed and fixed inputs):

1. Assign template families to splits (refactor_ai.data.splits).
2. Generate variants per family with string-seeded random generators, normalize their
   formatting, drop duplicates and keep only inputs that guard_clauses.check_input
   supports and whose reference target passes guard_clauses.rubric.
3. Load the pinned licensed sources (MBPP, HumanEval) and apply the same rules.
4. Execute originals, targets and mutants in the curation executor and build reference
   tests (refactor_ai.data.refgen); drop candidates without trustworthy tests.
5. Keep a fixed number of variants per family, build prompts and completions with a
   deterministic explanation, and add static analysis notes to part of the training
   split.
6. Check exact and near-duplicates across splits, against external pilot fixtures and
   against the demonstration cases; resolve and log them.
7. Return records, per-record metadata and a curation log; refactor_ai.data.manifest
   writes them with hashes.
"""

from __future__ import annotations

import ast
import builtins
import hashlib
import json
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from refactor_ai.data import leakage, refgen, sources
from refactor_ai.data.codegen import canonical_function
from refactor_ai.data.executor import Job, run_jobs
from refactor_ai.data.explain import explain, guard_changes
from refactor_ai.data.families import FAMILIES, all_families
from refactor_ai.data.mutation import mutants
from refactor_ai.data.splits import SPLITS, assign_family_splits
from refactor_ai.task_format import (
    PROMPT_VERSION,
    build_refactor_user_prompt,
    render_refactor_completion,
)
from refactor_ai.tasks import guard_clauses

DATASET_VERSION = "guard_clauses-v1"
DEFAULT_SEED = 20261020
EXTERNAL_WATCH_THRESHOLD = 0.5
TRAIN_ONLY_FAMILIES = {
    "flag-parse": (
        "same purpose as parse_bool in the models workstream pilot fixtures "
        "(training/pilot/functions.py; identifier/literal Jaccard 0.61, below the 0.8 "
        "near-duplicate rule); kept out of held-out splits as a precaution"
    ),
}
TEMPLATE_SOURCE = "team-template"
TEMPLATE_LICENSE = "LicenseRef-team-authored-pending"
REFACTORING_TYPE = guard_clauses.TASK_TYPE
RECORD_FIELDS = (
    "id",
    "source_group",
    "split",
    "prompt",
    "completion",
    "license",
    "refactoring_type",
    "original_code",
    "target_code",
    "function_name",
    "tests",
    "source",
    "source_url",
    "provenance",
    "prompt_version",
    "task_version",
)


@dataclass
class CurationConfig:
    root: Path
    seed: int = DEFAULT_SEED
    train_variants: int = 11
    heldout_variants: int = 7
    validation_families: int = 12
    test_families: int = 12
    surplus: int = 3
    max_attempts: int = 150
    families: list[str] | None = None
    real_sources: tuple[str, ...] = ("mbpp", "humaneval")
    allow_download: bool = False
    raw_dir: Path | None = None
    external_paths: tuple[Path, ...] | None = None
    demo_path: Path | None = None
    workers: int = 4

    def resolved_raw_dir(self) -> Path:
        return self.raw_dir or self.root / "data" / "raw"

    def resolved_external(self) -> tuple[Path, ...]:
        if self.external_paths is not None:
            return self.external_paths
        return (self.root / "training" / "pilot",)

    def resolved_demo(self) -> Path:
        return self.demo_path or self.root / "src" / "refactor_ai" / "fixtures" / "demo_cases.json"


@dataclass
class Candidate:
    key: str
    source: str
    group: str
    function_name: str
    original: str
    target: str
    calls: list[tuple[str, str]]
    license: str
    source_url: str
    family: str | None = None
    category: str | None = None
    attempt: int | None = None
    item_id: str | None = None
    styles: list[str] | None = None
    preferred: set[int] = field(default_factory=set)
    seed_call_count: int = 0


@dataclass
class CurationResult:
    records: list[dict]
    metadata: list[dict]
    log: dict
    config_summary: dict


def _qualify(code: str, function_name: str | None) -> tuple[str | None, str | None, str]:
    """Return (target, None, '') or (None, reason, detail) using the shared task rules."""
    check = guard_clauses.check_input(code)
    if not check.supported:
        return None, "unsupported:" + "+".join(check.reasons), check.describe()
    if function_name and check.function_name != function_name:
        return None, "function_name_mismatch", f"{check.function_name} != {function_name}"
    target = guard_clauses.to_guard_clauses(code)
    if target is None:
        return None, "no_target", "reference transformation returned None"
    result = guard_clauses.rubric(code, target)
    if not result.passed:
        return None, "rubric_failed", "; ".join(result.reasons)
    return target, None, ""


def _family_candidates(
    config: CurationConfig, assignment: dict[str, str], log: dict
) -> list[Candidate]:
    wanted_keys = sorted(config.families) if config.families else sorted(FAMILIES)
    candidates: list[Candidate] = []
    seen: dict[str, str] = {}
    for key in wanted_keys:
        fam = FAMILIES[key]
        need = config.train_variants if assignment[key] == "train" else config.heldout_variants
        need += config.surplus
        found = 0
        for attempt in range(config.max_attempts):
            if found >= need:
                break
            rng = random.Random(f"{config.seed}:{key}:{attempt}")
            variant = fam.build(rng)
            try:
                code = canonical_function(variant.render())
            except (SyntaxError, ValueError) as exc:
                log["exclusions"].append(
                    _exclusion(f"tpl-{key}#a{attempt:03d}", "generation", "invalid_code", str(exc))
                )
                continue
            normalized = leakage.normalized_code(code)
            if normalized in seen:
                log["generation"]["duplicates_skipped"] += 1
                continue
            seen[normalized] = key
            target, reason, detail = _qualify(code, variant.name)
            if target is None:
                log["exclusions"].append(
                    _exclusion(f"tpl-{key}#a{attempt:03d}", "qualification", reason, detail)
                )
                continue
            calls = refgen.calls_from_params(variant.params, f"{config.seed}:{key}:{attempt}:calls")
            candidates.append(
                Candidate(
                    key=f"tpl-{key}#a{attempt:03d}",
                    source=TEMPLATE_SOURCE,
                    group=f"tpl-{key}",
                    function_name=variant.name,
                    original=code,
                    target=target,
                    calls=calls,
                    license=TEMPLATE_LICENSE,
                    source_url=f"repo:src/refactor_ai/data/families/{_module_of(fam)}.py#{key}",
                    family=key,
                    category=fam.category,
                    attempt=attempt,
                    styles=list(variant.styles),
                )
            )
            found += 1
        log["generation"]["families"][key] = {"qualified_candidates": found, "needed": need}
    return candidates


def _module_of(fam) -> str:
    return fam.build.__module__.rsplit(".", 1)[-1]


def _real_candidates(config: CurationConfig, log: dict) -> list[Candidate]:
    candidates: list[Candidate] = []
    raw_dir = config.resolved_raw_dir()
    for name in config.real_sources:
        source = sources.SOURCES[name]
        path = sources.ensure_source(source, raw_dir, allow_download=config.allow_download)
        loader = sources.load_mbpp if name == "mbpp" else sources.load_humaneval
        items = loader(path)
        reasons: dict[str, list[str]] = defaultdict(list)
        qualified = []
        for item in items:
            target, reason, _detail = _qualify(item.code, item.function_name or None)
            if target is None:
                reasons[reason].append(item.item_id)
                continue
            if _free_names(item.code):
                reasons["free_names"].append(item.item_id)
                continue
            if not item.seed_calls:
                reasons["no_literal_test_calls"].append(item.item_id)
                continue
            derived = sources.derived_calls(item.seed_calls)
            calls = list(item.seed_calls) + derived
            item_slug = item.item_id.lower().replace("humaneval/", "")
            group = f"{name}-task-{item_slug}" if name == "mbpp" else f"{name}-{item_slug}"
            qualified.append(item.item_id)
            candidates.append(
                Candidate(
                    key=group,
                    source=name,
                    group=group,
                    function_name=item.function_name,
                    original=item.code,
                    target=target,
                    calls=calls,
                    license=source.license,
                    source_url=source.item_url_template.format(item=item.item_id),
                    item_id=item.item_id,
                    preferred=set(range(len(item.seed_calls))),
                    seed_call_count=len(item.seed_calls),
                )
            )
        log["real_sources"][name] = {
            "url": source.url,
            "sha256": source.sha256,
            "license": source.license,
            "license_url": source.license_url,
            "items": len(items),
            "qualified_static": len(qualified),
            "qualified_items": qualified,
            "excluded_by_reason": {
                key: sorted(ids, key=_natural) for key, ids in sorted(reasons.items())
            },
        }
    return candidates


def _natural(item_id: str) -> tuple:
    digits = "".join(ch for ch in item_id if ch.isdigit())
    return (int(digits) if digits else -1, item_id)


def _free_names(code: str) -> list[str]:
    """Names the function reads that are neither bound locally nor builtins."""
    func, _ = guard_clauses.parse_function(code)
    if func is None:
        return []
    bound = {arg.arg for arg in ast.walk(func.args) if isinstance(arg, ast.arg)}
    for node in ast.walk(func):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bound.add(node.id)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
    loads = {
        node.id
        for node in ast.walk(func)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }
    return sorted(loads - bound - set(dir(builtins)) - {func.name})


def _exclusion(candidate: str, stage: str, reason: str, detail: str) -> dict:
    return {"candidate": candidate, "stage": stage, "reason": reason, "detail": detail[:500]}


def _build_jobs(
    candidates: list[Candidate],
) -> tuple[list[Job], list[Job], dict[str, int], dict[str, list[str]]]:
    seed0_jobs: list[Job] = []
    seed1_jobs: list[Job] = []
    branch_counts: dict[str, int] = {}
    mutant_ids: dict[str, list[str]] = {}
    for cand in candidates:
        calls = tuple(cand.calls)
        name = cand.function_name
        seed0_jobs.append(Job(f"{cand.key}|orig", cand.original, name, calls, "lines"))
        seed1_jobs.append(Job(f"{cand.key}|orig", cand.original, name, calls, "lines"))
        instrumented, count = refgen.instrument_branches(cand.original)
        branch_counts[cand.key] = count
        seed0_jobs.append(Job(f"{cand.key}|branches", instrumented, name, calls, "branches"))
        seed0_jobs.append(Job(f"{cand.key}|target", cand.target, name, calls, "outcome"))
        ids = []
        for mutant in mutants(cand.original):
            ids.append(mutant.mutant_id)
            seed0_jobs.append(
                Job(f"{cand.key}|{mutant.mutant_id}", mutant.code, name, calls, "outcome")
            )
        mutant_ids[cand.key] = ids
    return seed0_jobs, seed1_jobs, branch_counts, mutant_ids


def _findings_for(code: str) -> list[dict]:
    check = guard_clauses.check_input(code)
    return [
        {"start_line": item.start_line, "end_line": item.end_line, "reason": item.reason}
        for item in check.opportunities
    ]


def uses_findings(record_id: str, seed: int) -> bool:
    """Rule for the multi-role prompt variant: about half of the training records."""
    return hashlib.sha256(f"{seed}:findings:{record_id}".encode()).digest()[0] % 2 == 0


SOURCE_LABELS = {
    "mbpp": (
        "MBPP task",
        "Austin et al., 2021, arXiv:2108.07732",
        "google-research/google-research@f82046b",
    ),
    "humaneval": (
        "HumanEval task",
        "Chen et al., 2021, arXiv:2107.03374",
        "openai/human-eval@463c980",
    ),
}


def _provenance(cand: Candidate, plan: refgen.TestPlan, seed: int) -> str:
    checked = plan.metrics["differential_calls_equal"]
    common = (
        "Target: guard_clauses.to_guard_clauses. Test outcomes: trusted original executed by "
        f"the curation executor; the target gave the same outcome on all {checked} usable inputs."
    )
    if cand.source == TEMPLATE_SOURCE:
        return (
            f"Team-authored template family '{cand.family}' ({cand.category}), attempt "
            f"{cand.attempt}, seed {seed}; written for this project by the coding agent on "
            f"behalf of the team, no third-party code; license pending a team decision. {common}"
        )
    label, citation, origin = SOURCE_LABELS[cand.source]
    source = sources.SOURCES[cand.source]
    return (
        f"{label} {cand.item_id.split('/')[-1]} ({source.license}; {citation}) from {origin}; "
        "line endings and trailing spaces normalized. Test inputs: the task's own "
        f"{cand.seed_call_count} test calls plus derived variations. {common}"
    )


def _record_id(cand: Candidate, index: int | None) -> str:
    if cand.source == TEMPLATE_SOURCE:
        return f"gc1-{cand.family}-{index:02d}"
    return f"gc1-{cand.group}"


def curate(config: CurationConfig) -> CurationResult:
    log: dict = {
        "prompt_version": PROMPT_VERSION,
        "task_version": guard_clauses.TASK_VERSION,
        "generation": {"duplicates_skipped": 0, "families": {}},
        "exclusions": [],
        "real_sources": {},
        "tests": {},
        "leakage": {},
        "selection": {},
    }
    family_list = [(fam.key, fam.category) for fam in all_families()]
    if config.families:
        family_list = [item for item in family_list if item[0] in set(config.families)]
    assignment = assign_family_splits(
        family_list,
        seed=config.seed,
        validation=config.validation_families,
        test=config.test_families,
        train_only=frozenset(TRAIN_ONLY_FAMILIES),
    )
    candidates = _family_candidates(config, assignment, log)
    candidates += _real_candidates(config, log)

    seed0_jobs, seed1_jobs, branch_counts, mutant_ids = _build_jobs(candidates)
    results0 = run_jobs(seed0_jobs, hash_seed=0, workers=config.workers)
    results1 = run_jobs(seed1_jobs, hash_seed=1, workers=config.workers)

    plans: dict[str, refgen.TestPlan] = {}
    discarded_calls: Counter = Counter()
    for cand in candidates:
        plan = refgen.build_test_plan(
            cand.original,
            cand.calls,
            results0[f"{cand.key}|orig"],
            results1[f"{cand.key}|orig"],
            results0[f"{cand.key}|branches"],
            results0[f"{cand.key}|target"],
            {mid: results0[f"{cand.key}|{mid}"] for mid in mutant_ids[cand.key]},
            branch_counts[cand.key],
            preferred=cand.preferred,
        )
        if isinstance(plan, refgen.Rejection):
            log["exclusions"].append(_exclusion(cand.key, "tests", plan.reason, plan.detail))
            continue
        discarded_calls.update(plan.discarded)
        plans[cand.key] = plan
    log["tests"]["discarded_calls_by_reason"] = dict(sorted(discarded_calls.items()))

    chosen: list[tuple[Candidate, str]] = []
    by_family: dict[str, list[Candidate]] = defaultdict(list)
    for cand in candidates:
        if cand.key in plans and cand.family is not None:
            by_family[cand.family].append(cand)
    for family_key in sorted(by_family):
        split = assignment[family_key]
        wanted = config.train_variants if split == "train" else config.heldout_variants
        ordered = sorted(by_family[family_key], key=lambda c: c.attempt)
        kept = ordered[:wanted]
        log["selection"][family_key] = {
            "split": split,
            "passing_candidates": len(ordered),
            "kept": len(kept),
            "surplus_not_used": [c.key for c in ordered[wanted:]],
        }
        chosen += [(cand, split) for cand in kept]
    for cand in candidates:
        if cand.family is None and cand.key in plans:
            chosen.append((cand, "test"))

    entries = _assemble(chosen, plans, config)
    entries = _resolve_leakage(entries, config, log)
    return _finish(entries, log, config, assignment)


@dataclass
class _Entry:
    record: dict
    meta: dict
    cand: Candidate


def _assemble(
    chosen: list[tuple[Candidate, str]], plans: dict, config: CurationConfig
) -> list[_Entry]:
    entries: list[_Entry] = []
    counters: dict[str, int] = defaultdict(int)
    for cand, split in sorted(chosen, key=lambda item: (item[0].group, item[0].attempt or 0)):
        index = None
        if cand.family is not None:
            counters[cand.family] += 1
            index = counters[cand.family]
        record_id = _record_id(cand, index)
        plan = plans[cand.key]
        explanation = explain(cand.original, cand.target)
        findings = _findings_for(cand.original)
        with_findings = split == "train" and uses_findings(record_id, config.seed)
        prompt = build_refactor_user_prompt(cand.original, findings if with_findings else None)
        record = {
            "id": record_id,
            "source_group": cand.group,
            "split": split,
            "prompt": prompt,
            "completion": render_refactor_completion(explanation, cand.target),
            "license": cand.license,
            "refactoring_type": REFACTORING_TYPE,
            "original_code": cand.original,
            "target_code": cand.target,
            "function_name": cand.function_name,
            "tests": plan.tests,
            "source": cand.source,
            "source_url": cand.source_url,
            "provenance": _provenance(cand, plan, config.seed),
            "prompt_version": PROMPT_VERSION,
            "task_version": guard_clauses.TASK_VERSION,
        }
        changes = guard_changes(cand.original)
        meta = {
            "id": record_id,
            "candidate": cand.key,
            "source": cand.source,
            "source_group": cand.group,
            "family": cand.family,
            "category": cand.category,
            "attempt": cand.attempt,
            "item_id": cand.item_id,
            "check_styles": cand.styles,
            "prompt_has_findings": with_findings,
            "nesting_depth_original": guard_clauses.code_nesting_depth(cand.original),
            "nesting_depth_target": guard_clauses.code_nesting_depth(cand.target),
            "guard_clauses_created": len(changes),
            "inverted_conditions": sum(change.inverted for change in changes),
            "original_lines": len(cand.original.splitlines()),
            "original_chars": len(cand.original),
            "prompt_chars": len(prompt),
            "completion_chars": len(record["completion"]),
            "test_metrics": plan.metrics,
        }
        entries.append(_Entry(record, meta, cand))
    return entries


def _split_rank(entry: _Entry) -> int:
    return SPLITS.index(entry.record["split"])


def _resolve_leakage(entries: list[_Entry], config: CurationConfig, log: dict) -> list[_Entry]:
    """Remove duplicates and near-duplicates; policy keeps the held-out record.

    Exact duplicates of a normalized prompt or original are removed everywhere. Equal
    normalized targets or completions are leakage only across splits (two nesting styles
    of one function legitimately share a target inside a split). For any cross-split
    match the record in the earlier split (train before validation before test) is
    removed, so held-out families stay complete. A held-out record that matches an
    external pilot fixture is removed; an overlap with a demonstration case is an error.
    """
    removed: dict[str, str] = {}
    exact_log = []

    def drop(entry: _Entry, reason: str, detail: str) -> None:
        if entry.record["id"] not in removed:
            removed[entry.record["id"]] = reason
            log["exclusions"].append(_exclusion(entry.record["id"], "leakage", reason, detail))

    exact_fields = (
        ("prompt", leakage.normalized_prompt, False),
        ("original_code", leakage.normalized_code, False),
        ("target_code", leakage.normalized_code, True),
        ("completion", leakage.normalized_prompt, True),
    )
    for field_name, normalizer, cross_split_only in exact_fields:
        groups: dict[str, list[_Entry]] = defaultdict(list)
        for entry in entries:
            if entry.record["id"] not in removed:
                groups[leakage.digest(normalizer(entry.record[field_name]))].append(entry)
        for group in groups.values():
            if len(group) < 2:
                continue
            group.sort(key=lambda e: (-_split_rank(e), e.record["id"]))
            keeper = group[0]
            for entry in group[1:]:
                if cross_split_only and entry.record["split"] == keeper.record["split"]:
                    continue
                exact_log.append(
                    {
                        "field": field_name,
                        "kept": keeper.record["id"],
                        "removed": entry.record["id"],
                    }
                )
                drop(entry, f"exact_duplicate_{field_name}", f"same as {keeper.record['id']}")

    def fingerprints(items: list[_Entry], field_name: str) -> list[leakage.Fingerprint]:
        return [
            leakage.Fingerprint.of(
                e.record["id"], e.record["split"], e.record["source_group"], e.record[field_name]
            )
            for e in items
            if e.record["id"] not in removed
        ]

    # Near duplicates across splits (each split pair once) on originals and on targets.
    by_id = {e.record["id"]: e for e in entries}
    cross_split = {}
    for field_name in ("original_code", "target_code"):
        prints = fingerprints(entries, field_name)
        per_split = {split: [p for p in prints if p.split == split] for split in SPLITS}
        examined = 0
        flagged: list[leakage.PairScore] = []
        top: list[leakage.PairScore] = []
        top_structure: list[leakage.PairScore] = []
        max_similarity: dict[str, float] = {}
        structure_vs_train: dict[str, float] = {}
        for left_split, right_split in (
            ("train", "validation"),
            ("train", "test"),
            ("validation", "test"),
        ):
            report = leakage.compare(per_split[left_split], per_split[right_split])
            examined += report.pairs_examined
            flagged += report.flagged
            top += report.top
            top_structure += report.top_structure
            for label, value in report.max_similarity.items():
                max_similarity[label] = max(max_similarity.get(label, 0.0), value)
            if left_split == "train":
                for fp in per_split[right_split]:
                    structure_vs_train[fp.label] = report.max_structure.get(fp.label, 0.0)
        for pair in flagged:
            loser = by_id[pair.left]  # the left side is always the earlier split
            drop(
                loser, "near_duplicate_across_splits", f"{field_name}: {pair.left} vs {pair.right}"
            )
        top.sort(key=lambda p: (-p.set_similarity, -p.bag_similarity, p.left, p.right))
        top_structure.sort(
            key=lambda p: (-p.structure_similarity, -p.set_similarity, p.left, p.right)
        )
        cross_split[field_name] = {
            "pairs_examined": examined,
            "flagged_pairs": [pair.as_dict() for pair in flagged],
            "max_cross_split_set_similarity_by_split": _max_by_split(entries, max_similarity),
            "top_pairs_by_set_similarity": [
                pair.as_dict() for pair in top[: leakage.REPORT_TOP_PAIRS]
            ],
            "structure_similarity_to_nearest_train_record": {
                split: _quantiles(
                    [
                        structure_vs_train[p.label]
                        for p in per_split[split]
                        if p.label in structure_vs_train
                    ]
                )
                for split in ("validation", "test")
            },
            "top_pairs_by_structure": [
                pair.as_dict() for pair in top_structure[: leakage.REPORT_TOP_PAIRS]
            ],
        }
    log["leakage"]["cross_split"] = cross_split
    log["leakage"]["exact_duplicates"] = exact_log

    # External fixtures (models workstream pilot) and demonstration cases.
    external, inventory = leakage.external_code(list(config.resolved_external()), config.root)
    demo_codes = _demo_codes(config.resolved_demo())
    log["leakage"]["external_inventory"] = inventory
    heldout = [e for e in entries if e.record["split"] != "train" and e.record["id"] not in removed]
    everything = [e for e in entries if e.record["id"] not in removed]
    for label_set, codes, pool, kind in (
        ("pilot", external, heldout, "external_pilot"),
        ("demo", demo_codes, everything, "demo_case"),
    ):
        outside = [
            leakage.Fingerprint.of(label, "external", label_set, code) for label, code in codes
        ]
        exact_external = {leakage.digest(leakage.normalized_code(code)) for _, code in codes}
        flagged = []
        examined = 0
        best = 0.0
        top: list[dict] = []
        watch: dict[tuple[str, str, str], dict] = {}
        for field_name in ("original_code", "target_code"):
            prints = fingerprints(pool, field_name)
            report = leakage.compare(prints, outside, skip_same_split=False)
            examined += report.pairs_examined
            best = max([best, *[report.max_similarity.get(p.label, 0.0) for p in prints]])
            top += [{**pair.as_dict(), "field": field_name} for pair in report.top]
            for pair in report.flagged:
                flagged.append({**pair.as_dict(), "field": field_name})
            for entry in pool:
                if (
                    leakage.digest(leakage.normalized_code(entry.record[field_name]))
                    in exact_external
                ):
                    flagged.append(
                        {
                            "left": entry.record["id"],
                            "right": label_set,
                            "exact": True,
                            "field": field_name,
                        }
                    )
            for left in prints:
                for right in outside:
                    similarity = leakage.jaccard_set(left.token_set, right.token_set)
                    if similarity >= EXTERNAL_WATCH_THRESHOLD:
                        key = (left.label, right.label, field_name)
                        watch[key] = {**leakage.score(left, right).as_dict(), "field": field_name}
        if kind == "demo_case" and flagged:
            raise ValueError(f"demonstration cases overlap the dataset: {flagged[:3]}")
        for item in flagged:
            drop(by_id[item["left"]], f"near_duplicate_{kind}", f"matches {item['right']}")
        top.sort(
            key=lambda p: (
                -p["jaccard_set"],
                -p["jaccard_multiset"],
                p["left"],
                p["right"],
                p["field"],
            )
        )
        log["leakage"][label_set] = {
            "compared_records": "validation and test" if kind == "external_pilot" else "all splits",
            "code_items": len(codes),
            "code_labels": [label for label, _ in codes],
            "pairs_examined": examined,
            "max_set_similarity": round(best, 4),
            "flagged": flagged,
            f"watch_list_set_similarity_at_least_{EXTERNAL_WATCH_THRESHOLD}": [
                watch[key] for key in sorted(watch)
            ],
            "top_pairs_by_set_similarity": top[:10],
        }
    return [e for e in entries if e.record["id"] not in removed]


def _max_by_split(entries: list[_Entry], max_similarity: dict[str, float]) -> dict:
    out = {}
    for split in SPLITS:
        values = [
            max_similarity[e.record["id"]]
            for e in entries
            if e.record["split"] == split and e.record["id"] in max_similarity
        ]
        out[split] = round(max(values), 4) if values else None
    return out


def _quantiles(values: list[float]) -> dict | None:
    """Nearest-rank quantiles (no interpolation) of a list of similarities."""
    if not values:
        return None
    ordered = sorted(values)

    def rank(q: float) -> float:
        index = max(0, min(len(ordered) - 1, int(-(-q * len(ordered) // 1)) - 1))
        return round(ordered[index], 4)

    return {
        "records": len(ordered),
        "min": round(ordered[0], 4),
        "median": rank(0.5),
        "p90": rank(0.9),
        "max": round(ordered[-1], 4),
    }


def _demo_codes(path: Path) -> list[tuple[str, str]]:
    if not path.exists():
        return []
    cases = json.loads(path.read_text(encoding="utf-8"))
    codes = []
    for case in cases:
        codes.append((f"demo:{case['case_id']}:original", case["original_code"]))
        if case.get("reference_code"):
            codes.append((f"demo:{case['case_id']}:reference", case["reference_code"]))
    return codes


def _finish(
    entries: list[_Entry], log: dict, config: CurationConfig, assignment: dict[str, str]
) -> CurationResult:
    entries.sort(key=lambda e: (SPLITS.index(e.record["split"]), e.record["id"]))
    for entry in entries:
        if tuple(entry.record) != RECORD_FIELDS:
            raise AssertionError("record fields drifted from the contract")
    records = [entry.record for entry in entries]
    metadata = [entry.meta for entry in entries]
    groups: dict[str, set[str]] = defaultdict(set)
    for record in records:
        groups[record["source_group"]].add(record["split"])
    crossing = sorted(group for group, splits in groups.items() if len(splits) > 1)
    if crossing:
        raise AssertionError(f"source groups cross splits: {crossing}")
    config_summary = {
        "seed": config.seed,
        "train_variants_per_family": config.train_variants,
        "heldout_variants_per_family": config.heldout_variants,
        "validation_families": config.validation_families,
        "test_families": config.test_families,
        "surplus_candidates_per_family": config.surplus,
        "max_attempts_per_family": config.max_attempts,
        "real_sources": list(config.real_sources),
        "real_source_split": "test (each item is its own source group)",
        "train_only_families": dict(sorted(TRAIN_ONLY_FAMILIES.items())),
        "external_watch_threshold": EXTERNAL_WATCH_THRESHOLD,
        "family_split_assignment": dict(sorted(assignment.items())),
        "findings_rule": (
            "train records whose sha256(f'{seed}:findings:{id}') first byte is even get the "
            "static guard_clauses.check_input opportunities as 'Analysis notes'; validation "
            "and test prompts never include notes"
        ),
        "near_duplicate_rule": (
            f"Allamanis (2019) identifier/literal token Jaccard: set >= {leakage.SET_THRESHOLD} "
            f"and multiset >= {leakage.BAG_THRESHOLD}, on ast-normalized original and target "
            "code, all functions regardless of size"
        ),
    }
    return CurationResult(records, metadata, log, config_summary)
