"""Education, human-resources and everyday-measurement families."""

from __future__ import annotations

from refactor_ai.data.families.base import Check, Param, family, maybe, pick, raises, returns
from refactor_ai.data.families.helpers import make, shuffled


@family("letter-grade", "grading")
def letter_grade(r):
    fn = pick(r, ["letter_grade", "grade_for_score", "to_letter"])
    score = pick(r, ["score", "points", "marks"])
    cuts = pick(r, [(90, 80, 70, 60), (85, 75, 65, 50), (93, 85, 77, 70)])
    checks = [
        Check(
            "max_score > 0", "max_score <= 0", raises("ValueError", "max_score must be positive")
        ),
        Check(
            f"0 <= {score} <= max_score",
            f"{score} < 0 or {score} > max_score",
            pick(r, [raises("ValueError", "score out of range"), returns("None")]),
        ),
    ]
    core = [
        f"percent = {score} * 100 / max_score",
        f"if percent >= {cuts[0]}:",
        "    return 'A'",
        f"elif percent >= {cuts[1]}:",
        "    return 'B'",
        f"elif percent >= {cuts[2]}:",
        "    return 'C'",
        f"elif percent >= {cuts[3]}:",
        "    return 'D'",
        "else:",
        "    return 'F'",
    ]
    params = [
        Param(score, (-1, 0, cuts[3], cuts[2], cuts[1], cuts[0], 100, 101), "float"),
        Param("max_score", (0, 100), "float", default=100),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Convert a score to a letter grade.",),
        returns="str | None",
    )


@family("course-enrollment", "education")
def course_enrollment(r):
    fn = pick(r, ["enroll_student", "register_course", "try_enroll"])
    credits = pick(r, ["current_credits", "credits"])
    completed = pick(r, ["completed", "passed_courses"])
    prereq = pick(r, ["prerequisite", "required_course"])
    seats = pick(r, ["seats_left", "open_seats"])
    limit = pick(r, [21, 18, 24])
    course_credits = pick(r, [3, 4])
    checks = [
        Check(
            f"{prereq} is None or {prereq} in {completed}",
            f"{prereq} is not None and {prereq} not in {completed}",
            raises("PermissionError", "missing prerequisite"),
        ),
        Check(
            f"{credits} + {course_credits} <= {limit}",
            f"{credits} + {course_credits} > {limit}",
            raises("ValueError", "credit limit exceeded"),
        ),
    ]
    checks = shuffled(r, checks)
    core = [f"if {seats} > 0:", "    return 'enrolled'", "return 'waitlisted'"]
    if maybe(r, 0.4):
        core = [
            f"if {seats} <= 0:",
            "    return 'waitlisted'",
            f"if {seats} <= 3:",
            "    return 'enrolled (last seats)'",
            "return 'enrolled'",
        ]
    params = [
        Param(credits, (12, limit - course_credits, limit), "int"),
        Param(completed, (("CS101",), ()), "tuple"),
        Param(prereq, (None, "CS101"), "str | None"),
        Param(seats, (0, 2, 3, 10), "int"),
    ]
    return make(
        r, fn, params, checks, core, docs=("Enrollment outcome for one course.",), returns="str"
    )


@family("exam-eligibility", "education")
def exam_eligibility(r):
    fn = pick(r, ["exam_eligibility", "can_sit_exam", "eligibility_status"])
    attendance = pick(r, ["attendance", "attendance_percent"])
    fees = pick(r, ["fees_paid", "tuition_paid"])
    suspended = pick(r, ["suspended", "is_suspended"])
    full, partial = pick(r, [(75, 60), (80, 65), (70, 50)])
    checks = [
        Check(f"not {suspended}", suspended, raises("PermissionError", "student is suspended")),
        Check(fees, f"not {fees}", returns("'fees outstanding'")),
        Check(
            f"0 <= {attendance} <= 100",
            f"{attendance} < 0 or {attendance} > 100",
            raises("ValueError", "attendance must be a percentage"),
        ),
    ]
    checks = shuffled(r, checks)
    core = [
        f"if {attendance} >= {full}:",
        "    return 'eligible'",
        f"elif {attendance} >= {partial}:",
        "    return 'needs approval'",
        "else:",
        "    return 'not eligible'",
    ]
    params = [
        Param(attendance, (-1, 0, partial - 1, partial, full, 100, 101), "float"),
        Param(fees, (True, False), "bool"),
        Param(suspended, (False, True), "bool"),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Whether a student may sit the final exam.",),
        returns="str",
    )


