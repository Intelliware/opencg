# Retail pack: Juniper Bay Bank

Juniper Bay Financial Group is fictional. Its people, figures and documents are illustrative and are not legal or regulatory guidance.

Owner: openCG maintainers

## What this pack shows

Retail banking content for Juniper Bay Bank, split across three classifications. Public documents are visible to everyone. Internal procedures are visible to staff. The confidential set carries the label `confidential:retail` and is visible only to the persona `demo-branch`.

The point of the pack is the **split answer**. Each internal procedure explains the process and names a confidential document by exact title for the specifics. The confidential document holds the numbers. A reader without the entitlement gets the process and a pointer. The persona with the entitlement gets the figures as well.

## Documents

Public (`public/`)
- `chequing-and-savings-account-disclosures.md` : Juniper Bay Bank Chequing and Savings Account Disclosures
- `overdraft-protection-terms.md` : Juniper Bay Bank Overdraft Protection Terms
- `dispute-and-chargeback-guide.md` : Juniper Bay Bank Dispute and Chargeback Guide

Internal (`internal/`)
- `account-opening-procedure.md` : Retail Account Opening and Credit Application Procedure
- `branch-cash-handling-standard.md` : Branch Cash Handling Standard
- `dispute-investigation-procedure.md` : Retail Dispute Investigation Procedure
- `financial-hardship-programme-procedure.md` : Financial Hardship Programme Procedure

Confidential (`confidential/`, label `confidential:retail`)
- `retail-credit-decisioning-policy.md` : Retail Credit Decisioning Policy
- `retail-collections-strategy.md` : Retail Collections Strategy
- `retail-pricing-exception-authorities.md` : Retail Pricing Exception Authorities

## How the questions work

`questions.json` lists scripted questions. Each entry names the question, the persona, the internal document, the confidential document, and what each audience should see. Ask the same question as `demo-reader` and as `demo-branch`. The reader should see the procedure and a pointer only. The persona should also see the specifics. Paths are relative to this folder.

## Public questions

These get the same answer for everyone:
- What is the monthly fee on Everyday Chequing and how can it be waived?
- How long do I have to raise a dispute on a card transaction?
- How much does overdraft protection cost in a month I use it?

## Cross-pack question

"What do staff do when a customer's story does not add up at account opening?" The answer draws on the retail account opening procedure and on the *Juniper Bay Group AML/ATF Programme Summary*, which is shared across the Wealth, Payments and Retail packs.
