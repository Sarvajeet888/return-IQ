import React, { useState, useEffect } from 'react'
import { Zap, Plus, Trash2, RefreshCw, ToggleLeft, ToggleRight, Clock, AlertTriangle } from 'lucide-react'
import { api } from '../../utils/api.js'
import { Card, PageHeader, Button, Alert, LoadingCenter, Badge } from '../../components/ui/index.jsx'

const RULE_TYPES = ['auto_approve', 'auto_reject', 'escalate', 'assign']
const CONDITION_KEYS = [
  { key: 'risk_score_lt', label: 'Risk Score <', type: 'number' },
  { key: 'risk_score_gt', label: 'Risk Score >', type: 'number' },
  { key: 'fraud_score_lt', label: 'Fraud Score <', type: 'number' },
  { key: 'fraud_score_gt', label: 'Fraud Score >', type: 'number' },
  { key: 'item_value_lt', label: 'Item Value (₹) <', type: 'number' },
  { key: 'item_value_gt', label: 'Item Value (₹) >', type: 'number' },
  { key: 'payment_mode_eq', label: 'Payment Mode =', type: 'text' },
  { key: 'category_eq', label: 'Category =', type: 'text' },
  { key: 'courier_eq', label: 'Courier =', type: 'text' },
]

const RULE_TYPE_COLORS = {
  auto_approve: 'accept', auto_reject: 'reject', escalate: 'escalate', assign: 'manual_review'
}

