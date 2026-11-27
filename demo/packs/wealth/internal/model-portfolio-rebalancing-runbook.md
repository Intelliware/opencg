# Wealth Model-Portfolio Rebalancing Runbook

Owner: Head of Portfolio Management
Applies to: Juniper Bay Wealth
Classification: Internal
Version: 1.6, Effective: 2026-04-01

## Purpose

This runbook describes how Portfolio Management rebalances client accounts to the five model portfolios described in the *Juniper Bay Wealth Managed Portfolio Family Overview*. It is for portfolio managers and trading operations.

## Roles

- **Portfolio Manager** owns the model and approves changes.
- **Trading Operations** prepares and executes orders.
- **Wealth Compliance Officer** reviews exceptions and any model change that alters a portfolio's risk profile.

## Rebalancing triggers

Accounts are rebalanced when any of the following occur:

1. **Calendar.** At the start of each quarter.
2. **Drift.** An asset class is more than five percentage points from its target weight.
3. **Model change.** The Portfolio Manager approves a change to the model.
4. **Cash event.** A deposit or withdrawal of more than CAD 10,000.
5. **Client change.** A client's risk profile changes after a suitability review under the *Wealth Suitability Review Procedure*.

## Procedure

1. Trading Operations runs the drift report on the first business day of each month and at each trigger.
2. For every account that breaches a trigger, the rebalancing tool proposes trades. Operations checks them for tax impact, available cash, and any restrictions on the account.
3. Accounts with a client-specific restriction are excluded from automatic rebalancing and handled manually.
4. The Portfolio Manager approves the batch.
5. Trading Operations places orders and monitors execution. Orders are aggregated and allocated fairly across accounts.
6. After execution, Operations reconciles holdings to the custodian and attaches the reconciliation to the batch record.

## Tax considerations

Where practicable, rebalance using new cash and income first. For non-registered accounts, check for realised gains before selling. Advisors are told about trades with a material tax effect before orders are placed.

## Failures and exceptions

- If a trade fails or settles late, Operations notifies the Portfolio Manager the same day.
- If a batch is found to be wrong after execution, stop and inform the Wealth Compliance Officer immediately. Corrections are made at the firm's cost where the client was harmed.
- Rebalancing must not be used to bring about a change in risk profile that the client has not agreed to.

## Controls

The Wealth Compliance Officer samples batches quarterly. A rebalancing record includes triggers, the approved trades, the approver and the reconciliation.

## Related documents

- *Wealth Suitability Review Procedure*
- *Juniper Bay Wealth Managed Portfolio Family Overview*
