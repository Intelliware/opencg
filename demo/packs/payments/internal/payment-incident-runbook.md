# Payment Incident Runbook

Owner: Head of Payments Operations
Applies to: Juniper Bay Payments
Classification: Internal
Version: 3.4
Effective: 2026-05-01

This runbook describes how Juniper Bay Payments detects, classifies and resolves incidents that disrupt payment processing across wires, EFT, Lynx and the Real-Time Rail. It applies to Operations, Technology and Client Support staff.

## What counts as an incident

An incident is any event that delays, blocks, duplicates or corrupts payments, or exposes payment data. Examples: a Real-Time Rail connection outage, a failed EFT batch, a screening engine failure, or a suspected fraud attack.

## Severity levels

| Level | Meaning |
|---|---|
| Severity 1 | Payments stopped or at risk of loss, many clients affected |
| Severity 2 | Degraded service, workaround available |
| Severity 3 | Minor issue, no client impact |

The incident commander assigns the level and can raise it at any time.

## Roles

- **Incident commander:** a shift lead or on-call manager, owns decisions.
- **Technical lead:** diagnoses the fault.
- **Communications lead:** informs clients and executives.
- **Scribe:** records the timeline.

## Response steps

1. **Detect.** Monitoring alerts or a staff report starts an incident ticket.
2. **Declare.** The incident commander sets the severity and opens the bridge line.
3. **Contain.** Stop the faulty flow if continuing would cause harm. Switch to wire transfers if real-time payments are down.
4. **Communicate.** The communications lead posts status updates at the intervals in the table below.
5. **Resolve.** The technical lead restores service and confirms with test payments.
6. **Reconcile.** Operations reconciles every payment that was in flight.
7. **Review.** A post-incident review is held within 5 business days.

| Severity | Status update interval |
|---|---|
| 1 | Every 30 minutes |
| 2 | Every 2 hours |
| 3 | Daily |

## Held and stuck payments during an incident

When payments are held because of an incident, a person must approve their release. The approval authority depends on the payment value and is set out in the *High-Value Payment Approval Limits* (Confidential). This runbook does not repeat the limits. If the approver is unavailable, follow the delegation rules in that document instead of improvising.

## Fraud-related incidents

If an incident looks like an attack, for example a burst of unusual payments, notify Fraud Operations. The fraud team applies the controls in the *Payments Fraud Detection Rules and Thresholds* (Confidential), including temporary velocity limits. Do not release suspect payments to meet a cut-off.

## Sanctions-related incidents

If screening is down, payments must not be released without screening. Hold them in the queue and follow the *Sanctions Alert Triage Procedure* once service returns.

## Regulatory and client notification

Material incidents may require notification to OSFI or Payments Canada. The communications lead consults Compliance before any external notification. Client complaints about an incident follow the *Juniper Bay Group Complaint-Handling Standard*.

## Post-incident review

The review records the cause, impact, timeline, what worked, what did not, and follow-up actions with owners and dates. Reviews are blameless and are filed in the incident register.
