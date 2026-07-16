# Chargeback Reason Codes — Simplified Compelling Evidence Requirements

## Visa Reason Codes

### Visa 10.4 — Other Fraud, Card Absent Environment

**Issuer claim:** Cardholder denies authorising a card-not-present transaction.

**Logic:** ANY TWO of the following:

1. Evidence the cardholder used the same card and same shipping address in two prior undisputed transactions with this merchant, completed more than 120 days but less than 365 days before the disputed transaction
2. Evidence the cardholder is in possession of and using the merchandise (e.g. signed-in account activity post-delivery, social media post tagging the merchant)
3. For digital goods: device fingerprint, IP address, geolocation, and customer account login matching prior undisputed transactions
4. Proof of delivery to the cardholder's verified billing address (not just shipping address) with signature confirmation

---

### Visa 10.5 — Visa Fraud Monitoring Program

**Issuer claim:** Transaction flagged under Visa's fraud monitoring program.

**⚠ Non-representable.** Recommend `accept_liability` unless the merchant can prove the transaction was miscoded by the issuer.

---

### Visa 12.5 — Incorrect Amount

**Issuer claim:** The amount charged does not match the amount the cardholder authorised.

**Logic:** ALL of the following:

1. The signed receipt, terms of service, or order confirmation showing the amount the cardholder agreed to
2. Documentation showing the amount charged matches that agreed amount
3. If a tip, gratuity, or adjustment was added, evidence the cardholder authorised it

---

### Visa 12.6.1 — Duplicate Processing

**Issuer claim:** The same transaction was processed more than once.

**Logic:** ALL of the following:

1. Evidence the two transactions are for two separate purchases (e.g. different order IDs, different items, different services rendered)
2. Documentation of each purchase event (separate invoices, separate delivery confirmations, separate service dates)
3. Transaction timestamps and authorisation codes for each charge

---

### Visa 13.1 — Merchandise / Services Not Received

**Issuer claim:** Cardholder paid but never received the goods or services.

**Logic:** ALL of the following:

1. Proof of delivery: tracking number, carrier name, and confirmation of delivery to the cardholder's address
2. For services: evidence the service was rendered on or before the expected date (booking confirmation, attendance log, access logs)
3. Date of delivery / service rendered is on or before the chargeback date
4. The delivery address materially matches the address provided by the cardholder at purchase

---

### Visa 13.2 — Cancelled Recurring Transaction

**Issuer claim:** Cardholder cancelled a recurring subscription but was still charged.

**Logic:** ALL of the following:

1. Terms of service disclosing the recurring billing arrangement and the cancellation method
2. Evidence the cardholder was notified of the upcoming charge (typically 7+ days in advance)
3. No record of the cardholder having submitted a cancellation request prior to the billing date
4. Evidence of the cardholder's original opt-in to the recurring arrangement

---

### Visa 13.3 — Not as Described or Defective Merchandise

**Issuer claim:** Cardholder received the goods but they are materially not as described or defective.

**Logic:** ALL of the following:

1. The merchant's published description of the item the cardholder purchased
2. Evidence the item delivered matches that description (photos, specs, serial number match)
3. Evidence the merchant offered a return/refund route and the cardholder did not use it, OR evidence the cardholder used and retained the merchandise after raising the complaint

---

### Visa 13.6 — Credit Not Processed

**Issuer claim:** The merchant agreed to a refund but never processed it.

**Logic:** EITHER of the following:

- Evidence that a refund was processed (refund transaction ID, date, amount)
- Evidence that no refund was ever agreed (merchant's refund policy and absence of any refund commitment in cardholder communications)

---

### Visa 13.7 — Cancelled Merchandise / Services

**Issuer claim:** Cardholder cancelled the purchase per the merchant's policy but was charged.

**Logic:** ALL of the following:

1. The merchant's cancellation policy as displayed at point of sale
2. Evidence the cardholder agreed to that policy (e.g. checkbox click record, signed terms)
3. Evidence the cardholder either did not cancel within the policy window, or cancelled outside the refundable period

---

## Mastercard Reason Codes

### Mastercard 4837 — No Cardholder Authorisation

**Issuer claim:** Cardholder denies authorising the transaction (card-not-present fraud equivalent).

**Logic:** ANY TWO of the following:

1. AVS match (full address) AND CVV match on the disputed transaction
2. 3D Secure authentication completed successfully (Mastercard SecureCode / Identity Check)
3. Two prior undisputed transactions from the same cardholder with this merchant in the past 12 months, with matching billing details
4. Proof of delivery to the cardholder's billing address with signature

---

### Mastercard 4853 — Cardholder Dispute (Goods / Services Not Provided)

**Issuer claim:** Goods or services were not provided as agreed.

**Logic:** ALL of the following:

1. Proof of delivery or service provision (tracking, confirmation, access log)
2. Evidence the goods or services materially match what was advertised
3. Either: no contact from the cardholder attempting to resolve the issue before the chargeback, OR documentation showing the merchant attempted resolution and the cardholder refused

---

### Mastercard 4855 — Goods / Services Not Provided

**Issuer claim:** Paid for goods or services that were never delivered or rendered.

**Logic:** ALL of the following:

1. Proof of delivery (tracking + carrier confirmation) or proof of service rendered (access logs, attendance, completed booking)
2. Date of delivery / service is before the chargeback date
3. Delivery address matches the cardholder's records

---

### Mastercard 4859 — No-Show / Addendum

**Issuer claim:** Cardholder was charged a no-show fee, late cancellation fee, or addendum charge that they dispute.

**Logic:** ALL of the following:

1. Evidence of the cardholder's original reservation or booking
2. The merchant's no-show / cancellation policy as disclosed at booking
3. Evidence the cardholder either failed to show or cancelled outside the policy window
4. Evidence the fee charged matches the policy disclosed

---

### Mastercard 4863 — Cardholder Does Not Recognise — Potential Fraud

**Issuer claim:** Cardholder does not recognise the transaction (may not be fraud — could be a confusing descriptor).

**Logic:** ANY ONE of the following:

1. Evidence the merchant's billing descriptor matches the merchant name the cardholder would recognise
2. AVS + CVV match on the disputed transaction
3. Prior undisputed transactions from the same cardholder with this merchant
4. Cardholder's IP / device / account login matching prior undisputed sessions

---

### Mastercard 4870 — Chip Liability Shift

**Issuer claim:** Counterfeit card used at a non-chip-enabled terminal (card-present only).

**⚠ Non-representable.** Card-present reason code. Recommend `accept_liability` and flag the merchant for terminal upgrade.
