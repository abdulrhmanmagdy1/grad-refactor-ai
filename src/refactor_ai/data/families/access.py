"""Access-control and security families."""

from __future__ import annotations

from refactor_ai.data.codegen import literal as lit
from refactor_ai.data.families.base import Check, Param, family, maybe, pick, raises, returns
from refactor_ai.data.families.helpers import make, shuffled


@family("resource-permission", "access_control")
def resource_permission(r):
    fn = pick(r, ["can_access", "is_allowed", "check_permission"])
    role = pick(r, ["role", "user_role"])
    action = pick(r, ["action", "operation"])
    owner = pick(r, ["is_owner", "owns_resource"])
    roles = ("admin", "editor", "viewer")
    checks = [
        Check(f"{role} in {lit(roles)}", f"{role} not in {lit(roles)}", returns("False")),
        Check(
            f"{action} in ('read', 'write', 'delete')",
            f"{action} not in ('read', 'write', 'delete')",
            raises("ValueError", expr=f"f'unknown action {{{action}}}'"),
        ),
    ]
    checks = shuffled(r, checks)
    core = [
        f"if {role} == 'admin':",
        "    return True",
        f"if {action} == 'read':",
        "    return True",
        f"if {action} == 'write':",
        f"    return {role} == 'editor' or {owner}",
        f"return {owner} and {role} == 'editor'",
    ]
    params = [
        Param(role, (*roles, "guest"), "str"),
        Param(action, ("read", "write", "delete", "share"), "str"),
        Param(owner, (False, True), "bool", default=False),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Whether a user may perform an action on a resource.",),
        returns="bool",
    )


@family("rate-limit", "access_control")
def rate_limit(r):
    fn = pick(r, ["remaining_requests", "quota_left", "requests_remaining"])
    used = pick(r, ["used", "requests_used"])
    plan = pick(r, ["plan", "tier"])
    window = pick(r, ["window_open", "in_window"])
    limits = pick(r, [(100, 1000, 10000), (60, 600, 6000), (50, 500, 5000)])
    checks = [
        Check(window, f"not {window}", returns("0")),
        Check(
            f"{plan} in ('free', 'pro', 'enterprise')",
            f"{plan} not in ('free', 'pro', 'enterprise')",
            raises("ValueError", expr=f"f'unknown plan {{{plan}}}'"),
        ),
        Check(f"{used} >= 0", f"{used} < 0", raises("ValueError", "usage cannot be negative")),
    ]
    core = [
        f"if {plan} == 'enterprise':",
        f"    limit = {limits[2]}",
        f"elif {plan} == 'pro':",
        f"    limit = {limits[1]}",
        "else:",
        f"    limit = {limits[0]}",
        f"if {used} >= limit:",
        "    raise RuntimeError('rate limit exceeded')",
        f"return limit - {used}",
    ]
    params = [
        Param(used, (-1, 0, limits[0] - 1, limits[0], limits[1], limits[2] - 1, limits[2]), "int"),
        Param(plan, ("free", "pro", "enterprise", "trial"), "str"),
        Param(window, (True, False), "bool", default=True),
    ]
    return make(
        r, fn, params, checks, core, docs=("Requests left in the current window.",), returns="int"
    )


@family("login-attempt", "access_control")
def login_attempt(r):
    fn = pick(r, ["login_result", "attempt_login", "authenticate_attempt"])
    locked = pick(r, ["locked", "account_locked"])
    failures = pick(r, ["failed_attempts", "failures"])
    ok = pick(r, ["password_ok", "credentials_valid"])
    max_attempts = pick(r, [3, 5])
    checks = [
        Check(f"not {locked}", locked, raises("PermissionError", "account is locked")),
        Check(f"{failures} < max_attempts", f"{failures} >= max_attempts", returns("'locked'")),
    ]
    core = [
        f"if {ok}:",
        "    return 'success'",
        f"elif {failures} + 1 >= max_attempts:",
        "    return 'locked'",
        "else:",
        "    return 'retry'",
    ]
    params = [
        Param(locked, (False, True), "bool"),
        Param(failures, (0, max_attempts - 1, max_attempts), "int"),
        Param(ok, (True, False), "bool"),
        Param("max_attempts", (max_attempts,), "int", default=max_attempts),
    ]
    return make(r, fn, params, checks, core, docs=("Outcome of one login attempt.",), returns="str")


@family("admin-authorization", "access_control")
def admin_authorization(r):
    fn = pick(r, ["authorize_admin_action", "authorize", "check_admin_request"])
    role = pick(r, ["role", "actor_role"])
    mfa = pick(r, ["mfa_verified", "second_factor_ok"])
    action = pick(r, ["action", "command"])
    actions = pick(
        r,
        [
            ("create_user", "reset_password", "delete_user"),
            ("add_member", "remove_member", "rotate_keys"),
        ],
    )
    checks = [
        Check(
            f"{role} == 'admin'",
            f"{role} != 'admin'",
            raises("PermissionError", "admin role required"),
        ),
        Check(mfa, f"not {mfa}", raises("PermissionError", "multi-factor verification required")),
        Check(
            f"{action} in {lit(actions)}",
            f"{action} not in {lit(actions)}",
            pick(r, [raises("ValueError", "unknown admin action"), returns("None")]),
        ),
    ]
    checks = [*shuffled(r, checks[:2]), checks[2]]
    core = [f"return {action} + ' allowed'"]
    if maybe(r, 0.5):
        core = [
            f"if {action} == {lit(actions[2])}:",
            "    return 'requires second approval'",
            f"return {action} + ' allowed'",
        ]
    params = [
        Param(role, ("admin", "member"), "str"),
        Param(mfa, (True, False), "bool"),
        Param(action, (*actions, "drop_tables"), "str"),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Authorize an administrative action.",),
        returns="str | None",
    )


