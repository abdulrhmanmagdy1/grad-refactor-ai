"""Validation, parsing and text-processing families."""

from __future__ import annotations

from refactor_ai.data.families.base import Check, Param, family, maybe, pick, raises, returns
from refactor_ai.data.families.helpers import make


@family("username-rules", "validation")
def username_rules(r):
    fn = pick(r, ["normalize_username", "clean_username", "validate_handle"])
    name = pick(r, ["name", "username", "handle"])
    low, high = pick(r, [(3, 16), (4, 20), (3, 12)])
    checks = [
        Check(
            f"isinstance({name}, str)",
            f"not isinstance({name}, str)",
            raises("TypeError", "username must be a string"),
        ),
        Check(
            f"{low} <= len(cleaned) <= {high}",
            f"len(cleaned) < {low} or len(cleaned) > {high}",
            raises("ValueError", f"username must have {low} to {high} characters"),
            setup=(f"cleaned = {name}.strip()",),
        ),
        Check(
            "cleaned.isalnum()",
            "not cleaned.isalnum()",
            pick(r, [raises("ValueError", "only letters and digits are allowed"), returns("None")]),
        ),
    ]
    core = ["return cleaned.lower()"]
    if maybe(r, 0.4):
        core = [
            "if cleaned[0].isdigit():",
            "    return '_' + cleaned.lower()",
            "return cleaned.lower()",
        ]
    params = [
        Param(
            name,
            (
                None,
                42,
                "  ab ",
                "Alice_99",
                "Bob2024",
                "9lives",
                "x" * (low - 1),
                "x" * low,
                "x" * high,
                "x" * (high + 1),
            ),
            "str",
        )
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Return the canonical form of a username.",),
        returns="str | None",
    )


@family("password-strength", "validation")
def password_strength(r):
    fn = pick(r, ["password_strength", "rate_password", "strength_label"])
    pw = pick(r, ["password", "secret", "candidate"])
    min_len = pick(r, [8, 10, 12])
    checks = [
        Check(
            f"isinstance({pw}, str)",
            f"not isinstance({pw}, str)",
            raises("TypeError", "password must be a string"),
        ),
        Check(f"len({pw}) >= min_length", f"len({pw}) < min_length", returns("'too short'")),
    ]
    core = [
        "score = 0",
        f"if any(ch.isdigit() for ch in {pw}):",
        "    score = score + 1",
        f"if any(ch.isupper() for ch in {pw}):",
        "    score = score + 1",
        f"if any(not ch.isalnum() for ch in {pw}):",
        "    score = score + 1",
        "if score == 3:",
        "    return 'strong'",
        "elif score >= 1:",
        "    return 'medium'",
        "else:",
        "    return 'weak'",
    ]
    params = [
        Param(
            pw,
            (None, "abc", "a" * min_len, "abcdefgh1" + "x" * min_len, "Abcdefg1!" + "y" * min_len),
            "str",
        ),
        Param("min_length", (min_len,), "int", default=min_len),
    ]
    return make(
        r, fn, params, checks, core, docs=("Classify the strength of a password.",), returns="str"
    )


@family("email-split", "parsing")
def email_split(r):
    fn = pick(r, ["split_email", "email_parts", "parse_address"])
    addr = pick(r, ["address", "email"])
    checks = [
        Check(
            f"{addr}.count('@') == 1",
            f"{addr}.count('@') != 1",
            raises("ValueError", "address must contain exactly one @"),
        ),
        Check(
            "local and domain",
            "not local or not domain",
            raises("ValueError", "missing local part or domain"),
            setup=(f"local, domain = {addr}.split('@')",),
        ),
        Check("'.' in domain", "'.' not in domain", returns("None")),
    ]
    core = ["return (local.lower(), domain.lower())"]
    if maybe(r, 0.4):
        core = [
            "if domain.endswith('.'):",
            "    return None",
            "return (local.lower(), domain.lower())",
        ]
    params = [
        Param(
            addr,
            ("plain", "a@@b.com", "@b.com", "ann@", "ann@host", "Ann@Example.ORG", "x@y."),
            "str",
        )
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Split an e-mail address into local part and domain.",),
        returns="tuple | None",
    )


