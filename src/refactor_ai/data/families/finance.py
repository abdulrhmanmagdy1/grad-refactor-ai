"""Banking, billing and personal-finance families."""

from __future__ import annotations

from refactor_ai.data.codegen import literal as lit
from refactor_ai.data.families.base import Check, Param, family, maybe, pick, raises, returns
from refactor_ai.data.families.helpers import make, shuffled


@family("loan-decision", "finance")
def loan_decision(r):
    fn = pick(r, ["loan_decision", "assess_loan", "credit_decision"])
    income = pick(r, ["income", "annual_income"])
    debt = pick(r, ["monthly_debt", "debt_payments"])
    score = pick(r, ["credit_score", "score"])
    max_ratio = pick(r, [0.45, 0.4, 0.5])
    prime, near = pick(r, [(740, 670), (720, 650), (760, 690)])
    checks = [
        Check(f"{income} > 0", f"{income} <= 0", raises("ValueError", "income must be positive")),
        Check(
            f"300 <= {score} <= 850",
            f"{score} < 300 or {score} > 850",
            raises("ValueError", "credit score out of range"),
        ),
    ]
    checks = shuffled(r, checks)
    core = [
        f"ratio = {debt} * 12 / {income}",
        f"if ratio > {max_ratio}:",
        "    return ('declined', None)",
        f"if {score} >= {prime}:",
        "    return ('approved', 4.5)",
        f"elif {score} >= {near}:",
        "    return ('approved', 6.9)",
        "return ('review', None)",
    ]
    params = [
        Param(income, (0, 24000, 90000), "float"),
        Param(debt, (100, 800, 900, 1000, 1200), "float"),
        Param(score, (299, 300, 600, near, prime, 850, 851), "int"),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Decision and interest rate for a loan application.",),
        returns="tuple",
    )


@family("atm-withdrawal", "finance")
def atm_withdrawal(r):
    fn = pick(r, ["withdraw", "dispense_cash", "atm_withdraw"])
    balance = pick(r, ["balance", "account_balance"])
    amount = pick(r, ["amount", "requested"])
    today = pick(r, ["withdrawn_today", "spent_today"])
    note = pick(r, [10, 20, 50])
    limit = pick(r, [500, 1000, 400])
    checks = [
        Check(f"{amount} > 0", f"{amount} <= 0", raises("ValueError", "amount must be positive")),
        Check(
            f"{amount} % {note} == 0",
            f"{amount} % {note} != 0",
            raises("ValueError", f"amount must be a multiple of {note}"),
        ),
        Check(
            f"{today} + {amount} <= daily_limit",
            f"{today} + {amount} > daily_limit",
            raises("ValueError", "daily limit reached"),
        ),
        Check(
            f"{amount} <= {balance}",
            f"{amount} > {balance}",
            raises("ValueError", "insufficient funds"),
        ),
    ]
    checks = [checks[0], checks[1], *shuffled(r, checks[2:])]
    core = [f"return {balance} - {amount}"]
    if maybe(r, 0.5):
        core = [
            f"remaining = {balance} - {amount}",
            "if remaining < 20:",
            "    return (remaining, 'low balance')",
            "return (remaining, 'ok')",
        ]
    params = [
        Param(balance, (note * 2, note * 2 + 5, note * 2 + 20, 100, 2000), "int"),
        Param(amount, (-note, 0, note + 5, note * 2, limit), "int"),
        Param(today, (0, limit - note), "int"),
        Param("daily_limit", (limit,), "int", default=limit),
    ]
    return make(r, fn, params, checks, core, docs=("Balance after a cash withdrawal.",))


@family("invoice-status", "billing")
def invoice_status(r):
    fn = pick(r, ["invoice_status", "billing_state", "classify_invoice"])
    total = pick(r, ["total", "amount_due"])
    paid = pick(r, ["paid", "amount_paid"])
    due = pick(r, ["due_day", "due_date"])
    today = pick(r, ["today", "current_day"])
    grace = pick(r, [30, 45, 60])
    checks = [
        Check(
            f"{total} > 0", f"{total} <= 0", raises("ValueError", "invoice total must be positive")
        ),
        Check(
            f"{paid} >= 0", f"{paid} < 0", raises("ValueError", "paid amount cannot be negative")
        ),
    ]
    checks = shuffled(r, checks)
    core = [
        f"if {paid} >= {total}:",
        "    return 'paid'",
        f"elif {today} <= {due}:",
        "    return 'open'",
        f"elif {today} - {due} <= {grace}:",
        "    return 'overdue'",
        "else:",
        "    return 'collections'",
    ]
    params = [
        Param(total, (0, 100), "float"),
        Param(paid, (-1, 0, 20, 100), "float"),
        Param(due, (10,), "int"),
        Param(today, (5, 10, 10 + grace, 11 + grace), "int"),
    ]
    return make(
        r, fn, params, checks, core, docs=("Collection state of an invoice.",), returns="str"
    )


