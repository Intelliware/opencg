# Juniper Bay Group Data Classification Standard

Owner: Chief Information Security Officer
Applies to: Juniper Bay Financial Group (Wealth, Payments, Bank)
Classification: Internal
Version: 1.4, Effective: 2026-01-01

## Purpose

This standard defines how documents and data at Juniper Bay Financial Group are classified and handled. Every document has exactly one classification. If the owner has not set one, treat it as Internal until the owner confirms. It is illustrative and is not legal or regulatory guidance.

## Classification levels

### Public

Approved for anyone, including people outside the group. Examples: product brochures, published fee schedules, general guidance on how to contact us. Public documents are approved by Marketing and the document owner before release.

### Internal

For all Juniper Bay staff and approved contractors. Not for release outside the group. Examples: procedures, runbooks, group standards such as the *Juniper Bay Group AML/ATF Programme Summary* and the *Juniper Bay Group Complaint-Handling Standard*. Internal documents are visible to every signed-in staff member regardless of line of business.

### Confidential

Restricted to one line of business, because exposure could cause financial loss, help fraud or evasion of controls, or breach client privacy. Confidential documents are labelled with the line of business that owns them:

- `confidential:wealth` for Juniper Bay Wealth
- `confidential:payments` for Juniper Bay Payments
- `confidential:retail` for Juniper Bay Bank retail banking

A person may read a Confidential document only if their role grants that line of business. A wealth advisor can read `confidential:wealth` documents but not `confidential:payments` or `confidential:retail`. Examples: fraud detection rules and thresholds, credit score cut-offs, advisor compensation grids, client records.

Confidentiality does not stop a related Internal document from describing the process. An Internal procedure may say that thresholds exist, who owns them and where they are set out, but must not repeat the figures. It names the Confidential document by title instead.

## Handling rules

| Rule | Public | Internal | Confidential |
|---|---|---|---|
| Who may read | Anyone | All staff | Staff holding the line-of-business role |
| Share outside the group | Allowed | Not allowed without approval | Not allowed |
| Store in approved systems only | Yes | Yes | Yes |
| Email to personal accounts | Allowed | Not allowed | Not allowed |
| Printing | Allowed | Allowed, shred after use | Avoid; shred after use |
| Access review | None | Annual | Every 6 months |
| Retention of access logs | 1 year | 2 years | 7 years |

Client personal information is Confidential regardless of where it appears. Never copy client details into Public or Internal documents. In examples, use "Client A" instead of names.

## Labelling and changes

The document owner sets the classification when a document is created and records it in the metadata block as `Classification:`. Downgrading a document needs approval from the owner and the Chief Information Security Officer. Upgrading may be done by the owner at any time.

## AI assistants

AI assistants connected to the group's knowledge catalogue only see what the person's role allows. An assistant answers from Public and Internal documents for every signed-in user, and from a Confidential document only when the user holds the matching line-of-business role. The assistant must not infer, estimate or reconstruct restricted figures it cannot see. If an answer depends on a restricted document the user cannot access, the assistant says that restricted detail exists and names the owning team. Every request is logged.

## Incidents

Suspected exposure of Confidential data is reported to the Security Operations Centre at once. The Chief Information Security Officer decides whether the matter is also a privacy breach, which follows the *Juniper Bay Group Complaint-Handling Standard* where clients are affected.

## Related documents

- *Juniper Bay Group AML/ATF Programme Summary*: AML records are Confidential to the line of business concerned.
- *Juniper Bay Group Complaint-Handling Standard*: complaint records are Confidential to the line of business concerned.
