## 1. Pre-flight (before any code change)

- [x] 1.1 Owner resolves Q1: 16.4.5 now, as a security-release exception (2026-11-12). Re-run `npm view next time --json` and the release notes. If a newer 16.4.x security release has appeared, re-check its age and advisories and update design.md D1.
- [ ] 1.2 Branch `upgrade-admin-ui-next-16` (stacked on `add-observability-stack` until PR #4 merges, then rebased onto `main`).
- [ ] 1.3 Record a baseline on the current 15.5.29 stack: run the stress script from task 2.1 (it works against 15.5 too) with defaults and save the JSON summary. Expect #418 > 0. This is the "before" number for the PR and issue #2.

## 2. Stress check (lands first, so it can measure both versions)

- [ ] 2.1 Add `services/admin-ui/scripts/hydration-stress.cjs` per design.md D3: env `BASE_URL` (default from `OPENCG__ADMIN_UI__HOST_PORT`, as in `e2e/env.ts`), `BROWSERS` (7), `CYCLES` (30); 8 routes with detail ids taken from `/queries` and `/entities`; counters for #418, other console errors, unhydrated `main h1`, stuck sidebar navigation and stuck row navigation; JSON summary; non-zero exit on any count > 0 or on missing seed data.
- [ ] 2.2 Add a `make hydration-stress` target (in `.PHONY` and `make help`) that runs the script with `node`, and pass through `BROWSERS`/`CYCLES`.
- [ ] 2.4 CI: in the `stack` job, a step that runs only on the nightly schedule, after `make e2e`: `make hydration-stress BROWSERS=4 CYCLES=10`, uploading the JSON summary as an artifact (always).
- [ ] 2.3 Document the target in `docs/OPERATIONS.md` next to `make e2e` (what it checks, how long it takes, when to run it: any Next/React bump).

## 3. Upgrade

- [ ] 3.1 `services/admin-ui/package.json`: `next` and `eslint-config-next` to the exact version from 1.1; `react`, `react-dom`, `@types/react`, `@types/react-dom` to `^19.2.0`; drop `@eslint/eslintrc`.
- [ ] 3.2 Root `package.json`: `engines.node` → `>=20.9.0`; add `pnpm.peerDependencyRules.allowedVersions` for `@tremor/react>react` and `@tremor/react>react-dom` → `19` (design.md D5).
- [ ] 3.3 `pnpm install` and commit `pnpm-lock.yaml`. Confirm pnpm reports no unmet peers.
- [ ] 3.4 Rewrite `eslint.config.mjs` to spread `eslint-config-next/core-web-vitals` and `eslint-config-next/typescript` (native flat config), keeping the `ignores` block and updating the header comment.
- [ ] 3.5 Add `// eslint-disable-next-line react-hooks/set-state-in-effect -- <reason>` at `GraphExplorer.tsx` (2 sites), `ConceptSearch.tsx` and `ThemeToggle.tsx`. Each reason says why the effect is intentional. Run `pnpm --filter @opencg/admin-ui lint` and confirm 0 problems.
- [ ] 3.6 Run `npx @next/codemod@<version> middleware-to-proxy .` in `services/admin-ui` (or rename by hand). Rename `src/middleware.test.ts` → `src/proxy.test.ts` and update its import, calls and `describe` title. Update the Web Crypto comment in `src/lib/session.ts` (no longer "edge").
- [ ] 3.7 Run `pnpm --filter @opencg/admin-ui build` once and commit the rewritten `tsconfig.json` and `next-env.d.ts`. Run it again and confirm `git status --porcelain` is clean.
- [ ] 3.8 Grep for anything design.md D8 says is absent (`next/image`, `cookies(`, `headers(`, `revalidateTag`, `experimental`, `@`-slot directories, `next lint`). Fix any new hit.

## 4. Verify

- [ ] 4.1 `make ci-static` green (lint, typecheck, unit tests, Storybook build, agent guides, OpenSpec, secrets scan).
- [ ] 4.2 Rebuild the admin UI image and bring the stack up (`make up-d`). `make smoke` green.
- [ ] 4.3 `make hydration-stress` with defaults against the rebuilt stack: zero on every counter. Save the JSON summary for the PR.
- [ ] 4.4 Remove the #418 reload workaround in `e2e/navigation.spec.ts` (the `flaky-hydration` annotation, the reload, and the issue #2 comment). A hydration error now fails the test.
- [ ] 4.5 `make e2e` green **3 consecutive runs** with the workaround removed.
- [ ] 4.6 Manual check in both themes: `/` (Tremor stat and breakdown cards), `/graph` map, theme toggle, toasts, a dialog and a select. With `OPENCG__ADMIN_UI__PASSWORD` set: the login redirect and a 401 from `/api/proxy/**`.
- [ ] 4.7 If 4.3 or 4.5 shows any #418, follow the fallback in design.md ("Fallback if Next 16 does not remove #418"). Amend this change's spec delta and tasks before continuing, and stop to show the owner.

## 5. Docs

- [ ] 5.1 AGENTS.md: stack table "Next.js 15 App Router" → "Next.js 16 App Router (React 19)"; "Where stuff lives" line for `services/admin-ui/`; the Storybook gotcha (keep the `@storybook/react-vite` rule, reword "Next 15.5"); add a gotcha that `next build` rewrites `tsconfig.json`/`next-env.d.ts`, so commit those when Next is bumped; mention `make hydration-stress`. Copy the body verbatim to `CLAUDE.md` and `.cursor/rules/opencg.mdc`. `make check-agent-guides` passes.
- [ ] 5.2 README stack table: "Next.js 15 (App Router)" → "Next.js 16 (App Router)"; the Node prerequisite, if stated, → 20.9+.
- [ ] 5.3 CHANGELOG `[Unreleased]`: under Changed, "Admin UI on Next.js 16 and React 19 (`upgrade-admin-ui-next-16`)"; under Fixed, "Intermittent React hydration error #418 in the admin UI (#2)"; note the Node 20.9 minimum for contributors.

## 6. Land

- [ ] 6.1 `openspec validate upgrade-admin-ui-next-16 --strict` passes.
- [ ] 6.2 Secret check before pushing (`git diff --cached | grep -iE "bearer [a-zA-Z0-9]{20,}|sk-[a-zA-Z0-9]{20,}"`). Commit, push, open a PR to `main` with the before/after stress summaries; `static`, `stack` and `dependency-review` green; one approving review.
- [ ] 6.3 Draft the closing comment for issue #2 (root cause, before/after numbers, link to the PR and this change). **The owner approves the text before it is posted.** Close the issue when the PR merges.
- [ ] 6.4 After merge, `openspec archive upgrade-admin-ui-next-16`.
- [x] 6.5 Owner decided Q2 (nightly stress run, task 2.4) and Q3 (keep Tremor) on 2026-11-12.