@family("phone-normalize", "parsing")
def phone_normalize(r):
    fn = pick(r, ["normalize_phone", "format_phone", "canonical_phone"])
    number = pick(r, ["number", "phone", "raw_number"])
    country = pick(r, ["+20", "+1", "+44"])
    checks = [
        Check("digits", "not digits", returns("None")),
        Check(
            "len(digits) in (10, 11)",
            "len(digits) not in (10, 11)",
            raises("ValueError", "phone number has the wrong length"),
        ),
    ]
    core = ["if digits.startswith('0'):", "    digits = digits[1:]", "return country_code + digits"]
    params = [
        Param(number, ("", "abc", "1234", "01012345678", "(010) 123-4567", "2125550123"), "str"),
        Param("country_code", (country,), "str", default=country),
    ]
    variant = make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Return the phone number in international form.",),
        returns="str | None",
    )
    variant.prelude = [f"digits = ''.join(ch for ch in {number} if ch.isdigit())"]
    return variant


@family("age-field", "parsing")
def age_field(r):
    fn = pick(r, ["parse_age", "age_from_form", "read_age"])
    text = pick(r, ["text", "raw", "value"])
    oldest = pick(r, [130, 120, 125])
    checks = [
        Check(f"{text} is not None", f"{text} is None", returns("None")),
        Check(
            "cleaned.isdigit()",
            "not cleaned.isdigit()",
            raises("ValueError", "age must be a whole number"),
            setup=(f"cleaned = {text}.strip()",),
        ),
    ]
    core = [
        "age = int(cleaned)",
        f"if age > {oldest}:",
        "    raise ValueError('age is not realistic')",
        "return age",
    ]
    params = [
        Param(text, (None, "", " 42 ", "abc", "-3", str(oldest), str(oldest + 1)), "str | None")
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Parse the age entered in a form.",),
        returns="int | None",
    )


@family("coupon-code", "validation")
def coupon_code(r):
    fn = pick(r, ["coupon_discount", "discount_for_code", "redeem_coupon"])
    code = pick(r, ["code", "coupon"])
    today = pick(r, ["today", "day_number"])
    expires = pick(r, ["expires", "expiry_day"])
    values = pick(r, [(10, 15, 25), (5, 10, 20), (8, 12, 30)])
    checks = [
        Check(
            f"len({code}) == 8",
            f"len({code}) != 8",
            raises("ValueError", "coupon codes have 8 characters"),
        ),
        Check(
            f"{code}[:3] in ('SAV', 'NEW', 'VIP')",
            f"{code}[:3] not in ('SAV', 'NEW', 'VIP')",
            raises("ValueError", "unknown coupon prefix"),
        ),
        Check(f"{today} <= {expires}", f"{today} > {expires}", returns("0")),
    ]
    core = [
        f"prefix = {code}[:3]",
        "if prefix == 'VIP':",
        f"    return {values[2]}",
        "elif prefix == 'NEW':",
        f"    return {values[1]}",
        "else:",
        f"    return {values[0]}",
    ]
    params = [
        Param(code, ("SAV", "SAVE2024", "NEW12345", "VIP00001", "ABC12345"), "str"),
        Param(today, (10, 30, 31), "int"),
        Param(expires, (30,), "int"),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Percentage discount granted by a coupon.",),
        returns="int",
    )


@family("card-checksum", "validation")
def card_checksum(r):
    fn = pick(r, ["card_number_valid", "passes_luhn", "check_card_number"])
    number = pick(r, ["number", "card_number", "digits"])
    low, high = pick(r, [(12, 19), (13, 19), (12, 16)])
    checks = [
        Check(
            f"isinstance({number}, str)",
            f"not isinstance({number}, str)",
            raises("TypeError", "card number must be a string"),
        ),
        Check(f"{number}.isdigit()", f"not {number}.isdigit()", returns("False")),
        Check(
            f"{low} <= len({number}) <= {high}",
            f"len({number}) < {low} or len({number}) > {high}",
            returns("False"),
        ),
    ]
    core = [
        "total = 0",
        f"for index, ch in enumerate(reversed({number})):",
        "    digit = int(ch)",
        "    if index % 2 == 1:",
        "        digit = digit * 2",
        "        if digit > 9:",
        "            digit = digit - 9",
        "    total = total + digit",
        "return total % 10 == 0",
    ]
    params = [
        Param(
            number,
            (
                1234,
                "12ab",
                "4111",
                "4111111111111111",
                "4111111111111112",
                "5" * (high + 1),
                "0" * (low - 1),
                "0" * low,
                "0" * high,
                "0" * (high + 1),
            ),
            "str",
        ),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Check a card number with the Luhn checksum.",),
        returns="bool",
    )


