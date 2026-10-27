from datetime import datetime, timedelta
from pathlib import Path

import pytest

from helpdesk.attachments import MAX_ATTACHMENT_BYTES, UploadStore
from helpdesk.desk import Helpdesk, NewComment, NewTicket
from helpdesk.escalation import Escalator
from helpdesk.models import Agent, Priority, Status, Ticket

T0 = datetime(2026, 4, 6, 9, 0)


def make_desk(tmp_path: Path) -> Helpdesk:
    agents = [
        Agent("amira", frozenset({"network", "hardware"})),
        Agent("bassem", frozenset({"network"})),
    ]
    return Helpdesk(agents, tmp_path / "uploads")


def new(title: str, category: str = "network", priority: Priority = Priority.NORMAL) -> NewTicket:
    return NewTicket(title, category, priority, "staff.member")


def ticket(ticket_id: int, created_at: datetime) -> Ticket:
    return Ticket(ticket_id, f"ticket {ticket_id}", "network", Priority.NORMAL, "staff.member", created_at)


def test_B1_each_unanswered_ticket_is_escalated_once():
    tickets = [ticket(1, T0), ticket(2, T0 + timedelta(minutes=5)), ticket(3, T0 + timedelta(minutes=10))]
    escalated: list[int] = []
    escalator = Escalator(on_escalate=lambda t: escalated.append(t.id))
    assert escalator.schedule(tickets) == 3
    assert escalator.tick(T0 + timedelta(hours=12)) == 3
    assert [t.escalations for t in tickets] == [1, 1, 1]
    assert sorted(escalated) == [1, 2, 3]


def test_B1_answered_ticket_is_left_alone_while_others_escalate():
    quiet = ticket(1, T0)
    answered = ticket(2, T0)
    answered.first_response_at = T0 + timedelta(hours=1)
    escalator = Escalator()
    escalator.schedule([quiet, answered])
    escalator.tick(T0 + timedelta(hours=12))
    assert quiet.escalations == 1
    assert answered.escalations == 0


def test_B2_reassigning_moves_the_load_to_the_new_agent(tmp_path):
    desk = make_desk(tmp_path)
    ticket = desk.open_ticket(new("Switch port dead"), T0)
    assert ticket.assignee == "amira"
    desk.reassign(ticket.id, "bassem")
    assert desk.board.agent("amira").open_tickets == 0
    assert desk.board.agent("bassem").open_tickets == 1
    follow_up = desk.open_ticket(new("Cable cut"), T0)
    assert follow_up.assignee == "amira"


def test_B3_raising_a_priority_makes_it_more_urgent():
    assert Priority.LOW.raised() is Priority.NORMAL
    assert Priority.NORMAL.raised() is Priority.HIGH
    assert Priority.HIGH.raised() is Priority.CRITICAL
    assert Priority.CRITICAL.raised() is Priority.CRITICAL


def test_B3_escalated_ticket_moves_up_one_priority(tmp_path):
    desk = make_desk(tmp_path)
    ticket = desk.open_ticket(new("Printer offline", "hardware", Priority.LOW), T0)
    desk.tick(T0 + timedelta(days=2))
    assert ticket.priority is Priority.NORMAL


def test_S1_attachment_names_cannot_leave_the_ticket_folder(tmp_path):
    root = tmp_path / "uploads"
    store = UploadStore(root)
    for name in ("../../escape.txt", "../2/planted.txt"):
        try:
            attachment = store.save(1, name, b"payload")
        except (ValueError, PermissionError):
            continue
        stored = Path(attachment.path).resolve()
        assert (root / "1").resolve() in stored.parents
    assert not (tmp_path / "escape.txt").exists()
    assert not (root / "2").exists()


def test_keep_plain_attachment_names_are_stored(tmp_path):
    store = UploadStore(tmp_path / "uploads")
    attachment = store.save(7, "router-config.txt", b"hostname r1")
    assert Path(attachment.path) == tmp_path / "uploads" / "7" / "router-config.txt"
    assert store.read(attachment) == b"hostname r1"


def test_keep_failed_upload_removes_the_files_already_stored(tmp_path):
    desk = make_desk(tmp_path)
    ticket = desk.open_ticket(new("Logs"), T0)
    files = [("first.log", b"ok"), ("huge.bin", b"0" * (MAX_ATTACHMENT_BYTES + 1))]
    with pytest.raises(ValueError):
        desk.add_comment(ticket.id, NewComment("amira", "logs attached", files), T0)
    assert ticket.comments == []
    assert ticket.first_response_at is None
    assert not (tmp_path / "uploads" / str(ticket.id) / "first.log").exists()


def test_keep_timers_fire_once_and_later_timers_wait(tmp_path):
    desk = make_desk(tmp_path)
    urgent = desk.open_ticket(new("Core switch", priority=Priority.HIGH), T0)
    normal = desk.open_ticket(new("Slow share"), T0)
    assert desk.tick(T0 + timedelta(hours=3)) == 1
    assert desk.tick(T0 + timedelta(hours=3)) == 0
    assert urgent.escalations == 1
    assert normal.escalations == 0
    assert desk.tick(T0 + timedelta(hours=9)) == 1
    assert normal.escalations == 1


def test_keep_resolution_frees_the_slot(tmp_path):
    desk = make_desk(tmp_path)
    ticket = desk.open_ticket(new("Done fast"), T0)
    desk.set_status(ticket.id, Status.RESOLVED, T0 + timedelta(minutes=30))
    assert desk.board.agent("amira").open_tickets == 0
    assert desk.tick(T0 + timedelta(days=3)) == 0
