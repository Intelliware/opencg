# Payments demo pack

Owner: openCG maintainers

Juniper Bay Financial Group is fictional. Its people, figures and documents are illustrative and are not legal or regulatory guidance.

This pack shows openCG serving **Juniper Bay Payments** documents (wire, EFT, real-time payments, fraud and sanctions) with role-based access. Documents are split into three classifications. Public and internal documents are visible to every demo reader. Confidential documents carry the classification `confidential:payments` and are visible only to the persona `demo-payments-ops`.

## Documents

| Folder | Document |
|---|---|
| public | `wire-and-eft-fees-and-cut-off-times.md` |
| public | `real-time-rail-service-guide.md` |
| internal | `wire-repair-and-returns-runbook.md` |
| internal | `iso-20022-migration-notes.md` |
| internal | `payment-incident-runbook.md` |
| internal | `sanctions-alert-triage-procedure.md` |
| confidential | `fraud-detection-rules-and-thresholds.md` |
| confidential | `sanctions-screening-tuning.md` |
| confidential | `high-value-payment-approval-limits.md` |

The documents refer to one another by exact title, so the knowledge graph shows relationships such as references and dependencies. The group documents under `demo/packs/group/internal/` are shared with every pack.

## How the questions work

`questions.json` lists split-answer questions. In each, an internal document explains the procedure and names a confidential document for the specifics. The persona `demo-payments-ops` gets a full answer with the figures. A reader without the confidential classification gets the procedure only, and the answer says the specifics are restricted. Each entry gives the internal and confidential files, and what each viewer sees.

## Public questions

Any user sees the same answer to these:

- What are the wire cut-off times?
- What is the fee for an outgoing international wire?
- What is the per-payment limit for a real-time payment?

## Cross-pack question

*What is the process for handling a client complaint about a held payment?* This draws on the *Juniper Bay Group Complaint-Handling Standard* (group) and the *Juniper Bay Payments Wire and EFT Fees and Cut-off Times* (payments).