@family("currency-convert", "finance")
def currency_convert(r):
    fn = pick(r, ["convert", "convert_amount", "exchange"])
    amount = pick(r, ["amount", "value"])
    src = pick(r, ["source", "from_code"])
    dst = pick(r, ["target", "to_code"])
    rates = pick(r, ["rates", "rate_table"])
    table = pick(
        r, [{"USD": 1.0, "EUR": 0.92, "EGP": 48.5}, {"USD": 1.0, "GBP": 0.79, "JPY": 151.0}]
    )
    codes = tuple(table)
    checks = [
        Check(f"{amount} >= 0", f"{amount} < 0", raises("ValueError", "amount cannot be negative")),
        Check(
            f"{src} in {rates} and {dst} in {rates}",
            f"{src} not in {rates} or {dst} not in {rates}",
            pick(r, [raises("KeyError", "unknown currency"), returns("None")]),
        ),
    ]
    core = [
        f"if {src} == {dst}:",
        f"    return round({amount}, 2)",
        f"in_base = {amount} / {rates}[{src}]",
        f"return round(in_base * {rates}[{dst}], 2)",
    ]
    params = [
        Param(amount, (-1, 0, 10, 99.5), "float"),
        Param(src, (codes[0], codes[1], "XXX"), "str"),
        Param(dst, (codes[0], codes[2]), "str"),
        Param(rates, (table,), "dict"),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Convert an amount between currencies.",),
        returns="float | None",
    )


@family("rent-late-fee", "billing")
def rent_late_fee(r):
    fn = pick(r, ["late_fee", "rent_penalty", "overdue_rent_fee"])
    rent = pick(r, ["rent", "monthly_rent"])
    days = pick(r, ["days_late", "late_days"])
    rate = pick(r, [0.05, 0.04, 0.06])
    daily = pick(r, [10, 5, 8])
    cap = pick(r, [0.2, 0.15, 0.25])
    grace = pick(r, [5, 3, 7])
    checks = [
        Check(f"{rent} > 0", f"{rent} <= 0", raises("ValueError", "rent must be positive")),
        Check(f"{days} >= 0", f"{days} < 0", raises("ValueError", "days late cannot be negative")),
        Check(f"{days} > grace_days", f"{days} <= grace_days", returns("0.0")),
    ]
    checks = [*shuffled(r, checks[:2]), checks[2]]
    core = [
        f"fee = {rent} * {rate} + ({days} - grace_days) * {daily}",
        f"return round(min(fee, {rent} * {cap}), 2)",
    ]
    params = [
        Param(rent, (0, 900, 2000), "float"),
        Param(days, (-1, 0, grace, grace + 1, 40), "int"),
        Param("grace_days", (grace,), "int", default=grace),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Late fee owed on an overdue rent payment.",),
        returns="float",
    )


@family("income-tax", "finance")
def income_tax(r):
    fn = pick(r, ["income_tax", "tax_owed", "annual_tax"])
    income = pick(r, ["income", "taxable_income"])
    resident = pick(r, ["resident", "is_resident"])
    free, band = pick(r, [(10000, 40000), (12000, 50000), (8000, 35000)])
    low, high = pick(r, [(0.1, 0.2), (0.12, 0.25), (0.08, 0.22)])
    flat = pick(r, [0.25, 0.3])
    checks = [
        Check(f"{income} >= 0", f"{income} < 0", raises("ValueError", "income cannot be negative")),
        Check(resident, f"not {resident}", returns(f"round({income} * {flat}, 2)")),
    ]
    base_tax = round((band - free) * low, 2)
    core = [
        f"if {income} <= {free}:",
        "    return 0.0",
        f"elif {income} <= {band}:",
        f"    return round(({income} - {free}) * {low}, 2)",
        "else:",
        f"    return round({base_tax} + ({income} - {band}) * {high}, 2)",
    ]
    params = [
        Param(income, (-1, 0, free, free + 1, band, band + 1, 100000), "float"),
        Param(resident, (True, False), "bool", default=True),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Income tax with a tax-free allowance and two bands.",),
        returns="float",
    )


