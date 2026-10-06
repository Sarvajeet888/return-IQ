import React, { useState, useEffect } from 'react'
import { formatMoney } from '../../utils/money.js'
import { RefreshCw } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell,
} from 'recharts'
import { api } from '../../utils/api.js'
import {
  Panel, PageHeader, Button, LoadingCenter, Alert,
  Metric, MetricRow, MonoValue, EmptyState, StatusDot,
} from '../../components/ui/index.jsx'

/* ═══════════════════════════════════════════════════════════════════════════
   Analytics — chart rules, applied without exception:

       Iron       raw / unresolved data
       Vermillion the resolved or final series
       Ash        grid lines
       Bone       background

   No rainbow charts. Where a chart needs more than two tones it steps
   through the noise→signal ramp rather than picking new hues.
   ═══════════════════════════════════════════════════════════════════════ */

const RAMP = ['#6B7078', '#8A857C', '#A89F91', '#DE4B22']  // noise → signal
const NOISE = '#6B7078'
const SIGNAL = '#DE4B22'
const GRID = '#DDD7CD'
const AXIS = { fill: '#6B7078', fontSize: 11, fontFamily: "'Martian Mono', monospace" }

const TOOLTIP = {
  contentStyle: {
    background: '#15171B', border: 'none', borderRadius: 5,
    fontSize: 11, fontFamily: "'Martian Mono', monospace", padding: '7px 10px',
  },
  labelStyle: { color: '#EDE9E3', marginBottom: 3 },
  itemStyle: { color: '#A9A296' },
  cursor: { fill: 'rgba(107,112,120,0.07)' },
}

/* Risk is the one place a status ramp is correct: low/medium/high are
   qualitative states, not points on a noise→signal scale. */
const RISK_TONES = { low: '#4A7C46', medium: '#E3C04A', high: '#A32E1C', critical: '#A32E1C' }

// PHASE 11: this page had its own currency formatter, which Phase 3 missed.
// Once the backend started sending money as { minor_units, currency, ... },
// Number(object) evaluated to NaN and these metrics rendered "₹NaN" — on the
// dashboard's headline figures. No test caught it because no test rendered
// this page. Now routed through the one shared formatter.
const inr = v => formatMoney(v, { decimals: false })

