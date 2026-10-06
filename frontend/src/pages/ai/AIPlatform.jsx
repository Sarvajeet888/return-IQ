import React, { useState, useEffect } from 'react'
import { formatMoney, formatPercent } from '../../utils/money'
import { Eye, MessageSquare, RefreshCw } from 'lucide-react'
import { api } from '../../utils/api.js'
import {
  Panel, PageHeader, Button, Alert, LoadingCenter, Badge, Tabs,
  Metric, MetricRow, MonoValue, SignalBar, DataTable, EmptyState,
  Input, Textarea, StatusDot, Divider,
} from '../../components/ui/index.jsx'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'

/* Chart rule: noise first, signal last. */
const SERIES = ['var(--chart-noise)', 'var(--chart-mid)', 'var(--chart-accent)', 'var(--chart-signal)']

const TOOLTIP = {
  contentStyle: {
    background: '#15171B', border: 'none', borderRadius: 5,
    fontSize: 11, fontFamily: "'Martian Mono', monospace", padding: '7px 10px',
  },
  labelStyle: { color: '#EDE9E3' }, itemStyle: { color: '#A9A296' },
}

/* ── Pipeline ─────────────────────────────────────────────────────────────
   The five stages a return passes through, drawn as one horizontal run.
   This replaces the old "model status" card: it shows the shape of the
   system rather than listing it. */
function Pipeline({ latencyMs }) {
  const stages = [
    { n: '01', label: 'Ingest', note: 'return received' },
    { n: '02', label: 'Features', note: 'mapped and encoded' },
    { n: '03', label: 'Score', note: '5 models, one pass' },
    { n: '04', label: 'Route', note: 'decision selected' },
    { n: '05', label: 'Emit', note: 'confidence attached' },
  ]
  return (
    <Panel
      eyebrow="Inference pipeline"
      title="What happens to a return"
      action={latencyMs != null && (
        <MonoValue size={12} color="var(--text-muted)">{latencyMs} ms end to end</MonoValue>
      )}
      pad={false}
    >
      <div style={{ display: 'grid', gridTemplateColumns: `repeat(${stages.length}, minmax(0,1fr))` }}>
        {stages.map((s, i) => {
          const last = i === stages.length - 1
          return (
            <div key={s.n} style={{
              padding: 'var(--s5)',
              borderLeft: i === 0 ? 'none' : '1px solid var(--border)',
              position: 'relative',
            }}>
              <div style={{
                fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.1em',
                color: last ? 'var(--vermillion)' : 'var(--text-faint)', marginBottom: 8,
              }}>
                {s.n}
              </div>
              <div style={{ fontSize: 'var(--t-sm)', fontWeight: 500, marginBottom: 3 }}>{s.label}</div>
              <div style={{ fontSize: 'var(--t-micro)', color: 'var(--text-muted)' }}>{s.note}</div>

              {/* The signal rule tightening across the run */}
              <div style={{
                marginTop: 'var(--s4)', height: 2, borderRadius: 1,
                background: last ? 'var(--vermillion)' : 'var(--surface-3)',
                opacity: last ? 1 : 0.4 + i * 0.12,
              }} />
            </div>
          )
        })}
      </div>
    </Panel>
  )
}

