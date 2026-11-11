## What and why

<!-- One or two sentences. Link the issue if there is one. -->

## OpenSpec change

<!-- The change this implements, for example openspec/changes/<name>/ and the task numbers, or "none: no requirement or scenario changes" for a tiny fix. -->

## Checklist

- [ ] The OpenSpec change exists, passes `openspec validate <name> --strict`, and was agreed before implementation (or this is a tiny fix that changes no requirement)
- [ ] The change's `tasks.md` is updated, including anything discovered during implementation
- [ ] Unit tests added or updated; `make ci-static` passes
- [ ] `make smoke` passes against a live stack
- [ ] `make e2e` passes, and new admin UI behaviour has an e2e test
- [ ] New shared admin UI components have a `*.stories.tsx` neighbour
- [ ] Docs updated (README, `docs/OPERATIONS.md`, `.env.example`) where behaviour or configuration changed
- [ ] No secrets, `.env` files or real credentials in the diff
- [ ] If the change is complete, it is archived (`openspec archive <name>`) here or in a follow-up
