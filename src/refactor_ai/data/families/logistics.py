"""Shipping, logistics and scheduling families."""

from __future__ import annotations

from refactor_ai.data.codegen import literal as lit
from refactor_ai.data.families.base import Check, Param, family, maybe, pick, raises, returns
from refactor_ai.data.families.helpers import make, shuffled


@family("parcel-shipping", "shipping")
def parcel_shipping(r):
    fn = pick(r, ["parcel_cost", "parcel_postage", "postage_for_parcel"])
    weight = pick(r, ["weight", "weight_kg", "kilos"])
    zone = pick(r, ["zone", "region", "destination"])
    signed = pick(r, ["signed_for", "needs_signature", "tracked"])
    zones = pick(r, [("local", "national", "international"), ("city", "country", "abroad")])
    bases = pick(r, [(4.0, 7.5, 15.0), (3.5, 6.0, 12.0), (5, 9, 20)])
    per_kg = pick(r, [1.2, 0.8, 2.0])
    max_weight = pick(r, [30, 25, 50])
    fee = pick(r, [1.5, 2.0, 2.75])
    checks = [
        Check(
            f"{weight} > 0", f"{weight} <= 0", raises("ValueError", f"{weight} must be positive")
        ),
        Check(
            f"{weight} <= {max_weight}",
            f"{weight} > {max_weight}",
            pick(r, [raises("ValueError", "parcel is too heavy"), returns("None")]),
        ),
        Check(
            f"{zone} in {lit(zones)}",
            f"{zone} not in {lit(zones)}",
            raises("ValueError", expr=f"f'unknown {zone}: {{{zone}}}'"),
        ),
    ]
    if maybe(r, 0.5):
        checks = [checks[2], checks[0], checks[1]]
    core = [
        f"if {zone} == {lit(zones[0])}:",
        f"    base = {bases[0]}",
        f"elif {zone} == {lit(zones[1])}:",
        f"    base = {bases[1]}",
        "else:",
        f"    base = {bases[2]}",
        f"cost = base + {weight} * {per_kg}",
        f"if {signed}:",
        f"    cost = cost + {fee}",
        "return round(cost, 2)",
    ]
    params = [
        Param(weight, (-2, 0, 0.5, 3, max_weight, max_weight + 1), "float"),
        Param(zone, (*zones, "moon"), "str"),
        Param(signed, (False, True), "bool", default=False),
    ]
    return make(
        r, fn, params, checks, core, docs=("Postage for one parcel.",), returns="float | None"
    )


@family("freight-quote", "shipping")
def freight_quote(r):
    fn = pick(r, ["freight_quote", "truck_quote", "haulage_price"])
    pallets = pick(r, ["pallets", "pallet_count"])
    distance = pick(r, ["distance_km", "km", "route_km"])
    hazardous = pick(r, ["hazardous", "dangerous_goods"])
    capacity = pick(r, [26, 33, 22])
    near, far = pick(r, [(100, 500), (150, 600), (80, 400)])
    rates = pick(r, [(3.5, 2.75, 2.1), (4.0, 3.0, 2.2), (3.2, 2.6, 1.9)])
    hazard_fee = pick(r, [150, 200, 120])
    checks = [
        Check(
            f"{pallets} > 0",
            f"{pallets} <= 0",
            raises("ValueError", "pallet count must be positive"),
        ),
        Check(f"{pallets} <= {capacity}", f"{pallets} > {capacity}", returns("None")),
        Check(
            f"{distance} > 0", f"{distance} <= 0", raises("ValueError", "distance must be positive")
        ),
    ]
    checks = [checks[0], *shuffled(r, checks[1:])]
    core = [
        f"if {distance} < {near}:",
        f"    rate = {rates[0]}",
        f"elif {distance} < {far}:",
        f"    rate = {rates[1]}",
        "else:",
        f"    rate = {rates[2]}",
        f"quote = {pallets} * {distance} * rate",
        f"if {hazardous}:",
        f"    quote = quote + {hazard_fee}",
        "return round(quote, 2)",
    ]
    params = [
        Param(pallets, (-1, 0, 1, 10, capacity, capacity + 1), "int"),
        Param(distance, (0, 50, near, far - 1, far, 900), "int"),
        Param(hazardous, (False, True), "bool", default=False),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Price quote for a full or part truckload.",),
        returns="float | None",
    )


