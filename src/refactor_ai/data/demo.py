"""Hand-written demonstration cases for src/refactor_ai/fixtures/demo_cases.json.

The six functions were written by hand for the demonstration (by the coding agent on
behalf of the data and evaluation workstream) in domains that no template family
covers. They range from two guard clauses to elif chains, loops and conditions whose
negation is easy to get wrong, so a demonstration can show both a passing and a failing
check. Inputs are chosen by hand to exercise every branch outcome and boundary; the
expected outcomes are obtained by executing the trusted original in the curation
executor, never typed by hand. build_demo_cases() also requires full branch coverage,
exercised return/raise statements and identical outcomes for the reference code.
"""

from __future__ import annotations

from dataclasses import dataclass

from refactor_ai.contracts import ReferenceCase
from refactor_ai.data import refgen
from refactor_ai.data.executor import Job, run_jobs
from refactor_ai.data.mutation import mutants
from refactor_ai.tasks import guard_clauses

DEMO_GROUP = "demo"
DEMO_LICENSE = "LicenseRef-team-authored-pending"


@dataclass(frozen=True)
class DemoSpec:
    case_id: str
    title: str
    difficulty: str
    code: str
    calls: tuple[tuple[str, str], ...]


def _calls(*items: str) -> tuple[tuple[str, str], ...]:
    """Each item is 'args' or 'args | kwargs' in Python literal syntax."""
    calls = []
    for item in items:
        args, _, kwargs = item.partition(" | ")
        calls.append((args.strip(), kwargs.strip() or "{}"))
    return tuple(calls)


LIBRARY_FINE = '''def library_fine(days_overdue, is_member):
    """Fine in cents for returning a library item late."""
    if days_overdue >= 0:
        if days_overdue > 0:
            rate = 20 if is_member else 35
            return min(days_overdue * rate, 1500)
        else:
            return 0
    else:
        raise ValueError("days_overdue cannot be negative")
'''

PRINT_JOB = '''def print_job_cost(pages, mode, duplex=False):
    """Cost in cents of a print job."""
    if pages > 0:
        if pages <= 500:
            if mode == "color":
                per_page = 25
            elif mode == "mono":
                per_page = 8
            else:
                raise ValueError("mode must be mono or color")
            cost = pages * per_page
            if duplex:
                cost = cost - pages // 2 * 2
            return cost
        else:
            return None
    else:
        raise ValueError("pages must be positive")
'''

WIFI_SIGNAL = '''def signal_quality(dbm, band):
    """Describe a Wi-Fi signal strength reading."""
    if isinstance(dbm, int):
        if -100 <= dbm <= 0:
            if band == "5GHz":
                dbm = dbm - 3
            if dbm >= -50:
                return "excellent"
            elif dbm >= -67:
                return "good"
            elif dbm >= -80:
                return "fair"
            else:
                return "poor"
        else:
            raise ValueError("dbm must be between -100 and 0")
    else:
        raise TypeError("dbm must be an integer")
'''

PORT_NUMBER = '''def parse_port(text, allow_privileged=False):
    """Parse a TCP port number typed by a user."""
    if text is not None:
        text = text.strip()
        if text.isdigit():
            port = int(text)
            if 1 <= port <= 65535:
                if port < 1024 and not allow_privileged:
                    raise PermissionError("privileged port")
                return port
            else:
                raise ValueError("port out of range")
        else:
            raise ValueError("port must be a number")
    else:
        return None
'''

RECYCLING_POINTS = '''def recycling_points(items, member_level):
    """Reward points for recyclables given as (material, grams) pairs."""
    if member_level in ("bronze", "silver", "gold"):
        if len(items) > 0:
            points = 0
            for material, grams in items:
                if grams <= 0:
                    continue
                if material == "glass":
                    points = points + grams // 100
                elif material in ("paper", "plastic"):
                    points = points + grams // 50
            if member_level == "gold":
                points = points * 2
            elif member_level == "silver":
                points = points + points // 2
            return points
        else:
            return 0
    else:
        raise ValueError("unknown member level")
'''

