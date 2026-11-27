# Sanctions Screening Tuning

Owner: Head of Compliance Systems
Applies to: Juniper Bay Payments
Classification: Confidential (confidential:payments)
Version: 3.1
Effective: 2026-06-15

This document records the match-score thresholds and list-handling settings of the sanctions screening engine used by Juniper Bay Payments. It supplies the specifics that the *Sanctions Alert Triage Procedure* defers to. All figures are fictional. Do not share this document outside Compliance and Payments Compliance, because knowing the thresholds helps a bad actor craft names that slip under them. See the *Juniper Bay Group Data Classification Standard*.

## Fuzzy match score thresholds

The engine produces a fuzzy-match score from 0 to 100 for each comparison of a name against a list entry.

| Score | Result |
|---|---|
| Below 70 | No alert |
| 70 to 84 | Level 1 alert, worked by a Payments Compliance analyst |
| 85 to 94 | Level 2 review by a senior analyst |
| 95 to 100 | Level 2 review plus automatic hold and notification to the Head of Sanctions and Payments Compliance |

The fuzzy match score that sends a sanctions alert to Level 2 review is **85**. A Level 1 analyst may also escalate a lower-scoring alert manually.

## Exact and strong matches

- A match on a unique identifier, such as a vessel number or registered company number, goes directly to Level 2 whatever the name score.
- A match on date of birth plus name with a score of 80 or more goes to Level 2.

## Auto-clear rules

Alerts under 75 are auto-cleared only if all of these hold:

1. The client or beneficiary was screened before and cleared.
2. No attribute of the entry has changed in the last 90 days.
3. The earlier clearance was made at Level 2 or above.

All auto-cleared alerts are logged and 10 percent are re-reviewed.

## List handling

| List | Update frequency | Applied |
|---|---|---|
| Canadian consolidated sanctions list | Daily | Within 2 hours of publication |
| United Nations consolidated list | Daily | Within 2 hours |
| Other supplementary lists | Weekly | Within 1 business day |
| Internal watch list | As needed | Immediately |

When a list changes, all active clients and open payments are re-screened within 24 hours.

## Name handling

- Names are normalised before matching: accents removed, titles removed and common prefixes standardised.
- Transliteration variants are matched at a 5 point score allowance.
- Names shorter than 4 characters are matched exactly to limit noise.

## Tuning governance

Thresholds are tested every quarter against a labelled sample of 1,000 historical alerts. The Sanctions Tuning Committee must approve any change. Lowering a threshold requires the Head of Sanctions and Payments Compliance and the AML Officer to sign off. Raising an alert threshold also needs the Chief Compliance Officer because it reduces coverage. Targets: at least 99 percent of true matches must be caught in testing, and Level 1 false positives should stay under 95 percent of alerts.

## Related documents

- *Sanctions Alert Triage Procedure* for how alerts are worked.
- *Juniper Bay Group AML/ATF Programme Summary* for the programme this tuning supports.
- *ISO 20022 Migration Notes* for the richer payment data that feeds screening.
