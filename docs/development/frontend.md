# Frontend development

The web interface is a React and TypeScript single-page application in `frontend/`, built with Vite. During development it runs on its own server and forwards API calls to the FastAPI service. For a demonstration, the built files in `frontend/dist` are served by FastAPI itself at http://127.0.0.1:8000/, so Node is not needed at run time. The interface follows the [component contracts](../architecture/contracts.md) and is checked against the backend's [example JSON](../architecture/examples/README.md). Design decisions and the list of interface states are in the [frontend report notes](../report/notes/frontend.md).

## Toolchain

| Item | Version or setting | Where |
|---|---|---|
| Node.js | 24.12.0 (`engines`: `^24.12.0`) | `frontend/.nvmrc`, `frontend/package.json` |
| npm | 11.6 or newer (`packageManager`: `npm@11.6.2`) | `frontend/package.json` |
| Dependencies | Exact versions, no ranges | `frontend/package.json`, `frontend/package-lock.json` |
| npm settings | `save-exact`, `engine-strict`, `ignore-scripts`, no funding messages | `frontend/.npmrc` |

`engine-strict` makes `npm ci` stop on another Node major version instead of building with an untested one. `ignore-scripts` stops package install scripts from running; none of the dependencies needs one.

| Package | Version | Purpose |
|---|---|---|
| react, react-dom | 19.3.1 | User interface |
| vite | 8.3.4 | Development server, proxy and production build |
| @vitejs/plugin-react | 6.1.2 | JSX transform and fast refresh |
| typescript | 6.0.3 | Type checking (`tsc -b`) |
| vitest | 5.0.5 | Test runner |
| jsdom | 29.1.1 | Browser environment for component tests (30.x needs Node 24.15 or newer) |
| @testing-library/react, @testing-library/dom, @testing-library/jest-dom | 16.3.3, 10.4.2, 7.0.1 | Component tests and DOM assertions |
| @types/react, @types/react-dom, @types/node | 19.3.0, 19.3.0, 24.19.2 | Type definitions |

There is no UI kit, editor component, CSS framework, font or icon package. `node_modules` takes about 110 MB.

The only bundled asset that is not code is the JetBrains Mono typeface for code (`frontend/public/fonts/`, two Latin `woff2` files of about 21 kB each, regular and semibold). It is licensed under the SIL Open Font License 1.1, which allows redistribution with software; the license text ships next to the files as `JetBrainsMono-OFL.txt`. The files were taken from the `@fontsource/jetbrains-mono` 5.2.8 package and are served from the page's own origin, so the page still makes no request to the internet. If the files are missing, code falls back to Cascadia Mono, Consolas or the system monospace face. Interface text uses the system font (Segoe UI Variable on Windows 11).

## Setup

```bash
cd frontend
npm ci
```

`npm ci` installs exactly what `package-lock.json` records. Use `npm install <package>@<version>` only when a dependency change is intended, and commit the updated lock file with it.

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Vite development server on http://127.0.0.1:5173 with hot reload |
| `npm run build` | Type check, then production build into `frontend/dist` |
| `npm run preview` | Serves the production build on http://127.0.0.1:4173 with the same proxy |
| `npm run typecheck` | `tsc -b` over the application, the tests and `vite.config.ts` |
| `npm test` | All tests once (`vitest run`); no backend needed |
| `npm run test:watch` | Tests in watch mode |

There is no lint script. Strict TypeScript settings (`strict`, `noUnusedLocals`, `noUncheckedIndexedAccess`, `noImplicitReturns` and others in `frontend/tsconfig.base.json`) and the tests are the static checks; ESLint was left out to keep the dependency set and disk use small.

## Running against the service

Start the service from the repository root, as described in the [setup guide](setup.md):

```bash
uv run uvicorn refactor_ai.api:app --host 127.0.0.1 --port 8000
```

Then, in a second terminal:

```bash
cd frontend
npm run dev
```

Open http://127.0.0.1:5173. The Vite server forwards every request under `/api` and `/health` to http://127.0.0.1:8000, so the browser sees one origin. To use a service on another address, set `REFACTOR_AI_BACKEND_URL` before `npm run dev` or `npm run preview`, for example `REFACTOR_AI_BACKEND_URL=http://127.0.0.1:8765 npm run dev` (PowerShell: `$env:REFACTOR_AI_BACKEND_URL = "http://127.0.0.1:8765"`). The service also allows cross-origin requests from `http://127.0.0.1:5173` and `http://localhost:5173`, but the proxy makes that unnecessary.

All API calls use URLs relative to the page (`/health`, `/api/v1/...`), so the same build works behind the proxy and when FastAPI serves it.

## Production build served by FastAPI