DICE_SCORE = '''def dice_score(dice, category):
    """Score five dice in a small Yacht-style game."""
    if len(dice) == 5:
        if all(1 <= value <= 6 for value in dice):
            if category == "yacht":
                if len(set(dice)) == 1:
                    return 50
                else:
                    return 0
            elif category == "straight":
                if sorted(dice) in ([1, 2, 3, 4, 5], [2, 3, 4, 5, 6]):
                    return 30
                return 0
            elif category == "chance":
                return sum(dice)
            else:
                raise ValueError("unknown category")
        else:
            raise ValueError("dice values must be between 1 and 6")
    else:
        raise ValueError("exactly five dice are required")
'''

DEMO_SPECS = (
    DemoSpec(
        "demo-library-fine",
        "Library fine (easy: two guard clauses)",
        "easy",
        LIBRARY_FINE,
        _calls("[-1, True]", "[0, False]", "[1, True]", "[1, False]", "[3, False]", "[100, True]"),
    ),
    DemoSpec(
        "demo-print-job",
        "Print job cost (easy: guards around an elif chain)",
        "easy",
        PRINT_JOB,
        _calls(
            "[0, 'mono']",
            "[-3, 'color']",
            "[1, 'mono']",
            "[5, 'color'] | {'duplex': True}",
            "[5, 'mono']",
            "[500, 'color']",
            "[501, 'mono']",
            "[10, 'draft']",
        ),
    ),
    DemoSpec(
        "demo-wifi-signal",
        "Wi-Fi signal quality (medium: chained range check and type check)",
        "medium",
        WIFI_SIGNAL,
        _calls(
            "['-60', '2.4GHz']",
            "[-101, '2.4GHz']",
            "[1, '5GHz']",
            "[-100, '2.4GHz']",
            "[0, '2.4GHz']",
            "[-50, '2.4GHz']",
            "[-48, '5GHz']",
            "[-67, '2.4GHz']",
            "[-68, '2.4GHz']",
            "[-80, '2.4GHz']",
            "[-81, '5GHz']",
        ),
    ),
    DemoSpec(
        "demo-port-number",
        "Port number parser (medium: boundaries and a compound condition)",
        "medium",
        PORT_NUMBER,
        _calls(
            "[None]",
            "[' 8080 ']",
            "['http']",
            "['-1']",
            "['0']",
            "['1']",
            "['1'] | {'allow_privileged': True}",
            "['1023']",
            "['1024']",
            "['65535']",
            "['65536']",
        ),
    ),
    DemoSpec(
        "demo-recycling-points",
        "Recycling reward points (hard: guards before a loop)",
        "hard",
        RECYCLING_POINTS,
        _calls(
            "[[('glass', 250)], 'platinum']",
            "[[], 'bronze']",
            "[[('glass', 250), ('paper', 120), ('metal', 500)], 'bronze']",
            "[[('plastic', -5), ('glass', 99)], 'bronze']",
            "[[('glass', 300), ('plastic', 100)], 'silver']",
            "[[('paper', 260)], 'gold']",
        ),
    ),
    DemoSpec(
        "demo-dice-score",
        "Dice score (hard: four levels, a negated all() and an elif chain)",
        "hard",
        DICE_SCORE,
        _calls(
            "[[1, 2, 3], 'chance']",
            "[[0, 1, 2, 3, 4], 'chance']",
            "[[1, 2, 3, 4, 7], 'yacht']",
            "[[3, 3, 3, 3, 3], 'yacht']",
            "[[3, 3, 3, 3, 4], 'yacht']",
            "[[5, 4, 3, 2, 1], 'straight']",
            "[[2, 3, 4, 5, 6], 'straight']",
            "[[1, 1, 2, 3, 4], 'straight']",
            "[[1, 2, 3, 4, 6], 'chance']",
            "[[6, 6, 6, 6, 6], 'pairs']",
        ),
    ),
)