@family("delivery-slot", "scheduling")
def delivery_slot(r):
    fn = pick(r, ["delivery_slot", "slot_for_hour", "pick_delivery_window"])
    hour = pick(r, ["hour", "order_hour"])
    day = pick(r, ["weekday", "day"])
    closed = pick(r, ["sun", "fri"])
    noon, evening = pick(r, [(12, 17), (11, 16), (13, 18)])
    open_days = tuple(d for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun") if d != closed)
    checks = [
        Check(
            f"0 <= {hour} < 24",
            f"{hour} < 0 or {hour} >= 24",
            raises("ValueError", "hour must be between 0 and 23"),
        ),
        Check(f"{day} in {lit(open_days)}", f"{day} not in {lit(open_days)}", returns("None")),
    ]
    if maybe(r, 0.5):
        core = [
            f"if {hour} < {noon}:",
            "    return 'morning'",
            f"elif {hour} < {evening}:",
            "    return 'afternoon'",
            "else:",
            "    return 'evening'",
        ]
    else:
        core = [
            f"if {hour} < {noon}:",
            "    slot = 'morning'",
            f"elif {hour} < {evening}:",
            "    slot = 'afternoon'",
            "else:",
            "    slot = 'evening'",
            f"if {day} == 'sat':",
            "    slot = slot + '-weekend'",
            "return slot",
        ]
    params = [
        Param(hour, (-1, 0, noon - 1, noon, evening, 23, 24), "int"),
        Param(day, ("mon", "sat", closed, "xyz"), "str"),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Name of the delivery window for an order.",),
        returns="str | None",
    )


@family("warehouse-bin", "logistics")
def warehouse_bin(r):
    fn = pick(r, ["assign_bin", "storage_bin", "choose_shelf"])
    length = pick(r, ["length_cm", "longest_side"])
    weight = pick(r, ["weight_kg", "mass_kg"])
    fragile = pick(r, ["fragile", "is_fragile"])
    max_weight = pick(r, [40, 35, 50])
    small, medium = pick(r, [(30, 80), (25, 60), (40, 100)])
    checks = [
        Check(
            f"{length} > 0 and {weight} > 0",
            f"{length} <= 0 or {weight} <= 0",
            raises("ValueError", "dimensions must be positive"),
        ),
        Check(f"{weight} <= {max_weight}", f"{weight} > {max_weight}", returns("'PALLET'")),
    ]
    core = [
        f"if {fragile}:",
        "    return 'FRAGILE'",
        f"if {length} <= {small}:",
        "    return 'A1'",
        f"elif {length} <= {medium}:",
        "    return 'B2'",
        "else:",
        "    return 'C3'",
    ]
    params = [
        Param(length, (0, 10, small, small + 1, medium, medium + 1), "int"),
        Param(weight, (-1, 0, 1, max_weight, max_weight + 1), "float"),
        Param(fragile, (False, True), "bool", default=False),
    ]
    return make(
        r, fn, params, checks, core, docs=("Storage bin code for an incoming item.",), returns="str"
    )


@family("customs-duty", "shipping")
def customs_duty(r):
    fn = pick(r, ["customs_duty", "import_duty", "duty_payable"])
    value = pick(r, ["declared_value", "value", "invoice_value"])
    category = pick(r, ["category", "goods_type"])
    minimis = pick(r, [150, 100, 200])
    rates = pick(r, [(0.0, 0.12, 0.05), (0.02, 0.1, 0.04), (0.0, 0.15, 0.06)])
    checks = [
        Check(
            f"{value} >= 0",
            f"{value} < 0",
            raises("ValueError", "declared value cannot be negative"),
        ),
        Check(
            f"{category} in ('books', 'clothing', 'electronics')",
            f"{category} not in ('books', 'clothing', 'electronics')",
            pick(r, [raises("ValueError", "unsupported category"), returns("None")]),
        ),
    ]
    checks = shuffled(r, checks)
    core = [
        f"if {value} <= {minimis}:",
        "    return 0.0",
        f"if {category} == 'books':",
        f"    rate = {rates[0]}",
        f"elif {category} == 'clothing':",
        f"    rate = {rates[1]}",
        "else:",
        f"    rate = {rates[2]}",
        f"return round({value} * rate, 2)",
    ]
    params = [
        Param(value, (-1, 0, minimis, minimis + 1, 900), "float"),
        Param(category, ("books", "clothing", "electronics", "food"), "str"),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Duty owed on an imported parcel.",),
        returns="float | None",
    )


@family("tracking-status", "logistics")
def tracking_status(r):
    fn = pick(r, ["next_status", "advance_shipment", "apply_tracking_event"])
    current = pick(r, ["current", "status"])
    event = pick(r, ["event", "scan_event"])
    states = ("created", "shipped", "in_transit", "delivered")
    checks = [
        Check(
            f"{current} in {lit(states)}",
            f"{current} not in {lit(states)}",
            raises("ValueError", expr=f"f'unknown status {{{current}}}'"),
        ),
        Check(
            f"{current} != 'delivered'",
            f"{current} == 'delivered'",
            raises("ValueError", "parcel already delivered"),
        ),
    ]
    core = [
        f"if {event} == 'scan':",
        f"    if {current} == 'created':",
        "        return 'shipped'",
        "    return 'in_transit'",
        f"elif {event} == 'deliver':",
        "    return 'delivered'",
        "else:",
        f"    return {current}",
    ]
    params = [
        Param(current, (*states, "lost"), "str"),
        Param(event, ("scan", "deliver", "note"), "str"),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Shipment status after a tracking event.",),
        returns="str",
    )


@family("container-loading", "logistics")
def container_loading(r):
    fn = pick(r, ["load_container", "pick_boxes", "fill_container"])
    weights = pick(r, ["weights", "box_weights"])
    capacity = pick(r, ["capacity", "max_load"])
    checks = [
        Check(
            f"{capacity} > 0", f"{capacity} <= 0", raises("ValueError", "capacity must be positive")
        ),
        Check(f"len({weights}) > 0", f"len({weights}) == 0", returns("[]")),
    ]
    if maybe(r, 0.5):
        checks.reverse()
    core = [
        "loaded = []",
        "total = 0",
        f"for weight in {weights}:",
        f"    if total + weight <= {capacity}:",
        "        loaded.append(weight)",
        "        total = total + weight",
        "return loaded",
    ]
    params = [
        Param(weights, ([], [5, 3, 9], [10, 20, 5, 1], [50]), "list"),
        Param(capacity, (-1, 0, 10, 25), "int"),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Greedily choose boxes that fit the container.",),
        returns="list",
    )


@family("meeting-end", "scheduling")
def meeting_end(r):
    fn = pick(r, ["meeting_end", "end_time", "schedule_meeting"])
    start = pick(r, ["start_hour", "begin_hour"])
    duration = pick(r, ["duration_minutes", "minutes"])
    day = pick(r, ["weekday", "day"])
    first, last = pick(r, [(8, 17), (9, 16), (7, 18)])
    close = pick(r, [18, 19, 20])
    checks = [
        Check(
            f"{day} not in ('sat', 'sun')",
            f"{day} in ('sat', 'sun')",
            raises("ValueError", "no meetings on weekends"),
        ),
        Check(
            f"{first} <= {start} <= {last}",
            f"{start} < {first} or {start} > {last}",
            returns("None"),
        ),
        Check(
            f"{duration} > 0", f"{duration} <= 0", raises("ValueError", "duration must be positive")
        ),
    ]
    checks = [checks[0], *shuffled(r, checks[1:])]
    core = [
        f"end = {start} * 60 + {duration}",
        f"if end > {close} * 60:",
        "    raise ValueError('meeting ends after office hours')",
        "return (end // 60, end % 60)",
    ]
    params = [
        Param(start, (first - 1, first, 12, last, last + 1), "int"),
        Param(duration, (0, 30, 60, 90, 120, 180, 600), "int"),
        Param(day, ("mon", "sat"), "str"),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("End time of a meeting as (hour, minute).",),
        returns="tuple | None",
    )


@family("bus-departure", "scheduling")
def bus_departure(r):
    fn = pick(r, ["next_departure", "next_bus", "following_departure"])
    minute = pick(r, ["minute", "now_minute"])
    first = pick(r, ["first", "first_departure"])
    last = pick(r, ["last", "last_departure"])
    interval = pick(r, ["interval", "headway"])
    checks = [
        Check(
            f"{interval} > 0", f"{interval} <= 0", raises("ValueError", "interval must be positive")
        ),
        Check(
            f"{first} <= {last}",
            f"{first} > {last}",
            raises("ValueError", "first departure is after the last"),
        ),
    ]
    core = [
        f"if {minute} <= {first}:",
        f"    return {first}",
        f"if {minute} > {last}:",
        "    return None",
        f"waited = ({minute} - {first}) % {interval}",
        "if waited == 0:",
        f"    return {minute}",
        f"return {minute} + {interval} - waited",
    ]
    params = [
        Param(minute, (300, 360, 365, 380, 1200, 1201, 1300), "int"),
        Param(first, (360, 1200, 1400), "int"),
        Param(last, (1200,), "int"),
        Param(interval, (0, 20), "int"),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Minute of the next departure, or None after service ends.",),
    )


@family("table-reservation", "scheduling")
def table_reservation(r):
    fn = pick(r, ["find_table", "assign_table", "seat_party"])
    party = pick(r, ["party_size", "guests"])
    tables = pick(r, ["tables", "table_sizes"])
    max_party = pick(r, [12, 10, 16])
    checks = [
        Check(f"{party} > 0", f"{party} <= 0", raises("ValueError", "party size must be positive")),
        Check(f"{party} <= {max_party}", f"{party} > {max_party}", returns("None")),
        Check(
            f"len({tables}) > 0",
            f"len({tables}) == 0",
            raises("ValueError", "no tables configured"),
        ),
    ]
    checks = shuffled(r, checks)
    core = [
        f"for index, seats in enumerate({tables}):",
        f"    if seats >= {party}:",
        "        return index",
        "return -1",
    ]
    params = [
        Param(party, (0, 2, 5, max_party, max_party + 1), "int"),
        Param(tables, ([], [2, 4, 6], [4, 4], [8]), "list"),
    ]
    return make(
        r, fn, params, checks, core, docs=("Index of the first table large enough for the party.",)
    )
