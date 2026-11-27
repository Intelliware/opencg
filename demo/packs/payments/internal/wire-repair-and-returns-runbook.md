# Wire Repair and Returns Runbook

Owner: Head of Payments Operations
Applies to: Juniper Bay Payments
Classification: Internal
Version: 4.2
Effective: 2026-04-15

This runbook tells Payments Operations analysts how to repair wires that fail validation, how to process returned wires, and when a wire must go to manual review before release. It supports the client-facing *Juniper Bay Payments Wire and EFT Fees and Cut-off Times* and replaces version 3 of this runbook, which is superseded.

## Scope

The runbook covers outgoing and incoming domestic and international wires handled by Juniper Bay Payments. Real-time payments are out of scope; see the *Payment Incident Runbook* for outages.

## Wire repair

A wire enters the repair queue when it fails automated validation. Typical causes:

1. Missing or malformed beneficiary account number.
2. Invalid or unrecognised BIC.
3. Truncated remittance data after conversion to ISO 20022; see the *ISO 20022 Migration Notes*.
4. Mismatch between beneficiary name and account details.

Steps:

1. Open the item from the repair queue and record the failure reason.
2. Correct the field from the client's original instruction only. Never infer a missing value.
3. If the original instruction is unclear, contact the client using the contact details on file, not details found in the instruction itself.
4. Re-submit the wire and note the correction in the case log.
5. Release the wire before the cut-off if possible.

Every correction must be logged. A wire that cannot be corrected within one business day is returned to the client.

## Manual review before release

Some outgoing wires are held for manual fraud review before release. The outgoing wire manual review threshold, the number of approvers required, and the other triggers that route a wire to review are set out in the *Payments Fraud Detection Rules and Thresholds* (Confidential). This runbook does not repeat them. Analysts who hold a wire for review must:

- place the wire in the "Fraud Review" status;
- not discuss the reason for the hold with the client beyond the standard wording given in the case template;
- ask the Fraud Operations team for a decision.

Approval levels for releasing a reviewed wire follow the *High-Value Payment Approval Limits* (Confidential).

## Returns

A wire is returned when the beneficiary bank rejects it or a client recalls it.

1. Match the incoming return to the original wire using the unique end-to-end reference.
2. Credit the client's account for the returned amount less any correspondent charges.
3. Apply the returned-wire handling fee listed in the public fee schedule, unless the return resulted from a Juniper Bay Payments error.
4. Notify the client of the return and the reason code.
5. If the reason suggests a possible fraud or sanctions issue, follow the *Sanctions Alert Triage Procedure* instead of crediting the client.

## Recall requests

Recalls are requests, not guarantees. Send a recall through the correspondent network as soon as the client asks. Record the request time and the response, and tell the client that the beneficiary bank may decline.

## Quality checks

Team leads review 5 percent of repaired wires each week. Findings are recorded and reviewed monthly by the Head of Payments Operations.

## Escalation

Escalate unresolved items to the shift lead. For suspected fraud, escalate to Fraud Operations immediately. For suspected money laundering or terrorist financing, follow the *Juniper Bay Group AML/ATF Programme Summary*.
