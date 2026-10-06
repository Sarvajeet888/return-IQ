import React, { useState } from 'react'
import { Download, BarChart2, Shield, Leaf, Users } from 'lucide-react'
import { api } from '../../utils/api.js'
import {
  Panel, PageHeader, Button, Alert, DataTable, MonoValue,
  EmptyState, Divider,
} from '../../components/ui/index.jsx'

/* Export logic — the CSV blob download and every report endpoint — is the
   previous implementation unchanged. Only the builder UI around it is new. */

const REPORTS = [
  { key: 'summary',   title: 'Summary',   icon: BarChart2, blurb: 'Every return with its prediction and routing decision.' },
  { key: 'fraud',     title: 'Fraud',     icon: Shield,    blurb: 'High-risk returns, ordered by fraud score.' },
  { key: 'carbon',    title: 'Carbon',    icon: Leaf,      blurb: 'CO₂ footprint broken down by courier and category.' },
  { key: 'customers', title: 'Customers', icon: Users,     blurb: 'Return rates and fraud patterns per customer.' },
]

export default function Reports() {
  const [active, setActive] = useState(null)
  const [reportData, setReportData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState({ type: '', text: '' })
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const range = { date_from: dateFrom || undefined, date_to: dateTo || undefined }

  const FETCHERS = {
    summary: () => api.getSummaryReport(range),
    fraud: () => api.getFraudReport(range),
    carbon: () => api.getCarbonReport(range),
    customers: () => api.getCustomerReport(),
  }

  async function generate(key) {
    setLoading(true); setActive(key); setMsg({ type: '', text: '' })
    try {
      setReportData(await FETCHERS[key]())
    } catch (e) {
      setMsg({ type: 'error', text: e.response?.data?.detail || e.message })
    } finally { setLoading(false) }
  }

  async function downloadCSV(key) {
    try {
      const blob = await api.downloadReport(key, range)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${key}_report.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setMsg({ type: 'error', text: `Export failed. ${e.message}` })
    }
  }

  const activeReport = REPORTS.find(r => r.key === active)

  /* Build table columns from whatever shape the report returns. */
  const columns = reportData?.rows?.length
    ? Object.keys(reportData.rows[0]).map(c => ({
        key: c,
        header: c.replace(/_/g, ' '),
        maxWidth: 220,
        render: row => {
          const v = row[c]
          if (v === null || v === undefined) return <span style={{ color: 'var(--text-faint)' }}>—</span>
          if (typeof v === 'number') return <MonoValue size={11.5} weight={400}>{v.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</MonoValue>
          return String(v)
        },
      }))
    : []

  return (
    <div>
      <PageHeader
        eyebrow="Intelligence"
        title="Reports"
        subtitle="Build a report, read it here, take the CSV with you."
      />

      {msg.text && <Alert type={msg.type || 'info'} style={{ marginBottom: 'var(--s4)' }}>{msg.text}</Alert>}

      {/* ── Builder ──────────────────────────────────────────────────────── */}
      <Panel eyebrow="Build" title="Choose a report">
        <div style={{ display: 'flex', gap: 'var(--s4)', flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 'var(--s5)' }}>
          <div>
            <label className="label" style={{ display: 'block', marginBottom: 5 }}>From</label>
            <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
              style={{
                padding: '7px 10px', borderRadius: 'var(--r)', border: '1px solid var(--border-2)',
                background: 'var(--bone)', color: 'var(--text-primary)',
                fontSize: 'var(--t-sm)', fontFamily: 'var(--font-mono)',
              }} />
          </div>
          <div>
            <label className="label" style={{ display: 'block', marginBottom: 5 }}>To</label>
            <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
              style={{
                padding: '7px 10px', borderRadius: 'var(--r)', border: '1px solid var(--border-2)',
                background: 'var(--bone)', color: 'var(--text-primary)',
                fontSize: 'var(--t-sm)', fontFamily: 'var(--font-mono)',
              }} />
          </div>
          {(dateFrom || dateTo) && (
            <Button variant="ghost" size="sm" onClick={() => { setDateFrom(''); setDateTo('') }}>
              Clear dates
            </Button>
          )}
          <span style={{ fontSize: 'var(--t-xs)', color: 'var(--text-faint)', marginLeft: 'auto' }}>
            Leave dates empty to cover everything on record.
          </span>
        </div>

        <Divider style={{ margin: '0 0 var(--s4)' }} />

        {/* Report list — ruled rows, not a card grid. Each row is one
            report, its description, and its two actions. */}
        <div>
          {REPORTS.map(({ key, title, icon: Icon, blurb }, i) => {
            const on = active === key
            return (
              <div key={key} style={{
                display: 'flex', alignItems: 'center', gap: 'var(--s4)',
                padding: 'var(--s4) 0',
                borderTop: i === 0 ? 'none' : '1px solid var(--border)',
                flexWrap: 'wrap',
              }}>
                <Icon size={16} strokeWidth={1.6}
                  style={{ color: on ? 'var(--vermillion)' : 'var(--text-muted)', flexShrink: 0 }} />
                <div style={{ flex: '1 1 260px', minWidth: 0 }}>
                  <div style={{ fontSize: 'var(--t-sm)', fontWeight: 500, marginBottom: 2 }}>{title}</div>
                  <div style={{ fontSize: 'var(--t-xs)', color: 'var(--text-muted)' }}>{blurb}</div>
                </div>
                <div style={{ display: 'flex', gap: 'var(--s2)', flexShrink: 0 }}>
                  <Button size="sm" variant={on ? 'primary' : 'secondary'}
                    loading={loading && on} onClick={() => generate(key)}>
                    {on && reportData ? 'Rebuild' : 'Build'}
                  </Button>
                  <Button size="sm" variant="ghost" icon={<Download size={12} />}
                    onClick={() => downloadCSV(key)}>
                    CSV
                  </Button>
                </div>
              </div>
            )
          })}
        </div>
      </Panel>

      {/* ── Result ───────────────────────────────────────────────────────── */}
      {reportData && (
        <Panel
          pad={false}
          className="animate-in"
          style={{ marginTop: 'var(--s4)' }}
          eyebrow={`Generated ${new Date(reportData.generated_at).toLocaleString('en-IN')}`}
          title={`${activeReport?.title} report — ${reportData.rows?.length ?? 0} rows`}
          action={
            <Button size="sm" icon={<Download size={13} />} onClick={() => downloadCSV(active)}>
              Download CSV
            </Button>
          }
        >
          {/* Totals strip */}
          {reportData.totals && Object.keys(reportData.totals).length > 0 && (
            <div style={{
              display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
              borderBottom: '1px solid var(--border)',
            }}>
              {Object.entries(reportData.totals)
                .filter(([, v]) => typeof v !== 'object')
                .map(([k, v], i) => (
                  <div key={k} style={{
                    padding: 'var(--s4) var(--s5)',
                    borderLeft: i === 0 ? 'none' : '1px solid var(--border)',
                  }}>
                    <div style={{ fontSize: 'var(--t-micro)', color: 'var(--text-muted)', marginBottom: 5 }}>
                      {k.replace(/_/g, ' ')}
                    </div>
                    <MonoValue size={18}>
                      {typeof v === 'number' ? v.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : String(v)}
                    </MonoValue>
                  </div>
                ))}
            </div>
          )}

          <div className="scroll-y" style={{ maxHeight: 520 }}>
            <DataTable
              columns={columns}
              rows={reportData.rows || []}
              dense
              empty={
                <EmptyState
                  title="No rows in this range"
                  description="Widen the date range, or clear it to cover everything."
                  action={<Button variant="secondary" size="sm"
                    onClick={() => { setDateFrom(''); setDateTo(''); generate(active) }}>
                    Clear dates and rebuild
                  </Button>}
                />
              }
            />
          </div>
        </Panel>
      )}
    </div>
  )
}
