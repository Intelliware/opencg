# Juniper Bay Payments Real-Time Rail Service Guide

Owner: Head of Payments Product
Applies to: Juniper Bay Payments
Classification: Public
Version: 2.1
Effective: 2026-03-01

This guide describes how business clients send and receive real-time payments through Juniper Bay Payments. Real-time payments travel over Payments Canada's Real-Time Rail (RTR), the national platform for instant, data-rich payments. Juniper Bay Financial Group is fictional; all figures are illustrative.

## What real-time payments offer

- Payments arrive in seconds, 24 hours a day, every day of the year.
- Payments are final once confirmed. They cannot be recalled by the sender.
- Payments carry rich remittance data in ISO 20022 format, so a receiver can match a payment to an invoice automatically.

## Limits

| Limit | Amount (CAD) |
|---|---|
| Per payment, standard client | 25,000 |
| Per day, standard client | 100,000 |
| Per payment, verified high-volume client | 100,000 |

Clients that need higher limits can apply through their relationship manager. Limit increases are assessed individually and may require additional verification.

## Sending a payment

1. Enter the receiver's alias or account details.
2. Review the confirmation of payee screen, which shows the name held by the receiving bank.
3. Approve the payment. Clients with dual authorization enabled need a second approver.
4. A confirmation message arrives within seconds.

Because payments are final, check the receiver's details carefully before approving.

## Receiving a payment

Funds are available in the client's account as soon as a payment is received. Each incoming payment includes the sender's reference and any remittance data. A payment may be held or returned if it fails a compliance check.

## Fees

| Service | Fee (CAD) |
|---|---|
| Outgoing real-time payment | 1.50 |
| Incoming real-time payment | 0.00 |
| Request for payment | 0.50 |

## Availability and maintenance

The service is built for continuous operation, but the Real-Time Rail and Juniper Bay Payments both run planned maintenance windows. Maintenance is announced at least 5 business days in advance on the client portal. During an outage, clients can use wire transfers; see the *Juniper Bay Payments Wire and EFT Fees and Cut-off Times*.

## Security

Juniper Bay Payments monitors every real-time payment for fraud and may decline or hold a payment that looks unusual. A held payment is reviewed as quickly as possible and the client is contacted. Clients should keep payment credentials private, enable dual authorization and report any unrecognised payment immediately.

## Mistaken or fraudulent payments

Because payments are final, a mistaken payment cannot be reversed by Juniper Bay Payments alone. The client should contact Juniper Bay Payments immediately, and Juniper Bay Payments will ask the receiving bank to request the funds back. Return of funds depends on the receiver's agreement and cannot be guaranteed.

## Complaints

Complaints are handled under the *Juniper Bay Group Complaint-Handling Standard*.
