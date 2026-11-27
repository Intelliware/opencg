# High-Value Payment Approval Limits

Owner: Chief Operating Officer, Juniper Bay Payments
Applies to: Juniper Bay Payments
Classification: Confidential (confidential:payments)
Version: 2.3
Effective: 2026-05-15

This document sets who must approve the release of a high-value payment at Juniper Bay Payments, by value. It supplies the specifics that the *Wire Repair and Returns Runbook* and the *Payment Incident Runbook* defer to. All figures are fictional. Do not share this document outside Payments leadership and Operations. See the *Juniper Bay Group Data Classification Standard*.

## Approval limits by payment value

These limits apply to the release of any outgoing wire, Lynx payment or real-time payment, and to the release of any payment held during an incident.

| Payment value (CAD) | Required approvers |
|---|---|
| Under 50,000 | One Payments Operations analyst |
| 50,000 to 249,999 | Two approvers: a Payments Operations shift lead and a second analyst or shift lead |
| 250,000 to 999,999 | Two approvers plus the Head of Payments Operations |
| 1,000,000 to 4,999,999 | Head of Payments Operations and the Chief Operating Officer |
| 5,000,000 or more | Chief Operating Officer and the Chief Financial Officer, with the Chief Risk Officer informed |

A payment above CAD 250,000 must be approved by the Head of Payments Operations. A payment above CAD 1,000,000 must be approved by the Chief Operating Officer. Payments of CAD 5,000,000 or more need the Chief Financial Officer as well.

## Four-eyes rule

The person who creates or repairs a payment can never approve its release. Approvers must be different people with separate credentials, and an approver cannot approve using a delegate's login.

## Delegation

| Role | Delegate when absent |
|---|---|
| Head of Payments Operations | Senior Manager, Payments Operations |
| Chief Operating Officer | Chief Risk Officer |
| Chief Financial Officer | Deputy Chief Financial Officer |

Delegation must be recorded in the approval log before the approval is given. A delegate has the same limit as the person they cover, except that no one may delegate approval of payments of CAD 5,000,000 or more below the Chief Risk Officer.

## Payments held during an incident

During a Severity 1 incident, the incident commander may authorise the release of held payments up to CAD 250,000 after the approvals above. Larger payments follow the table in full. Approvals are not relaxed for speed.

## Interaction with fraud and sanctions controls

Approval is required in addition to fraud review and sanctions clearance, not instead of it. See the *Payments Fraud Detection Rules and Thresholds* and the *Sanctions Screening Tuning*. A payment on hold for sanctions can never be approved for release under this document.

## Evidence

Each approval is recorded with the approver's role, time and payment reference. Records are kept for 7 years and are available to internal audit.

## Review

The limits are reviewed each year by the Chief Operating Officer and the Chief Risk Officer, and the review is reported to the Juniper Bay Payments board.