@family("scholarship", "education")
def scholarship(r):
    fn = pick(r, ["scholarship_amount", "award_amount", "grant_for_student"])
    gpa = pick(r, ["gpa", "grade_point_average"])
    income = pick(r, ["family_income", "household_income"])
    region = pick(r, ["region", "home_area"])
    top, good = pick(r, [(3.7, 3.3), (3.8, 3.5), (3.6, 3.0)])
    amounts = pick(r, [(5000, 3000), (4000, 2500), (6000, 3500)])
    need_line = pick(r, [30000, 25000, 40000])
    checks = [
        Check(
            f"0.0 <= {gpa} <= 4.0",
            f"{gpa} < 0.0 or {gpa} > 4.0",
            raises("ValueError", "gpa must be between 0 and 4"),
        ),
        Check(f"{income} >= 0", f"{income} < 0", raises("ValueError", "income cannot be negative")),
    ]
    core = [
        f"if {gpa} >= {top}:",
        f"    amount = {amounts[0]}",
        f"elif {gpa} >= {good}:",
        f"    amount = {amounts[1]}",
        "else:",
        "    amount = 0",
        f"if {income} < {need_line}:",
        "    amount = amount + 1500",
        f"if {region} == 'rural':",
        "    amount = amount + 500",
        "return amount",
    ]
    params = [
        Param(gpa, (-0.1, 0.0, 2.5, good, top, 4.0, 4.1), "float"),
        Param(income, (-1, 0, 10000, need_line), "int"),
        Param(region, ("urban", "rural"), "str"),
    ]
    return make(
        r, fn, params, checks, core, docs=("Scholarship amount for one applicant.",), returns="int"
    )


@family("late-penalty", "grading")
def late_penalty(r):
    fn = pick(r, ["penalized_score", "apply_late_penalty", "late_adjusted_score"])
    score = pick(r, ["score", "raw_score"])
    days = pick(r, ["days_late", "late_days"])
    per_day = pick(r, [10, 5, 15])
    max_days = pick(r, [5, 7, 3])
    checks = [
        Check(f"{score} >= 0", f"{score} < 0", raises("ValueError", "score cannot be negative")),
        Check(f"{days} >= 0", f"{days} < 0", raises("ValueError", "days late cannot be negative")),
        Check(f"{days} <= {max_days}", f"{days} > {max_days}", returns("0")),
    ]
    checks = [*shuffled(r, checks[:2]), checks[2]]
    core = [
        f"if {days} == 0:",
        f"    return {score}",
        f"return max({score} - {days} * {per_day}, 0)",
    ]
    params = [
        Param(score, (-1, 0, 35, 88), "int"),
        Param(days, (-1, 0, 2, max_days, max_days + 1), "int"),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Score after the late-submission penalty.",),
        returns="int",
    )


@family("quiz-score", "grading")
def quiz_score(r):
    fn = pick(r, ["quiz_score", "percent_correct", "mark_quiz"])
    answers = pick(r, ["answers", "responses"])
    key = pick(r, ["key", "answer_key"])
    checks = [
        Check(
            f"len({key}) > 0", f"len({key}) == 0", raises("ValueError", "the answer key is empty")
        ),
        Check(
            f"len({answers}) == len({key})",
            f"len({answers}) != len({key})",
            pick(r, [raises("ValueError", "answer count does not match the key"), returns("None")]),
        ),
    ]
    core = [
        "correct = 0",
        f"for given, expected in zip({answers}, {key}):",
        "    if given == expected:",
        "        correct = correct + 1",
        f"return round(correct * 100 / len({key}), 1)",
    ]
    params = [
        Param(answers, (["a"], ["a", "c", "b"], ["b", "c", "b"]), "list"),
        Param(key, ((), ("a", "c", "d")), "tuple"),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Percentage of correct answers.",),
        returns="float | None",
    )


@family("bmi-category", "health")
def bmi_category(r):
    fn = pick(r, ["bmi_category", "body_mass_class", "classify_bmi"])
    weight = pick(r, ["weight_kg", "mass"])
    height = pick(r, ["height_m", "height"])
    checks = [
        Check(f"{weight} > 0", f"{weight} <= 0", raises("ValueError", "weight must be positive")),
        Check(f"{height} > 0", f"{height} <= 0", raises("ValueError", "height must be positive")),
    ]
    checks = shuffled(r, checks)
    core = [
        f"bmi = {weight} / ({height} * {height})",
        "if bmi < 18.5:",
        "    return 'underweight'",
        "elif bmi < 25:",
        "    return 'normal'",
        "elif bmi < 30:",
        "    return 'overweight'",
        "else:",
        "    return 'obese'",
    ]
    params = [
        Param(weight, (0, 50, 70, 74, 85, 100, 110, 120), "float"),
        Param(height, (0, 1.8, 2.0), "float"),
    ]
    return make(r, fn, params, checks, core, docs=("Body-mass-index category.",), returns="str")