@family("budget-alert", "finance")
def budget_alert(r):
    fn = pick(r, ["budget_alert", "spending_warning", "check_budget"])
    spent = pick(r, ["spent", "spending"])
    budget = pick(r, ["budget", "monthly_budget"])
    category = pick(r, ["category", "label"])
    warn = pick(r, [0.8, 0.9, 0.75])
    checks = [
        Check(f"{budget} > 0", f"{budget} <= 0", raises("ValueError", "budget must be positive")),
        Check(f"{spent} >= 0", f"{spent} < 0", raises("ValueError", "spending cannot be negative")),
    ]
    core = [
        f"ratio = {spent} / {budget}",
        "if ratio >= 1:",
        f"    return {category} + ': over budget'",
        f"if ratio >= {warn}:",
        f"    return {category} + ': nearly used up'",
        "return None",
    ]
    params = [
        Param(spent, (-1, 0, 50, round(warn * 100), 95, 100, 120), "float"),
        Param(budget, (0, 100), "float"),
        Param(category, ("food",), "str"),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Warning text when a budget is nearly used up.",),
        returns="str | None",
    )


@family("savings-goal", "finance")
def savings_goal(r):
    fn = pick(r, ["months_to_goal", "savings_months", "time_to_target"])
    goal = pick(r, ["goal", "target_amount"])
    saved = pick(r, ["saved", "current_savings"])
    monthly = pick(r, ["monthly", "monthly_deposit"])
    horizon = pick(r, [120, 60, 240])
    checks = [
        Check(f"{goal} > 0", f"{goal} <= 0", raises("ValueError", "goal must be positive")),
        Check(f"{saved} < {goal}", f"{saved} >= {goal}", returns("0")),
        Check(f"{monthly} > 0", f"{monthly} <= 0", returns("None")),
    ]
    core = [
        "months = 0",
        f"balance = {saved}",
        f"while balance < {goal}:",
        f"    balance = balance + {monthly}",
        "    months = months + 1",
        f"if months > {horizon}:",
        "    return None",
        "return months",
    ]
    params = [
        Param(goal, (0, 1000, 100000), "float"),
        Param(saved, (0, 1000), "float"),
        Param(monthly, (0, 50, 400), "float"),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Months of saving needed to reach a goal.",),
        returns="int | None",
    )


@family("expense-claim", "finance")
def expense_claim(r):
    fn = pick(r, ["approve_expense", "review_claim", "expense_decision"])
    amount = pick(r, ["amount", "claimed"])
    kind = pick(r, ["kind", "expense_type"])
    receipt = pick(r, ["has_receipt", "receipt_attached"])
    limits = pick(
        r,
        [
            {"travel": 500, "meals": 60, "supplies": 200},
            {"travel": 800, "meals": 75, "supplies": 150},
        ],
    )
    checks = [
        Check(f"{amount} > 0", f"{amount} <= 0", raises("ValueError", "amount must be positive")),
        Check(
            f"{kind} in {lit(tuple(limits))}",
            f"{kind} not in {lit(tuple(limits))}",
            raises("ValueError", expr=f"f'unknown expense type {{{kind}}}'"),
        ),
        Check(
            f"{receipt} or {amount} <= 25",
            f"not {receipt} and {amount} > 25",
            returns("'needs receipt'"),
        ),
    ]
    core = [
        f"limit = {lit(limits)}[{kind}]",
        f"if {amount} <= limit:",
        "    return 'approved'",
        "return 'manager approval'",
    ]
    params = [
        Param(amount, (0, 20, 25, 50, *limits.values(), 400, 900), "float"),
        Param(kind, (*limits, "gifts"), "str"),
        Param(receipt, (True, False), "bool"),
    ]
    return make(r, fn, params, checks, core, docs=("Route an expense claim.",), returns="str")