```bash
cd frontend
npm run build
cd ..
uv run uvicorn refactor_ai.api:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/. FastAPI serves `frontend/dist` for paths that no API route matches. `frontend/dist` and `frontend/node_modules` are ignored by Git, so build again after a fresh clone or a frontend change. The built `index.html` carries a Content Security Policy that allows scripts, styles, images, fonts and requests only from the page's own origin: the page works offline and cannot load anything from the internet.

## Tests

```bash
cd frontend
npm test
```

Tests replace `fetch` with an in-memory fake of the service (`src/test/mockServer.ts`), so requests go through the real API client without a network or backend. At most two test workers run at once (`maxWorkers` in `vite.config.ts`), because the demonstration laptop has 8 GB of memory shared with model work; a full run takes about 20 to 60 seconds there. Dates are checked in UTC whatever the machine's time zone. The tests cover:

- the unified diff parser (hunks, additions and removals, line numbers, missing counts, CRLF, stripped context lines, no-newline markers, malformed and empty diffs) and the side-by-side alignment;
- the display-only Python highlighter (every character kept, keywords, names, strings with prefixes and escapes, numbers, comments, soft keywords, triple-quoted strings and brackets across lines) and the indentation outline drawn beside a proposal (levels by Python's block rule, continuation and comment lines, tabs, CRLF);
- polling with fake timers (750 ms delay growing to 3 s, reset on a status change, stop on a terminal status, on `stop()` and on unmount, maximum wait, network errors and fatal errors);
- the API client's error handling (ErrorResponse codes and details, FastAPI's default validation body, `Retry-After`, network failures, timeouts, cancellation, malformed responses, download file names);
- every disposition and every status of the four verification dimensions, including that `not_available`, `not_run` and `error` never use the pass color or a check mark;
- the whole page: health and the fake-provider banner, input limits, submission, progress, results, 422 and 503 errors with the input kept, demonstration cases and the reference-case link, failed and interrupted runs with "Try again", history with reopening and deletion, copy, download and accept or reject;
- that the TypeScript contract mirror has exactly the fields, enums and literals of `src/refactor_ai/contracts.py`, plus the task limits and rubric checks of `src/refactor_ai/tasks/guard_clauses.py` (`src/test/contractMirror.test.ts`);
- that every file in `docs/architecture/examples/` matches the mirrored contract field by field and renders correctly, including every health state in the header (`src/test/contractExamples.test.tsx`);
- that every stop reason the coordinator writes and every run error code the service writes has a readable explanation, and that the test fixtures use the default generation limits of `WorkflowSettings`;
- WCAG AA contrast of the color pairs used in both themes, including every syntax color on plain, added and removed code lines (`src/styles/contrast.test.ts`).

An optional end-to-end test drives the real client and poller against a running service. It is skipped unless `REFACTOR_AI_E2E_URL` is set, and it creates and deletes its own runs:

```bash
cd frontend
REFACTOR_AI_E2E_URL=http://127.0.0.1:8000 npm test -- src/test/e2e.test.ts
```

In PowerShell, set `$env:REFACTOR_AI_E2E_URL = "http://127.0.0.1:8000"` first. With the fake provider its results are plumbing evidence only, not evidence of model behavior.

## Source layout

| Path | Contents |
|---|---|
| `src/api/contracts.ts` | TypeScript mirror of the contract models, enums and limits |
| `src/api/client.ts` | Typed API client and the `ApiError` model |
| `src/lib/` | Diff parsing and alignment, polling, text measurement as the service does it, formatting, status vocabulary, the display-only Python highlighter (`highlight.ts`) and the indentation outline (`shape.ts`) |
| `src/state/` | Reducers for the editor and the runs this page tracks |
| `src/components/` | Header, input panel and editor, run panel (progress, outcome, diff, verification, findings, decision, run record), history; `CodeText.tsx` draws one highlighted code line with indentation guides and `CodeShape.tsx` the before and after outline |
| `src/styles/` | Design tokens (light and dark, including code and syntax colors) with the `@font-face` rules, base elements and the application layout |
| `public/fonts/` | JetBrains Mono (OFL 1.1) and its license |
| `src/test/` | Test fixtures, the fake service, contract and example checks, the optional end-to-end test |

## Changing a contract

When a model in `src/refactor_ai/contracts.py` changes, `contractMirror.test.ts` and `contractExamples.test.tsx` fail until the frontend is updated. Update `src/api/contracts.ts` and the field list in `src/test/contractFields.ts`; the field lists only compile when they name exactly the properties of the TypeScript interface.

## Troubleshooting

- `npm ci` fails with `EBADENGINE`: switch to Node 24.12.0 or a newer 24.x release (`nvm use` reads `.nvmrc`).
- `npm run dev` fails because port 5173 is in use: the port is fixed (`strictPort`) because the service's CORS rules name it. Stop the other server first.
- Every request fails with HTTP 502 or "Cannot reach the refactoring service": the service is not running on 127.0.0.1:8000, or `REFACTOR_AI_BACKEND_URL` points elsewhere.