export default function Analytics() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  async function load() {
    setLoading(true); setError('')
    try { setData(await api.getAnalytics()) }
    catch (e) { setError(e.response?.data?.detail || e.message) }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  if (loading) return <LoadingCenter text="Crunching" />
  if (error) return (
    <div>
      <PageHeader eyebrow="Control room" title="Analytics" />
      <Alert type="error">{error}</Alert>
    </div>
  )

  const riskData = data?.risk_distribution || []

  return (
    <div>
      <PageHeader
        eyebrow="Control room"
        title="Analytics"
        subtitle="The shape of your returns, cut four ways."
        actions={
          <Button variant="secondary" size="sm" icon={<RefreshCw size={13} />} onClick={load}>
            Refresh
          </Button>
        }
      />

      <MetricRow>
        <Metric value={data?.total_returns ?? 0} label="Total returns" />
        <Metric value={inr(data?.revenue_saved)} label="Value recovered" tone="var(--vermillion)" />
        <Metric value={(data?.avg_risk_score || 0).toFixed(1)} label="Average risk" sub="out of 100" />
        <Metric value={(data?.avg_fraud_score || 0).toFixed(1)} label="Average fraud" sub="out of 100" />
        <Metric value={`${(data?.total_carbon_kg || 0).toFixed(1)} kg`} label="Carbon tracked" sub="CO₂" />
      </MetricRow>

      <div className="grid grid--2" style={{ marginTop: 'var(--s4)' }}>

        {/* ── Why returns happen ─────────────────────────────────────────── */}
        <Panel eyebrow="Cause" title="Why returns happen">
          {(data?.reason_breakdown?.length || 0) > 0 ? (
            <ResponsiveContainer width="100%" height={216}>
              <BarChart data={data.reason_breakdown} layout="vertical" margin={{ left: 0, right: 16 }}>
                <CartesianGrid stroke={GRID} horizontal={false} />
                <XAxis type="number" tick={AXIS} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="name" tick={AXIS} axisLine={false} tickLine={false}
                  width={100} tickFormatter={v => v.replace(/_/g, ' ')} />
                <Tooltip {...TOOLTIP} />
                {/* The leading reason resolves to Vermillion; the rest stay noise. */}
                <Bar dataKey="value" name="returns" radius={[0, 2, 2, 0]} barSize={13}>
                  {data.reason_breakdown.map((_, i) => (
                    <Cell key={i} fill={i === 0 ? SIGNAL : NOISE} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : <EmptyState title="No reason data" />}
        </Panel>

        {/* ── Value bands ────────────────────────────────────────────────── */}
        <Panel eyebrow="Value" title="Returns by item value">
          {(data?.value_buckets?.length || 0) > 0 ? (
            <ResponsiveContainer width="100%" height={216}>
              <BarChart data={data.value_buckets} margin={{ left: -12, right: 4 }}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="range" tick={AXIS} axisLine={false} tickLine={false} />
                <YAxis tick={AXIS} axisLine={false} tickLine={false} width={42} />
                <Tooltip {...TOOLTIP} />
                <Bar dataKey="count" name="returns" fill={NOISE} radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : <EmptyState title="No value data" />}
        </Panel>

        {/* ── Risk mix ───────────────────────────────────────────────────── */}
        <Panel eyebrow="Risk" title="How risk is distributed">
          {riskData.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={186}>
                <PieChart>
                  <Pie data={riskData} cx="50%" cy="50%" innerRadius={52} outerRadius={78}
                    dataKey="count" nameKey="level" paddingAngle={2} stroke="none">
                    {riskData.map((d, i) => (
                      <Cell key={i} fill={RISK_TONES[String(d.level).toLowerCase()] || RAMP[i % RAMP.length]} />
                    ))}
                  </Pie>
                  <Tooltip {...TOOLTIP} />
                </PieChart>
              </ResponsiveContainer>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 7, marginTop: 'var(--s4)' }}>
                {riskData.map((d, i) => (
                  <div key={d.level} style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', fontSize: 'var(--t-xs)' }}>
                    <StatusDot tone={RISK_TONES[String(d.level).toLowerCase()] || RAMP[i % RAMP.length]} size={7} />
                    <span style={{ color: 'var(--text-secondary)', textTransform: 'capitalize', flex: 1 }}>{d.level}</span>
                    <MonoValue size={11.5}>{d.count}</MonoValue>
                  </div>
                ))}
              </div>
            </>
          ) : <EmptyState title="No risk data" />}
        </Panel>

        {/* ── Couriers ───────────────────────────────────────────────────── */}
        <Panel eyebrow="Carrier" title="Returns by courier">
          {(data?.courier_breakdown?.length || 0) > 0 ? (
            <ResponsiveContainer width="100%" height={216}>
              <BarChart data={data.courier_breakdown} margin={{ left: -12, right: 4 }}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="name" tick={AXIS} axisLine={false} tickLine={false} />
                <YAxis tick={AXIS} axisLine={false} tickLine={false} width={42} />
                <Tooltip {...TOOLTIP} />
                <Bar dataKey="value" name="returns" radius={[2, 2, 0, 0]}>
                  {data.courier_breakdown.map((_, i) => (
                    <Cell key={i} fill={RAMP[Math.min(i, RAMP.length - 1)]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : <EmptyState title="No courier data" />}
        </Panel>
      </div>

      {/* ── Trend ─────────────────────────────────────────────────────────── */}
      <Panel eyebrow="Over time" title="Monthly volume" style={{ marginTop: 'var(--s4)' }}>
        {(data?.monthly_trend?.length || 0) > 0 ? (
          <ResponsiveContainer width="100%" height={196}>
            <BarChart data={data.monthly_trend} margin={{ left: -12, right: 4 }}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="month" tick={AXIS} axisLine={false} tickLine={false} />
              <YAxis tick={AXIS} axisLine={false} tickLine={false} width={42} />
              <Tooltip {...TOOLTIP} />
              {/* Most recent month resolves to Vermillion — it is the live one. */}
              <Bar dataKey="count" name="returns" radius={[2, 2, 0, 0]}>
                {data.monthly_trend.map((_, i) => (
                  <Cell key={i} fill={i === data.monthly_trend.length - 1 ? SIGNAL : NOISE} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : <EmptyState title="No trend data" description="Volume builds up here over time." />}
      </Panel>
    </div>
  )
}
