# forum

The backend of a small discussion forum, as plain Python objects (no server).

Users have roles (member, moderator, admin). Threads hold posts; authors may edit
their own posts for a short window after posting, staff may edit any post. Moderators
ban users (for a number of days or permanently), lock and pin threads, and hide posts
that enough people reported. Mentioning `@username` in a post notifies that user, and
replying notifies earlier participants. Post bodies and anything else users type are
HTML-escaped when rendered.
