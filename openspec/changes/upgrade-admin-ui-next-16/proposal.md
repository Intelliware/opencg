## Why

The admin UI throws React error #418 (a hydration mismatch, `args[]=HTML`) on some production page loads (GitHub issue #2). It shows up only in a production build with several browsers under CPU load: about 8–9% of `/entities` loads with 7 concurrent Chromium browsers, and none with one. The root cause is in the framework, not the app. With Next 15.5.29, hydration can start while `document.readyState` is still `"loading"`. The page segment then suspends with no Suspense boundary above it, and React's hydration cursor ends up one level too deep. The two app-side workarounds we tried (a root `<Suspense>` and `app/loading.tsx`) removed #418 but left client navigations stuck. Today the e2e suite reloads the page once when #418 appears, which hides the bug instead of fixing it.

Next.js 15.5.29 is the last 15.x release, and its App Router runs a React 19.2 canary from August 2025. Next 16 ships a rewritten client router and a newer React canary. A trial upgrade (see design.md) gave **0 #418 errors in 1,820 stressed page loads** on Next 16, against **43 in 560** (7.7%) on 15.5.29 with the same machine, the same live pipeline and the same probe, run interleaved. It also gave 0 stuck navigations. Upgrading is the lowest-risk fix and keeps the admin UI on a supported release line.

## What Changes

- **Upgrade Next.js** in `services/admin-ui` from 15.5.29 to **16.4.5** (security release, 2026-11-03), with `eslint-config-next` at the same version. 16.4.3 is the newest 16.x that is over two weeks old, but it lacks the November 2026 security fixes that 15.5.29 already has. One of them (GHSA-pc58-hwjq-p385, response injection when self-hosted apps forward fetched responses) matches what our `/api/proxy/**` route handlers do. See design.md D1. The owner approved taking 16.4.5 now (2026-11-12) as a recorded exception to the two-week rule for a security release.
- **Move React to 19**: `react`, `react-dom` → `^19.2.0`; `@types/react`, `@types/react-dom` → `^19.2.0`. The App Router keeps using Next's vendored React canary. The declared version drives vitest, Testing Library and Storybook.
- **Rename `src/middleware.ts` → `src/proxy.ts`** and its export `middleware` → `proxy` (the `middleware` convention is deprecated in 16, and the build warns about it). Rename `middleware.test.ts` → `proxy.test.ts`. The admin access gate now runs on the Node.js runtime instead of Edge. Its behaviour stays the same.
- **ESLint flat config**: replace the `FlatCompat` shim in `eslint.config.mjs` with the native flat exports of `eslint-config-next@16`. `FlatCompat` crashes on them. `eslint-config-next@16` brings `eslint-plugin-react-hooks@7`, whose new `react-hooks/set-state-in-effect` rule flags 4 existing call sites. They get justified inline disables, with no behaviour change (design.md D4).
- **Commit the files Next 16 rewrites** on first build (`tsconfig.json`: `jsx: "react-jsx"` and `.next/dev/types/**/*.ts` in `include`; `next-env.d.ts`: import-style route types). This keeps the clean-checkout contract: a build must not dirty the tree.
- **Add a hydration stress check**: `services/admin-ui/scripts/hydration-stress.cjs` plus a `make hydration-stress` target. It loads every route from several concurrent browsers against a production build and counts #418, other console errors, unhydrated pages and stuck client navigations. It is built from the issue #2 probes (probe8, probe12, probe16).
- **Remove the e2e reload workaround** in `e2e/navigation.spec.ts`. A hydration error fails the suite again.
- **BREAKING (contributors only)**: Node.js ≥ 20.9.0 is now the minimum (root `engines`). CI and the Dockerfile already use Node 22, so nothing changes for them.
- Docs: AGENTS.md / CLAUDE.md / `.cursor/rules/opencg.mdc` (kept identical), README stack table, CHANGELOG. Close issue #2 after the owner approves the comment.

- **Nightly regression guard**: a smaller stress pass (4 browsers × 10 cycles) runs in the nightly `stack` CI job. Tremor stays (owner decision).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `admin-ui`: ADDED "Hydration stability under load" (the stress check and its zero-error bar) and "Supported framework baseline" (Next 16 with all published advisories fixed, React 19, Node ≥ 20.9). MODIFIED "End-to-end browser test suite" (no tolerance for hydration errors) and "Clean-checkout build" (`next build` must not modify tracked files).

## Impact

- **Code**: `services/admin-ui/package.json`, `pnpm-lock.yaml`, `eslint.config.mjs`, `tsconfig.json`, `next-env.d.ts`, `src/middleware.ts` → `src/proxy.ts`, `src/middleware.test.ts` → `src/proxy.test.ts`, a comment in `src/lib/session.ts`, 4 inline lint disables (`GraphExplorer.tsx`, `ConceptSearch.tsx`, `ThemeToggle.tsx`), `e2e/navigation.spec.ts`, new `scripts/hydration-stress.cjs`, `Makefile`, root `package.json` (`engines`, a `peerDependencyRules` entry for `@tremor/react`).
- **Unchanged**: `next.config.mjs` (no `webpack`, `images`, `experimental` or runtime-config options), app routes (`params` and `searchParams` are already awaited everywhere; no `cookies()`, `headers()`, `next/image`, parallel routes, AMP or `revalidateTag`), Dockerfile (Node 22, standalone output still works), CI workflow (Node 22, ESLint CLI, no `next lint`), Storybook 8.6 with `@storybook/react-vite`.
- **Dependencies**: `@tremor/react@3.18.7` declares `react@^18` and is effectively unmaintained (last publish January 2025). It builds and runs under React 19 in the trial. We keep it, allow the peer mismatch explicitly, and track replacing it as a follow-up (design.md D5).
- **Risk**: medium. It is a framework major version, but the trial shows typecheck, 89 unit tests, `next build` and `build-storybook` green after the changes above. The remaining unknowns are the e2e suite and visual checks of Tremor charts and the graph map, which only a live-stack run can cover.
