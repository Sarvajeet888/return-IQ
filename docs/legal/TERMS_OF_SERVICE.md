# Terms of Service — ReturnIQ Enterprise

**Effective Date:** 1 August 2025
**Version:** 1.0

---

## 1. Agreement

By registering for or using ReturnIQ Enterprise ("the Service"), you ("Merchant",
"you", "your") agree to these Terms of Service ("Terms") in full. If you are entering
these Terms on behalf of a company or other legal entity, you represent that you have
the authority to bind that entity.

If you do not agree, do not use the Service.

---

## 2. Description of Service

ReturnIQ Enterprise provides:
- Machine learning-based return cost prediction
- Fraud risk scoring (rule-based)
- Damage assessment scoring (rule-based)
- Routing decision recommendations (accept / reject / manual_review / refund_and_keep)
- Return, customer, and workflow management tools
- Reporting and analytics dashboards
- REST API access for ERP/WMS integration

---

## 3. Account Registration & Security

3.1 You must provide accurate, current, and complete information during registration.

3.2 You are responsible for maintaining the confidentiality of your credentials and for
all activity that occurs under your account.

3.3 You must notify us immediately at security@returniq.in if you suspect unauthorised
access to your account.

3.4 You must not share API keys across organisations or expose them in client-side code.

3.5 We reserve the right to suspend accounts where we detect suspicious activity,
credential sharing, or terms violations.

---

## 4. Acceptable Use

You agree **not** to:

- Use the Service to process returns for transactions that did not occur
- Submit fabricated order IDs, SKUs, or customer identifiers to manipulate model outputs
- Attempt to reverse-engineer, extract, or replicate the trained ML model
- Probe, scan, or test the Service for vulnerabilities without written permission
- Use the Service in violation of any applicable law or regulation
- Resell or sublicense access to the Service to third parties without written permission
- Automate bulk requests beyond documented rate limits
- Use the Service to process data belonging to an organisation other than your own

---

## 5. AI Predictions — Important Limitations

**5.1 Not a final decision.** ReturnIQ's routing decisions are recommendations, not
binding determinations. You remain solely responsible for all return-handling decisions
made by your business.

**5.2 Accuracy is not guaranteed.** The cost prediction model is trained on historical
data and will be less accurate for novel product categories, unusual return reasons, or
market conditions not represented in training data. Fraud and damage scores are
rule-based heuristics — they are not trained ML models.

**5.3 Human oversight required.** You must maintain a human review process for
high-value returns, disputed decisions, and any cases where the platform recommends
rejection of a legitimate customer claim. See `AI_TRANSPARENCY.md` for full disclosure.

**5.4 No warranty on outcomes.** Using a "reject" routing decision from ReturnIQ as the
sole basis for denying a customer's return without human review is at your own risk and
may expose you to consumer protection liability.

---

## 6. Data & Privacy

6.1 You are responsible for ensuring you have the right to upload any customer data to
the Service, and that doing so complies with India's Digital Personal Data Protection Act
(DPDP Act 2023) and any other applicable privacy laws.

6.2 You must not upload special category personal data (health records, financial account
numbers, government IDs) unless you have a specific data processing agreement with us.

6.3 Our processing of your data is governed by our Privacy Policy, which forms part of
these Terms.

---

## 7. Intellectual Property

7.1 The ReturnIQ software, ML models, documentation, and brand are owned by ReturnIQ
and protected by copyright and other IP laws.

7.2 The data you upload remains yours. You grant ReturnIQ a limited licence to process
your data solely for the purpose of providing the Service.

7.3 You may not use ReturnIQ's name, logo, or trademarks without prior written consent.

7.4 Feedback you submit about the Service may be used by ReturnIQ to improve the
platform without compensation or attribution to you.

---

## 8. Uptime & Service Levels

8.1 We aim for 99.5% monthly uptime for the API and core prediction path. Scheduled
maintenance will be announced at least 24 hours in advance.

8.2 We do not guarantee uninterrupted service and are not liable for downtime caused by
infrastructure failures, force majeure, third-party service outages, or security
incidents.

---

## 9. Liability Limitations

**To the maximum extent permitted by applicable law:**

9.1 ReturnIQ's total cumulative liability to you for any claims arising from or related
to the Service shall not exceed the total fees paid by you in the **three months**
immediately preceding the event giving rise to the claim.

9.2 ReturnIQ shall not be liable for:
- Indirect, incidental, consequential, or punitive damages
- Loss of profits, revenue, data, or business opportunities
- Losses arising from your reliance on AI prediction outputs without human review
- Losses caused by third-party integrations, courier failures, or fraud by your customers
- Downtime or data loss caused by infrastructure outside ReturnIQ's direct control

9.3 Nothing in these Terms limits liability for death or personal injury caused by
negligence, or for fraud or fraudulent misrepresentation.

---

## 10. Account Suspension & Termination

10.1 **By you:** You may close your account at any time by contacting support or using
`DELETE /api/v1/users/account`. Your data will be retained for 90 days then deleted per
the Data Retention Policy, except audit logs which are retained for 2 years.

10.2 **By us:** We may suspend or terminate your account immediately, with or without
notice, if:
- You materially breach these Terms
- You fail to pay applicable fees (when billing is enabled)
- We are required to do so by law
- We reasonably believe you are engaged in fraudulent activity

10.3 On termination, your access to the Service will cease. You may request a data
export within 30 days of termination.

---

## 11. Modifications to the Service & Terms

11.1 We may modify the Service at any time, including adding, changing, or removing
features. We will provide reasonable notice for material changes.

11.2 We may update these Terms from time to time. Material changes will be notified
by email and in-app notification at least 14 days before they take effect. Continued
use after that date constitutes acceptance.

---

## 12. Governing Law & Disputes

12.1 These Terms are governed by the laws of India.

12.2 Any dispute arising from these Terms or the Service shall first be submitted to
good-faith negotiation for 30 days. If unresolved, disputes shall be referred to
binding arbitration under the Arbitration and Conciliation Act, 1996, in
[City], India. The language of arbitration shall be English.

12.3 Nothing prevents either party from seeking urgent injunctive relief from a
competent court.

---

## 13. General

- **Entire agreement:** These Terms, the Privacy Policy, Cookie Policy, and any
  executed Order Form constitute the entire agreement between you and ReturnIQ.
- **Severability:** If any provision is found unenforceable, the remaining provisions
  remain in effect.
- **No waiver:** Our failure to enforce any right is not a waiver of that right.
- **Assignment:** You may not assign your rights under these Terms without our written
  consent. We may assign our rights in connection with a merger or acquisition.

---

**Contact:** legal@returniq.in