class DemoCaseError(ValueError):
    pass


def build_demo_cases(workers: int = 2) -> list[ReferenceCase]:
    """Build and verify the demonstration cases from DEMO_SPECS."""
    prepared = []
    seed0_jobs: list[Job] = []
    seed1_jobs: list[Job] = []
    for spec in DEMO_SPECS:
        check = guard_clauses.check_input(spec.code)
        if not check.supported:
            raise DemoCaseError(f"{spec.case_id}: unsupported ({check.reasons})")
        target = guard_clauses.to_guard_clauses(spec.code)
        if target is None or not guard_clauses.rubric(spec.code, target).passed:
            raise DemoCaseError(f"{spec.case_id}: reference target fails the rubric")
        name = check.function_name
        instrumented, branch_count = refgen.instrument_branches(spec.code)
        mutant_list = mutants(spec.code)
        seed0_jobs += [
            Job(f"{spec.case_id}|orig", spec.code, name, spec.calls, "lines"),
            Job(f"{spec.case_id}|branches", instrumented, name, spec.calls, "branches"),
            Job(f"{spec.case_id}|target", target, name, spec.calls, "outcome"),
        ]
        seed0_jobs += [
            Job(f"{spec.case_id}|{m.mutant_id}", m.code, name, spec.calls, "outcome")
            for m in mutant_list
        ]
        seed1_jobs.append(Job(f"{spec.case_id}|orig", spec.code, name, spec.calls, "lines"))
        prepared.append((spec, name, target, branch_count, [m.mutant_id for m in mutant_list]))
    results0 = run_jobs(seed0_jobs, hash_seed=0, workers=workers)
    results1 = run_jobs(seed1_jobs, hash_seed=1, workers=workers)
    cases = []
    for spec, name, target, branch_count, mutant_ids in prepared:
        plan = refgen.build_test_plan(
            spec.code,
            list(spec.calls),
            results0[f"{spec.case_id}|orig"],
            results1[f"{spec.case_id}|orig"],
            results0[f"{spec.case_id}|branches"],
            results0[f"{spec.case_id}|target"],
            {mid: results0[f"{spec.case_id}|{mid}"] for mid in mutant_ids},
            branch_count,
            preferred=set(range(len(spec.calls))),
            min_tests=len(spec.calls),
            max_tests=len(spec.calls),
        )
        if isinstance(plan, refgen.Rejection):
            raise DemoCaseError(f"{spec.case_id}: {plan.reason}: {plan.detail}")
        metrics = plan.metrics
        if metrics["tests"] != len(spec.calls):
            raise DemoCaseError(f"{spec.case_id}: some hand-chosen calls were not usable")
        if metrics["branch_outcomes_covered"] != metrics["branch_outcomes_total"]:
            raise DemoCaseError(f"{spec.case_id}: branch coverage is incomplete: {metrics}")
        cases.append(
            ReferenceCase(
                case_id=spec.case_id,
                task_type=guard_clauses.TASK_TYPE,
                title=spec.title,
                function_name=name,
                original_code=spec.code,
                reference_code=target,
                tests=plan.tests,
                source_group=DEMO_GROUP,
                license=DEMO_LICENSE,
                provenance=(
                    f"Hand-written for the demonstration ({spec.difficulty}) by the coding "
                    "agent on behalf of the data and evaluation workstream; not derived from "
                    "any dataset record. reference_code from guard_clauses.to_guard_clauses; "
                    "expected outcomes from executing the original in the curation executor; "
                    f"all {metrics['branch_outcomes_total']} branch outcomes and "
                    f"{metrics['exit_lines']} return/raise statements exercised; "
                    f"{metrics['mutants_killed']} of {metrics['mutants']} single-point "
                    "mutants detected. Redistribution license pending a team decision."
                ),
            )
        )
    return cases


def demo_cases_json(cases: list[ReferenceCase]) -> str:
    import json

    return json.dumps([case.model_dump(mode="json") for case in cases], indent=2) + "\n"
