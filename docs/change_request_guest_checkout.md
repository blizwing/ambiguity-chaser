# Change Request CR-2026-014: Guest Checkout

> Dummy project document, written to be the source material for writing
> requirements. All business values (percentages, limits, durations) are
> invented for the exercise. No real people, companies or data.

| Field | Value |
|---|---|
| CR ID | CR-2026-014 |
| Type | New feature (with changes to existing behaviour) |
| Product | ShopFront web store (the dummy e-commerce app behind `test_corpus.json`) |
| Raised by | Head of E-commerce (business sponsor) |
| Analysed by | Solution Architect / Business Analyst |
| Priority | High |
| Target release | Release 4.2 |
| Status | Analysis complete, awaiting requirements breakdown |

---

## 1. Summary

Let a shopper complete a purchase without creating an account. Today every
checkout requires login, and the sign-up step is the largest drop-off point
in the funnel.

## 2. Business justification

- 38% of shoppers who reach the login/sign-up wall abandon the cart (web
  analytics, last 90 days).
- Support receives about 120 tickets a month for "forgot password" at
  checkout time, which is a direct cost.
- Competitor stores offer guest checkout as standard.
- **Target:** reduce checkout abandonment at the account step from 38% to
  25% within 3 months of release.

## 3. Current behaviour (as is)

1. A shopper adds items to the cart. The cart exists in the browser session
   only (not saved) until login.
2. At "Proceed to checkout" the shopper is sent to login or sign-up.
3. After login, the cart is merged with any saved cart and checkout continues.
4. Account rules already in force: 5 failed logins lock the account for 15
   minutes; sessions expire after 30 minutes of inactivity; password reset
   emails arrive within 60 seconds and the link expires after 24 hours;
   marketing emails can be switched off in settings while transactional
   emails still arrive.

## 4. Proposed behaviour (to be)

1. At "Proceed to checkout", the shopper chooses **Log in**, **Create
   account** or **Continue as guest**.
2. A guest provides: email address, delivery address, phone number
   (optional), payment details.
3. The guest sees an order summary and the cart total, including tax,
   before paying.
4. On success the guest gets an order confirmation page and a confirmation
   email containing an order number and a tracking link.
5. After the order, the confirmation page offers "Create an account with
   these details" (set a password only; no other fields to re-enter).
6. Guest orders are retrievable through the tracking link and by entering
   order number plus email address on a "Track my order" page.

## 5. Scope

**In scope**
- Guest checkout flow for web, all supported countries and currencies.
- Guest order confirmation, tracking and the optional post-order account
  creation.
- Marketing consent capture for guests.
- Fraud and abuse controls specific to guests.
- Reporting: guest orders must appear in the monthly sales report and its
  CSV export.

**Out of scope (this CR)**
- Mobile apps (separate CR).
- Saved payment methods for guests.
- Guest returns and refunds self-service (handled by support for now).
- Changing the existing login, lockout or password reset behaviour.

## 6. Actors

| Actor | Description |
|---|---|
| Guest shopper | Not logged in, no account. |
| Registered shopper | Has an account. Behaviour unchanged except for the new checkout choice screen. |
| Support agent | Looks up guest orders for customers. |
| Admin | Uses the admin dashboard and the monthly sales report. |
| Email service | Sends confirmation and tracking emails. |
| Payment provider | Authorises and captures payment. |

## 7. Business rules

- BR-1: A guest order is tied to the email address given at checkout. If that
  email already belongs to a registered account, the guest is told an
  account exists and is offered login, but may still continue as guest.
- BR-2: Guests are limited to 3 guest orders per email address in any
  rolling 24 hours.
- BR-3: Guest orders above 500.00 in the store currency need an additional
  fraud check before dispatch.
- BR-4: Guest checkout sessions follow the same inactivity timeout as
  logged-in sessions (30 minutes). The cart contents are kept on timeout;
  the entered personal details are not.
- BR-5: Marketing email to a guest is allowed only if the guest ticks an
  unticked-by-default consent box. Confirmation and tracking emails are
  transactional and are always sent.
- BR-6: Tax is calculated on the delivery address, and the cart total is the
  sum of item price multiplied by quantity, plus tax, exactly as for
  registered shoppers.
- BR-7: A guest who later creates an account has all guest orders placed with
  the same email address attached to it, once the email is verified.
- BR-8: Guest personal data is kept for 24 months after the last order, then
  anonymised.

## 8. Functional detail

### 8.1 Choice screen
Shown at checkout to anyone not logged in. Three options, as in section 4.
Logged-in shoppers skip it.

### 8.2 Guest details form
- Email: required, must be a valid format.
- Delivery address: required; the same address validation as registered
  checkout.