function RuleCard({ rule, onDelete, onToggle }) {
  return (
    <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 10, padding: 16, marginBottom: 12 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 12 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)' }}>{rule.name}</span>
            <Badge variant={RULE_TYPE_COLORS[rule.rule_type] || 'accept'}>{rule.rule_type.replace(/_/g, ' ')}</Badge>
            {!rule.is_active && <Badge variant="inactive">Paused</Badge>}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
            Priority: {rule.priority} · Triggered {rule.triggered_count} times
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button onClick={() => onToggle(rule)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: rule.is_active ? 'var(--green)' : 'var(--text-muted)' }}>
            {rule.is_active ? <ToggleRight size={22} /> : <ToggleLeft size={22} />}
          </button>
          <Button size="sm" variant="danger" icon={<Trash2 size={12} />} onClick={() => onDelete(rule.id)}>Delete</Button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div>
          <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-muted)', letterSpacing: '0.02em', marginBottom: 6 }}>Conditions (ALL must match)</div>
          {Object.entries(rule.conditions || {}).map(([k, v]) => (
            <div key={k} style={{ fontSize: 12, color: 'var(--text-secondary)', background: 'var(--surface)', borderRadius: 6, padding: '4px 8px', marginBottom: 4, fontFamily: 'var(--font-mono)' }}>
              {k} = {String(v)}
            </div>
          ))}
        </div>
        <div>
          <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-muted)', letterSpacing: '0.02em', marginBottom: 6 }}>Action</div>
          {Object.entries(rule.action || {}).map(([k, v]) => (
            <div key={k} style={{ fontSize: 12, color: 'var(--text-secondary)', background: 'var(--surface)', borderRadius: 6, padding: '4px 8px', marginBottom: 4, fontFamily: 'var(--font-mono)' }}>
              {k}: {String(v)}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function CreateRuleModal({ onClose, onCreated }) {
  const [name, setName] = useState('')
  const [ruleType, setRuleType] = useState('auto_approve')
  const [priority, setPriority] = useState(0)
  const [conditions, setConditions] = useState([{ key: 'risk_score_lt', value: '30' }])
  const [actionStatus, setActionStatus] = useState('approved')
  const [actionNotify, setActionNotify] = useState(true)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  async function save() {
    setSaving(true); setErr('')
    const condObj = {}
    for (const c of conditions) {
      if (c.key && c.value !== '') condObj[c.key] = isNaN(c.value) ? c.value : Number(c.value)
    }
    const action = { notify: actionNotify }
    if (actionStatus) action.status = actionStatus
    try {
      await api.createWorkflowRule({ name, rule_type: ruleType, conditions: condObj, action, priority: Number(priority) })
      onCreated()
    } catch (e) {
      setErr(e.response?.data?.detail || e.message)
    } finally { setSaving(false) }
  }

  const inputStyle = { width: '100%', padding: '8px 10px', borderRadius: 7, border: '1px solid var(--border-2)', background: 'var(--surface-2)', color: 'var(--text-primary)', fontSize: 13, boxSizing: 'border-box' }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--r-lg)', padding: 28, width: 540, maxHeight: '90vh', overflowY: 'auto' }}>
        <div style={{ fontSize: 16, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 20 }}>Create Workflow Rule</div>
        {err && <Alert type="error" style={{ marginBottom: 12 }}>{err}</Alert>}

        <div style={{ marginBottom: 14 }}>
          <label style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-muted)', display: 'block', marginBottom: 5 }}>Rule Name</label>
          <input style={inputStyle} value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Auto-approve low risk" />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
          <div>
            <label style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-muted)', display: 'block', marginBottom: 5 }}>Rule Type</label>
            <select style={inputStyle} value={ruleType} onChange={e => setRuleType(e.target.value)}>
              {RULE_TYPES.map(t => <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-muted)', display: 'block', marginBottom: 5 }}>Priority (lower = higher priority)</label>
            <input style={inputStyle} type="number" value={priority} onChange={e => setPriority(e.target.value)} min={0} />
          </div>
        </div>

        <div style={{ marginBottom: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <label style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-muted)' }}>Conditions (ALL must match)</label>
            <Button size="sm" variant="ghost" icon={<Plus size={12} />} onClick={() => setConditions([...conditions, { key: 'risk_score_lt', value: '' }])}>Add</Button>
          </div>
          {conditions.map((c, i) => (
            <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
              <select style={{ ...inputStyle, flex: 2 }} value={c.key} onChange={e => { const nc = [...conditions]; nc[i].key = e.target.value; setConditions(nc) }}>
                {CONDITION_KEYS.map(k => <option key={k.key} value={k.key}>{k.label}</option>)}
              </select>
              <input style={{ ...inputStyle, flex: 1 }} value={c.value} onChange={e => { const nc = [...conditions]; nc[i].value = e.target.value; setConditions(nc) }} placeholder="value" />
              <Button size="sm" variant="danger" onClick={() => setConditions(conditions.filter((_, j) => j !== i))}>✕</Button>
            </div>
          ))}
        </div>

        <div style={{ marginBottom: 20 }}>
          <label style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-muted)', display: 'block', marginBottom: 8 }}>Action</label>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 4 }}>Set Status To</div>
              <input style={inputStyle} value={actionStatus} onChange={e => setActionStatus(e.target.value)} placeholder="e.g. approved" />
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--text-secondary)', cursor: 'pointer' }}>
              <input type="checkbox" checked={actionNotify} onChange={e => setActionNotify(e.target.checked)} />
              Send notification
            </label>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={save} loading={saving} disabled={!name}>Create Rule</Button>
        </div>
      </div>
    </div>
  )
}

