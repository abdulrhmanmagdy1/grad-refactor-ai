# webapp

A small web backend without a framework or a server. A front server parses each HTTP
request into a `webapp.routing.Request` and calls `WebApp.handle`, which returns a
`Response`.

- `routing`: request and response types, a router with `<name>` placeholders (404 for an
  unknown path, 405 for a known path with the wrong method).
- `passwords`: PBKDF2 password hashing.
- `accounts`: registration, login with a lockout after repeated failures, profiles.
- `sessions`: bearer-token sessions with an idle timeout and a maximum age.
- `permissions`: roles and what each role may do.
- `ratelimit`: a sliding-window limit on requests per client address.
- `app`: the handlers that tie these together.

Run the tests with `python -m pytest`.
