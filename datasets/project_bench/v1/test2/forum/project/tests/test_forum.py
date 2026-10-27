from datetime import datetime, timedelta

import pytest

from forum.board import Board
from forum.moderation import Moderation, Report
from forum.notifications import Inbox
from forum.posts import can_edit
from forum.text import excerpt, extract_mentions, render_body
from forum.users import Role, User, UserDirectory

T0 = datetime(2026, 5, 1, 12, 0)


def make_board():
    users = UserDirectory()
    alice = users.add(User("alice", "Alice", T0))
    bob = users.add(User("bob", "Bob B.", T0))
    mod = users.add(User("mod_mia", "Mia", T0, Role.MODERATOR))
    board = Board(users, Moderation(users), Inbox())
    return board, alice, bob, mod


def test_usernames_unique_ignoring_case():
    users = UserDirectory()
    users.add(User("alice", "Alice", T0))
    with pytest.raises(ValueError):
        users.add(User("ALICE", "Other", T0))
    assert users.get("Alice").display_name == "Alice"


def test_bad_username_rejected():
    with pytest.raises(ValueError):
        UserDirectory().add(User("a b", "x", T0))


def test_create_thread_and_reply():
    board, alice, bob, _ = make_board()
    thread = board.create_thread(alice, "Hello", "First post", T0)
    board.reply(bob, thread.thread_id, "Welcome", T0 + timedelta(minutes=1))
    assert [p.author for p in thread.posts] == ["alice", "bob"]
    assert [n.kind for n in board.inbox.unread("alice")] == ["reply"]


def test_mention_notifies_the_user():
    board, alice, bob, _ = make_board()
    thread = board.create_thread(alice, "Plans", "Hi all", T0)
    board.reply(alice, thread.thread_id, "What do you think, @Bob?", T0)
    notes = board.inbox.unread("bob")
    assert [n.kind for n in notes] == ["mention"]
    assert notes[0].text.startswith("alice mentioned you")


def test_author_edits_within_window():
    board, alice, _, _ = make_board()
    thread = board.create_thread(alice, "Typo", "helo", T0)
    post = board.edit(alice, thread.posts[0].post_id, "hello", T0 + timedelta(minutes=5))
    assert post.body == "hello"


def test_author_cannot_edit_after_window():
    board, alice, _, _ = make_board()
    thread = board.create_thread(alice, "Typo", "helo", T0)
    assert not can_edit(alice, thread.posts[0], T0 + timedelta(minutes=20))


def test_others_cannot_edit_but_staff_can():
    board, alice, bob, mod = make_board()
    post = board.create_thread(alice, "Mine", "text", T0).posts[0]
    assert not can_edit(bob, post, T0)
    assert can_edit(mod, post, T0 + timedelta(days=3))


def test_temporary_ban_blocks_then_expires():
    board, alice, bob, mod = make_board()
    board.moderation.ban(mod, "bob", "spam", T0, days=2)
    thread = board.create_thread(alice, "Open", "text", T0)
    with pytest.raises(PermissionError):
        board.reply(bob, thread.thread_id, "more spam", T0 + timedelta(days=1))
    board.reply(bob, thread.thread_id, "sorry", T0 + timedelta(days=3))


def test_members_cannot_ban():
    board, alice, _, _ = make_board()
    with pytest.raises(PermissionError):
        board.moderation.ban(alice, "bob", "rude", T0, days=1)


def test_locked_thread_refuses_replies():
    board, alice, bob, mod = make_board()
    thread = board.create_thread(alice, "Closed soon", "text", T0)
    board.moderation.lock_thread(mod, thread, T0)
    with pytest.raises(PermissionError):
        board.reply(bob, thread.thread_id, "late", T0)
    assert board.moderation.audit == ["2026-05-01 12:00 mod_mia locked thread 1"]


def test_pinned_threads_listed_first():
    board, alice, _, mod = make_board()
    first = board.create_thread(alice, "Old", "text", T0)
    board.create_thread(alice, "New", "text", T0 + timedelta(hours=1))
    board.moderation.pin_thread(mod, first, T0)
    assert [t.title for t in board.listing()] == ["Old", "New"]


def test_reported_post_hidden_at_threshold():
    board, alice, bob, mod = make_board()
    thread = board.create_thread(alice, "Hot take", "text", T0)
    reports = [Report(1, "bob", "rude"), Report(1, "mod_mia", "rude"), Report(1, "alice", "x")]
    assert board.moderation.hide_reported(thread.posts, reports, threshold=2) == [1]
    assert board.page(thread.thread_id, 1) == []


def test_paging():
    board, alice, bob, _ = make_board()
    thread = board.create_thread(alice, "Count", "0", T0)
    for i in range(1, 5):
        board.reply(bob, thread.thread_id, str(i), T0)
    assert [p.body for p in board.page(thread.thread_id, 2, per_page=2)] == ["2", "3"]


def test_body_is_escaped_and_mentions_linked():
    html = render_body("<b>hi</b> @bob\n\nbye", lambda name: name == "bob")
    assert html == (
        '<p>&lt;b&gt;hi&lt;/b&gt; <a class="mention" href="/u/bob">@bob</a></p><p>bye</p>'
    )


def test_render_page_marks_late_edits():
    board, alice, _, _ = make_board()
    thread = board.create_thread(alice, "Edited", "one", T0)
    board.edit(alice, thread.posts[0].post_id, "two", T0 + timedelta(minutes=10))
    page = board.render_page(thread.thread_id, 1)
    assert "(edited)" in page
    assert '<span class="author">Alice</span>' in page


def test_mentions_and_excerpt():
    assert extract_mentions("@Ann and @ann, mail me@x.com, @bob") == ["ann", "bob"]
    assert excerpt("word " * 30, limit=20) == "word word word..."