export default function Workflows() {
  const [rules, setRules] = useState([])
  const [slaBreaches, setSlaBreaches] = useState([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [msg, setMsg] = useState({ type: '', text: '' })
  const [tab, setTab] = useState('rules')

  async function load() {
    setLoading(true)
    try {
      const [r, sla] = await Promise.all([api.getWorkflowRules(), api.getSlaList({ breached_only: true })])
      setRules(r)
      setSlaBreaches(sla)
    } catch (e) {
      setMsg({ type: 'error', text: e.message })
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  async function deleteRule(id) {
    if (!window.confirm('Delete this rule?')) return
    try { await api.deleteWorkflowRule(id); load() } catch (e) { setMsg({ type: 'error', text: e.message }) }
  }

  async function toggleRule(rule) {
    try {
      await api.updateWorkflowRule(rule.id, { is_active: !rule.is_active })
      load()
    } catch (e) { setMsg({ type: 'error', text: e.message }) }
  }

  async function checkBreaches() {
    try {
      const r = await api.checkSlaBreaches()
      setMsg({ type: 'success', text: `Found ${r.newly_breached} new SLA breaches` })
      load()
    } catch (e) { setMsg({ type: 'error', text: e.message }) }
  }

  return (
    <div className="animate-in">
      <PageHeader title="Workflow Automation" subtitle="Auto-approve, reject, escalate, and track SLAs" actions={
        <div style={{ display: 'flex', gap: 10 }}>
          <Button variant="secondary" size="sm" icon={<RefreshCw size={14} />} onClick={load}>Refresh</Button>
          <Button size="sm" icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>New Rule</Button>
        </div>
      } />
      {msg.text && <Alert type={msg.type || 'info'} style={{ marginBottom: 16 }}>{msg.text}</Alert>}
      {showCreate && <CreateRuleModal onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); load() }} />}

      <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid var(--border)', marginBottom: 24 }}>
        {[['rules', `Rules (${rules.length})`], ['sla', `SLA Breaches (${slaBreaches.length})`]].map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)} style={{
            padding: '8px 18px', fontSize: 13, fontWeight: tab === k ? 700 : 500,
            color: tab === k ? 'var(--brand)' : 'var(--text-secondary)',
            background: 'none', border: 'none', borderBottom: tab === k ? '2px solid var(--brand)' : '2px solid transparent',
            cursor: 'pointer',
          }}>{l}</button>
        ))}
      </div>

      {loading ? <LoadingCenter /> : (
        <>
          {tab === 'rules' && (
            <div>
              {rules.length === 0 ? (
                <Card style={{ textAlign: 'center', padding: 48 }}>
                  <Zap size={40} style={{ color: 'var(--text-muted)', margin: '0 auto 16px' }} />
                  <div style={{ fontSize: 15, fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 8 }}>No workflow rules yet</div>
                  <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 20 }}>Create rules to automatically approve low-risk returns, flag fraud, or set SLA timers.</div>
                  <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>Create First Rule</Button>
                </Card>
              ) : rules.map(r => <RuleCard key={r.id} rule={r} onDelete={deleteRule} onToggle={toggleRule} />)}
            </div>
          )}

          {tab === 'sla' && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
                <Button variant="secondary" size="sm" icon={<Clock size={14} />} onClick={checkBreaches}>Check for New Breaches</Button>
              </div>
              {slaBreaches.length === 0 ? (
                <Card style={{ textAlign: 'center', padding: 40 }}>
                  <div style={{ fontSize: 32, marginBottom: 12 }}>✅</div>
                  <div style={{ fontSize: 15, fontWeight: 500, color: 'var(--green)' }}>No SLA breaches</div>
                  <div style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 6 }}>All returns are within their SLA windows.</div>
                </Card>
              ) : (
                <Card>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr>
                        {['Return ID', 'SLA Deadline', 'Escalated', 'Resolved'].map(h => (
                          <th key={h} style={{ textAlign: 'left', fontSize: 12, fontWeight: 500, color: 'var(--text-muted)', letterSpacing: '0.02em', padding: '10px 12px', borderBottom: '1px solid var(--border)' }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {slaBreaches.map((s, i) => (
                        <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                          <td style={{ padding: '10px 12px', fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--red)' }}>{s.return_request_id?.slice(0, 12)}…</td>
                          <td style={{ padding: '10px 12px', fontSize: 12, color: 'var(--text-secondary)' }}>{new Date(s.sla_deadline).toLocaleString()}</td>
                          <td style={{ padding: '10px 12px' }}><Badge variant={s.escalated ? 'escalate' : 'inactive'}>{s.escalated ? 'Yes' : 'No'}</Badge></td>
                          <td style={{ padding: '10px 12px' }}><Badge variant={s.resolved_at ? 'accept' : 'reject'}>{s.resolved_at ? 'Yes' : 'Open'}</Badge></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Card>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
