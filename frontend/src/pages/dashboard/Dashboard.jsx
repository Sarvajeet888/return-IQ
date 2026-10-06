import React, { useState, useEffect } from 'react'
import { formatMoney, formatScore } from '../../utils/money.js'
import { Package, RefreshCw, ArrowRight } from 'lucide-react'
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  AreaChart, Area, XAxis, YAxis, CartesianGrid, BarChart, Bar,
} from 'recharts'
import { Link } from 'react-router-dom'
import { api } from '../../utils/api.js'
import { useAuth } from '../../store/AuthContext.jsx'
import {
  Panel, Badge, PageHeader, Button, LoadingCenter, Alert, EmptyState,
  Metric, MetricRow, MonoValue, SignalBar, DataTable, StatusDot,
} from '../../components/ui/index.jsx'

/* ── Chart palette ────────────────────────────────────────────────────────
   Same rule everywhere: Iron is unresolved, Vermillion is resolved, Ash is
   the grid. Decision colours are the one exception — a decision needs to be
   distinguishable at a glance, so each keeps its status tone. */
const DECISION_COLORS = {
  accept: '#4A7C46',
  reject: '#A32E1C',
  refund_and_keep: '#4A6478',
  charge_return_fee: '#E3C04A',
}

const AXIS = { fill: '#6B7078', fontSize: 11, fontFamily: "'Martian Mono', monospace" }
const GRID = '#DDD7CD'

const TOOLTIP = {
  contentStyle: {
    background: '#15171B', border: 'none', borderRadius: 5,
    fontSize: 11, fontFamily: "'Martian Mono', monospace", padding: '7px 10px',
  },
  labelStyle: { color: '#EDE9E3', marginBottom: 3 },
  itemStyle: { color: '#A9A296' },
  cursor: { fill: 'rgba(107,112,120,0.07)' },
}

// PHASE 11: this page had its own currency formatter, which Phase 3 missed.
// Once the backend started sending money as { minor_units, currency, ... },
// Number(object) evaluated to NaN and these metrics rendered "₹NaN" — on the
// dashboard's headline figures. No test caught it because no test rendered
// this page. Now routed through the one shared formatter.
const inr = v => formatMoney(v, { decimals: false })

