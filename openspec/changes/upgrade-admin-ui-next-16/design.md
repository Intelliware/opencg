## Context

Issue #2 is an intermittent React error #418 in the admin UI's production build. It was root-caused before this change (see proposal.md). In short: under CPU load, hydration starts while `document.readyState` is still `"loading"`, the page segment suspends with no Suspense boundary above it, and React expects the page's `<section>` but finds its `<h1>`. Both app-side fixes we tried had a cost we would not accept:

| Attempt | #418 | Side effect |
|---|---|---|
| Root `<Suspense>` around `{children}` in `src/app/layout.tsx` | 0 / 672 loads | Client navigation into `/queries` never commits |
| `src/app/loading.tsx` | 0 / 742 loads | 3 / 30 row clicks to `/queries/<id>` hang (baseline 0 / 30); `make e2e` failed twice |

So the bug is in Next 15.5 / its vendored React canary (`19.2.0-canary-0bdb9206-20250818`). It is not app code. The e2e suite works around it by reloading once on #418 (`e2e/navigation.spec.ts`).

Current stack in `services/admin-ui`: Next 15.5.29 (the last 15.x), `react`/`react-dom` `^18.3.1` declared (the App Router ignores this and uses the vendored canary), `@types/react` 18, ESLint 9 via `FlatCompat`, Storybook 8.6 with `@storybook/react-vite`, vitest 4, Testing Library 16, Tremor 3.18, Radix/shadcn, `next-themes` 0.4, `sonner` 1.7. Node 22 in CI (`.github/workflows/ci.yml`) and the Dockerfile (`node:22-alpine`); root `engines.node` is `>=20`.

## Goals / Non-Goals

**Goals**

- Remove #418 at its source by moving to Next 16, and prove it with a repeatable stress check instead of a single green e2e run.
- Remove the e2e reload workaround.
- Keep every existing gate green: `make ci-static` (lint, typecheck, unit tests, Storybook, agent guides, OpenSpec, secrets), `make smoke`, `make e2e`.
- Keep runtime behaviour identical, including the admin access gate.

**Non-Goals**

- Adopting Next 16 features (Cache Components, React Compiler, View Transitions, `PageProps` helpers).
- Storybook 9/10, Tailwind 4, ESLint 10 or TypeScript 6+/7 upgrades.
- Replacing Tremor, or refactoring effects that the new `react-hooks` rules flag.

## Decisions

### D1. Target Next 16.4.5, not 16.4.3 or 16.4.6

The project rule is to pin versions at least two weeks old. Publish times from `npm view next time --json` on 2026-11-12:

| Version | Published | Age | Notes |
|---|---|---|---|
| 16.4.3 | 2026-10-23 | 20 days | Newest 16.x that is over two weeks old |
| 16.4.4 | 2026-11-02 | 10 days | Backports only |
| 16.4.5 | 2026-11-03 | 9 days | **Security release** (7 moderate advisories) |
| 15.5.29 | 2026-11-03 | 9 days | Our current version: 3 of those advisories, backported |
| 16.4.6 | 2026-11-09 | 3 days | `latest` tag; backports only |

