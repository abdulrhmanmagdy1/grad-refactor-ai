"""Pricing and retail families."""

from __future__ import annotations

from refactor_ai.data.codegen import literal as lit
from refactor_ai.data.families.base import Check, Param, family, maybe, pick, raises, returns
from refactor_ai.data.families.helpers import make, shuffled


@family("member-discount", "pricing")
def member_discount(r):
    fn = pick(r, ["member_price", "discounted_total", "checkout_total", "apply_member_discount"])
    total = pick(r, ["total", "subtotal", "amount"])
    level = pick(r, ["level", "tier", "membership"])
    coupon = pick(r, ["coupon", "promo_code", "voucher"])
    levels = pick(r, [("basic", "silver", "gold"), ("standard", "plus", "premium")])
    rates = pick(r, [(0.0, 0.1, 0.15), (0.0, 0.05, 0.12), (0.02, 0.08, 0.2)])
    code = pick(r, ["WELCOME5", "SPRING10", "LOYAL"])
    bonus = pick(r, [0.05, 0.1, 0.03])
    checks = [
        Check(
            f"{total} > 0",
            f"{total} <= 0",
            pick(r, [returns("0.0"), raises("ValueError", f"{total} must be positive")]),
        ),
        Check(
            f"{level} in {lit(levels)}",
            f"{level} not in {lit(levels)}",
            pick(r, [raises("ValueError", f"unknown {level}"), returns(total)]),
        ),
    ]
    if maybe(r, 0.5):
        core = [
            f"if {level} == {lit(levels[2])}:",
            f"    rate = {rates[2]}",
            f"elif {level} == {lit(levels[1])}:",
            f"    rate = {rates[1]}",
            "else:",
            f"    rate = {rates[0]}",
        ]
    else:
        table = {levels[0]: rates[0], levels[1]: rates[1], levels[2]: rates[2]}
        core = [f"rate = {lit(table)}[{level}]"]
    core += [
        f"if {coupon} == {lit(code)}:",
        f"    rate = rate + {bonus}",
        f"return round({total} * (1 - rate), 2)",
    ]
    params = [
        Param(total, (-10, 0, 19.99, 100, 250.5), "float"),
        Param(level, (*levels, "platinum"), "str"),
        Param(coupon, (None, code, "OTHER"), "str | None", default=None),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Return the price after the membership discount.", "Apply the member rate."),
        returns="float",
    )


@family("bulk-pricing", "pricing")
def bulk_pricing(r):
    fn = pick(r, ["unit_price", "price_per_item", "bulk_unit_price"])
    qty = pick(r, ["quantity", "qty", "count"])
    base = pick(r, ["base_price", "list_price", "price"])
    wholesale = pick(r, ["wholesale", "is_reseller", "trade_account"])
    big, mid = pick(r, [(100, 20), (50, 10), (200, 25)])
    f_big, f_mid = pick(r, [(0.8, 0.9), (0.75, 0.88), (0.85, 0.95)])
    max_order = pick(r, [500, 1000, 250])
    checks = [
        Check(f"{qty} >= 1", f"{qty} < 1", raises("ValueError", f"{qty} must be at least 1")),
        Check(
            f"{base} > 0",
            f"{base} <= 0",
            pick(r, [raises("ValueError", "price must be positive"), returns("None")]),
        ),
    ]
    if maybe(r, 0.5):
        checks.append(Check(f"{qty} <= {max_order}", f"{qty} > {max_order}", returns("None")))
    total_result = maybe(r, 0.4)
    core = [
        f"if {qty} >= {big}:",
        f"    unit = {base} * {f_big}",
        f"elif {qty} >= {mid}:",
        f"    unit = {base} * {f_mid}",
        "else:",
        f"    unit = {base}",
        f"if {wholesale}:",
        "    unit = unit * 0.95",
        f"return round(unit * {qty}, 2)" if total_result else "return round(unit, 2)",
    ]
    params = [
        Param(qty, (0, 1, mid - 1, mid, big, max_order, max_order + 1), "int"),
        Param(base, (-1.0, 0, 2.5, 40), "float"),
        Param(wholesale, (False, True), "bool", default=False),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Price for an order line with volume discounts.",),
        returns="float | None",
    )


