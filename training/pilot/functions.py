"""Pilot functions for the T04 model benchmark and the T05 LoRA feasibility pilot.

PILOT MATERIAL, NOT THE DATASET. These small functions were written for this pilot by
the models workstream (coding agent, 2026-10-20). They are not curated data, they are
not part of datasets/, and results on them say nothing about final model quality. The
curated dataset and its frozen splits belong to the data workstream.

Each function is written in the nested style that the guard_clauses task targets and
must pass guard_clauses.check_input (build_pilot_data.py enforces this).

- purpose "benchmark": base-model inference measurements (T04), never trained on.
- purpose "lora_pilot": records for the bounded LoRA smoke run (T05). Their split only
  serves the pilot; "test" records exist because the dataset validator requires all
  three splits, and they are never passed to the Trainer.

maximal_inputs() builds three synthetic in-scope functions of exactly 3,000 characters
(realistic ASCII code, a digit-dense literal and Arabic text) that are used only to
measure token lengths and long-context latency.
"""

from __future__ import annotations

PILOT_LICENSE = "team-authored pilot material (no project license selected; see NOTICE.md)"
PILOT_SOURCE = "models workstream pilot functions (training/pilot/functions.py)"

PILOT_FUNCTIONS: list[dict] = [
    {
        "id": "bench-01",
        "purpose": "benchmark",
        "split": None,
        "code": """
def shipping_cost(weight, express):
    if weight > 0:
        if express:
            return 10 + weight * 2
        else:
            return 5 + weight
    else:
        raise ValueError("weight must be positive")
""",
    },
    {
        "id": "bench-02",
        "purpose": "benchmark",
        "split": None,
        "code": """
def describe_user(user):
    if user is not None:
        if user.get("active"):
            name = user.get("name", "unknown")
            return "Active user: " + name
        else:
            return "Inactive user"
    else:
        return "No user"
""",
    },
    {
        "id": "bench-03",
        "purpose": "benchmark",
        "split": None,
        "code": """
def letter_grade(score):
    if 0 <= score <= 100:
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        else:
            return "F"
    else:
        raise ValueError("score out of range")
""",
    },
    {
        "id": "bench-04",
        "purpose": "benchmark",
        "split": None,
        "code": '''
def apply_discount(prices, rate):
    """Return the prices after applying a discount rate."""
    if prices:
        if 0 < rate < 1:
            result = []
            for price in prices:
                result.append(round(price * (1 - rate), 2))
            return result
        else:
            raise ValueError("rate must be between 0 and 1")
    else:
        return []
''',
    },
    {
        "id": "bench-05",
        "purpose": "benchmark",
        "split": None,
        "code": """
def parse_port(text):
    if text:
        if text.isdigit():
            port = int(text)
            if 0 < port < 65536:
                return port
            else:
                raise ValueError("port out of range")
        else:
            raise ValueError("port must be numeric")
    else:
        raise ValueError("port is required")
""",
    },
    {
        "id": "bench-06",
        "purpose": "benchmark",
        "split": None,
        "code": """
def withdraw(balance, amount):
    if amount > 0:
        if amount <= balance:
            return balance - amount
        else:
            raise ValueError("insufficient funds")
    else:
        raise ValueError("amount must be positive")
""",
    },
    {
        "id": "bench-07",
        "purpose": "benchmark",
        "split": None,
        "code": """
def classify_temperature(celsius, unit):
    if unit == "C":
        if celsius < 0:
            return "freezing"
        elif celsius < 20:
            return "cold"
        else:
            return "warm"
    else:
        return "unknown unit"
""",
    },
    {
        "id": "bench-08",
        "purpose": "benchmark",
        "split": None,
        "code": """
def average_positive(values):
    if values is not None:
        if len(values) > 0:
            total = 0
            count = 0
            for value in values:
                if value > 0:
                    total += value
                    count += 1
            if count == 0:
                return 0.0
            return total / count
        else:
            return 0.0
    else:
        raise TypeError("values must not be None")
""",
    },
    {
        "id": "pilot-01",
        "purpose": "lora_pilot",
        "split": "train",
        "code": """
def normalize_username(name):
    if isinstance(name, str):
        stripped = name.strip()
        if stripped:
            return stripped.lower()
        else:
            raise ValueError("name must not be blank")
    else:
        raise TypeError("name must be a string")
""",
    },
    {
        "id": "pilot-02",
        "purpose": "lora_pilot",
        "split": "train",
        "code": """
def bmi_category(weight_kg, height_m):
    if height_m > 0:
        bmi = weight_kg / (height_m * height_m)
        if bmi < 18.5:
            return "underweight"
        elif bmi < 25:
            return "normal"
        else:
            return "overweight"
    else:
        raise ValueError("height must be positive")
""",
    },
    {
        "id": "pilot-03",
        "purpose": "lora_pilot",
        "split": "train",
        "code": """
def first_even(numbers):
    if numbers:
        for number in numbers:
            if number % 2 == 0:
                return number
        return None
    else:
        return None
""",
    },
    {
        "id": "pilot-04",
        "purpose": "lora_pilot",
        "split": "train",
        "code": """
def ticket_price(age, is_member):
    if age >= 0:
        if age < 12:
            return 5
        else:
            if is_member:
                return 8
            else:
                return 12
    else:
        raise ValueError("age must not be negative")
""",
    },
    {
        "id": "pilot-05",
        "purpose": "lora_pilot",
        "split": "train",
        "code": """
def safe_ratio(numerator, denominator, default):
    if denominator is not None:
        if denominator != 0:
            return numerator / denominator
        else:
            return default
    else:
        return default
""",
    },
    {
        "id": "pilot-06",
        "purpose": "lora_pilot",
        "split": "train",
        "code": """
def format_price(amount, currency):
    if amount is not None:
        if currency == "USD":
            return "$" + format(amount, ".2f")
        elif currency == "EUR":
            return format(amount, ".2f") + " EUR"
        else:
            return format(amount, ".2f") + " " + currency
    else:
        return "n/a"
""",
    },
    {
        "id": "pilot-07",
        "purpose": "lora_pilot",
        "split": "train",
        "code": """
def access_level(user, resource):
    if user is not None:
        if user.get("admin"):
            return "full"
        else:
            if resource in user.get("resources", []):
                return "read"
            else:
                return "none"
    else:
        raise PermissionError("anonymous access is not allowed")
""",
    },
    {
        "id": "pilot-08",
        "purpose": "lora_pilot",
        "split": "train",
        "code": """
def count_vowels(text):
    if text is not None:
        if isinstance(text, str):
            count = 0
            for char in text.lower():
                if char in "aeiou":
                    count += 1
            return count
        else:
            raise TypeError("text must be a string")
    else:
        return 0
""",
    },
    {
        "id": "pilot-09",
        "purpose": "lora_pilot",
        "split": "train",
        "code": """
def interest_rate(balance, years):
    if balance > 0:
        if years >= 5:
            return 0.05
        elif years >= 2:
            return 0.03
        else:
            return 0.01
    else:
        return 0.0
""",
    },
    {
        "id": "pilot-10",
        "purpose": "lora_pilot",
        "split": "train",
        "code": """
def parse_bool(value):
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("yes", "true", "1"):
            return True
        elif lowered in ("no", "false", "0"):
            return False
        else:
            raise ValueError("unrecognized boolean text")
    else:
        return bool(value)
""",
    },
    {
        "id": "pilot-11",
        "purpose": "lora_pilot",
        "split": "train",
        "code": """
def clamp_percentage(value):
    if value is not None:
        if value < 0:
            return 0
        else:
            if value > 100:
                return 100
            else:
                return value
    else:
        raise ValueError("value is required")
""",
    },
    {
        "id": "pilot-12",
        "purpose": "lora_pilot",
        "split": "train",
        "code": """
def shipping_zone(country, weight):
    if country:
        if country == "EG":
            if weight <= 5:
                return "local-small"
            else:
                return "local-large"
        else:
            return "international"
    else:
        raise ValueError("country is required")
""",
    },
    {
        "id": "pilot-13",
        "purpose": "lora_pilot",
        "split": "train",
        "code": """
def password_strength(password):
    if password:
        if len(password) >= 12:
            has_digit = any(ch.isdigit() for ch in password)
            if has_digit:
                return "strong"
            else:
                return "medium"
        else:
            return "weak"
    else:
        return "empty"
""",
    },
    {
        "id": "pilot-14",
        "purpose": "lora_pilot",
        "split": "train",
        "code": """
def middle_value(values):
    if values:
        size = len(values)
        if size % 2 == 1:
            return values[size // 2]
        else:
            upper = values[size // 2]
            lower = values[size // 2 - 1]
            return (upper + lower) / 2
    else:
        raise ValueError("values must not be empty")
""",
    },
    {
        "id": "pilot-15",
        "purpose": "lora_pilot",
        "split": "train",
        "code": """
def allow_request(count, limit, is_admin):
    if not is_admin:
        if limit > 0:
            if count < limit:
                return True
            else:
                return False
        else:
            raise ValueError("limit must be positive")
    else:
        return True
""",
    },
    {
        "id": "pilot-16",
        "purpose": "lora_pilot",
        "split": "train",
        "code": """
def file_extension(filename):
    if "." in filename:
        name, extension = filename.rsplit(".", 1)
        if name and extension:
            return extension.lower()
        else:
            return ""
    else:
        return ""
""",
    },
    {
        "id": "pilot-17",
        "purpose": "lora_pilot",
        "split": "validation",
        "code": """
def temperature_alert(reading, threshold):
    if reading is not None:
        if threshold is not None:
            if reading > threshold:
                return "alert"
            else:
                return "ok"
        else:
            raise ValueError("threshold is required")
    else:
        return "missing"
""",
    },
    {
        "id": "pilot-18",
        "purpose": "lora_pilot",
        "split": "validation",
        "code": """
def order_status(order):
    if order.get("paid"):
        if order.get("shipped"):
            if order.get("delivered"):
                return "delivered"
            else:
                return "in transit"
        else:
            return "processing"
    else:
        return "awaiting payment"
""",
    },
    {
        "id": "pilot-19",
        "purpose": "lora_pilot",
        "split": "validation",
        "code": """
def capped_total(items, cap):
    if cap > 0:
        total = 0
        for item in items:
            if item > 0:
                total += item
        if total > cap:
            return cap
        else:
            return total
    else:
        raise ValueError("cap must be positive")
""",
    },
    {
        "id": "pilot-20",
        "purpose": "lora_pilot",
        "split": "validation",
        "code": """
def status_text(code):
    if isinstance(code, int):
        if 200 <= code < 300:
            return "success"
        elif 400 <= code < 500:
            return "client error"
        elif 500 <= code < 600:
            return "server error"
        else:
            return "other"
    else:
        raise TypeError("code must be an integer")
""",
    },
    {
        "id": "pilot-21",
        "purpose": "lora_pilot",
        "split": "test",
        "code": """
def round_to_multiple(value, step):
    if step != 0:
        if value >= 0:
            return round(value / step) * step
        else:
            return -round(-value / step) * step
    else:
        raise ZeroDivisionError("step must not be zero")
""",
    },
    {
        "id": "pilot-22",
        "purpose": "lora_pilot",
        "split": "test",
        "code": """
def weekday_name(index, names):
    if names is not None:
        if 0 <= index < len(names):
            return names[index]
        else:
            raise IndexError("index out of range")
    else:
        raise ValueError("names are required")
""",
    },
]


