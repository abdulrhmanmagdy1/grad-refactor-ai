"""Devices, operations, games and inventory families."""

from __future__ import annotations

from refactor_ai.data.codegen import literal as lit
from refactor_ai.data.families.base import Check, Param, family, maybe, pick, raises, returns
from refactor_ai.data.families.helpers import make, shuffled


@family("thermostat", "iot")
def thermostat(r):
    fn = pick(r, ["thermostat_action", "hvac_command", "climate_action"])
    current = pick(r, ["current", "room_temp"])
    target = pick(r, ["target", "setpoint"])
    mode = pick(r, ["mode", "hvac_mode"])
    low, high = pick(r, [(5, 35), (10, 30), (7, 32)])
    band = pick(r, [0.5, 1.0])
    checks = [
        Check(
            f"{mode} in ('heat', 'cool', 'auto')",
            f"{mode} not in ('heat', 'cool', 'auto')",
            returns("'off'"),
        ),
        Check(
            f"{low} <= {target} <= {high}",
            f"{target} < {low} or {target} > {high}",
            raises("ValueError", "target outside the safe range"),
        ),
    ]
    core = [
        f"diff = {target} - {current}",
        f"if abs(diff) < {band}:",
        "    return 'idle'",
        f"if {mode} == 'heat':",
        "    return 'heat' if diff > 0 else 'idle'",
        f"if {mode} == 'cool':",
        "    return 'cool' if diff < 0 else 'idle'",
        "return 'heat' if diff > 0 else 'cool'",
    ]
    params = [
        Param(current, (18, 20, 20.5, 21, 21.5, 22, 24), "float"),
        Param(target, (low - 1, low, 21, high, high + 1), "float"),
        Param(mode, ("heat", "cool", "auto", "fan"), "str"),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Command for the heating and cooling unit.",),
        returns="str",
    )


@family("battery-status", "iot")
def battery_status(r):
    fn = pick(r, ["battery_status", "power_state", "battery_label"])
    percent = pick(r, ["percent", "charge_percent"])
    charging = pick(r, ["charging", "plugged_in"])
    temp = pick(r, ["temperature_c", "cell_temp"])
    hot = pick(r, [60, 55, 50])
    critical, low = pick(r, [(10, 25), (5, 20), (15, 30)])
    checks = [
        Check(
            f"0 <= {percent} <= 100",
            f"{percent} < 0 or {percent} > 100",
            raises("ValueError", "percent must be between 0 and 100"),
        ),
        Check(f"{temp} < {hot}", f"{temp} >= {hot}", raises("RuntimeError", "battery overheating")),
    ]
    checks = shuffled(r, checks)
    core = [
        f"if {charging}:",
        f"    return 'full' if {percent} == 100 else 'charging'",
        f"elif {percent} < {critical}:",
        "    return 'critical'",
        f"elif {percent} < {low}:",
        "    return 'low'",
        "else:",
        "    return 'ok'",
    ]
    params = [
        Param(percent, (-1, 0, critical, low, 100, 101), "int"),
        Param(charging, (False, True), "bool"),
        Param(temp, (30, hot), "float"),
    ]
    return make(r, fn, params, checks, core, docs=("Human-readable battery state.",), returns="str")


@family("sensor-calibration", "iot")
def sensor_calibration(r):
    fn = pick(r, ["calibrate", "calibrated_reading", "correct_reading"])
    reading = pick(r, ["reading", "raw_value"])
    offset = pick(r, ["offset", "bias"])
    low, high = pick(r, [(-40, 125), (-20, 85), (0, 100)])
    checks = [
        Check(f"{reading} is not None", f"{reading} is None", returns("None")),
        Check("scale > 0", "scale <= 0", raises("ValueError", "scale must be positive")),
    ]
    core = [
        f"value = ({reading} + {offset}) * scale",
        f"if {low} <= value <= {high}:",
        "    return round(value, 2)",
        "return None",
    ]
    if maybe(r, 0.5):
        core = [
            f"value = ({reading} + {offset}) * scale",
            f"if value < {low} or value > {high}:",
            "    return None",
            "return round(value, 2)",
        ]
    params = [
        Param(reading, (None, low - 10, low, 20.5, high, high + 1), "float | None"),
        Param(offset, (0, -1.5), "float"),
        Param("scale", (0, 1.0, 1.1), "float", default=1.0),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Apply offset and scale to a sensor reading.",),
        returns="float | None",
    )


