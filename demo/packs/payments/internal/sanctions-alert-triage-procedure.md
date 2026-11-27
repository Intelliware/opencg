# Sanctions Alert Triage Procedure

Owner: Head of Sanctions and Payments Compliance
Applies to: Juniper Bay Payments
Classification: Internal
Version: 2.8
Effective: 2026-06-01

This procedure explains how Payments Compliance analysts work sanctions screening alerts raised on payments and clients. It applies the *Juniper Bay Group AML/ATF Programme Summary* to payment flows and depends on the screening engine owned by Compliance Systems.

## Purpose

Every payment and every new or changed beneficiary is screened against sanctions and watch lists. The screening engine compares names and attributes and produces a match score. A score above the alert level creates an alert that an analyst must work. The purpose of triage is to decide quickly and consistently whether an alert is a true match.

## Alert levels

| Level | Who works it | Outcome |
|---|---|---|
| Level 1 | Payments Compliance analyst | Clear obvious false positives or escalate |
| Level 2 | Senior analyst | Detailed review of possible matches |
| Level 3 | Head of Sanctions and Payments Compliance | Final decision on true matches |

The fuzzy-match score that sends an alert to Level 2 review, and the lower score at which alerts are auto-cleared, are set out in the *Sanctions Screening Tuning* (Confidential) document. This procedure does not repeat them, because publishing them would help a bad actor craft names that slip under the threshold.

## Level 1 steps

1. Open the alert and note which list and entry matched.
2. Compare the name, date of birth, address, country and any identifiers.
3. If at least one strong identifier differs, clear the alert and record the reason.
4. If the evidence is unclear, escalate to Level 2. When in doubt, escalate.
5. Never release a payment while an alert is open.

## Level 2 steps

1. Gather extra evidence: client file, payment history and public sources.
2. Decide: false positive, possible match or true match.
3. For a possible or true match, escalate to Level 3 and keep the payment on hold.
4. Record the full reasoning in the case notes.

## Level 3 steps

The Head of Sanctions and Payments Compliance confirms the decision. For a true match:

- block or reject the payment as the law requires;
- freeze funds where applicable;
- report as required to the relevant authorities, with support from the AML Officer; see the *Juniper Bay Group AML/ATF Programme Summary*;
- do not tell the client about the investigation. Tipping off is prohibited.

## Service levels

| Level | Target time to decision |
|---|---|
| Level 1 | 2 hours |
| Level 2 | 1 business day |
| Level 3 | 2 business days |

Payments held for screening are not released to meet a cut-off.

## Records and quality assurance

All decisions and reasoning are kept for the period set by the group retention schedule. A 10 percent sample of cleared alerts is re-reviewed each month by a second analyst, and results feed the tuning reviews.

## Related documents

- *Wire Repair and Returns Runbook* for returned wires that raise a sanctions concern.
- *Payment Incident Runbook* for screening outages.
