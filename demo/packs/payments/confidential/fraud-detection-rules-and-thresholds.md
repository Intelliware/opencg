# Payments Fraud Detection Rules and Thresholds

Owner: Head of Fraud Operations
Applies to: Juniper Bay Payments
Classification: Confidential (confidential:payments)
Version: 5.0
Effective: 2026-07-01

This document sets the rules and thresholds that route payments to fraud review at Juniper Bay Payments. It supplies the specifics that the *Wire Repair and Returns Runbook* and the *Payment Incident Runbook* defer to. All figures are fictional and deliberately round. Do not share this document outside the Payments and Fraud teams, because publishing thresholds helps fraudsters stay under them. See the *Juniper Bay Group Data Classification Standard*.

## Outgoing wire manual review threshold

Every outgoing wire of **CAD 50,000 or more** is held for manual fraud review before release. This is the outgoing wire manual review threshold.

- Two approvers are required for a manual review of a wire at or above CAD 50,000: one Fraud Operations analyst and one Payments Operations shift lead.
- Wires of CAD 250,000 or more also need the Head of Fraud Operations to confirm the review, in addition to the approvers above.
- International wires to a destination in the high-risk country list are held for manual review at **CAD 10,000 or more**.

## Wire trigger rules

A wire is also routed to manual review, whatever its amount, if any of these apply:

1. The beneficiary account was added less than 24 hours earlier and the wire is CAD 20,000 or more.
2. The client changed contact details in the last 48 hours.
3. The wire is the first to a new beneficiary country for that client.
4. The instruction arrived through an unusual channel for the client.
5. The beneficiary name does not match the name on the confirmation of payee check.

## Velocity limits

| Rule | Threshold | Action |
|---|---|---|
| Outgoing payments per client per hour | 10 or more | Hold, review |
| Outgoing value per client per day | CAD 500,000 | Hold, review |
| Failed authentication attempts | 3 in 15 minutes | Lock access, call client |
| Same beneficiary, repeated payments | 5 in 1 hour | Hold, review |

## Real-time payment rules

- Real-time payments of CAD 10,000 or more to a new beneficiary require step-up authentication.
- Real-time payments above CAD 25,000 are declined for standard clients, which matches the public limit in the *Juniper Bay Payments Real-Time Rail Service Guide*.
- A risk score of 80 or more out of 100 holds the payment for review.

## Risk score bands

| Score | Action |
|---|---|
| 0 to 49 | Release |
| 50 to 79 | Release and sample for post-payment review |
| 80 to 100 | Hold for manual review |

## Review decision times

Fraud Operations aims to decide each held wire within 60 minutes of it entering the queue during business hours. If a decision cannot be made before the cut-off, the wire is released on the next business day, not forced through.

## Contacting the client

Fraud Operations calls the client on a number held on file, never a number given in the instruction. The standard call script confirms the amount, the beneficiary and the purpose, and does not disclose the rule that triggered the hold.

## Rule governance

Thresholds are reviewed every quarter by the Fraud Rules Committee and may be changed only with the approval of the Head of Fraud Operations and the Chief Risk Officer. Each change is logged with the reason and the observed false-positive rate. Target false-positive rate for wire review is 20 percent or less.

## Related documents

- *High-Value Payment Approval Limits* for who approves release of reviewed payments.
- *Sanctions Screening Tuning* for screening, which is separate from fraud review.