@family("ticket-pricing", "pricing")
def ticket_pricing(r):
    fn = pick(r, ["ticket_price", "admission_price", "cinema_ticket_price"])
    age = pick(r, ["age", "visitor_age"])
    day = pick(r, ["day", "weekday"])
    student = pick(r, ["student", "has_student_card"])
    child, senior, adult = pick(r, [(6, 7, 11), (5, 8, 12), (4, 6, 10)])
    cheap_day = pick(r, ["tue", "wed"])
    days = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    checks = shuffled(
        r,
        [
            Check(f"{age} >= 0", f"{age} < 0", raises("ValueError", "age cannot be negative")),
            Check(
                f"{day} in {lit(days)}",
                f"{day} not in {lit(days)}",
                pick(r, [raises("ValueError", "invalid day"), returns("None")]),
            ),
        ],
    )
    core = [
        f"if {age} < 12:",
        f"    price = {child}",
        f"elif {age} >= 65:",
        f"    price = {senior}",
        "else:",
        f"    price = {adult}",
        f"if {student} and {age} >= 12:",
        "    price = price - 2",
        f"if {day} == {lit(cheap_day)}:",
        "    price = price - 1",
        "return price",
    ]
    params = [
        Param(age, (-1, 0, 11, 12, 30, 64, 65, 80), "int"),
        Param(day, ("mon", cheap_day, "sat", "holiday"), "str"),
        Param(student, (False, True), "bool", default=False),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Ticket price in whole currency units.",),
        returns="int | None",
    )


@family("parking-fee", "pricing")
def parking_fee(r):
    fn = pick(r, ["parking_fee", "parking_charge", "garage_fee"])
    minutes = pick(r, ["minutes", "duration_minutes", "parked_minutes"])
    vehicle = pick(r, ["vehicle", "vehicle_type"])
    permit = pick(r, ["has_permit", "resident_permit"])
    rates = pick(r, [(1, 2, 4), (1, 3, 5), (2, 3, 6)])
    cap = pick(r, [20, 25, 30])
    checks = [
        Check(f"not {permit}", permit, returns("0")),
        Check(
            f"{minutes} > 0", f"{minutes} <= 0", raises("ValueError", "minutes must be positive")
        ),
        Check(
            f"{vehicle} in ('car', 'motorbike', 'van')",
            f"{vehicle} not in ('car', 'motorbike', 'van')",
            raises("ValueError", "unsupported vehicle"),
        ),
    ]
    checks = [checks[0], *shuffled(r, checks[1:])]
    core = [
        f"hours = ({minutes} + 59) // 60",
        f"if {vehicle} == 'motorbike':",
        f"    rate = {rates[0]}",
        f"elif {vehicle} == 'van':",
        f"    rate = {rates[2]}",
        "else:",
        f"    rate = {rates[1]}",
        f"return min(hours * rate, {cap})",
    ]
    params = [
        Param(minutes, (-5, 0, 1, 60, 61, 200, 900), "int"),
        Param(vehicle, ("car", "motorbike", "van", "bus"), "str"),
        Param(permit, (False, True), "bool"),
    ]
    return make(r, fn, params, checks, core, docs=("Fee for one parking session.",), returns="int")


@family("hotel-booking", "pricing")
def hotel_booking(r):
    fn = pick(r, ["booking_total", "stay_price", "room_quote"])
    nights = pick(r, ["nights", "night_count"])
    season = pick(r, ["season", "period"])
    guests = pick(r, ["guests", "guest_count"])
    high, shoulder, low = pick(r, [(180, 140, 110), (210, 150, 95), (160, 130, 100)])
    extra = pick(r, [25, 30, 20])
    max_guests = pick(r, [4, 5, 6])
    checks = [
        Check(
            f"{nights} >= 1",
            f"{nights} < 1",
            raises("ValueError", "stay must be at least one night"),
        ),
        Check(
            f"{guests} >= 1",
            f"{guests} < 1",
            raises("ValueError", "at least one guest is required"),
        ),
        Check(
            f"{guests} <= {max_guests}",
            f"{guests} > {max_guests}",
            pick(r, [raises("ValueError", "too many guests for one room"), returns("None")]),
        ),
    ]
    core = [
        f"if {season} == 'high':",
        f"    nightly = {high}",
        f"elif {season} == 'shoulder':",
        f"    nightly = {shoulder}",
        "else:",
        f"    nightly = {low}",
        f"if {guests} > 2:",
        f"    nightly = nightly + ({guests} - 2) * {extra}",
        f"total = nightly * {nights}",
        f"if {nights} >= 7:",
        "    total = total * 0.9",
        "return round(total, 2)",
    ]
    params = [
        Param(nights, (0, 1, 3, 7, 10), "int"),
        Param(season, ("high", "shoulder", "low"), "str"),
        Param(guests, (0, 1, 2, 3, max_guests, max_guests + 1), "int"),
    ]
    return make(
        r, fn, params, checks, core, docs=("Total price of a hotel stay.",), returns="float | None"
    )


