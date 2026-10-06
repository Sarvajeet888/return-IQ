import React, { useState } from 'react'
import { formatMoney, formatScore } from '../../utils/money'
import { Send, RotateCcw } from 'lucide-react'
import { api } from '../../utils/api.js'
import {
  Panel, Button, Input, Select, Textarea, Checkbox, Alert, Badge,
  PageHeader, MonoValue, SignalBar, Divider,
} from '../../components/ui/index.jsx'

/* ═══════════════════════════════════════════════════════════════════════════
   New return — the page reads as three movements:

       Input   →   Analysis   →   Decision

   Only the presentation changed. The payload, the validation, the
   createReturn call and the demo-fill helper are the previous logic
   untouched: this page still POSTs exactly what it always did.
   ═══════════════════════════════════════════════════════════════════════ */

const INIT = {
  platform_order_id: '', customer_identifier: '', sku: '', item_category: 'apparel',
  item_value: '', origin_pincode: '', destination_pincode: '',
  weight_grams: '', volumetric_weight_grams: '', return_reason_code: 'size_issue',
  courier: 'BlueDart', payment_mode: 'Prepaid', condition: 'good',
  fragile: false, festive: false, customer_notes: '',
}

/* What each decision means, in the operator's language — active voice,
   says what happens next rather than describing a state. */
const DECISION_META = {
  accept:            { label: 'Accept',            tone: 'var(--green)', desc: 'Low risk. Process through the standard workflow.' },
  reject:            { label: 'Reject',            tone: 'var(--red)',   desc: 'Risk is above threshold. The return has been blocked.' },
  refund_and_keep:   { label: 'Refund and keep',   tone: 'var(--blue)',  desc: 'Moving it costs more than the item. Refund without a pickup.' },
  charge_return_fee: { label: 'Charge return fee', tone: 'var(--amber)', desc: 'Moderate risk. Accept, and charge the return fee.' },
}

// Phase 3: local formatter removed. One shared helper, exact server data.
const inr = v => formatMoney(v)

function fillDemo(setForm) {
  const rand = arr => arr[Math.floor(Math.random() * arr.length)]
  setForm({
    platform_order_id: `ORD-${Math.floor(Math.random() * 90000) + 10000}`,
    customer_identifier: 'cust_' + Math.random().toString(36).slice(2, 10),
    sku: rand(['TSHIRT-L-RED', 'JEANS-32-BLU', 'SAREE-SILK-GRN', 'SHOE-NK-42', 'KURTA-M-WHT']),
    item_category: rand(['apparel', 'electronics', 'footwear', 'accessories']),
    item_value: String(Math.floor(Math.random() * 3000) + 299),
    origin_pincode: rand(['400001', '560001', '110001', '700001', '500001']),
    destination_pincode: rand(['411001', '380001', '302001', '530001', '201301']),
    weight_grams: String(Math.floor(Math.random() * 800) + 100),
    volumetric_weight_grams: String(Math.floor(Math.random() * 1000) + 200),
    return_reason_code: rand(['size_issue', 'damaged', 'not_as_described', 'wrong_item', 'quality_issue', 'change_of_mind']),
    courier: rand(['BlueDart', 'Delhivery', 'DTDC', 'Ekart', 'XpressBees']),
    payment_mode: Math.random() > 0.5 ? 'Prepaid' : 'COD',
    condition: rand(['like_new', 'good', 'fair', 'damaged']),
    fragile: Math.random() > 0.75,
    festive: Math.random() > 0.85,
    customer_notes: 'Product received in damaged packaging.',
  })
}