16.4.3 passes the age rule but would be a **security regression**: it lacks GHSA-pc58-hwjq-p385, GHSA-7qx7-33qx-rqx2 and GHSA-f3mh-rxg3-f5g2, which 15.5.29 already fixes ([v16.4.5 release notes](https://github.com/vercel/next.js/releases/tag/v16.4.5), [v15.5.29 release notes](https://github.com/vercel/next.js/releases/tag/v15.5.29)). GHSA-pc58 ("cross-client response injection and disclosure in self-hosted Next.js applications forwarding fetched responses") matches our `/api/proxy/**` route handlers exactly. So the target is **16.4.5**, the first 16.x carrying every fix 15.5.29 has. It turns two weeks old on **2026-11-17**. **Owner decision (2026-11-12): take 16.4.5 now, as a recorded exception to the two-week rule for a security release.** We pin the exact version (`"next": "16.4.5"`, `"eslint-config-next": "16.4.5"`) rather than `^`, so Dependabot proposes each later patch as its own PR, which the stress check can gate (D3).

The trial ran on both 16.4.3 and 16.4.5. Results were identical.

### D2. React 19 in package.json; the App Router still uses Next's canary

Next 16.4.x vendors `react-dom` `19.3.0-canary-278794d7-20261002` for the App Router (checked in `node_modules/next/dist/compiled/react-dom`). The upgrade guide says the same thing: "The App Router in Next.js 16 uses the latest React Canary release" ([upgrade guide, "React 19.2"](https://nextjs.org/docs/app/guides/upgrading/version-16#react-192)). The `react`/`react-dom` we declare are used by vitest, Testing Library and Storybook. We move them to `^19.2.0` (`^19.2.0` resolved to 19.3.1, published 2026-10-14) and the types to `^19.2.0`. Keeping React 18 for tests while the app runs a 19 canary would test a different React from the one users get.

Peer checks (`npm view <pkg> peerDependencies`): `next-themes`, `sonner` 1.7, every `@radix-ui/*`, `lucide-react`, `@testing-library/react` 16, `react-force-graph-2d` and `@storybook/react-vite@8.6.19` (`^19.0.0-beta`) all accept React 19. Only `@tremor/react` objects (D5).

### D3. Verification: a committed stress script, not a Playwright project

The bug needs many concurrent browser *processes* hammering a *production* build for hundreds of loads. A Playwright project fits badly. Its workers share the e2e suite's `fullyParallel`/`workers` settings and global setup (fixture seeding, the overlay teardown). A test that loops 1,000+ loads makes the report useless. And putting it in `make e2e` would add several minutes to every run. So we commit the issue #2 probes as one script, `services/admin-ui/scripts/hydration-stress.cjs` (CommonJS like the probes, loads `@playwright/test` from the admin UI package), with a `make hydration-stress` target. Inputs (env, with defaults): `BASE_URL` (default: the same admin URL the e2e suite uses, `http://127.0.0.1:${OPENCG__ADMIN_UI__HOST_PORT:-3000}`), `BROWSERS` (7), `CYCLES` (30).

Per browser, per cycle, over every route (`/`, `/queries`, `/queries/<id>`, `/vectors`, `/entities`, `/entities/<id>`, `/ingestion`, `/graph`; the two detail ids are taken from the first row of `/queries` and `/entities` at start-up):

1. Full load, wait for `networkidle`. Record any `pageerror` or `console.error` (#418 separately, others as "other console errors").
2. Check that `main h1` exists and has a `__reactFiber$*` key (hydrated), as in probe12.
3. Click a sidebar link to a different page and wait up to 5 s for the URL to change ("stuck sidebar navigation", probe12).
4. Once per cycle per browser, on `/queries`, click the first row link and wait up to 5 s for `/queries/<id>` (probe16, "stuck row navigation").

It prints a JSON summary and exits non-zero if any counter is above zero. Defaults give 7 × 30 × 8 = **1,680 loads**. At the 15.5 baseline (7.7% on `/entities`; the e2e comment estimates ~1% on any route), the chance of zero hits by luck is below 10⁻⁷ even at 1% per load (0.99¹⁶⁸⁰ ≈ 5 × 10⁻⁸). It also needs a seeded stack, so it runs after `make smoke` or `make e2e` has populated data. The script fails clearly if `/queries` or `/entities` has no rows.

**Nightly in CI (owner decision, 2026-11-12).** The full 1,680 loads take several minutes, so CI runs a smaller pass, `BROWSERS=4 CYCLES=10` (320 loads), as a step of the `stack` job that runs **only on the nightly schedule**, after `make e2e` has seeded data. A shared GitHub runner's CPU profile differs from the machine that reproduced the bug, so a green nightly is a regression guard, not proof; the full run stays a required manual step for any Next or React version bump. The step uploads the JSON summary as an artifact.

### D4. ESLint: native flat config; inline disables for the new hooks rule

`eslint-config-next@16` exports flat configs (`eslint-config-next/core-web-vitals`, `eslint-config-next/typescript`), and `FlatCompat.extends("next/core-web-vitals")` crashes on them ("Converting circular structure to JSON", seen in the trial). The upgrade guide confirms flat config is the default ([upgrade guide, "ESLint Flat Config"](https://nextjs.org/docs/app/guides/upgrading/version-16#eslint-flat-config)). The new config spreads the two exports after the existing `ignores` block, and `@eslint/eslintrc` leaves `devDependencies`.

`eslint-config-next@16` brings `eslint-plugin-react-hooks@7`. Its `react-hooks/set-state-in-effect` rule fails 4 existing lines:

- `src/app/graph/GraphExplorer.tsx:110`, `:127`: loading/reset state set at the start of a fetch effect.
- `src/components/ConceptSearch.tsx:17`: clears results when the query becomes empty.
- `src/components/ThemeToggle.tsx:13`: the `mounted` flag that `next-themes` documents for avoiding a theme hydration mismatch.

Rewriting these (for example `useSyncExternalStore` for `mounted`, or moving the resets into event handlers) changes rendering behaviour, and that is the one thing this change must not do while we measure hydration. So each gets an `// eslint-disable-next-line react-hooks/set-state-in-effect -- <reason>` comment. The rule stays on for new code. The trial confirmed these 4 are the only lint failures. Alternative rejected: turning the rule off globally.

### D5. Keep Tremor 3.18.7 with an explicit peer allowance

`@tremor/react@3.18.7` declares `react: ^18.0.0` and pins `@headlessui/react@2.2.0`, `react-day-picker@8`, `recharts@2`. Its last publish was 2025-01-13. It is used in `src/app/page.tsx` and `src/components/StatCard.tsx` (plus a story). In the trial, pnpm only warns (`unmet peer react@^18.0.0: found 19.3.1`), and `next build` and `build-storybook` succeed. We add `pnpm.peerDependencyRules.allowedVersions: { "@tremor/react>react": "19", "@tremor/react>react-dom": "19" }` to the root `package.json` so the warning is a recorded decision, not noise. The e2e overview test and a manual look at the `/` dashboard in both themes confirm it renders. Owner decision (2026-11-12): keep Tremor; no replacement change is planned until it actually breaks.

### D6. `middleware.ts` → `proxy.ts`

Next 16 deprecates the `middleware` file and export names in favour of `proxy`, and `proxy` always runs on the Node.js runtime ([upgrade guide, "middleware to proxy"](https://nextjs.org/docs/app/guides/upgrading/version-16#middleware-to-proxy)). Our middleware sets no `runtime`, so on 15.5 it ran on Edge. `src/lib/session.ts` uses Web Crypto only, which Node 22 provides globally, so the move is safe. `npx @next/codemod@16.4.5 middleware-to-proxy .` renames the file and function but **not** `middleware.test.ts`. We rename that test and its import/calls by hand. The `x-middleware-next` header assertions still pass (89/89 in the trial). The `config.matcher` is unchanged. The comment in `session.ts` ("runs in both the middleware (edge) and Node") is updated.

### D7. Commit the files `next build` rewrites

On first build, Next 16 rewrote `tsconfig.json` (`"jsx": "preserve"` → `"react-jsx"`, added `.next/dev/types/**/*.ts` to `include`, reflowed arrays) and `next-env.d.ts` (`/// <reference path>` → `import "./.next/types/routes.d.ts"` and `import "./.next/types/root-params.d.ts"`). Both files are tracked. If we don't commit the rewritten forms, every build dirties the tree, which breaks the "Clean-checkout build" requirement. The MODIFIED requirement makes this explicit.

### D8. What else in the upgrade guide we checked, and why it doesn't apply

From the [Next 16 upgrade guide](https://nextjs.org/docs/app/guides/upgrading/version-16) (last updated 2026-11-06):

- **Node ≥ 20.9.0, TypeScript ≥ 5.1.0**: CI and Docker use Node 22; TypeScript is `^5.6.0` (resolves to 5.9.3). Root `engines.node` becomes `>=20.9.0`.
- **Async request APIs** (sync access removed): every `params`/`searchParams` in `src/app` is already typed as a `Promise` and awaited (`graph/page.tsx`, `entities/page.tsx`, `login/page.tsx`, `queries/[id]/page.tsx`, `api/proxy/entities/[id]/route.ts`, `api/proxy/graph/[...path]/route.ts`). No `cookies()`, `headers()` or `draftMode()` calls exist.
- **Turbopack default for `next build`**: `next.config.mjs` has no `webpack` key, and no plugin adds one; the trial built with Turbopack in about 7 s. Storybook builds with Vite and is unaffected.
- **`next lint` removed**: the `lint` script is already `eslint .` (archived change `prepare-open-source-release`, D2b); `make ci-static` and CI call `pnpm -r lint`.
- **`next/image` defaults, `images.domains`**: no `next/image` usage, no `images` config.
- **Removed config** (`serverRuntimeConfig`, `publicRuntimeConfig`, `experimental.ppr`, `dynamicIO`, AMP, `devIndicators` options): none used.
- **Parallel routes need `default.js`**: no `@slot` directories.
- **`revalidateTag` signature, `scroll-behavior` override, `.next/dev` dev output**: not used / no smooth scroll / `.next` is already gitignored.
- **Standalone output**: the trial's `.next/standalone/services/admin-ui/server.js` has the same layout the Dockerfile copies.

## Trial upgrade (2026-11-12)

A copy of the workspace (root manifests, `packages/shared`, `services/admin-ui`) went into the session scratchpad, which was the only place anything was installed or built. The steps:

1. Next 16.4.3, then 16.4.5; React and types `^19.2.0`; `eslint-config-next` matched.
2. `pnpm install`: one peer warning (Tremor, D5).
3. `pnpm typecheck`: **pass**, no source changes.
4. `pnpm test` (vitest): **89/89 pass**, before and after the proxy rename.
5. `pnpm lint`: **crash** with `FlatCompat`; after D4's config, **4 errors** (`set-state-in-effect`), all listed in D4.
6. `pnpm build`: **pass** (Turbopack), with the `middleware` deprecation warning until D6, and the `tsconfig.json`/`next-env.d.ts` rewrite (D7).
7. `pnpm build-storybook`: **pass** on Storybook 8.6.19.
8. Stress runs. Both builds ran under `next start` on spare ports against the live compose pipeline (read-only GETs; the stack was not changed), with the probe scripts from the issue #2 investigation, 7 browsers, interleaved so that machine load hit both versions equally:

| Build | Probe | Loads | #418 |
|---|---|---|---|
| 15.5.29 (local `next start`) | probe8 `/entities`, 4 runs | 560 | **43 (7.7%)** |
| 15.5.29 (compose container, port 3300) | probe8 `/entities` | 140 | 13 (9.3%) |
| 16.4.3 | probe8 `/entities`, 3 runs | 420 | **0** |
| 16.4.3 | probe8, 6 list routes × 15 cycles | 630 | **0** |
| 16.4.5 | probe8 `/entities` | 140 | **0** |
| 16.4.5 | probe8, 6 list routes × 15 cycles | 630 | **0** |
| 16.4.3 and 16.4.5 | probe12 (`/entities` → sidebar click) | 105 each | 0 #418, 0 unhydrated `h1`, **0 stuck** |
| 16.4.3 and 16.4.5 | probe16 (`/queries` row click) | 5 each | **0 stuck** |

Not covered by the trial: `make e2e` (it needs the compose image rebuilt, which this proposal must not do), the detail routes under stress, and a visual check of Tremor charts and the graph map. Those are tasks in phase 4.

We did not find the exact upstream commit that fixes the bug. Next 16 changed both the client router ("complete overhaul of the routing and navigation system") and the React canary, so we cannot say which change fixed it. The acceptance bar is therefore empirical (D3), and the stress check stays in the repo so a regression in a later Next patch is detectable.

## Fallback if Next 16 does not remove #418

If the stress check at implementation time shows any #418 on 16.4.5 (or the version Q1 settles on):

1. **Retry the two app-side fixes on 16.** The router rewrite may have fixed the stuck-transition bug that ruled them out. Re-test the root `<Suspense>` and `app/loading.tsx` variants with the stress script (which also counts stuck navigations) and with `make e2e` ×3. Adopt the first variant that scores zero on every counter.
2. **If neither works**, ship the upgrade anyway (it is no worse than 15.5, and it keeps us on a supported line with the security fixes). Keep the e2e reload workaround with a comment pointing at the upstream issue, and leave issue #2 open.
3. **File an upstream issue** on `vercel/next.js` with a minimal reproduction: a two-route App Router app whose page awaits a slow fetch with no Suspense boundary, plus the stress script. Before posting, the owner reviews the issue text, since it is public.

The spec deltas below describe the success path. If the fallback is taken, this change is amended (a new scenario allowing the documented workaround) before archive, not silently.

## Risks / Trade-offs

- **Shipping a release under two weeks old** (16.4.5) → owner-approved exception: it is a security release on the active LTS line, and we pin it exactly.
- **Tremor under React 19** has no upstream support → the build and the e2e overview check cover the components we use; the owner chose to keep it until it breaks.
- **The proxy now runs on Node instead of Edge** → the gate is a few lines of cookie/HMAC logic with unit tests and e2e auth tests (`e2e/auth.spec.ts`).
- **The stress check is machine-dependent**: a fast machine may never reproduce a regression → it was reproducible on the owner's machine at 7.7–9.3%, and the script's browser count and cycles are configurable.
- **Lint disables hide real smells** → each has a reason, the rule stays on, and refactoring is a follow-up.

## Resolved Decisions (owner, 2026-11-12)

- **Q1. Version.** Ship Next 16.4.5 now as a recorded security-release exception to the two-week rule (D1).
- **Q2. Stress in CI.** Run a smaller stress pass (4 browsers × 10 cycles) nightly in the `stack` job (D3).
- **Q3. Tremor.** Keep it (D5).
- **Q4. Issue #2 comment.** The owner approves the exact text before it is posted (task 6.3).