@family("gift-card", "retail")
def gift_card(r):
    fn = pick(r, ["redeem_gift_card", "redeem_card", "apply_gift_card"])
    balance = pick(r, ["balance", "card_balance"])
    amount = pick(r, ["amount", "charge"])
    active = pick(r, ["active", "is_active"])
    expired = pick(r, ["expired", "is_expired"])
    checks = [
        Check(active, f"not {active}", raises("PermissionError", "card is not active")),
        Check(f"not {expired}", expired, raises("PermissionError", "card has expired")),
        Check(f"{amount} > 0", f"{amount} <= 0", raises("ValueError", "amount must be positive")),
    ]
    checks = shuffled(r, checks[:2]) + checks[2:]
    if maybe(r, 0.5):
        core = [
            f"if {amount} <= {balance}:",
            f"    return round({balance} - {amount}, 2)",
            "else:",
            "    raise ValueError('insufficient balance')",
        ]
    else:
        core = [
            f"remaining = {balance} - {amount}",
            "if remaining < 0:",
            "    raise ValueError('insufficient balance')",
            "return round(remaining, 2)",
        ]
    params = [
        Param(balance, (0, 25.5, 100), "float"),
        Param(amount, (-5, 0, 10, 25.5, 150), "float"),
        Param(active, (True, False), "bool"),
        Param(expired, (False, True), "bool"),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Return the balance left after a purchase.",),
        returns="float",
    )


@family("sales-tax", "pricing")
def sales_tax(r):
    fn = pick(r, ["sales_tax", "tax_due", "compute_tax"])
    amount = pick(r, ["amount", "net_amount", "price"])
    region = pick(r, ["region", "district"])
    exempt = pick(r, ["exempt", "tax_exempt"])
    rates = pick(
        r,
        [
            {"north": 0.07, "south": 0.05, "east": 0.06},
            {"north": 0.08, "south": 0.04, "east": 0.065},
        ],
    )
    threshold = pick(r, [1000, 2000, 500])
    surcharge = pick(r, [5, 10, 2.5])
    checks = [
        Check(f"not {exempt}", exempt, returns("0.0")),
        Check(f"{amount} >= 0", f"{amount} < 0", raises("ValueError", "amount cannot be negative")),
        Check(
            f"{region} in {lit(tuple(rates))}",
            f"{region} not in {lit(tuple(rates))}",
            raises("ValueError", expr=f"f'no tax rate for {{{region}}}'"),
        ),
    ]
    core = [
        f"rate = {lit(rates)}[{region}]",
        f"tax = {amount} * rate",
        f"if {amount} > {threshold}:",
        f"    tax = tax + {surcharge}",
        "return round(tax, 2)",
    ]
    params = [
        Param(amount, (-1, 0, 99.99, threshold, threshold + 1), "float"),
        Param(region, (*rates, "west"), "str"),
        Param(exempt, (False, True), "bool", default=False),
    ]
    return make(
        r, fn, params, checks, core, docs=("Sales tax owed on a purchase.",), returns="float"
    )


@family("subscription-renewal", "pricing")
def subscription_renewal(r):
    fn = pick(r, ["renewal_price", "next_invoice_amount", "plan_renewal_cost"])
    plan = pick(r, ["plan", "plan_name", "tier"])
    years = pick(r, ["loyalty_years", "years_subscribed"])
    auto = pick(r, ["auto_renew", "autopay"])
    prices = pick(r, [(5, 15, 30), (4, 12, 25), (8, 20, 45)])
    checks = [
        Check(
            f"{plan} in ('basic', 'pro', 'team')",
            f"{plan} not in ('basic', 'pro', 'team')",
            pick(r, [returns("None"), raises("ValueError", f"unknown {plan}")]),
        ),
        Check(f"{years} >= 0", f"{years} < 0", raises("ValueError", "years cannot be negative")),
    ]
    core = [
        f"if {plan} == 'team':",
        f"    price = {prices[2]}",
        f"elif {plan} == 'pro':",
        f"    price = {prices[1]}",
        "else:",
        f"    price = {prices[0]}",
        f"if {years} >= 3:",
        "    price = price * 0.8",
        f"elif {years} >= 1:",
        "    price = price * 0.9",
        f"if not {auto}:",
        "    price = price + 2",
        "return round(price, 2)",
    ]
    params = [
        Param(plan, ("basic", "pro", "team", "gold"), "str"),
        Param(years, (-1, 0, 1, 2, 3, 5), "int"),
        Param(auto, (True, False), "bool", default=True),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Monthly price charged at renewal.",),
        returns="float | None",
    )