export default function NewReturn() {
  const [form, setForm] = useState(INIT)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const set = k => e => {
    const val = e.target.type === 'checkbox' ? e.target.checked : e.target.value
    setForm(f => ({ ...f, [k]: val }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true); setError(''); setResult(null)
    try {
      const payload = {
        ...form,
        item_value: parseFloat(form.item_value),
        weight_grams: parseInt(form.weight_grams),
        volumetric_weight_grams: parseInt(form.volumetric_weight_grams),
      }
      const data = await api.createReturn(payload)
      setResult(data)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (e) {
      setError(e.response?.data?.detail || e.message)
    } finally { setLoading(false) }
  }

  const pred = result?.prediction
  const meta = pred ? DECISION_META[pred.routing_decision] : null

  return (
    <div>
      <PageHeader
        eyebrow="Returns"
        title="Score a return"
        subtitle="Enter the return once. The model scores it and issues a decision before you commit to moving anything."
        actions={
          <Button variant="secondary" size="sm" icon={<RotateCcw size={13} />} onClick={() => fillDemo(setForm)}>
            Fill sample data
          </Button>
        }
      />

      {error && <Alert type="error" style={{ marginBottom: 'var(--s4)' }}>{error}</Alert>}

      {/* ── MOVEMENT 3 (shown first once it exists) · DECISION ───────────── */}
      {pred && meta && (
        <div className="scale-in" style={{ marginBottom: 'var(--s6)' }}>
          <Panel pad={false} style={{ borderLeft: `2px solid ${meta.tone}` }}>
            <div style={{ padding: 'var(--s5)' }}>
              <div className="eyebrow eyebrow--signal" style={{ marginBottom: 'var(--s3)' }}>
                Decision issued
              </div>

              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 'var(--s5)', flexWrap: 'wrap' }}>
                <div style={{ flex: '1 1 320px', minWidth: 0 }}>
                  <h2 style={{ fontSize: 'var(--t-h2)', color: meta.tone, marginBottom: 6 }}>
                    {meta.label}
                  </h2>
                  <p style={{ fontSize: 'var(--t-sm)', color: 'var(--text-secondary)', maxWidth: '48ch' }}>
                    {meta.desc}
                  </p>
                </div>

                <div style={{ textAlign: 'right', flexShrink: 0 }}>
                  <div className="eyebrow" style={{ marginBottom: 4 }}>Confidence</div>
                  <MonoValue size={30} color="var(--text-primary)">
                    {((pred.confidence_score || 0) * 100).toFixed(1)}%
                  </MonoValue>
                </div>
              </div>
            </div>

            {/* Analysis readout — the numbers behind the decision */}
            <div style={{ borderTop: '1px solid var(--border)', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(146px, 1fr))' }}>
              {[
                { label: 'Predicted cost', value: inr(pred.predicted_cost_inr) },
                { label: 'Resale value', value: inr(pred.resale_value_estimate) },
                { label: 'Carbon', value: `${pred.carbon_footprint_kg} kg` },
                { label: 'Latency', value: formatScore(pred.inference_latency_ms, { suffix: ' ms' }) },
              ].map((m, i) => (
                <div key={m.label} style={{
                  padding: 'var(--s4) var(--s5)',
                  borderLeft: i === 0 ? 'none' : '1px solid var(--border)',
                }}>
                  <div style={{ fontSize: 'var(--t-micro)', color: 'var(--text-muted)', marginBottom: 5 }}>{m.label}</div>
                  <MonoValue size={17}>{m.value}</MonoValue>
                </div>
              ))}
            </div>

            {/* Risk and fraud as bars — noise resolving, not just digits */}
            <div style={{ borderTop: '1px solid var(--border)', padding: 'var(--s5)', display: 'grid', gap: 'var(--s4)' }}>
              {[
                { label: 'Risk', value: Number(pred.risk_score) },
                { label: 'Fraud', value: Number(pred.fraud_score) },
              ].map(b => (
                <div key={b.label} style={{ display: 'flex', alignItems: 'center', gap: 'var(--s4)' }}>
                  <span style={{ fontSize: 'var(--t-xs)', color: 'var(--text-muted)', width: 44, flexShrink: 0 }}>
                    {b.label}
                  </span>
                  <div style={{ flex: 1 }}><SignalBar value={b.value} height={6} /></div>
                </div>
              ))}

              {pred.explainability?.risk_factors?.length > 0 && (
                <>
                  <Divider style={{ margin: 0 }} />
                  <div>
                    <div className="eyebrow" style={{ marginBottom: 'var(--s3)' }}>What drove this</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                      {pred.explainability.risk_factors.map(f => (
                        <span key={f} style={{
                          fontSize: 'var(--t-micro)', background: 'var(--surface-2)',
                          color: 'var(--text-secondary)', border: '1px solid var(--border)',
                          borderRadius: 'var(--r-sm)', padding: '3px 9px',
                        }}>
                          {f}
                        </span>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </div>
          </Panel>

          <div style={{ marginTop: 'var(--s3)', display: 'flex', gap: 'var(--s2)' }}>
            <Button variant="secondary" size="sm" onClick={() => { setResult(null); setForm(INIT) }}>
              Score another
            </Button>
            <Button variant="ghost" size="sm" onClick={() => { window.location.href = '/returns' }}>
              View all returns
            </Button>
          </div>
        </div>
      )}

      {/* ── MOVEMENT 1 · INPUT ────────────────────────────────────────────── */}
      <form onSubmit={handleSubmit}>
        <Panel eyebrow="Step one" title="The return">
          <div className="grid grid--2">
            <Input label="Order ID" value={form.platform_order_id} onChange={set('platform_order_id')}
              placeholder="ORD-12345" required />
            <Input label="Customer identifier" value={form.customer_identifier} onChange={set('customer_identifier')}
              placeholder="hashed customer ID" hint="Hashed upstream — never a raw customer ID." required />
            <Input label="SKU" value={form.sku} onChange={set('sku')} placeholder="PROD-SKU-001" required />

            <Select label="Category" value={form.item_category} onChange={set('item_category')}>
              {['apparel', 'electronics', 'footwear', 'accessories', 'furniture', 'grocery', 'books', 'toys', 'beauty', 'sports']
                .map(c => <option key={c} value={c}>{c[0].toUpperCase() + c.slice(1)}</option>)}
            </Select>

            <Input label="Item value (₹)" type="number" value={form.item_value} onChange={set('item_value')}
              placeholder="799" min="0" step="0.01" required />

            <Select label="Condition" value={form.condition} onChange={set('condition')}>
              {[['unopened', 'Unopened'], ['like_new', 'Like new'], ['good', 'Good'], ['fair', 'Fair'], ['damaged', 'Damaged']]
                .map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
          </div>
        </Panel>

        <Panel eyebrow="Step two" title="The movement" style={{ marginTop: 'var(--s4)' }}>
          <div className="grid grid--2">
            <Input label="Origin pincode" value={form.origin_pincode} onChange={set('origin_pincode')}
              placeholder="400001" maxLength={6} pattern="\d{6}" required />
            <Input label="Destination pincode" value={form.destination_pincode} onChange={set('destination_pincode')}
              placeholder="110001" maxLength={6} pattern="\d{6}" required />
            <Input label="Actual weight (g)" type="number" value={form.weight_grams} onChange={set('weight_grams')}
              placeholder="300" min="1" required />
            <Input label="Volumetric weight (g)" type="number" value={form.volumetric_weight_grams}
              onChange={set('volumetric_weight_grams')} placeholder="400" min="1" required />

            <Select label="Courier" value={form.courier} onChange={set('courier')}>
              {['BlueDart', 'Delhivery', 'DTDC', 'Ekart', 'XpressBees', 'Shadowfax', 'Ecom Express', 'FedEx']
                .map(c => <option key={c} value={c}>{c}</option>)}
            </Select>

            <Select label="Return reason" value={form.return_reason_code} onChange={set('return_reason_code')}>
              {[['size_issue', 'Size issue'], ['damaged', 'Damaged'], ['not_as_described', 'Not as described'],
                ['wrong_item', 'Wrong item'], ['quality_issue', 'Quality issue'],
                ['change_of_mind', 'Change of mind'], ['defective', 'Defective']]
                .map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>

            <Select label="Payment mode" value={form.payment_mode} onChange={set('payment_mode')}>
              <option value="Prepaid">Prepaid</option>
              <option value="COD">Cash on delivery</option>
            </Select>

            <div style={{ display: 'flex', gap: 'var(--s5)', alignItems: 'center', paddingTop: 22 }}>
              <Checkbox label="Fragile" checked={form.fragile} onChange={set('fragile')} />
              <Checkbox label="Festive season" checked={form.festive} onChange={set('festive')} />
            </div>

            <div style={{ gridColumn: '1 / -1' }}>
              <Textarea label="Customer notes" value={form.customer_notes} onChange={set('customer_notes')}
                placeholder="What the customer said about the issue" rows={3} />
            </div>
          </div>

          <Divider />

          <div style={{ display: 'flex', gap: 'var(--s3)', alignItems: 'center', flexWrap: 'wrap' }}>
            <Button type="submit" loading={loading} icon={<Send size={14} />} size="lg">
              {loading ? 'Scoring' : 'Score this return'}
            </Button>
            <Button type="button" variant="ghost"
              onClick={() => { setForm(INIT); setResult(null); setError('') }}>
              Clear
            </Button>
            <span style={{ fontSize: 'var(--t-xs)', color: 'var(--text-faint)' }}>
              Five models run in one pass, typically under 10 ms.
            </span>
          </div>
        </Panel>
      </form>
    </div>
  )
}