@family("postcode-region", "parsing")
def postcode_region(r):
    fn = pick(r, ["postcode_region", "region_for_postcode", "sorting_region"])
    code = pick(r, ["code", "postcode", "zip_code"])
    a, b = pick(r, [(3, 6), (2, 5), (4, 7)])
    checks = [
        Check(
            f"isinstance({code}, str)",
            f"not isinstance({code}, str)",
            raises("TypeError", "postcode must be a string"),
        ),
        Check(
            f"len({code}) == 5 and {code}.isdigit()",
            f"len({code}) != 5 or not {code}.isdigit()",
            pick(r, [raises("ValueError", "postcode must have five digits"), returns("None")]),
        ),
    ]
    core = [
        f"first = int({code}[0])",
        f"if first <= {a}:",
        "    return 'north'",
        f"elif first <= {b}:",
        "    return 'central'",
        "else:",
        "    return 'south'",
    ]
    params = [
        Param(code, (12345.0, "1234", "12a45", "10115", f"{a}0000", f"{b}0000", "99999"), "str")
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Sorting region for a five-digit postcode.",),
        returns="str | None",
    )


@family("version-parse", "parsing")
def version_parse(r):
    fn = pick(r, ["parse_version", "version_tuple", "split_version"])
    text = pick(r, ["text", "version"])
    checks = [
        Check(text, f"not {text}", returns("None")),
        Check(
            "len(parts) == 3",
            "len(parts) != 3",
            raises("ValueError", "expected MAJOR.MINOR.PATCH"),
            setup=(f"parts = {text}.split('.')",),
        ),
        Check(
            "all(part.isdigit() for part in parts)",
            "not all(part.isdigit() for part in parts)",
            raises("ValueError", "version parts must be numbers"),
        ),
    ]
    core = ["return (int(parts[0]), int(parts[1]), int(parts[2]))"]
    if maybe(r, 0.4):
        core = [
            "numbers = tuple(int(part) for part in parts)",
            "if numbers == (0, 0, 0):",
            "    raise ValueError('version 0.0.0 is not allowed')",
            "return numbers",
        ]
    params = [Param(text, ("", "1.2", "1.2.x", "1.10.3", "0.9.1", "0.0.0"), "str")]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Parse a semantic version string.",),
        returns="tuple | None",
    )


@family("key-value-line", "parsing")
def key_value_line(r):
    fn = pick(r, ["parse_setting", "parse_config_line", "split_assignment"])
    line = pick(r, ["line", "raw_line"])
    sep = pick(r, ["=", ":"])
    comment = pick(r, ["#", ";"])
    checks = [
        Check(
            f"stripped and not stripped.startswith({comment!r})",
            f"not stripped or stripped.startswith({comment!r})",
            returns("None"),
        ),
        Check(
            f"{sep!r} in stripped",
            f"{sep!r} not in stripped",
            raises("ValueError", f"expected key{sep}value"),
        ),
        Check(
            "key",
            "not key",
            raises("ValueError", "empty key"),
            setup=(f"key, value = stripped.split({sep!r}, 1)", "key = key.strip()"),
        ),
    ]
    core = ["return (key, value.strip())"]
    params = [
        Param(
            line,
            ("", f"{comment} note", "plain", f" {sep}x", f"name {sep} demo", f"port{sep}8080 "),
            "str",
        ),
    ]
    variant = make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Split one configuration line into key and value.",),
        returns="tuple | None",
    )
    variant.prelude = [f"stripped = {line}.strip()"]
    return variant


@family("duration-parse", "parsing")
def duration_parse(r):
    fn = pick(r, ["duration_seconds", "parse_duration", "to_seconds"])
    text = pick(r, ["text", "duration"])
    checks = [
        Check(
            f"len({text}) >= 2", f"len({text}) < 2", raises("ValueError", "duration is too short")
        ),
        Check(
            "amount.isdigit()",
            "not amount.isdigit()",
            raises("ValueError", "amount must be a whole number"),
            setup=(f"unit = {text}[-1]", f"amount = {text}[:-1]"),
        ),
    ]
    core = [
        "if unit == 's':",
        "    return int(amount)",
        "elif unit == 'm':",
        "    return int(amount) * 60",
        "elif unit == 'h':",
        "    return int(amount) * 3600",
        "else:",
        "    raise ValueError('unknown unit')",
    ]
    params = [Param(text, ("5", "xs", "45s", "10m", "2h", "3d"), "str")]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Convert a duration such as '10m' to seconds.",),
        returns="int",
    )


@family("flag-parse", "parsing")
def flag_parse(r):
    fn = pick(r, ["parse_flag", "to_bool", "parse_switch"])
    value = pick(r, ["value", "raw"])
    checks = [
        Check(f"{value} is not None", f"{value} is None", returns("default")),
        Check(
            f"isinstance({value}, str)",
            f"not isinstance({value}, str)",
            raises("TypeError", "flag must be a string"),
        ),
    ]
    core = [
        f"lowered = {value}.strip().lower()",
        "if lowered in ('1', 'true', 'yes', 'on'):",
        "    return True",
        "elif lowered in ('0', 'false', 'no', 'off'):",
        "    return False",
        "else:",
        "    raise ValueError('not a boolean: ' + lowered)",
    ]
    params = [
        Param(value, (None, 1, " Yes", "off", "maybe"), "str | None"),
        Param("default", (False, True), "bool", default=False),
    ]
    return make(
        r, fn, params, checks, core, docs=("Interpret a configuration switch.",), returns="bool"
    )