@family("score-bonus", "games")
def score_bonus(r):
    fn = pick(r, ["round_bonus", "score_with_bonus", "final_score"])
    score = pick(r, ["score", "points"])
    streak = pick(r, ["streak", "win_streak"])
    level = pick(r, ["level", "stage"])
    bonuses = pick(r, [(500, 200, 50), (300, 120, 40), (1000, 400, 100)])
    double_from = pick(r, [10, 8, 12])
    checks = [
        Check(f"{score} >= 0", f"{score} < 0", raises("ValueError", "score cannot be negative")),
        Check(f"{level} >= 1", f"{level} < 1", raises("ValueError", "levels start at 1")),
    ]
    checks = shuffled(r, checks)
    core = [
        "bonus = 0",
        f"if {streak} >= 10:",
        f"    bonus = {bonuses[0]}",
        f"elif {streak} >= 5:",
        f"    bonus = {bonuses[1]}",
        f"elif {streak} >= 3:",
        f"    bonus = {bonuses[2]}",
        f"if {level} >= {double_from}:",
        "    bonus = bonus * 2",
        f"return {score} + bonus",
    ]
    params = [
        Param(score, (-1, 0, 1200), "int"),
        Param(streak, (0, 3, 5, 10), "int"),
        Param(level, (0, 1, double_from), "int"),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Score for a round including streak bonuses.",),
        returns="int",
    )


@family("retry-backoff", "operations")
def retry_backoff(r):
    fn = pick(r, ["retry_delay", "backoff_seconds", "next_retry_delay"])
    attempt = pick(r, ["attempt", "try_number"])
    retryable = pick(r, ["retryable", "is_transient"])
    max_attempts = pick(r, [8, 5, 6])
    checks = [
        Check(retryable, f"not {retryable}", returns("None")),
        Check(
            f"{attempt} >= 1", f"{attempt} < 1", raises("ValueError", "attempt numbers start at 1")
        ),
        Check(
            f"{attempt} <= {max_attempts}",
            f"{attempt} > {max_attempts}",
            raises("RuntimeError", "too many retries"),
        ),
    ]
    core = [f"delay = base * 2 ** ({attempt} - 1)", "return min(delay, cap)"]
    params = [
        Param(attempt, (0, 1, 3, max_attempts, max_attempts + 1), "int"),
        Param(retryable, (True, False), "bool"),
        Param("base", (0.5,), "float", default=0.5),
        Param("cap", (4.0, 30.0), "float", default=30.0),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Seconds to wait before the next retry.",),
        returns="float | None",
    )