- Phone: optional.
- Marketing consent: optional checkbox (BR-5).

### 8.3 Payment
Same payment provider flow as registered checkout. A failed payment returns
the guest to the payment step with their details and cart intact.

### 8.4 Confirmation
Order number, summary, total and a message that an email is on its way. The
confirmation email must arrive within 60 seconds of a successful payment.

### 8.5 Order tracking
- Tracking link in the email opens the order status page without login.
- "Track my order" requires order number and email address. Five wrong
  attempts from one IP block further attempts for 15 minutes.
- The tracking link expires 90 days after the order date.

### 8.6 Post-order account creation
Guest sets a password. The account is created with the checkout email, an
email verification message is sent, and BR-7 applies once verified.

## 9. Non-functional requirements

| Area | Target |
|---|---|
| Performance | Choice screen and guest form render within 2 seconds on a standard broadband connection. Order submission responds within 5 seconds at the 95th percentile. |
| Capacity | Handle 200 concurrent guest checkouts. |
| Security | Guest payment data is never stored by ShopFront (provider tokens only). Tracking links are unguessable (at least 128 bits of randomness). |
| Privacy | Consent and retention per BR-5 and BR-8. A guest can request deletion by contacting support. |
| Accessibility | WCAG 2.1 AA for the new screens. |
| Browsers | Latest two versions of Chrome, Firefox, Safari and Edge. |

## 10. Impact analysis

| Area | Impact | Existing test case |
|---|---|---|
| Login / lockout | No change. Guest flow must not create an account that can be locked. | TC-001 |
| Password reset | No change. Post-order account creation sets a password directly. | TC-002 |
| Reports / CSV export | Guest orders must be included. New column "Customer type" (guest / registered). Row count must still match. | TC-003 |
| Search pagination | No change. | TC-004 |
| Session timeout | Applies to the guest flow (BR-4). Needs a guest variant of the check. | TC-005 |
| Upload limit | Not affected. | TC-006 |
| Cart total | Reused unchanged. Must give the same total for guest and registered. | TC-007 |
| Email preferences | Guests have no settings page, so consent is captured at checkout only (BR-5). | TC-008 |
| Admin access | Support agents need read access to guest orders. Role rules unchanged. | TC-009 |
| Dashboard load time | Order volume rises. Must still render in 3 seconds with 1000 records. | TC-010 |
| Database | New order-customer link without a user ID; new retention job (BR-8). | n/a |
| Integrations | Payment provider (guest customer reference), email service (two new templates). | n/a |

## 11. Dependencies

- Payment provider confirms guest-order support (due before development
  starts).
- Legal approval of the consent wording and the 24-month retention period.
- Two new email templates from the content team.

## 12. Assumptions

- The existing address validation can be reused as is.
- The current tax engine accepts a delivery address with no customer
  record.
- Analytics event tracking is already in place, so the 38% baseline is
  trustworthy.

## 13. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Guest checkout is used for card testing / fraud | Medium | High | BR-2, BR-3 and provider fraud screening. |
| Duplicate customer records for repeat guests | High | Medium | BR-1 and BR-7. |
| Guest data retained longer than allowed | Low | High | BR-8 retention job with an audit report. |
| Support cannot find a guest order | Medium | Low | Admin search by email and order number. |

## 14. Open questions for stakeholders

1. Should a guest be able to see their own order history across multiple
   guest orders, or only individual orders by link?
2. If the guest's email matches an existing account (BR-1), should the
   order still be attached to that account automatically?
3. Is BR-3's 500.00 threshold in the store currency or converted to a base
   currency for multi-currency stores?
4. What happens to a guest order if the confirmation email bounces?
5. Are gift orders (delivery to a different person) in scope for the
   confirmation email wording?

## 15. High-level acceptance criteria

- A shopper with no account can place and pay for an order and receive a
  confirmation email.
- Guest and registered orders show the same totals for the same cart.
- Guest orders appear in the monthly sales report and CSV export with the
  correct customer type.
- No marketing email is sent to a guest who did not opt in.
- A guest can track an order by link and by order number plus email.
- The existing login, lockout, session and password reset behaviour is
  unchanged.

## 16. Suggested use for the requirements exercise

Write requirements from sections 4, 7, 8 and 9 one at a time. Section 14 is
a set of genuine gaps: a requirement that depends on one of them should be
written with the gap visible, then checked with the agent to see whether it
asks the right question rather than guessing. Try a few deliberately vague
ones too ("the page should load quickly", "guests are limited sensibly") and
at least one pair that disagree with each other (for example BR-4 against
section 8.5), since catching a contradiction across requirements is why
this project exists.