def maximal_inputs() -> dict[str, str]:
    """In-scope functions of at most 3,000 characters and 60 lines."""
    lines = [
        "def review_shipment(shipment, carrier_rules, customs_limit):",
        '    """Decide how a shipment should be handled before it is dispatched."""',
        "    if shipment is not None:",
        '        if shipment.get("destination"):',
        '            weight = shipment.get("weight_kg", 0)',
        '            value = shipment.get("declared_value", 0)',
        "            if weight > 0:",
    ]
    lines.append("                if value > customs_limit:")
    lines.append(
        '                    raise ValueError("The declared value exceeds the customs limit '
        'and needs a manual customs declaration before dispatch")'
    )
    thresholds = [1000, 800, 600, 500, 400, 300, 200, 150, 100, 75, 50, 30, 20, 10, 5, 2, 1]
    for index, threshold in enumerate(thresholds):
        keyword = "if" if index == 0 else "elif"
        lines.append(f"                {keyword} weight > {threshold}:")
        lines.append(
            f'                    category = "over-{threshold}-kg"  # band {index + 1} of '
            f"{len(thresholds)}"
        )
    lines += [
        "                else:",
        '                    category = "letter"',
        '                rule = carrier_rules.get(category, carrier_rules.get("default"))',
        "                if rule is None:",
        '                    raise LookupError("No carrier rule matches the shipment category '
        'and no default rule is configured for this carrier")',
        '                return {"category": category, "carrier": rule, "weight": weight}',
        "            else:",
        '                raise ValueError("The shipment weight must be a positive number of '
        'kilograms before it can be dispatched")',
        "        else:",
        '            raise ValueError("The shipment needs a destination address before '
        'it can be dispatched")',
        "    else:",
        '        raise ValueError("A shipment record is required")',
    ]
    realistic = "\n".join(lines) + "\n"
    # Pad the docstring to exactly 3,000 characters without changing the structure.
    pad = 3000 - len(realistic)
    if pad < 0:
        raise ValueError(f"the realistic input is {len(realistic)} characters, over 3,000")
    filler = " Weight bands, customs value and carrier rules are checked in order." * 20
    realistic = realistic.replace('dispatched."""', "dispatched." + filler[:pad] + '"""', 1)
    digits = "1234567890" * 400
    head = "def checksum(value):\n    if value:\n        if value > 0:\n            return "
    tail = "\n        else:\n            return 0\n    else:\n        return 0\n"
    dense = head + digits[: 3000 - len(head) - len(tail)] + tail
    arabic_word = "مرحبا "
    head = 'def greeting(name):\n    if name:\n        if len(name) > 3:\n            return "'
    tail = '"\n        else:\n            return name\n    else:\n        return ""\n'
    arabic = head + (arabic_word * 600)[: 3000 - len(head) - len(tail)] + tail
    return {"realistic_ascii": realistic, "digit_dense": dense, "arabic_text": arabic}


def pilot_functions(purpose: str | None = None) -> list[dict]:
    """Pilot functions with code normalized to start at 'def' and end with one newline."""
    selected = []
    for item in PILOT_FUNCTIONS:
        if purpose is not None and item["purpose"] != purpose:
            continue
        selected.append({**item, "code": item["code"].strip("\n") + "\n"})
    return selected