export default function Dashboard() {
  const { user } = useAuth()
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  async function load() {
    setLoading(true); setError('')
    try { setStats(await api.getDashboard()) }
    catch (e) { setError(e.response?.data?.detail || e.message) }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  if (loading) return <LoadingCenter text="Reading signal" />

  if (error) return (
    <div>
      <PageHeader title="Control room" eyebrow="Overview" />
      <Alert type="error" style={{ marginBottom: 'var(--s4)' }}>{error}</Alert>
      <Button variant="secondary" icon={<RefreshCw size={13} />} onClick={load}>Try again</Button>
    </div>
  )

  const pieData = Object.entries(stats?.decisions || {})
    .map(([k, v]) => ({ name: k.replace(/_/g, ' '), value: v, color: DECISION_COLORS[k] || '#6B7078' }))

  const monthlyData = (stats?.monthly_trend || [])
    .map(m => ({ ...m, month: m.month?.slice(5) || m.month }))

  const firstName = user?.full_name?.split(' ')[0]

  /* Recent returns — same fields as before, expressed through DataTable. */
  const recentColumns = [
    { key: 'platform_order_id', header: 'Order', mono: true,
      render: r => <MonoValue size={11.5} color="var(--text-primary)">{r.platform_order_id}</MonoValue> },
    { key: 'sku', header: 'SKU', maxWidth: 150 },
    { key: 'item_category', header: 'Category',
      render: r => <span style={{ color: 'var(--text-muted)' }}>{r.item_category}</span> },
    { key: 'item_value', header: 'Value', align: 'right',
      render: r => <MonoValue size={11.5} color="var(--text-muted)">{inr(r.item_value)}</MonoValue> },
    { key: 'cost', header: 'Predicted cost', align: 'right',
      render: r => r.prediction
        ? <MonoValue size={11.5} color="var(--text-primary)">{inr(r.prediction.predicted_cost)}</MonoValue>
        : '—' },
    { key: 'risk', header: 'Risk', width: 130,
      render: r => r.prediction ? <SignalBar value={Number(r.prediction.risk_score)} height={4} /> : '—' },
    { key: 'fraud', header: 'Fraud', align: 'right',
      render: r => r.prediction
        ? <MonoValue size={11.5} color={Number(r.prediction.fraud_score) > 60 ? 'var(--red)' : 'var(--text-muted)'}>
            {formatScore(r.prediction.fraud_score, { decimals: 0 })}
          </MonoValue>
        : '—' },
    { key: 'decision', header: 'Decision',
      render: r => r.prediction ? <Badge variant={r.prediction.routing_decision} /> : '—' },
  ]

  return (
    <div>
      <PageHeader
        eyebrow="Control room"
        title={firstName ? `Good day, ${firstName}` : 'Control room'}
        subtitle="Everything the platform has resolved since you were last here."
        actions={
          <Button variant="secondary" size="sm" icon={<RefreshCw size={13} />} onClick={load}>
            Refresh
          </Button>
        }
      />

      {/* ── Instrument panel — one strip, divided by rules ───────────────── */}
      <MetricRow>
        <Metric value={stats?.total_returns ?? 0} label="Returns processed" sub="all time" />
        <Metric value={inr(stats?.avg_predicted_cost)} label="Average cost" sub="per return" />
        <Metric value={inr(stats?.revenue_saved)} label="Value recovered" sub="via routing" tone="var(--vermillion)" />
        <Metric value={(stats?.avg_risk_score || 0).toFixed(1)} label="Average risk" sub="out of 100" />
        <Metric value={stats?.kpis?.fraud_flagged ?? 0} label="Flagged for fraud" sub="high risk" />
        <Metric value={`${(stats?.total_carbon_kg || 0).toFixed(1)} kg`} label="Carbon tracked" sub="CO₂" />
      </MetricRow>

      {/* ── Signals row ──────────────────────────────────────────────────── */}
      <div className="grid grid--split-1-2" style={{ marginTop: 'var(--s4)' }}>
        <Panel title="Decisions issued" eyebrow="Resolved">
          {pieData.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={172}>
                <PieChart>
                  <Pie data={pieData} cx="50%" cy="50%" innerRadius={50} outerRadius={74}
                    dataKey="value" paddingAngle={2} stroke="none">
                    {pieData.map((e, i) => <Cell key={i} fill={e.color} />)}
                  </Pie>
                  <Tooltip {...TOOLTIP} />
                </PieChart>
              </ResponsiveContainer>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 7, marginTop: 'var(--s4)' }}>
                {pieData.map(d => (
                  <div key={d.name} style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', fontSize: 'var(--t-xs)' }}>
                    <StatusDot tone={d.color} size={7} />
                    <span style={{ color: 'var(--text-secondary)', textTransform: 'capitalize', flex: 1 }}>{d.name}</span>
                    <MonoValue size={11.5}>{d.value}</MonoValue>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <EmptyState
              title="Nothing resolved yet"
              description="Score a return and its decision appears here."
              action={<Button size="sm" onClick={() => { window.location.href = '/new-return' }}>Score a return</Button>}
            />
          )}
        </Panel>

        <Panel title="Return volume" eyebrow="Last 6 months">
          {monthlyData.length > 0 ? (
            <ResponsiveContainer width="100%" height={244}>
              <AreaChart data={monthlyData} margin={{ top: 6, right: 6, bottom: 0, left: -18 }}>
                <defs>
                  <linearGradient id="signalFade" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#DE4B22" stopOpacity={0.18} />
                    <stop offset="100%" stopColor="#DE4B22" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="month" tick={AXIS} axisLine={false} tickLine={false} />
                <YAxis tick={AXIS} axisLine={false} tickLine={false} width={44} />
                <Tooltip {...TOOLTIP} />
                <Area type="monotone" dataKey="count" name="returns"
                  stroke="#DE4B22" strokeWidth={1.75} fill="url(#signalFade)"
                  dot={{ fill: '#DE4B22', r: 2.5, strokeWidth: 0 }}
                  activeDot={{ r: 4, strokeWidth: 0 }} />
              </AreaChart>
            </ResponsiveContainer>
          ) : <EmptyState title="No trend yet" description="Volume builds up here over time." />}
        </Panel>
      </div>

      {/* ── Category + platform readouts ─────────────────────────────────── */}
      <div className="grid grid--2" style={{ marginTop: 'var(--s4)' }}>
        <Panel title="Where returns come from" eyebrow="By category">
          {(stats?.category_breakdown?.length || 0) > 0 ? (
            <ResponsiveContainer width="100%" height={190}>
              <BarChart data={stats.category_breakdown} layout="vertical"
                margin={{ left: 0, right: 14, top: 0, bottom: 0 }}>
                <CartesianGrid stroke={GRID} horizontal={false} />
                <XAxis type="number" tick={AXIS} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="name" tick={AXIS} axisLine={false} tickLine={false} width={82} />
                <Tooltip {...TOOLTIP} />
                <Bar dataKey="value" name="returns" fill="#6B7078" radius={[0, 2, 2, 0]} barSize={13} />
              </BarChart>
            </ResponsiveContainer>
          ) : <EmptyState title="No category data" />}
        </Panel>

        <Panel title="Platform" eyebrow="Health">
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {[
              { label: 'Auto-approval rate', value: `${stats?.kpis?.auto_approval_rate ?? 0}%`, tone: 'var(--green)' },
              // These were once hardcoded constants presented as real
              // measurements. The backend now returns null and we say so
              // plainly — "Not measured" is honest, 0 would not be.
              { label: 'Average processing time',
                value: stats?.kpis?.avg_processing_time_hrs != null
                  ? `${stats.kpis.avg_processing_time_hrs} hrs` : 'Not measured',
                tone: stats?.kpis?.avg_processing_time_hrs != null ? 'var(--text-primary)' : 'var(--text-faint)' },
              { label: 'Customer satisfaction',
                value: stats?.kpis?.customer_satisfaction != null
                  ? `${stats.kpis.customer_satisfaction} / 5` : 'Not measured',
                tone: stats?.kpis?.customer_satisfaction != null ? 'var(--text-primary)' : 'var(--text-faint)' },
              { label: 'Average fraud score', value: `${(stats?.avg_fraud_score || 0).toFixed(1)} / 100`, tone: 'var(--text-primary)' },
            ].map(({ label, value, tone }, i) => (
              <div key={label} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '13px 0', borderTop: i === 0 ? 'none' : '1px solid var(--border)',
              }}>
                <span style={{ fontSize: 'var(--t-sm)', color: 'var(--text-secondary)' }}>{label}</span>
                <MonoValue size={13} color={tone}>{value}</MonoValue>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      {/* ── Live stream ──────────────────────────────────────────────────── */}
      <Panel
        pad={false}
        style={{ marginTop: 'var(--s4)' }}
        eyebrow="Live"
        title="Most recent returns"
        action={
          <Link to="/returns" style={{
            display: 'inline-flex', alignItems: 'center', gap: 5,
            fontSize: 'var(--t-xs)', color: 'var(--text-secondary)',
          }}>
            All returns <ArrowRight size={12} />
          </Link>
        }
      >
        <DataTable
          columns={recentColumns}
          rows={stats?.recent_returns || []}
          dense
          empty={
            <EmptyState
              icon={Package}
              title="No returns yet"
              description="Score your first return and it appears here immediately."
              action={<Button size="sm" onClick={() => { window.location.href = '/new-return' }}>Score a return</Button>}
            />
          }
        />
      </Panel>
    </div>
  )
}
