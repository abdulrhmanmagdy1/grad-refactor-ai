"""The board: creating threads, replying, editing and reading pages."""

from __future__ import annotations

from datetime import datetime

from forum import posts
from forum.moderation import Moderation
from forum.notifications import Inbox, mention_jobs, reply_notifications
from forum.posts import Post, Thread
from forum.text import render_post
from forum.users import User, UserDirectory

MAX_TITLE = 120


class Board:
    """All threads of the forum, with moderation and notifications wired in."""

    def __init__(self, users: UserDirectory, moderation: Moderation, inbox: Inbox) -> None:
        self.users = users
        self.moderation = moderation
        self.inbox = inbox
        self._threads: dict[int, Thread] = {}
        self._posts: dict[int, Post] = {}
        self._next_thread = 1
        self._next_post = 1

    def thread(self, thread_id: int) -> Thread:
        """The thread with this id; raises KeyError when there is none."""
        return self._threads[thread_id]

    def post(self, post_id: int) -> Post:
        """The post with this id; raises KeyError when there is none."""
        return self._posts[post_id]

    def _check_can_post(self, author: User, now: datetime) -> None:
        if self.moderation.is_banned(author.username, now):
            raise PermissionError(f"{author.username} is banned")

    def _store(self, thread: Thread, author: User, body: str, now: datetime) -> Post:
        if not body.strip():
            raise ValueError("a post cannot be empty")
        post = Post(self._next_post, thread.thread_id, author.username, body, now)
        jobs = mention_jobs(post, self.users)
        replies = reply_notifications(thread, post, set(post.mentions))
        thread.posts.append(post)
        self._posts[post.post_id] = post
        self._next_post += 1
        for job in jobs:
            self.inbox.deliver(job())
        for notification in replies:
            self.inbox.deliver(notification)
        return post

    def create_thread(self, author: User, title: str, body: str, now: datetime) -> Thread:
        """Start a thread with ``body`` as its first post."""
        self._check_can_post(author, now)
        title = title.strip()
        if not title or len(title) > MAX_TITLE:
            raise ValueError(f"titles are 1 to {MAX_TITLE} characters")
        thread = Thread(self._next_thread, title, author.username, now)
        self._store(thread, author, body, now)
        self._threads[thread.thread_id] = thread
        self._next_thread += 1
        return thread

    def reply(self, author: User, thread_id: int, body: str, now: datetime) -> Post:
        """Add a reply to an unlocked thread."""
        self._check_can_post(author, now)
        thread = self.thread(thread_id)
        if thread.locked:
            raise PermissionError(f"thread {thread_id} is locked")
        return self._store(thread, author, body, now)

    def edit(self, user: User, post_id: int, body: str, now: datetime) -> Post:
        """Change a post's body, subject to the editing rules and bans."""
        self._check_can_post(user, now)
        return posts.edit(user, self.post(post_id), body, now)

    def page(self, thread_id: int, number: int, per_page: int = 20) -> list[Post]:
        """Visible posts on page ``number`` of a thread; pages count from 1."""
        if number < 1 or per_page < 1:
            raise ValueError("pages and page sizes start at 1")
        visible = self.thread(thread_id).visible_posts()
        start = (number - 1) * per_page
        return visible[start : start + per_page]

    def render_page(self, thread_id: int, number: int, per_page: int = 20) -> str:
        """HTML for one page of a thread."""
        return "\n".join(
            render_post(p, self.users.get(p.author), self.users.__contains__)
            for p in self.page(thread_id, number, per_page)
        )

    def listing(self) -> list[Thread]:
        """Threads for the front page: pinned first, then newest first."""
        return sorted(
            self._threads.values(),
            key=lambda t: (not t.pinned, -t.created_at.timestamp()),
        )