@family("blood-pressure", "health")
def blood_pressure(r):
    fn = pick(r, ["pressure_stage", "blood_pressure_stage", "bp_category"])
    sys_ = pick(r, ["systolic", "upper"])
    dia = pick(r, ["diastolic", "lower"])
    checks = [
        Check(
            f"{sys_} > 0 and {dia} > 0",
            f"{sys_} <= 0 or {dia} <= 0",
            raises("ValueError", "readings must be positive"),
        ),
        Check(
            f"{sys_} > {dia}",
            f"{sys_} <= {dia}",
            raises("ValueError", "systolic must exceed diastolic"),
        ),
    ]
    core = [
        f"if {sys_} >= 180 or {dia} >= 120:",
        "    return 'crisis'",
        f"if {sys_} >= 140 or {dia} >= 90:",
        "    return 'stage 2'",
        f"if {sys_} >= 130 or {dia} >= 80:",
        "    return 'stage 1'",
        f"if {sys_} >= 120:",
        "    return 'elevated'",
        "return 'normal'",
    ]
    params = [
        Param(
            sys_, (0, 70, 80, 85, 115, 119, 120, 125, 129, 130, 135, 139, 140, 150, 179, 180), "int"
        ),
        Param(dia, (0, 75, 79, 80, 85, 89, 90, 95, 119, 120, 125), "int"),
    ]
    return make(
        r, fn, params, checks, core, docs=("Blood-pressure category for a reading.",), returns="str"
    )


@family("shift-pay", "payroll")
def shift_pay(r):
    fn = pick(r, ["shift_pay", "wage_for_shift", "pay_for_hours"])
    hours = pick(r, ["hours", "hours_worked"])
    rate = pick(r, ["hourly_rate", "rate"])
    night = pick(r, ["night_shift", "is_night"])
    regular = pick(r, [8, 7, 9])
    max_hours = pick(r, [16, 14, 12])
    allowance = pick(r, [20, 15, 25])
    checks = [
        Check(f"{hours} >= 0", f"{hours} < 0", raises("ValueError", "hours cannot be negative")),
        Check(
            f"{hours} <= {max_hours}",
            f"{hours} > {max_hours}",
            raises("ValueError", "shift is too long"),
        ),
        Check(f"{rate} > 0", f"{rate} <= 0", raises("ValueError", "hourly rate must be positive")),
    ]
    core = [
        f"normal = min({hours}, {regular})",
        f"overtime = {hours} - normal",
        f"pay = normal * {rate} + overtime * {rate} * 1.5",
        f"if {night}:",
        f"    pay = pay + {allowance}",
        "return round(pay, 2)",
    ]
    params = [
        Param(hours, (-1, 0, regular, regular + 2, max_hours, max_hours + 1), "float"),
        Param(rate, (0, 12.5), "float"),
        Param(night, (False, True), "bool", default=False),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Pay for one shift including overtime.",),
        returns="float",
    )


@family("leave-request", "hr")
def leave_request(r):
    fn = pick(r, ["review_leave", "leave_decision", "check_leave_request"])
    days = pick(r, ["days", "days_requested"])
    balance = pick(r, ["balance", "days_available"])
    notice = pick(r, ["notice_days", "days_notice"])
    long_notice, short_notice = pick(r, [(14, 3), (10, 2), (21, 5)])
    checks = [
        Check(f"{days} > 0", f"{days} <= 0", raises("ValueError", "days must be positive")),
        Check(
            f"{days} <= {balance}",
            f"{days} > {balance}",
            returns("'rejected: insufficient balance'"),
        ),
    ]
    core = [
        f"if {notice} >= {long_notice}:",
        "    return 'approved'",
        f"elif {notice} >= {short_notice}:",
        "    return 'manager review'",
        "else:",
        "    return 'rejected: short notice'",
    ]
    params = [
        Param(days, (0, 2, 5, 12), "int"),
        Param(balance, (5, 20), "int"),
        Param(notice, (1, short_notice, long_notice), "int"),
    ]
    return make(r, fn, params, checks, core, docs=("Decide a leave request.",), returns="str")