@family("text-truncate", "text")
def text_truncate(r):
    fn = pick(r, ["truncate", "shorten", "clip_text"])
    text = pick(r, ["text", "message"])
    limit = pick(r, ["limit", "max_chars"])
    checks = [
        Check(f"{limit} > 0", f"{limit} <= 0", raises("ValueError", "limit must be positive")),
        Check(
            f"len(suffix) < {limit}",
            f"len(suffix) >= {limit}",
            raises("ValueError", "suffix is longer than the limit"),
        ),
    ]
    core = [
        f"if len({text}) <= {limit}:",
        f"    return {text}",
        f"return {text}[:{limit} - len(suffix)].rstrip() + suffix",
    ]
    params = [
        Param(text, ("short", "abcdefghij", "a longer sentence here"), "str"),
        Param(limit, (0, 3, 4, 10), "int"),
        Param("suffix", ("...",), "str", default="..."),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Shorten text to at most limit characters.",),
        returns="str",
    )


@family("title-slug", "text")
def title_slug(r):
    fn = pick(r, ["make_slug", "slugify_title", "url_slug"])
    title = pick(r, ["title", "headline"])
    max_len = pick(r, [40, 30, 20])
    checks = [
        Check(
            f"isinstance({title}, str)",
            f"not isinstance({title}, str)",
            raises("TypeError", "title must be a string"),
        ),
        Check(f"{title}.strip()", f"not {title}.strip()", raises("ValueError", "title is empty")),
    ]
    core = [
        f"words = [word for word in {title}.lower().split() if word.isalnum()]",
        "slug = '-'.join(words)",
        "if len(slug) > max_length:",
        "    slug = slug[:max_length].rstrip('-')",
        "return slug",
    ]
    params = [
        Param(title, (None, "   ", "Hello World", "Guard clauses in Python " * 3), "str"),
        Param("max_length", (max_len,), "int", default=max_len),
    ]
    return make(r, fn, params, checks, core, docs=("Turn a title into a URL slug.",), returns="str")


@family("hex-color", "parsing")
def hex_color(r):
    fn = pick(r, ["parse_hex_color", "hex_to_rgb", "color_from_hex"])
    text = pick(r, ["text", "color"])
    checks = [
        Check(f"{text}.startswith('#')", f"not {text}.startswith('#')", returns("None")),
        Check(
            "len(digits) in (3, 6)",
            "len(digits) not in (3, 6)",
            raises("ValueError", "expected 3 or 6 hex digits"),
            setup=(f"digits = {text}[1:]",),
        ),
        Check(
            "all(ch in '0123456789abcdefABCDEF' for ch in digits)",
            "not all(ch in '0123456789abcdefABCDEF' for ch in digits)",
            raises("ValueError", "invalid hex digit"),
        ),
    ]
    core = [
        "if len(digits) == 3:",
        "    digits = ''.join(ch * 2 for ch in digits)",
        "return (int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16))",
    ]
    params = [Param(text, ("red", "#12", "#ggg", "#fa0", "#00FF7f"), "str")]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Parse '#rgb' or '#rrggbb' into a tuple.",),
        returns="tuple | None",
    )


@family("csv-row", "parsing")
def csv_row(r):
    fn = pick(r, ["row_to_record", "parse_row", "row_as_dict"])
    row = pick(r, ["row", "fields"])
    columns = pick(r, ["columns", "header"])
    checks = [
        Check(
            f"len({columns}) > 0",
            f"len({columns}) == 0",
            raises("ValueError", "no columns defined"),
        ),
        Check(
            f"len({row}) == len({columns})",
            f"len({row}) != len({columns})",
            raises("ValueError", "row has the wrong number of fields"),
        ),
    ]
    core = [
        "record = {}",
        f"for name, value in zip({columns}, {row}):",
        "    if value.strip() == '':",
        "        record[name] = None",
        "    else:",
        "        record[name] = value.strip()",
        "return record",
    ]
    params = [
        Param(row, (["a"], ["1", " x ", ""]), "list"),
        Param(columns, ((), ("id", "name", "note")), "tuple"),
    ]
    return make(
        r, fn, params, checks, core, docs=("Map one CSV row to a dictionary.",), returns="dict"
    )