@family("feature-rollout", "access_control")
def feature_rollout(r):
    fn = pick(r, ["flag_enabled", "in_rollout", "feature_active_for"])
    user = pick(r, ["user_id", "account_id"])
    percent = pick(r, ["rollout_percent", "percent"])
    enabled = pick(r, ["enabled", "flag_on"])
    salt = pick(r, [37, 41, 53])
    checks = [
        Check(enabled, f"not {enabled}", returns("False")),
        Check(
            f"0 <= {percent} <= 100",
            f"{percent} < 0 or {percent} > 100",
            raises("ValueError", "rollout percent must be between 0 and 100"),
        ),
        Check(f"{user} >= 0", f"{user} < 0", raises("ValueError", "ids cannot be negative")),
    ]
    core = [f"bucket = {user} * {salt} % 100", f"return bucket < {percent}"]
    if maybe(r, 0.4):
        core = [
            f"if {percent} == 100:",
            "    return True",
            f"bucket = {user} * {salt} % 100",
            f"return bucket < {percent}",
        ]
    params = [
        Param(user, (-1, 0, 7, 12345), "int"),
        Param(percent, (-1, 0, 50, 100, 101), "int"),
        Param(enabled, (True, False), "bool", default=True),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Whether a user is inside a feature rollout.",),
        returns="bool",
    )


@family("document-clearance", "access_control")
def document_clearance(r):
    fn = pick(r, ["can_read_document", "clearance_allows", "may_open"])
    clearance = pick(r, ["clearance", "user_level"])
    label = pick(r, ["classification", "document_level"])
    need = pick(r, ["need_to_know", "has_need"])
    checks = [
        Check(
            f"{clearance} in levels",
            f"{clearance} not in levels",
            raises("ValueError", "unknown clearance"),
        ),
        Check(
            f"{label} in levels",
            f"{label} not in levels",
            raises("ValueError", "unknown classification"),
        ),
        Check(
            f"levels.index({clearance}) >= levels.index({label})",
            f"levels.index({clearance}) < levels.index({label})",
            returns("False"),
        ),
    ]
    checks = [*shuffled(r, checks[:2]), checks[2]]
    core = [f"if {label} == 'top_secret':", f"    return {need}", "return True"]
    params = [
        Param(clearance, ("public", "secret", "top_secret", "root"), "str"),
        Param(label, ("internal", "top_secret", "vault"), "str"),
        Param(need, (False, True), "bool", default=False),
    ]
    variant = make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("Whether a reader may open a classified document.",),
        returns="bool",
    )
    variant.prelude = ["levels = ('public', 'internal', 'secret', 'top_secret')"]
    return variant


@family("session-timeout", "access_control")
def session_timeout(r):
    fn = pick(r, ["session_state", "check_session", "session_status"])
    idle = pick(r, ["idle_seconds", "idle_for"])
    remember = pick(r, ["remember_me", "persistent"])
    role = pick(r, ["role", "client_type"])
    short, long_ = pick(r, [(900, 3600), (600, 7200), (1200, 3600)])
    checks = [
        Check(f"{idle} >= 0", f"{idle} < 0", raises("ValueError", "idle time cannot be negative")),
        Check(
            f"{role} != 'kiosk'",
            f"{role} == 'kiosk'",
            returns(f"'expired' if {idle} > 120 else 'active'"),
        ),
    ]
    core = [
        f"limit = {long_} if {remember} else {short}",
        f"if {idle} > limit:",
        "    return 'expired'",
        f"if {idle} > limit - 60:",
        "    return 'warning'",
        "return 'active'",
    ]
    params = [
        Param(
            idle,
            (
                -1,
                0,
                100,
                120,
                121,
                short - 60,
                short - 59,
                short,
                short + 1,
                long_ - 60,
                long_,
                long_ + 1,
            ),
            "int",
        ),
        Param(remember, (False, True), "bool"),
        Param(role, ("user", "kiosk"), "str"),
    ]
    return make(
        r,
        fn,
        params,
        checks,
        core,
        docs=("State of a session after a period of inactivity.",),
        returns="str",
    )


@family("reset-token", "security")
def reset_token(r):
    fn = pick(r, ["token_status", "check_reset_token", "reset_link_state"])
    token = pick(r, ["token", "reset_token"])
    issued = pick(r, ["issued_minute", "created_at"])
    now = pick(r, ["now_minute", "current_minute"])
    length = pick(r, [12, 16])
    ttl = pick(r, [30, 15, 60])
    checks = [
        Check(
            f"len({token}) == {length}",
            f"len({token}) != {length}",
            raises("ValueError", "malformed token"),
        ),
        Check("not used", "used", returns("'used'")),
    ]
    checks = shuffled(r, checks)
    core = [
        f"age = {now} - {issued}",
        "if age < 0:",
        "    raise ValueError('token issued in the future')",
        f"if age <= {ttl}:",
        "    return 'valid'",
        "return 'expired'",
    ]
    params = [
        Param(token, ("short", "x" * length), "str"),
        Param(issued, (100,), "int"),
        Param(now, (90, 100, 100 + ttl, 101 + ttl), "int"),
        Param("used", (False, True), "bool", default=False),
    ]
    return make(
        r, fn, params, checks, core, docs=("State of a password-reset token.",), returns="str"
    )