@family("garden-watering", "household")
def garden_watering(r):
    fn = pick(r, ["water_liters", "irrigation_amount", "watering_need"])
    area = pick(r, ["area_m2", "bed_area"])
    soil = pick(r, ["soil", "soil_type"])
    rain = pick(r, ["rain_mm", "rainfall"])
    per_m2 = pick(r, [(6, 4, 3), (7, 5, 3), (5, 4, 2)])
    skip = pick(r, [10, 8, 12])
    checks = [
        Check(f"{area} > 0", f"{area} <= 0", raises("ValueError", "area must be positive")),
        Check(
            f"{soil} in ('sand', 'loam', 'clay')",
            f"{soil} not in ('sand', 'loam', 'clay')",
            pick(r, [raises("ValueError", "unknown soil type"), returns("None")]),
        ),
    ]
    core = [
        f"if {rain} >= {skip}:",
        "    return 0.0",
        f"if {soil} == 'sand':",
        f"    need = {per_m2[0]}",
        f"elif {soil} == 'loam':",
        f"    need = {per_m2[1]}",
        "else:",
        f"    need = {per_m2[2]}",
        f"liters = {area} * (need - {rain} * 0.5)",
        "return round(max(liters, 0.0), 1)",
    ]
    params = [
        Param(area, (0, 2.5, 12), "float"),
        Param(soil, ("sand", "loam", "clay", "rock"), "str"),
        Param(rain, (0, 4, skip), "float"),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Litres of water a garden bed needs today.",),
        returns="float | None",
    )


@family("recipe-scaling", "household")
def recipe_scaling(r):
    fn = pick(r, ["scale_quantity", "scaled_amount", "adjust_ingredient"])
    qty = pick(r, ["quantity", "amount"])
    servings = pick(r, ["servings", "portions"])
    base = pick(r, [4, 2, 6])
    checks = [
        Check(
            "base_servings > 0",
            "base_servings <= 0",
            raises("ValueError", "base servings must be positive"),
        ),
        Check(
            f"{servings} > 0", f"{servings} <= 0", raises("ValueError", "servings must be positive")
        ),
        Check(f"{qty} >= 0", f"{qty} < 0", raises("ValueError", "quantity cannot be negative")),
    ]
    checks = [checks[0], *shuffled(r, checks[1:])]
    core = [
        f"scaled = {qty} * {servings} / base_servings",
        "if unit == 'pcs':",
        "    return max(1, round(scaled))",
        "return round(scaled, 1)",
    ]
    params = [
        Param(qty, (-1, 0, 250, 3), "float"),
        Param(servings, (0, 1, 8), "int"),
        Param("base_servings", (0, base), "int", default=base),
        Param("unit", ("g", "pcs"), "str", default="g"),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Scale an ingredient for a different number of servings.",),
    )


@family("voter-check", "civic")
def voter_check(r):
    fn = pick(r, ["voting_status", "can_vote", "ballot_eligibility"])
    age = pick(r, ["age", "voter_age"])
    citizen = pick(r, ["citizen", "is_citizen"])
    registered = pick(r, ["registered", "is_registered"])
    district = pick(r, ["district", "precinct"])
    min_age = pick(r, [18, 16, 21])
    checks = [
        Check(citizen, f"not {citizen}", returns("'not eligible'")),
        Check(f"{age} >= {min_age}", f"{age} < {min_age}", returns("'too young'")),
    ]
    checks = shuffled(r, checks)
    core = [
        f"if not {registered}:",
        "    return 'register first'",
        f"return 'vote in ' + {district}",
    ]
    if maybe(r, 0.5):
        core = [
            f"if {registered}:",
            f"    return 'vote in ' + {district}",
            "else:",
            "    return 'register first'",
        ]
    params = [
        Param(age, (min_age - 1, min_age, 40), "int"),
        Param(citizen, (True, False), "bool"),
        Param(registered, (True, False), "bool"),
        Param(district, ("north",), "str"),
    ]
    return make(r, fn, params, checks, core, docs=("Voting status for a resident.",), returns="str")


@family("license-class", "civic")
def license_class(r):
    fn = pick(r, ["license_class", "required_license", "driving_permit_class"])
    age = pick(r, ["age", "driver_age"])
    weight = pick(r, ["vehicle_weight_kg", "gross_weight"])
    passengers = pick(r, ["passengers", "seats"])
    heavy = pick(r, [3500, 7500])
    checks = [
        Check(f"{age} >= 16", f"{age} < 16", returns("None")),
        Check(
            f"{weight} > 0",
            f"{weight} <= 0",
            raises("ValueError", "vehicle weight must be positive"),
        ),
    ]
    core = [
        f"if {passengers} > 8:",
        f"    return 'D' if {age} >= 24 else None",
        f"if {weight} > {heavy}:",
        f"    return 'C' if {age} >= 21 else None",
        f"return 'B' if {age} >= 18 else 'AM'",
    ]
    params = [
        Param(age, (15, 16, 17, 18, 20, 21, 23, 24), "int"),
        Param(weight, (0, 1200, heavy, heavy + 1), "int"),
        Param(passengers, (0, 8, 9), "int", default=0),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Licence class needed to drive a vehicle.",),
        returns="str | None",
    )
