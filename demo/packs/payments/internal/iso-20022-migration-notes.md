# ISO 20022 Migration Notes

Owner: Head of Payments Technology
Applies to: Juniper Bay Payments
Classification: Internal
Version: 1.6
Effective: 2026-02-01

These notes describe how Juniper Bay Payments is moving its wire, Lynx and real-time payment flows to the ISO 20022 messaging standard. They are working notes for engineers, analysts and support staff, not a client communication. They depend on the Payments Canada rollout of ISO 20022 for Lynx and the Real-Time Rail (RTR).

## Why migrate

ISO 20022 carries richer, structured data than legacy formats. Benefits for Juniper Bay Payments include better sanctions matching, fewer repair items and automatic invoice matching for clients. The Real-Time Rail uses ISO 20022 natively, so any real-time payment already depends on it. See the *Juniper Bay Payments Real-Time Rail Service Guide* for the client view.

## Scope

| Flow | Status |
|---|---|
| Real-Time Rail | Live, native ISO 20022 |
| Lynx high-value payments | Live, native |
| Outgoing international wires | Translating at the edge until the correspondent network completes migration |
| Domestic EFT files | Not in scope, legacy format retained |

## Translation approach

Where a counterparty still uses a legacy format, an adapter translates in both directions. Translation can lose data:

- Structured addresses are collapsed into unstructured lines.
- Long remittance information is truncated.
- Party identifiers may be dropped.

Every truncation is logged and the item may enter the repair queue; see the *Wire Repair and Returns Runbook*.

## Data fields analysts need to know

- **End-to-end identifier:** stays the same across the whole payment chain. Use it for matching returns.
- **Unique transaction reference:** assigned by Juniper Bay Payments.
- **Purpose code:** needed on some international payments.
- **Structured remittance:** used by clients to reconcile invoices.

## Interaction with screening

Richer party data gives the screening engine more attributes to compare, and fewer false positives. Match-score tuning is owned by the Compliance Systems team and is not described here; the *Sanctions Alert Triage Procedure* explains how alerts are worked.

## Testing

Each release is tested with a standard set of 200 sample messages covering valid, invalid and edge-case payments. Regression results are kept for 12 months. The Head of Payments Technology signs off each release.

## Known issues

1. Some correspondent banks reject structured addresses and cause returns.
2. Free-text remittance over 140 characters is truncated on legacy flows.
3. Reporting dashboards still group payments by legacy message type.

## Open items

- Retire the edge adapter once the correspondent network completes migration.
- Update the client portal to show structured remittance data.
- Agree retention rules for the richer data with the Privacy Office, following the *Juniper Bay Group Data Classification Standard*.

## Contacts

Questions go to the Payments Technology team through the engineering queue. Incidents follow the *Payment Incident Runbook*.
