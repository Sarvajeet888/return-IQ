import React, { useState, useEffect } from 'react'
import { formatMoney, formatScore } from '../../utils/money'
import { RefreshCw, Search, Package, X } from 'lucide-react'
import { api } from '../../utils/api.js'
import {
  Panel, Badge, Button, PageHeader, LoadingCenter, Alert, EmptyState,
  SignalBar, DataTable, MonoValue, Divider,
} from '../../components/ui/index.jsx'

/* Colour rule on this page:
     Iron       — an unresolved return (no prediction yet)
     Vermillion — the decision, and the selected row's marker
   Nothing else is allowed to carry accent colour. */

// Phase 3: local formatter removed. One shared helper, exact server data.
const inr = v => formatMoney(v, { decimals: false })

const FILTERS = [
  { key: 'status',   label: 'Status',   opts: ['pending', 'prediction_done', 'approved', 'rejected', 'in_transit', 'refunded'] },
  { key: 'decision', label: 'Decision', opts: ['accept', 'reject', 'refund_and_keep', 'charge_return_fee'] },
  { key: 'category', label: 'Category', opts: ['apparel', 'electronics', 'footwear', 'accessories', 'furniture'] },
]

export default function ReturnsList() {
  const [data, setData] = useState({ items: [], total: 0, page: 1, page_size: 20, total_pages: 1 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [filters, setFilters] = useState({ status: '', decision: '', category: '' })
  const [selected, setSelected] = useState(null)
  const [page, setPage] = useState(1)

  async function load(p = 1) {
    setLoading(true); setError('')
    try {
      const params = {
        page: p, page_size: 20, search: search || undefined,
        ...Object.fromEntries(Object.entries(filters).filter(([, v]) => v)),
      }
      const res = await api.getReturns(params)
      setData(res); setPage(p)
    } catch (e) { setError(e.response?.data?.detail || e.message) }
    finally { setLoading(false) }
  }

  useEffect(() => {
    const t = setTimeout(() => load(1), 300)
    return () => clearTimeout(t)
  }, [search, filters])

  const dirty = search || Object.values(filters).some(Boolean)

  const columns = [
    { key: 'platform_order_id', header: 'Order',
      render: r => <MonoValue size={11.5} color="var(--text-primary)">{r.platform_order_id}</MonoValue> },
    { key: 'sku', header: 'SKU', maxWidth: 150 },
    { key: 'item_category', header: 'Category',
      render: r => <span style={{ color: 'var(--text-muted)' }}>{r.item_category}</span> },
    { key: 'item_value', header: 'Value', align: 'right',
      render: r => <MonoValue size={11.5} color="var(--text-muted)">{inr(r.item_value)}</MonoValue> },
    { key: 'cost', header: 'Cost', align: 'right',
      render: r => r.prediction
        ? <MonoValue size={11.5}>{inr(r.prediction.predicted_cost_inr)}</MonoValue>
        : <span style={{ color: 'var(--text-faint)' }}>—</span> },
    { key: 'risk', header: 'Risk', width: 130,
      render: r => r.prediction
        ? <SignalBar value={Number(r.prediction.risk_score)} height={4} />
        : <span style={{ color: 'var(--text-faint)' }}>unscored</span> },
    { key: 'decision', header: 'Decision',
      render: r => r.prediction
        ? <Badge variant={r.prediction.routing_decision} />
        : <Badge variant="inactive">Unresolved</Badge> },
    { key: 'status', header: 'Status',
      render: r => <span style={{ color: 'var(--text-muted)' }}>{r.status?.replace(/_/g, ' ')}</span> },
    { key: 'created_at', header: 'Date', align: 'right',
      render: r => <MonoValue size={11} color="var(--text-faint)">
        {r.created_at ? new Date(r.created_at).toLocaleDateString('en-IN') : '—'}
      </MonoValue> },
  ]

  return (
    <div>
      <PageHeader
        eyebrow="Returns"
        title="All returns"
        subtitle={`${data.total} request${data.total === 1 ? '' : 's'} on record.`}
        actions={
          <Button variant="secondary" size="sm" icon={<RefreshCw size={13} />} onClick={() => load(page)}>
            Refresh
          </Button>
        }
      />

      {error && <Alert type="error" style={{ marginBottom: 'var(--s4)' }}>{error}</Alert>}

      <div style={{ display: 'flex', gap: 'var(--s4)', alignItems: 'flex-start' }}>
        <div style={{ flex: 1, minWidth: 0 }}>

          {/* ── Filter strip — a single ruled row, not a card ───────────── */}
          <div style={{
            display: 'flex', gap: 'var(--s2)', flexWrap: 'wrap', alignItems: 'center',
            paddingBottom: 'var(--s3)', marginBottom: 'var(--s4)',
            borderBottom: '1px solid var(--border)',
          }}>
            <div style={{ position: 'relative', flex: '1 1 240px', minWidth: 200 }}>
              <Search size={13} style={{
                position: 'absolute', left: 0, top: '50%', transform: 'translateY(-50%)',
                color: 'var(--text-muted)', pointerEvents: 'none',
              }} />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search order, SKU, or category"
                style={{
                  width: '100%', background: 'transparent', border: 'none',
                  borderBottom: '1px solid transparent', padding: '6px 0 6px 22px',
                  color: 'var(--text-primary)', fontSize: 'var(--t-sm)', outline: 'none',
                }}
              />
            </div>

            {FILTERS.map(({ key, label, opts }) => (
              <select
                key={key}
                value={filters[key]}
                onChange={e => setFilters(f => ({ ...f, [key]: e.target.value }))}
                style={{
                  background: filters[key] ? 'var(--brand-subtle)' : 'var(--surface)',
                  border: `1px solid ${filters[key] ? 'var(--brand-border)' : 'var(--border-2)'}`,
                  borderRadius: 'var(--r)', padding: '5px 9px',
                  color: filters[key] ? 'var(--brand-dark)' : 'var(--text-muted)',
                  fontSize: 'var(--t-xs)', outline: 'none', cursor: 'pointer',
                }}
              >
                <option value="">{label}</option>
                {opts.map(o => <option key={o} value={o}>{o.replace(/_/g, ' ')}</option>)}
              </select>
            ))}

            {dirty && (
              <Button variant="ghost" size="sm"
                onClick={() => { setSearch(''); setFilters({ status: '', decision: '', category: '' }) }}>
                Clear
              </Button>
            )}
          </div>

          {loading ? <LoadingCenter /> : (
            <Panel pad={false}>
              <DataTable
                columns={columns}
                rows={data.items}
                dense
                selectedKey={selected?.id}
                onRowClick={r => setSelected(s => (s?.id === r.id ? null : r))}
                empty={
                  <EmptyState
                    icon={Package}
                    title={dirty ? 'Nothing matches those filters' : 'No returns yet'}
                    description={dirty
                      ? 'Widen the search or clear the filters to see more.'
                      : 'Score your first return and it appears in this table.'}
                    action={dirty
                      ? <Button variant="secondary" size="sm"
                          onClick={() => { setSearch(''); setFilters({ status: '', decision: '', category: '' }) }}>
                          Clear filters
                        </Button>
                      : <Button size="sm" onClick={() => { window.location.href = '/new-return' }}>Score a return</Button>}
                  />
                }
              />

              {data.total_pages > 1 && (
                <div style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: 'var(--s3) var(--s5)', borderTop: '1px solid var(--border)',
                }}>
                  <MonoValue size={11} color="var(--text-muted)" weight={400}>
                    {((page - 1) * 20) + 1}–{Math.min(page * 20, data.total)} of {data.total}
                  </MonoValue>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => load(page - 1)}>
                      Previous
                    </Button>
                    <Button variant="secondary" size="sm" disabled={page >= data.total_pages} onClick={() => load(page + 1)}>
                      Next
                    </Button>
                  </div>
                </div>
              )}
            </Panel>
          )}
        </div>

        {/* ── Detail panel ─────────────────────────────────────────────────
            Reads top to bottom as: what arrived → what the model made of it. */}
        {selected && (
          <aside className="slide-in hide-mobile" style={{ width: 320, flexShrink: 0 }}>
            <Panel
              style={{ position: 'sticky', top: 'calc(var(--topbar-h) + var(--s4))' }}
              eyebrow="Return detail"
              title={selected.platform_order_id}
              action={
                <button onClick={() => setSelected(null)} aria-label="Close detail"
                  style={{ color: 'var(--text-muted)', display: 'flex', padding: 2 }}>
                  <X size={15} />
                </button>
              }
            >
              <div className="eyebrow" style={{ marginBottom: 'var(--s3)' }}>Measurement</div>
              <DetailList rows={[
                ['SKU', selected.sku],
                ['Category', selected.item_category],
                ['Item value', inr(selected.item_value)],
                ['Condition', selected.condition || '—'],
                ['Courier', selected.courier],
                ['Payment', selected.payment_mode],
                ['Route', `${selected.origin_pincode} → ${selected.destination_pincode}`],
                ['Weight', `${selected.weight_grams}g · vol ${selected.volumetric_weight_grams}g`],
                ['Reason', selected.return_reason_code?.replace(/_/g, ' ')],
                ['Fragile', selected.fragile ? 'Yes' : 'No'],
                ['Festive', selected.festive ? 'Yes' : 'No'],
              ]} />

              {selected.prediction ? (
                <>
                  <Divider />
                  <div className="eyebrow eyebrow--signal" style={{ marginBottom: 'var(--s3)' }}>Estimate</div>

                  <div style={{ marginBottom: 'var(--s4)' }}>
                    <Badge variant={selected.prediction.routing_decision} />
                  </div>

                  <DetailList rows={[
                    ['Predicted cost', inr(selected.prediction.predicted_cost_inr)],
                    ['Risk', formatScore(selected.prediction.risk_score, { suffix: ' / 100' })],
                    ['Fraud', `${Number(selected.prediction.fraud_score || 0).toFixed(1)} / 100`],
                    ['Damage probability', `${((selected.prediction.damage_probability || 0) * 100).toFixed(0)}%`],
                    ['Resale value', inr(selected.prediction.resale_value_estimate)],
                    ['Carbon', `${selected.prediction.carbon_footprint_kg} kg`],
                    ['Confidence', `${((selected.prediction.confidence_score || 0) * 100).toFixed(1)}%`],
                    ['Model', selected.prediction.model_version],
                    ['Latency', formatScore(selected.prediction.inference_latency_ms, { suffix: ' ms' })],
                  ]} signal />
                </>
              ) : (
                <>
                  <Divider />
                  <div style={{ fontSize: 'var(--t-xs)', color: 'var(--text-muted)', lineHeight: 1.6 }}>
                    This return has not been scored yet, so there is no estimate to show.
                  </div>
                </>
              )}
            </Panel>
          </aside>
        )}
      </div>
    </div>
  )
}

/* A label/value list ruled between rows. `signal` renders values in the
   resolved tone, so the estimate block reads differently from the raw
   measurement block above it. */
function DetailList({ rows, signal = false }) {
  return (
    <div>
      {rows.map(([label, value], i) => (
        <div key={label} style={{
          display: 'flex', justifyContent: 'space-between', gap: 'var(--s3)',
          padding: '7px 0', borderTop: i === 0 ? 'none' : '1px solid var(--border)',
        }}>
          <span style={{ fontSize: 'var(--t-xs)', color: 'var(--text-muted)', flexShrink: 0 }}>{label}</span>
          <MonoValue size={11.5} color={signal ? 'var(--text-primary)' : 'var(--text-secondary)'}
            style={{ textAlign: 'right', whiteSpace: 'normal', wordBreak: 'break-word' }}>
            {value}
          </MonoValue>
        </div>
      ))}
    </div>
  )
}
