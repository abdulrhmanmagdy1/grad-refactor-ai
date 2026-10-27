from datetime import datetime, timedelta

import pytest

from forum.board import Board
from forum.moderation import Ban, Moderation, Report
from forum.notifications import Inbox, Notification, mention_jobs
from forum.posts import Post, can_edit
from forum.text import render_body, render_post
from forum.users import Role, User, UserDirectory

T0 = datetime(2026, 5, 1, 12, 0)


def make_board():
    users = UserDirectory()
    alice = users.add(User("alice", "Alice", T0))
    bob = users.add(User("bob", "Bob", T0))
    carol = users.add(User("carol", "Carol", T0))
    mod = users.add(User("mod_mia", "Mia", T0, Role.MODERATOR))
    board = Board(users, Moderation(users), Inbox())
    return board, alice, bob, carol, mod


def test_B1_each_mentioned_user_gets_their_own_notification():
    board, *_ = make_board()
    post = Post(9, 1, "carol", "Ping @alice and @bob", T0)
    recipients = [job().recipient for job in mention_jobs(post, board.users)]
    assert sorted(recipients) == ["alice", "bob"]


def test_B1_board_delivers_every_mention():
    board, alice, _, carol, _ = make_board()
    thread = board.create_thread(carol, "Team", "Hi", T0)
    board.reply(carol, thread.thread_id, "@alice @bob please review", T0)
    assert [n.kind for n in board.inbox.unread("alice")] == ["mention"]
    assert [n.kind for n in board.inbox.unread("bob")] == ["mention"]


def test_B2_author_cannot_edit_a_day_later():
    board, alice, *_ = make_board()
    post = board.create_thread(alice, "Old", "text", T0).posts[0]
    assert not can_edit(alice, post, T0 + timedelta(days=1, minutes=5))


def test_B2_edit_refused_a_week_later():
    board, alice, *_ = make_board()
    post = board.create_thread(alice, "Old", "text", T0).posts[0]
    with pytest.raises(PermissionError):
        board.edit(alice, post.post_id, "changed", T0 + timedelta(days=7, minutes=1))


def test_B3_permanent_ban_is_active():
    ban = Ban("bob", "spam", "mod_mia", T0, None)
    assert ban.is_active(T0 + timedelta(days=400))


def test_B3_permanently_banned_user_cannot_post():
    board, alice, bob, _, mod = make_board()
    board.moderation.ban(mod, "bob", "spam", T0)
    thread = board.create_thread(alice, "Open", "text", T0)
    assert board.moderation.is_banned("bob", T0 + timedelta(days=30))
    with pytest.raises(PermissionError):
        board.reply(bob, thread.thread_id, "still here", T0 + timedelta(days=30))


def test_S1_display_name_is_escaped():
    author = User("mallory", '<script>alert("x")</script>', T0)
    post = Post(1, 1, "mallory", "hello", T0)
    html = render_post(post, author, lambda name: False)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_keep_ban_not_active_before_start_or_after_end():
    ban = Ban("bob", "spam", "mod_mia", T0, T0 + timedelta(days=2))
    assert not ban.is_active(T0 - timedelta(minutes=1))
    assert ban.is_active(T0 + timedelta(days=1))
    assert not ban.is_active(T0 + timedelta(days=2))


def test_keep_lift_temporary_ban():
    board, _, bob, _, mod = make_board()
    board.moderation.ban(mod, "bob", "spam", T0, days=10)
    assert board.moderation.lift_bans(mod, "bob", T0 + timedelta(days=1)) == 1
    assert not board.moderation.is_banned("bob", T0 + timedelta(days=2))


def test_keep_moderator_cannot_ban_admin():
    users = UserDirectory()
    mod = users.add(User("mod_mia", "Mia", T0, Role.MODERATOR))
    users.add(User("root", "Root", T0, Role.ADMIN))
    with pytest.raises(PermissionError):
        Moderation(users).ban(mod, "root", "x", T0)


def test_keep_edit_within_window_and_staff_any_time():
    board, alice, _, _, mod = make_board()
    post = board.create_thread(alice, "Now", "text", T0).posts[0]
    assert can_edit(alice, post, T0 + timedelta(minutes=14))
    assert not can_edit(alice, post, T0 + timedelta(minutes=16))
    assert can_edit(mod, post, T0 + timedelta(days=30))


def test_keep_self_mention_and_unknown_skipped():
    board, *_ = make_board()
    post = Post(3, 1, "alice", "@alice talks to @nobody", T0)
    assert mention_jobs(post, board.users) == []


def test_keep_single_mention_text():
    board, *_ = make_board()
    post = Post(4, 1, "alice", "thanks @bob", T0)
    [job] = mention_jobs(post, board.users)
    note = job()
    assert isinstance(note, Notification)
    assert (note.recipient, note.kind, note.post_id) == ("bob", "mention", 4)
    assert note.text == "alice mentioned you: thanks @bob"


def test_keep_mention_links_only_known_users():
    html = render_body("@bob meets @eve <i>", lambda name: name.lower() == "bob")
    assert html == '<p><a class="mention" href="/u/bob">@bob</a> meets @eve &lt;i&gt;</p>'


def test_keep_render_post_shows_name_and_escaped_body():
    author = User("bob", "Bob Builder", T0)
    post = Post(2, 1, "bob", "a < b", T0)
    html = render_post(post, author, lambda name: False)
    assert "Bob Builder" in html
    assert "<p>a &lt; b</p>" in html
    assert "(edited)" not in html


def test_keep_prune_read_removes_only_read():
    inbox = Inbox()
    for i in range(4):
        inbox.deliver(Notification("bob", "reply", i, "x", read=i % 2 == 0))
    assert inbox.prune_read("bob") == 2
    assert [n.post_id for n in inbox.all("bob")] == [1, 3]


def test_keep_hide_reported_ignores_self_reports_and_duplicates():
    board, alice, *_ = make_board()
    post = board.create_thread(alice, "Take", "text", T0).posts[0]
    reports = [Report(1, "alice", "x"), Report(1, "bob", "x"), Report(1, "BOB", "y")]
    assert board.moderation.hide_reported([post], reports, threshold=2) == []
    assert not post.hidden


def test_keep_moderator_cannot_pin_own_thread():
    board, _, _, _, mod = make_board()
    thread = board.create_thread(mod, "Rules", "text", T0)
    with pytest.raises(PermissionError):
        board.moderation.pin_thread(mod, thread, T0)
    assert not thread.pinned
