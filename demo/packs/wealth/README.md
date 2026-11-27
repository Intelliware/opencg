# Wealth demo pack (Juniper Bay Wealth)

Owner: openCG maintainers

Juniper Bay Financial Group is fictional. Its people, figures and documents are illustrative and are not legal or regulatory guidance.

## What this pack shows

Juniper Bay Wealth is the wealth-management subsidiary of the fictional Juniper Bay Financial Group. The pack has ten documents in three tiers. Public documents are visible to everyone. Internal documents are visible to staff. Confidential documents carry the classification `confidential:wealth` and are visible only to the `demo-advisor` persona.

The point is the **split answer**. An internal procedure gives the process and names a confidential document for the specifics. A reader without wealth entitlement gets the process and learns that specifics exist. The advisor persona gets the numbers as well.

## Documents

Public (`public/`)
- `managed-portfolio-family-overview.md`
- `fee-schedule.md`
- `client-onboarding-guide.md`

Internal (`internal/`)
- `kyc-refresh-procedure.md`
- `suitability-review-procedure.md`
- `model-portfolio-rebalancing-runbook.md`
- `wealth-complaints-handling.md`

Confidential (`confidential/`)
- `suitability-exception-register-policy.md`
- `high-net-worth-client-segmentation-thresholds.md`
- `advisor-compensation-grid.md`

The internal documents also reference the shared group documents *Juniper Bay Group AML/ATF Programme Summary*, *Juniper Bay Group Complaint-Handling Standard* and *Juniper Bay Group Data Classification Standard* (see `demo/packs/group/`).

## How the questions work

`questions.json` lists scripted questions. Each names the `internal` document, the `confidential` document, what `demo-advisor` should see and what a reader without `confidential:wealth` should see. Ask each question twice, once as `demo-reader` and once as `demo-advisor`, and compare.

## Public questions (same answer for everyone)

- What is the annual advisory fee on a 500,000 dollar account?
- Which managed portfolios does Juniper Bay Wealth offer, and what are their risk profiles?
- What do I need to bring to open an account?

## Cross-pack question

- How does a wealth complaint relate to the group complaint standard? (The *Wealth Complaints Handling* document applies the *Juniper Bay Group Complaint-Handling Standard*, so both are retrieved.)
