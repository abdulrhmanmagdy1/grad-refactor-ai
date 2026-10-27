from datetime import datetime, timedelta
from pathlib import Path

import pytest

from helpdesk.desk import Helpdesk, NewComment, NewTicket
from helpdesk.models import Agent, Priority, Status
from helpdesk.report import open_breaches_by_agent
from helpdesk.sla import resolution_deadline, response_deadline

T0 = datetime(2026, 3, 2, 8, 30)


def make_desk(tmp_path: Path) -> Helpdesk:
    agents = [
        Agent("amira", frozenset({"network", "hardware"})),
        Agent("bassem", frozenset({"network"}), max_open=1),
        Agent("dina", frozenset({"accounts"})),
    ]
    return Helpdesk(agents, tmp_path / "uploads")


def new(title: str, category: str, priority: Priority = Priority.NORMAL) -> NewTicket:
    return NewTicket(title, category, priority, "staff.member")


def test_new_ticket_goes_to_the_least_loaded_skilled_agent(tmp_path):
    desk = make_desk(tmp_path)
    first = desk.open_ticket(new("VPN drops", "network"), T0)
    second = desk.open_ticket(new("Wi-Fi slow", "network"), T0)
    assert first.assignee == "amira"
    assert second.assignee == "bassem"
    assert first.status is Status.ASSIGNED
    assert desk.board.agent("amira").open_tickets == 1


def test_ticket_without_a_qualified_agent_stays_new(tmp_path):
    desk = make_desk(tmp_path)
    ticket = desk.open_ticket(new("Printer jam", "printing"), T0)
    assert ticket.assignee is None
    assert ticket.status is Status.NEW


def test_full_agents_are_skipped(tmp_path):
    desk = make_desk(tmp_path)
    desk.open_ticket(new("a", "network"), T0)
    desk.open_ticket(new("b", "network"), T0)
    third = desk.open_ticket(new("c", "network"), T0)
    assert third.assignee == "amira"


def test_resolving_frees_the_agent_and_reopening_takes_the_slot_back(tmp_path):
    desk = make_desk(tmp_path)
    ticket = desk.open_ticket(new("Password reset", "accounts"), T0)
    desk.set_status(ticket.id, Status.IN_PROGRESS, T0 + timedelta(minutes=5))
    desk.set_status(ticket.id, Status.RESOLVED, T0 + timedelta(minutes=20))
    assert ticket.resolved_at == T0 + timedelta(minutes=20)
    assert desk.board.agent("dina").open_tickets == 0
    desk.set_status(ticket.id, Status.IN_PROGRESS, T0 + timedelta(hours=1))
    assert ticket.resolved_at is None
    assert desk.board.agent("dina").open_tickets == 1


def test_illegal_status_change_is_refused(tmp_path):
    desk = make_desk(tmp_path)
    ticket = desk.open_ticket(new("Monitor flickers", "hardware"), T0)
    with pytest.raises(ValueError):
        desk.set_status(ticket.id, Status.CLOSED, T0)


def test_first_public_agent_comment_is_the_first_response(tmp_path):
    desk = make_desk(tmp_path)
    ticket = desk.open_ticket(new("Laptop slow", "hardware"), T0)
    desk.add_comment(ticket.id, NewComment("staff.member", "any news?"), T0 + timedelta(minutes=10))
    desk.add_comment(ticket.id, NewComment("amira", "checking logs", internal=True), T0 + timedelta(minutes=15))
    assert ticket.first_response_at is None
    desk.add_comment(ticket.id, NewComment("amira", "on my way"), T0 + timedelta(minutes=20))
    assert ticket.first_response_at == T0 + timedelta(minutes=20)


def test_attachments_are_stored_per_ticket(tmp_path):
    desk = make_desk(tmp_path)
    ticket = desk.open_ticket(new("Error popup", "hardware"), T0)
    comment = desk.add_comment(
        ticket.id, NewComment("staff.member", "screenshot", [("error.png", b"\x89PNG")]), T0
    )
    attachment = comment.attachments[0]
    assert Path(attachment.path) == tmp_path / "uploads" / str(ticket.id) / "error.png"
    assert desk.uploads.read(attachment) == b"\x89PNG"


def test_closed_ticket_can_be_deleted_with_its_files(tmp_path):
    desk = make_desk(tmp_path)
    ticket = desk.open_ticket(new("Old", "accounts"), T0)
    desk.add_comment(ticket.id, NewComment("dina", "log", [("a.txt", b"1"), ("b.txt", b"2")]), T0)
    desk.set_status(ticket.id, Status.RESOLVED, T0)
    desk.set_status(ticket.id, Status.CLOSED, T0)
    assert desk.delete_ticket(ticket.id) == 2
    assert not (tmp_path / "uploads" / str(ticket.id)).exists()


def test_deadlines_follow_the_priority(tmp_path):
    desk = make_desk(tmp_path)
    ticket = desk.open_ticket(new("Server down", "network", Priority.CRITICAL), T0)
    assert response_deadline(ticket) == T0 + timedelta(minutes=30)
    assert resolution_deadline(ticket) == T0 + timedelta(hours=4)


def test_unanswered_ticket_is_escalated_once(tmp_path):
    desk = make_desk(tmp_path)
    ticket = desk.open_ticket(new("Shared drive missing", "network"), T0)
    assert desk.tick(T0 + timedelta(hours=7)) == 0
    assert desk.tick(T0 + timedelta(hours=9)) == 1
    assert desk.tick(T0 + timedelta(hours=20)) == 0
    assert ticket.escalations == 1


def test_answered_ticket_is_not_escalated(tmp_path):
    desk = make_desk(tmp_path)
    ticket = desk.open_ticket(new("Mouse broken", "hardware"), T0)
    desk.add_comment(ticket.id, NewComment("amira", "bringing a new one"), T0 + timedelta(hours=1))
    desk.tick(T0 + timedelta(days=1))
    assert ticket.escalations == 0
    assert ticket.priority is Priority.NORMAL


def test_sla_report_counts_breaches(tmp_path):
    desk = make_desk(tmp_path)
    late = desk.open_ticket(new("Email bounce", "accounts", Priority.HIGH), T0)
    quick = desk.open_ticket(new("Unlock account", "accounts", Priority.HIGH), T0)
    desk.set_status(quick.id, Status.RESOLVED, T0 + timedelta(hours=1))
    rows = {row.priority: row for row in desk.report(T0 + timedelta(hours=30))}
    assert rows[Priority.HIGH].tickets == 2
    assert rows[Priority.HIGH].resolved == 1
    assert rows[Priority.HIGH].breached == 1
    assert rows[Priority.HIGH].compliance == 50.0
    assert rows[Priority.LOW].compliance == 100.0
    assert open_breaches_by_agent(desk.tickets.values(), T0 + timedelta(hours=30)) == {"dina": [late.id]}