export default function AIPlatform() {
  const [tab, setTab] = useState('performance')
  const [perf, setPerf] = useState(null)
  const [history, setHistory] = useState([])
  const [histTotal, setHistTotal] = useState(0)
  const [histPage, setHistPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(null)
  const [explain, setExplain] = useState(null)
  const [explainLoading, setExplainLoading] = useState(false)
  const [msg, setMsg] = useState({ type: '', text: '' })
  const [feedback, setFeedback] = useState({ predId: '', accurate: null, comments: '' })

  useEffect(() => { loadTab(tab) }, [tab, histPage])

  async function loadTab(t) {
    setLoading(true)
    try {
      if (t === 'performance') {
        setPerf(await api.getAiPerformance())
      } else if (t === 'history') {
        const r = await api.getPredictionHistory({ page: histPage, page_size: 20 })
        setHistory(r.items); setHistTotal(r.total)
      }
    } catch (e) { setMsg({ type: 'error', text: e.message }) }
    finally { setLoading(false) }
  }

  async function loadExplanation(returnId) {
    setExplainLoading(true); setExplain(null)
    try { setExplain(await api.explainPrediction(returnId)) }
    catch (e) { setMsg({ type: 'error', text: e.message }) }
    finally { setExplainLoading(false) }
  }

  async function submitFeedback() {
    try {
      await api.submitFeedback({
        prediction_id: feedback.predId,
        was_accurate: feedback.accurate,
        comments: feedback.comments,
      })
      setMsg({ type: 'success', text: 'Feedback recorded. It feeds the next training run.' })
      setFeedback({ predId: '', accurate: null, comments: '' })
    } catch (e) { setMsg({ type: 'error', text: e.message }) }
  }

  const historyColumns = [
    { key: 'order_id', header: 'Order',
      render: p => <MonoValue size={11.5} color="var(--text-primary)">{p.order_id}</MonoValue> },
    { key: 'routing_decision', header: 'Decision',
      render: p => <Badge variant={p.routing_decision}>{p.routing_decision?.replace(/_/g, ' ')}</Badge> },
    { key: 'risk_score', header: 'Risk', width: 120,
      render: p => <SignalBar value={p.risk_score ?? 0} height={4} /> },
    { key: 'fraud_score', header: 'Fraud', align: 'right',
      render: p => <MonoValue size={11.5} color={p.fraud_score > 70 ? 'var(--red)' : 'var(--text-muted)'}>
        {p.fraud_score?.toFixed(0)}
      </MonoValue> },
    { key: 'confidence_score', header: 'Confidence', align: 'right',
      render: p => <MonoValue size={11.5}>{formatPercent(p.confidence_score)}</MonoValue> },
    { key: 'predicted_cost_inr', header: 'Cost', align: 'right',
      render: p => <MonoValue size={11.5}>{formatMoney(p.predicted_cost, { decimals: false })}</MonoValue> },
    { key: 'model_version', header: 'Model',
      render: p => <MonoValue size={11} color="var(--text-faint)" weight={400}>{p.model_version}</MonoValue> },
    { key: 'created_at', header: 'Date', align: 'right',
      render: p => <MonoValue size={11} color="var(--text-faint)" weight={400}>
        {new Date(p.created_at).toLocaleDateString('en-IN')}
      </MonoValue> },
    { key: 'action', header: '', align: 'right',
      render: p => (
        <Button size="sm" variant="ghost" icon={<Eye size={12} />}
          onClick={() => { setTab('explain'); setSelected(p.return_id); loadExplanation(p.return_id) }}>
          Explain
        </Button>
      ) },
  ]

  return (
    <div>
      <PageHeader
        eyebrow="Intelligence"
        title="Models"
        subtitle="What the models predicted, why they predicted it, and how well they are holding up."
        actions={
          <Button variant="secondary" size="sm" icon={<RefreshCw size={13} />} onClick={() => loadTab(tab)}>
            Refresh
          </Button>
        }
      />

      {msg.text && <Alert type={msg.type || 'info'} style={{ marginBottom: 'var(--s4)' }}>{msg.text}</Alert>}

      <div style={{ marginBottom: 'var(--s6)' }}>
        <Tabs
          active={tab}
          onChange={setTab}
          tabs={[
            ['performance', 'Performance'],
            ['history', 'Prediction history'],
            ['explain', 'Explain'],
            ['feedback', 'Feedback'],
          ]}
        />
      </div>

      {loading ? <LoadingCenter /> : (
        <>
          {/* ── PERFORMANCE ───────────────────────────────────────────────── */}
          {tab === 'performance' && perf && (
            <div className="stack">
              <MetricRow>
                <Metric value={perf.total_predictions ?? 0} label="Predictions served" />
                <Metric value={formatPercent(perf.avg_confidence)} label="Average confidence" tone="var(--vermillion)" />
                <Metric value={perf.avg_risk_score?.toFixed(1) ?? '—'} label="Average risk" sub="out of 100" />
                <Metric value={perf.label_collection?.fraud_labels_collected ?? 0} label="Fraud labels collected"
                  sub={perf.label_collection?.fraud_training_ready ? 'ready to train' : 'collecting'} />
              </MetricRow>

              <Pipeline />

              <div className="grid grid--2">
                <Panel eyebrow="Output" title="Decision distribution">
                  {Object.keys(perf.decision_distribution || {}).length > 0 ? (
                    <ResponsiveContainer width="100%" height={210}>
                      <PieChart>
                        <Pie
                          data={Object.entries(perf.decision_distribution || {}).map(([k, v]) => ({ name: k.replace(/_/g, ' '), value: v }))}
                          cx="50%" cy="50%" innerRadius={54} outerRadius={80}
                          dataKey="value" paddingAngle={2} stroke="none"
                        >
                          {Object.keys(perf.decision_distribution || {}).map((_, i) => (
                            <Cell key={i} fill={SERIES[i % SERIES.length]} />
                          ))}
                        </Pie>
                        <Tooltip {...TOOLTIP} />
                      </PieChart>
                    </ResponsiveContainer>
                  ) : <EmptyState title="No predictions yet" />}
                </Panel>

                <Panel eyebrow="Training" title="Label collection">
                  <p style={{ fontSize: 'var(--t-xs)', color: 'var(--text-muted)', marginBottom: 'var(--s5)', lineHeight: 1.6 }}>
                    Confirmed outcomes become training labels. Once a threshold is
                    reached, that model can be retrained on your own data instead of
                    the shipped baseline.
                  </p>

                  {[
                    { label: 'Fraud labels', count: perf.label_collection?.fraud_labels_collected || 0, threshold: 200, ready: perf.label_collection?.fraud_training_ready },
                    { label: 'Damage labels', count: perf.label_collection?.damage_labels_collected || 0, threshold: 200, ready: perf.label_collection?.damage_training_ready },
                  ].map(item => (
                    <div key={item.label} style={{ marginBottom: 'var(--s5)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 7 }}>
                        <span style={{ fontSize: 'var(--t-sm)', color: 'var(--text-secondary)' }}>{item.label}</span>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <MonoValue size={11.5} color="var(--text-muted)">
                            {item.count} / {item.threshold}
                          </MonoValue>
                          {item.ready && <StatusDot tone="live" size={6} label="ready" />}
                        </span>
                      </div>
                      <SignalBar
                        value={Math.min(item.count, item.threshold)}
                        max={item.threshold}
                        showValue={false}
                        height={6}
                        tone={item.ready ? 'var(--green)' : 'var(--vermillion)'}
                      />
                    </div>
                  ))}
                </Panel>
              </div>
            </div>
          )}

          {/* ── HISTORY ───────────────────────────────────────────────────── */}
          {tab === 'history' && (
            <Panel pad={false}>
              <DataTable
                columns={historyColumns}
                rows={history}
                rowKey={(p, i) => p.return_id ?? i}
                dense
                empty={<EmptyState title="No predictions yet" description="Score a return to populate this history." />}
              />
              <div style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: 'var(--s3) var(--s5)', borderTop: '1px solid var(--border)',
              }}>
                <MonoValue size={11} color="var(--text-muted)" weight={400}>
                  {histTotal} predictions
                </MonoValue>
                <div style={{ display: 'flex', gap: 6 }}>
                  <Button size="sm" variant="secondary" disabled={histPage === 1}
                    onClick={() => setHistPage(p => p - 1)}>Previous</Button>
                  <Button size="sm" variant="secondary" disabled={history.length < 20}
                    onClick={() => setHistPage(p => p + 1)}>Next</Button>
                </div>
              </div>
            </Panel>
          )}

          {/* ── EXPLAIN ───────────────────────────────────────────────────── */}
          {tab === 'explain' && (
            <div className="stack">
              {!selected ? (
                <Panel>
                  <EmptyState
                    icon={Eye}
                    title="Pick a prediction to explain"
                    description="Open prediction history and choose Explain on any row."
                    action={<Button variant="secondary" size="sm" onClick={() => setTab('history')}>
                      Go to prediction history
                    </Button>}
                  />
                </Panel>
              ) : explainLoading ? <LoadingCenter text="Reading the model" /> : explain ? (
                <>
                  <Panel eyebrow="Summary" title="What the model produced">
                    <div style={{
                      display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
                      gap: '1px', background: 'var(--border)',
                      border: '1px solid var(--border)', borderRadius: 'var(--r)',
                      overflow: 'hidden',
                    }}>
                      {Object.entries(explain.prediction || {}).map(([k, v]) => (
                        <div key={k} style={{ background: 'var(--surface)', padding: '12px 14px' }}>
                          <div style={{ fontSize: 'var(--t-micro)', color: 'var(--text-muted)', marginBottom: 4 }}>
                            {k.replace(/_/g, ' ')}
                          </div>
                          <MonoValue size={13}>
                            {typeof v === 'number' ? v.toFixed(2) : String(v)}
                          </MonoValue>
                        </div>
                      ))}
                    </div>
                  </Panel>

                  <Panel eyebrow="Driver" title={explain.explainability?.top_cost_driver || 'Top cost driver'}>
                    <p style={{
                      fontSize: 'var(--t-sm)', color: 'var(--text-secondary)', lineHeight: 1.7,
                      borderLeft: '2px solid var(--vermillion)', paddingLeft: 'var(--s4)',
                    }}>
                      {explain.top_driver_interpretation}
                    </p>
                    {explain.methodology_note && (
                      <>
                        <Divider />
                        <p style={{ fontSize: 'var(--t-xs)', color: 'var(--text-faint)', lineHeight: 1.6 }}>
                          {explain.methodology_note}
                        </p>
                      </>
                    )}
                  </Panel>

                  {explain.explainability?.feature_importances && (
                    <Panel eyebrow="Weights" title="Feature importance">
                      {explain.explainability.feature_importances.map((f, i) => (
                        <div key={i} style={{
                          display: 'flex', alignItems: 'center', gap: 'var(--s4)',
                          padding: '9px 0', borderTop: i === 0 ? 'none' : '1px solid var(--border)',
                        }}>
                          <MonoValue size={10} color="var(--text-faint)" weight={400} style={{ width: 22 }}>
                            {String(i + 1).padStart(2, '0')}
                          </MonoValue>
                          <span style={{
                            flex: 1, fontSize: 'var(--t-xs)', color: 'var(--text-secondary)',
                            fontFamily: 'var(--font-mono)', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis',
                          }}>
                            {f.feature}
                          </span>
                          <div style={{ width: 170, flexShrink: 0 }}>
                            <SignalBar
                              value={f.importance * 100}
                              showValue={false}
                              height={5}
                              tone={i === 0 ? 'var(--vermillion)' : 'var(--iron)'}
                            />
                          </div>
                          <MonoValue size={11} color="var(--text-muted)" style={{ width: 48, textAlign: 'right' }}>
                            {formatPercent(f.importance)}
                          </MonoValue>
                        </div>
                      ))}
                    </Panel>
                  )}
                </>
              ) : null}
            </div>
          )}

          {/* ── FEEDBACK ──────────────────────────────────────────────────── */}
          {tab === 'feedback' && (
            <Panel eyebrow="Correction" title="Tell the model it was wrong" style={{ maxWidth: 560 }}>
              <p style={{ fontSize: 'var(--t-sm)', color: 'var(--text-muted)', marginBottom: 'var(--s5)', lineHeight: 1.6 }}>
                Flagged predictions become labelled examples. This is the fastest way
                to move the model off the shipped baseline and onto your own data.
              </p>

              <div className="stack">
                <Input
                  label="Return ID"
                  value={feedback.predId}
                  onChange={e => setFeedback({ ...feedback, predId: e.target.value })}
                  placeholder="Paste the return ID"
                  hint="Copy it from prediction history."
                />

                <div>
                  <div className="label" style={{ marginBottom: 'var(--s2)' }}>Was the prediction right?</div>
                  <div style={{ display: 'flex', gap: 'var(--s2)' }}>
                    {[{ label: 'Yes, it was right', val: true }, { label: 'No, it was wrong', val: false }].map(({ label, val }) => {
                      const on = feedback.accurate === val
                      return (
                        <button
                          key={String(val)}
                          onClick={() => setFeedback({ ...feedback, accurate: val })}
                          style={{
                            flex: 1, padding: '10px 14px', borderRadius: 'var(--r)',
                            fontSize: 'var(--t-sm)', fontWeight: 500,
                            border: `1px solid ${on ? 'var(--vermillion)' : 'var(--border-2)'}`,
                            background: on ? 'var(--brand-subtle)' : 'var(--surface)',
                            color: on ? 'var(--brand-dark)' : 'var(--text-secondary)',
                            transition: 'var(--tr-color)',
                          }}
                        >
                          {label}
                        </button>
                      )
                    })}
                  </div>
                </div>

                <Textarea
                  label="What should it have decided?"
                  value={feedback.comments}
                  onChange={e => setFeedback({ ...feedback, comments: e.target.value })}
                  placeholder="Optional, but the most useful part"
                  rows={3}
                />

                <div>
                  <Button
                    onClick={submitFeedback}
                    disabled={!feedback.predId || feedback.accurate === null}
                    icon={<MessageSquare size={14} />}
                  >
                    Send feedback
                  </Button>
                </div>
              </div>
            </Panel>
          )}
        </>
      )}
    </div>
  )
}