@family("cache-eviction", "operations")
def cache_eviction(r):
    fn = pick(r, ["should_evict", "evict_entry", "is_stale"])
    age = pick(r, ["age_seconds", "age"])
    hits = pick(r, ["hits", "hit_count"])
    pinned = pick(r, ["pinned", "is_pinned"])
    ttl = pick(r, [300, 600, 120])
    checks = [
        Check(f"not {pinned}", pinned, returns("False")),
        Check(f"{age} >= 0", f"{age} < 0", raises("ValueError", "age cannot be negative")),
    ]
    core = [
        f"if {age} > {ttl}:",
        "    return True",
        f"if {hits} == 0 and {age} > {ttl // 2}:",
        "    return True",
        "return False",
    ]
    params = [
        Param(age, (-1, 0, 10, ttl // 2, ttl // 2 + 1, ttl, ttl + 1), "int"),
        Param(hits, (0, 4), "int"),
        Param(pinned, (False, True), "bool", default=False),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Whether a cache entry should be evicted.",),
        returns="bool",
    )


@family("elevator-direction", "devices")
def elevator_direction(r):
    fn = pick(r, ["elevator_direction", "next_move", "lift_command"])
    current = pick(r, ["current_floor", "at_floor"])
    requested = pick(r, ["requested_floor", "target_floor"])
    load = pick(r, ["load_kg", "cabin_load"])
    top = pick(r, [12, 8, 20])
    capacity = pick(r, [630, 800, 1000])
    checks = [
        Check(
            f"0 <= {requested} <= {top}",
            f"{requested} < 0 or {requested} > {top}",
            raises("ValueError", "floor does not exist"),
        ),
        Check(f"{load} <= {capacity}", f"{load} > {capacity}", returns("'overloaded'")),
    ]
    checks = shuffled(r, checks)
    core = [
        f"if {requested} > {current}:",
        "    return 'up'",
        f"elif {requested} < {current}:",
        "    return 'down'",
        "else:",
        "    return 'open doors'",
    ]
    params = [
        Param(current, (3,), "int"),
        Param(requested, (-1, 0, 3, top, top + 1), "int"),
        Param(load, (200, capacity, capacity + 1), "int"),
    ]
    return make(
        r, fn, params, checks, core, docs=("Direction the elevator should move.",), returns="str"
    )


@family("traffic-light", "devices")
def traffic_light(r):
    fn = pick(r, ["next_light", "advance_signal", "signal_state"])
    state = pick(r, ["state", "light"])
    waiting = pick(r, ["pedestrian_waiting", "button_pressed"])
    seconds = pick(r, ["seconds_in_state", "elapsed"])
    green, yellow, red = pick(r, [(60, 4, 45), (50, 3, 40), (70, 5, 50)])
    checks = [
        Check(
            f"{state} in ('green', 'yellow', 'red')",
            f"{state} not in ('green', 'yellow', 'red')",
            raises("ValueError", expr=f"f'unknown state {{{state}}}'"),
        ),
        Check(f"{seconds} >= 0", f"{seconds} < 0", raises("ValueError", "time cannot be negative")),
    ]
    core = [
        f"if {state} == 'green':",
        f"    if {waiting} and {seconds} >= 20:",
        "        return 'yellow'",
        f"    return 'yellow' if {seconds} >= {green} else 'green'",
        f"if {state} == 'yellow':",
        f"    return 'red' if {seconds} >= {yellow} else 'yellow'",
        f"return 'green' if {seconds} >= {red} else 'red'",
    ]
    params = [
        Param(state, ("green", "yellow", "red", "blue"), "str"),
        Param(waiting, (False, True), "bool"),
        Param(seconds, (-1, 0, 20, yellow, red, green), "int"),
    ]
    return make(
        r, fn, params, checks, core, docs=("Next state of a traffic signal.",), returns="str"
    )


@family("log-filter", "operations")
def log_filter(r):
    fn = pick(r, ["should_log", "passes_filter", "keep_record"])
    level = pick(r, ["level", "record_level"])
    threshold = pick(r, ["threshold", "min_level"])
    logger = pick(r, ["logger", "source"])
    checks = [
        Check(
            f"{level} in levels", f"{level} not in levels", raises("ValueError", "unknown level")
        ),
        Check(
            f"{threshold} in levels",
            f"{threshold} not in levels",
            raises("ValueError", "unknown threshold"),
        ),
        Check(f"{logger} not in muted", f"{logger} in muted", returns(f"{level} == 'error'")),
    ]
    checks = [*shuffled(r, checks[:2]), checks[2]]
    core = [f"return levels[{level}] >= levels[{threshold}]"]
    if maybe(r, 0.4):
        core = [
            f"if {level} == 'error':",
            "    return True",
            f"return levels[{level}] >= levels[{threshold}]",
        ]
    params = [
        Param(level, ("debug", "warning", "error", "trace"), "str"),
        Param(threshold, ("info", "fatal"), "str"),
        Param(logger, ("app", "noisy"), "str"),
        Param("muted", ((), ("noisy",)), "tuple", default=()),
    ]
    variant = make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Whether a log record passes the filter.",),
        returns="bool",
    )
    variant.prelude = ["levels = {'debug': 10, 'info': 20, 'warning': 30, 'error': 40}"]
    return variant


@family("disk-usage", "operations")
def disk_usage(r):
    fn = pick(r, ["disk_alert", "storage_state", "volume_status"])
    used = pick(r, ["used_gb", "used"])
    total = pick(r, ["total_gb", "capacity_gb"])
    critical = pick(r, [95, 98, 90])
    checks = [
        Check(f"{total} > 0", f"{total} <= 0", raises("ValueError", "total size must be positive")),
        Check(
            f"0 <= {used} <= {total}",
            f"{used} < 0 or {used} > {total}",
            raises("ValueError", "used space out of range"),
        ),
    ]
    core = [
        f"percent = {used} * 100 / {total}",
        f"if percent >= {critical}:",
        "    return 'critical'",
        "elif percent >= warn_percent:",
        "    return 'warning'",
        "else:",
        "    return 'ok'",
    ]
    params = [
        Param(used, (-1, 10, 79, 80, 85, critical - 1, critical, 101), "float"),
        Param(total, (0, 100), "float"),
        Param("warn_percent", (80,), "int", default=80),
    ]
    return make(
        r, fn, params, checks, core, docs=("Alert level for a disk volume.",), returns="str"
    )


@family("http-status", "web")
def http_status(r):
    fn = pick(r, ["describe_status", "status_class", "classify_response"])
    code = pick(r, ["code", "status_code"])
    retry = pick(r, ["retry_server_errors", "retry_on_5xx"])
    checks = [
        Check(
            f"isinstance({code}, int)",
            f"not isinstance({code}, int)",
            raises("TypeError", "status code must be an integer"),
        ),
        Check(
            f"100 <= {code} <= 599",
            f"{code} < 100 or {code} > 599",
            raises("ValueError", "status code out of range"),
        ),
    ]
    core = [
        f"if {code} < 300:",
        f"    return 'success' if {code} >= 200 else 'informational'",
        f"if {code} < 400:",
        "    return 'redirect'",
        f"if {code} < 500:",
        "    return 'client error'",
        f"return 'retry' if {retry} else 'server error'",
    ]
    params = [
        Param(
            code,
            ("200", 99, 100, 101, 199, 200, 299, 300, 399, 400, 404, 499, 500, 599, 600),
            "int",
        ),
        Param(retry, (True, False), "bool", default=True),
    ]
    return make(
        r, fn, params, checks, core, docs=("Category of an HTTP status code.",), returns="str"
    )


@family("inventory-reorder", "inventory")
def inventory_reorder(r):
    fn = pick(r, ["reorder_quantity", "units_to_order", "replenishment"])
    stock = pick(r, ["stock", "on_hand"])
    sales = pick(r, ["daily_sales", "demand_per_day"])
    lead = pick(r, ["lead_days", "lead_time"])
    discontinued = pick(r, ["discontinued", "end_of_life"])
    factor = pick(r, [2, 3])
    checks = [
        Check(f"not {discontinued}", discontinued, returns("0")),
        Check(
            f"{stock} >= 0 and {sales} >= 0",
            f"{stock} < 0 or {sales} < 0",
            raises("ValueError", "stock and sales cannot be negative"),
        ),
        Check(f"{lead} > 0", f"{lead} <= 0", raises("ValueError", "lead time must be positive")),
    ]
    core = [
        f"needed = {sales} * {lead} * {factor}",
        f"if {stock} >= needed:",
        "    return 0",
        f"return needed - {stock}",
    ]
    params = [
        Param(stock, (-1, 0, 50, 500), "int"),
        Param(sales, (0, 5, 20), "int"),
        Param(lead, (0, 3), "int"),
        Param(discontinued, (False, True), "bool", default=False),
    ]
    return make(
        r, fn, params, checks, core, docs=("Units to reorder for one product.",), returns="int"
    )


@family("stock-reservation", "inventory")
def stock_reservation(r):
    fn = pick(r, ["reserve_stock", "hold_items", "allocate_units"])
    sku = pick(r, ["sku", "item_code"])
    qty = pick(r, ["quantity", "units"])
    stock = pick(r, ["stock", "inventory"])
    checks = [
        Check(f"{sku} in {stock}", f"{sku} not in {stock}", raises("KeyError", "unknown item")),
        Check(f"{qty} > 0", f"{qty} <= 0", raises("ValueError", "quantity must be positive")),
        Check(
            f"{stock}[{sku}] >= {qty}",
            f"{stock}[{sku}] < {qty}",
            pick(r, [returns("False"), raises("ValueError", "not enough stock")]),
        ),
    ]
    core = [
        f"remaining = {stock}[{sku}] - {qty}",
        "if remaining < 5:",
        "    return 'reserved, reorder soon'",
        "return 'reserved'",
    ]
    params = [
        Param(sku, ("A1", "B2", "Z9"), "str"),
        Param(qty, (0, 1, 3, 6, 40), "int"),
        Param(stock, ({"A1": 50, "B2": 6},), "dict"),
    ]
    return make(r, fn, params, checks, core, docs=("Reserve units of an item for an order.",))


@family("water-tariff", "utilities")
def water_tariff(r):
    fn = pick(r, ["water_bill", "water_charge", "consumption_cost"])
    used = pick(r, ["cubic_meters", "usage_m3"])
    meter_ok = pick(r, ["meter_ok", "meter_working"])
    tiers = pick(r, [(10, 30), (15, 40), (8, 25)])
    prices = pick(r, [(0.5, 1.2, 2.5), (0.4, 1.0, 2.0), (0.65, 1.5, 3.0)])
    fixed = pick(r, [3.0, 5.0, 2.5])
    checks = [
        Check(
            meter_ok, f"not {meter_ok}", raises("RuntimeError", "meter fault; estimate required")
        ),
        Check(f"{used} >= 0", f"{used} < 0", raises("ValueError", "usage cannot be negative")),
    ]
    core = [
        f"if {used} <= {tiers[0]}:",
        f"    variable = {used} * {prices[0]}",
        f"elif {used} <= {tiers[1]}:",
        f"    variable = {tiers[0]} * {prices[0]} + ({used} - {tiers[0]}) * {prices[1]}",
        "else:",
        f"    variable = {tiers[0]} * {prices[0]} + ({tiers[1]} - {tiers[0]}) * {prices[1]}"
        f" + ({used} - {tiers[1]}) * {prices[2]}",
        f"return round({fixed} + variable, 2)",
    ]
    params = [
        Param(used, (-1, 0, tiers[0], tiers[0] + 1, tiers[1], tiers[1] + 1), "float"),
        Param(meter_ok, (True, False), "bool"),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Monthly water bill with tiered prices.",),
        returns="float",
    )


@family("vending-change", "devices")
def vending_change(r):
    fn = pick(r, ["vend", "dispense", "buy_item"])
    slot = pick(r, ["slot", "selection"])
    paid = pick(r, ["paid", "inserted"])
    prices = pick(r, ["prices", "price_list"])
    checks = [
        Check(f"{slot} in {prices}", f"{slot} not in {prices}", raises("KeyError", "empty slot")),
        Check(
            f"{paid} >= {prices}[{slot}]",
            f"{paid} < {prices}[{slot}]",
            returns(f"('insert more', {prices}[{slot}] - {paid})"),
        ),
    ]
    core = [
        f"change = {paid} - {prices}[{slot}]",
        "if change == 0:",
        "    return ('enjoy', 0)",
        "return ('take change', change)",
    ]
    table = pick(r, [{"A1": 150, "B3": 90}, {"C2": 120, "D4": 75}])
    params = [
        Param(slot, (*table, "Z9"), "str"),
        Param(paid, (50, *table.values(), 200), "int"),
        Param(prices, (table,), "dict"),
    ]
    return make(
        r, fn, params, checks, core, docs=("Vending outcome and change in cents.",), returns="tuple"
    )


@family("seat-upgrade", "travel")
def seat_upgrade(r):
    fn = pick(r, ["upgrade_offer", "seat_upgrade", "offer_upgrade"])
    tier = pick(r, ["status_tier", "loyalty_tier"])
    seats = pick(r, ["free_business_seats", "seats_left"])
    fare = pick(r, ["fare_class", "booking_class"])
    tiers = ("blue", "silver", "gold")
    checks = [
        Check(f"{seats} > 0", f"{seats} <= 0", returns("None")),
        Check(f"{fare} != 'basic'", f"{fare} == 'basic'", returns("None")),
        Check(
            f"{tier} in {lit(tiers)}",
            f"{tier} not in {lit(tiers)}",
            raises("ValueError", "unknown loyalty tier"),
        ),
    ]
    checks = shuffled(r, checks)
    core = [
        f"nearly_full = {seats} < 3",
        f"if {tier} == 'gold':",
        "    return 0",
        f"elif {tier} == 'silver':",
        "    return 150 if nearly_full else 99",
        "else:",
        "    return 300",
    ]
    params = [
        Param(tier, (*tiers, "red"), "str"),
        Param(seats, (0, 2, 9), "int"),
        Param(fare, ("basic", "flex"), "str"),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Price of a business-class upgrade, or None.",),
        returns="int | None",
    )
