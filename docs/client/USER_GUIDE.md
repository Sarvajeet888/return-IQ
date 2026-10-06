# User Guide — ReturnIQ Enterprise

## Getting Started

### Creating Your Account
1. Go to your ReturnIQ URL and click **Register**
2. Enter your organisation name, full name, email, and a strong password
   (min 8 characters, 1 uppercase, 1 digit)
3. You are automatically the `org_admin` for your organisation
4. You will land on the Dashboard

---

## Processing a Return

### Single Return
1. Click **New Return** in the sidebar
2. Fill in the return details:
   - **Order ID** — your platform's order reference
   - **Customer** — customer email or identifier
   - **SKU & Category** — the item being returned
   - **Item Value** — original sale price in INR
   - **Pincodes** — origin (customer) and destination (warehouse)
   - **Weight** — actual and volumetric (dimensional) weight in grams
   - **Return Reason** — select from the dropdown
   - **Courier** — the courier handling this return
   - **Payment Mode** — Prepaid or COD
   - **Condition** — your assessment of the item condition
3. Click **Submit Return**
4. The AI scores the return in under 100ms and shows you:
   - **Routing Decision** — accept / reject / manual_review / refund_and_keep
   - **Predicted Cost** — estimated processing cost in INR
   - **Risk Score** — 0–100 (higher = more risk)
   - **Fraud Score** — 0–100 (rule-based heuristic)
   - **Top Cost Driver** — what's driving the predicted cost

### Bulk Import
For importing multiple returns at once (e.g., end-of-day batch from your OMS):
1. Go to **Returns** → **Bulk Import**
2. Upload a JSON file with up to 50 returns (same schema as single return)
3. Or use the `POST /api/v1/returns/bulk` API endpoint from your ERP

---

## Understanding Predictions

### Routing Decisions

| Decision | Meaning |
|---|---|
| **accept** | Low risk, cost justified — approve the return |
| **reject** | High fraud risk or cost exceeds value — investigate before approving |
| **manual_review** | Ambiguous — a human should review before deciding |
| **refund_and_keep** | Item value too low to justify return shipping — refund the customer and let them keep the item |

### Risk Score
A 0–100 score combining cost, fraud, and damage signals. Think of it as
"how much attention does this return need?". Scores above your org's threshold trigger
extra scrutiny.

### Important: What the AI Can and Cannot Do
- ✅ The cost prediction is a real ML model trained on ~80K returns
- ⚠️ The fraud and damage scores are rule-based calculations, not ML models
- ⚠️ All decisions are recommendations — you are responsible for final decisions
- See `docs/legal/AI_TRANSPARENCY.md` for full details

### Overriding a Decision
If you disagree with the AI's recommendation:
1. Open the return
2. Go to **AI Platform** → find the prediction → click **Override**
3. Enter the correct decision and your reason
4. The override is logged in the audit trail

---

## Return Timeline & Notes

Every return has a timeline showing all events in chronological order:
- Return created
- Prediction completed (with routing decision)
- Notes added by your team
- Documents uploaded
- Status changes
- SLA deadline

### Adding Notes
1. Open a return
2. Click **Add Note**
3. Type your note and save
4. Notes are visible to all org members and are permanent (cannot be deleted)

---

## Uploading Documents

Attach damage photos, invoices, warranty cards, and shipping labels to returns:
1. Open the return
2. Go to the **Documents** tab
3. Click **Upload Document**
4. Select file (JPEG, PNG, WebP, or PDF — max 10MB)
5. Check **This is a damage photo** if applicable

Documents are automatically deleted 90 days after the return is closed.

---

## Customers

### Finding a Customer
1. Go to **Customers** in the sidebar
2. Use the search box to find by name or email
3. Filter by risk level or blacklist status

### Customer Analytics
Click any customer to see:
- Total returns and total return value
- Fraud return count and fraud rate
- Return reason breakdown
- Category breakdown

### Blacklisting a Customer
If a customer is confirmed as fraudulent:
1. Open the customer record
2. Click **Blacklist Customer** (requires `org_admin` role)
3. Enter a reason
4. The customer is flagged — new returns from this identifier will show a high fraud score

---

## Notifications

The bell icon in the sidebar shows your unread notification count.
Click it to see notifications. You can mark individual or all notifications as read.

Types of notifications you'll receive:
- High fraud score return detected
- Customer blacklisted
- SLA breach
- Workflow rule triggered

---

## Reports & Export

Go to **Reports** in the sidebar to generate:

| Report | Contents |
|---|---|
| Summary | All returns with predictions, costs, routing decisions |
| Fraud | High-risk returns ranked by fraud score |
| Carbon | Carbon footprint breakdown by courier and category |
| Customers | Customer return rates and fraud analysis |

Use **Export CSV** to download any report for analysis in Excel.

---

## Workflow Automation

Set up rules to automate routine decisions:

**Example — Auto-approve low-risk returns:**
1. Go to **Workflows** in the sidebar
2. Click **New Rule**
3. Name: "Auto-approve low risk"
4. Rule Type: `auto_approve`
5. Conditions: `risk_score_lt = 20`, `item_value_lt = 500`
6. Action: Status → `approved`, Notify = ✅
7. Priority: 1
8. Save

Now every return with risk score < 20 and item value < ₹500 will be automatically
approved, and your team gets a notification.

---

## SLA Tracking

Every return automatically gets an SLA deadline (default: 48 hours from creation,
or custom if set by a workflow rule).

To check for SLA breaches:
1. Go to **Workflows** → **SLA Breaches** tab
2. Or click **Check for New Breaches** to scan manually

In production, set up a cron job to call `GET /api/v1/workflows/sla/check-breaches`
every 15 minutes to automatically detect and notify on breaches.
