# Web Interface (`frontend/`)

The single-page interface served by FastAPI at `/`. It was rebuilt from scratch
as a layered application — not a skin over the old one — around one rule:
**the interface may never show a number the API did not measure.**

## Stack

- **React 19 + TypeScript 6** (strict, `verbatimModuleSyntax`, no `any`)
- **Vite 8** (Rolldown) with the `@/` path alias
- **Tailwind CSS v4** driven by semantic design tokens (`src/styles/tokens.css`)
- **TanStack Query** for every piece of server state (caching, retries, polling)
- **TanStack Virtual**-ready list rendering, **Zustand** for UI-only state
- **Zod** contracts that validate every API response
- **Monaco Editor** (bundled locally, loaded lazily) for the buffers and the diff
- **Vitest + Testing Library** for unit and component tests
- **ESLint 9** (flat config, `react-hooks` + `jsx-a11y`) and **Prettier**

No CDN, no API key, no telemetry: the interface works fully offline.

## Architecture

```
src/
├── app/         composition root: providers, theme bridge, error boundary, shell
├── entities/    server state: typed query/mutation hooks over the API
├── features/    user-facing capabilities (workspace, results, history, overlays)
├── shared/      reusable pieces: api client, design system, hooks, utilities
└── styles/      design tokens
```

Dependency direction is `app → features → entities → shared`; nothing in
`shared/` may import from `features/`.

### Data flow

1. `shared/api/http.ts` performs the request: timeout, abort support, typed
   errors and the server's `X-Request-ID` are preserved.
2. `shared/api/contract.ts` validates the payload with Zod. A contract drift
   surfaces as an explicit error instead of `undefined` in the UI.
3. `entities/queries.ts` exposes the data as TanStack Query hooks. A run is
   polled every 700 ms while it is executing, so the phase
   (`analyzing → generating → verifying`) stays visible.
4. Features render from those hooks; UI-only state (active tab, open drawer)
   lives in small Zustand stores.

### Highlights

- **Monaco diff editor** with a side-by-side/inline switch, plus a raw unified
  diff fallback — the reviewer sees real syntax-highlighted changes.
- **Command palette** (`Ctrl+K`) covering every primary action, and a keyboard
  shortcut sheet (`Ctrl+/`).
- **Live run phases** — the pipeline runs in the background and the UI follows
  its progress instead of blocking on one long request.
- **Markdown report export** straight from the stored run record (`GET
  /runs/{id}/report`), plus candidate download and clipboard copy.
- **History drawer** with status filters, search, JSON/CSV export of the visible
  runs, and a two-run comparison view (verdict, provider, duration, tokens, metrics).
- **FR08 budgets** (model calls, tokens, duration, retries) are editable in the
  workspace and shown back in the results strip, and the dominant rule detected
  by the analyzer can be requested as the run's refactoring type.
- **Accessible by construction** — WAI-ARIA tab pattern, focus-trapped dialogs,
  live regions for notifications, visible focus rings, and `prefers-reduced-motion`
  support.
- **Responsive** — a stacked layout with a source/results switch on small
  screens, the two-column workspace on large ones.

## Commands

```bash
npm install        # once
npm run dev        # dev server on :5173, proxying the API on :8000
npm run lint       # ESLint (flat config, strict)
npm run typecheck  # tsc --noEmit
npm run test       # Vitest
npm run build      # typecheck + production build into dist/
npm run verify     # lint + typecheck + test + build (the CI gate)
```

The production bundle is written to `frontend/dist` and served by FastAPI at
`/`; it is committed so the project runs from a clean clone without Node.
