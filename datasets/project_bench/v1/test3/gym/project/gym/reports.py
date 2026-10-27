"""Month-end summary for the gym manager."""

from __future__ import annotations

from decimal import Decimal

from gym import billing, memberships
from gym.checkins import CheckInDesk
from gym.classes import Schedule
from gym.trainers import TrainerDiary


def monthly_report(
    book: memberships.MembershipBook,
    schedule: Schedule,
    desk: CheckInDesk,
    diary: TrainerDiary,
    invoices: list[billing.Invoice],
    year: int,
    month: int,
) -> str:
    """Plain-text summary of one month: members, attendance, classes, trainers, revenue."""
    label = f"{year:04d}-{month:02d}"
    lines = [f"Gym report {label}", ""]

    active = [m for m in book.memberships.values() if memberships.active_days(m, year, month)]
    per_plan: dict[str, int] = {}
    for membership in active:
        per_plan[membership.plan.name] = per_plan.get(membership.plan.name, 0) + 1
    lines.append(f"Active memberships: {len(active)}")
    for plan_name in sorted(per_plan):
        lines.append(f"  {plan_name}: {per_plan[plan_name]}")
    lines.append("")

    visits = desk.visits_in_month(year, month)
    per_member: dict[str, int] = {}
    for visit in visits:
        per_member[visit.member_id] = per_member.get(visit.member_id, 0) + 1
    lines.append(f"Check-ins: {len(visits)}")
    if per_member:
        top_id, top_count = sorted(per_member.items(), key=lambda item: (-item[1], item[0]))[0]
        top_name = book.members[top_id].name if top_id in book.members else top_id
        lines.append(f"Most visits: {top_name} ({top_count})")
    absent = [m.member_id for m in active if m.member_id not in per_member]
    lines.append(f"Active members who never came: {len(absent)}")
    lines.append("")

    sessions = schedule.in_month(year, month)
    places = sum(c.capacity for c in sessions)
    taken = sum(len(c.booked) for c in sessions)
    waiting = sum(len(c.waitlist) for c in sessions)
    lines.append(f"Classes held: {len(sessions)}")
    if places:
        lines.append(f"Places filled: {taken}/{places} ({100 * taken // places}%)")
    full = [c for c in sessions if c.is_full]
    lines.append(f"Full classes: {len(full)}, members left on waitlists: {waiting}")
    lines.append("")

    training = diary.sessions_in_month(year, month)
    done = [s for s in training if s.status == "completed"]
    cancelled = [s for s in training if s.status == "cancelled"]
    lines.append(f"Personal training: {len(done)} completed, {len(cancelled)} cancelled")
    lines.append("")

    billed = [invoice for invoice in invoices if invoice.month == label]
    revenue = sum((invoice.total for invoice in billed), Decimal("0.00"))
    lines.append(f"Invoices issued: {len(billed)}")
    lines.append(f"Revenue: {revenue:.2f}")
    if billed:
        largest = max(billed, key=lambda invoice: invoice.total)
        lines.append(f"Largest invoice: {largest.member_id} {largest.total:.2f}")
    return "\n".join(lines)
