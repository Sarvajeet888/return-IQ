// Customers Page
import React, { useState, useEffect } from 'react'
import { formatMoney } from '../../utils/money'
import { Users, RefreshCw, ChevronRight, AlertTriangle } from 'lucide-react'
import { api } from '../../utils/api.js'
import { Card, PageHeader, Button, LoadingCenter, Alert, Badge, EmptyState, RiskBar } from '../../components/ui/index.jsx'

export function CustomersPage() {
  const [customers, setCustomers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(null)

  async function load() {
    setLoading(true); setError('')
    try {
      // GET /customers/ returns a paginated object { items, total, page,
      // page_size }, not a bare array. It used to return an array, and this
      // page silently rendered blank after the change because
      // `customers.map` on an object throws inside render.
      const res = await api.getCustomers({ page: 1, page_size: 100 })
      setCustomers(Array.isArray(res) ? res : (res?.items ?? []))
    }
    catch (e) { setError(e.response?.data?.detail || e.message) }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  return (
    <div className="animate-in">
      <PageHeader title="Customers" subtitle={`${customers.length} customers tracked`} actions={<Button variant="secondary" icon={<RefreshCw size={14} />} size="sm" onClick={load}>Refresh</Button>} />
      {error && <Alert type="error" style={{ marginBottom: 16 }}>{error}</Alert>}
      {loading ? <LoadingCenter /> : (
        <Card>
          {customers.length === 0 ? <EmptyState icon={Users} title="No customers yet" description="Customers appear here after returns are submitted." /> : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    {['Customer','City','Orders','Returns','CLV','Fraud Score','Risk Level'].map(h => (
                      <th key={h} style={{ textAlign: 'left', fontSize: 12, fontWeight: 500, color: 'var(--text-muted)', letterSpacing: '0.5px', padding: '12px', borderBottom: '1px solid var(--border)', whiteSpace: 'nowrap' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {customers.map(c => (
                    <tr key={c.id} style={{ cursor: 'pointer', transition: 'background 0.1s' }}
                      onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-2)'}
                      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                    >
                      <td style={{ padding: '12px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <div style={{ width: 32, height: 32, borderRadius: '50%', background: '#DE4B22', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 500, color: '#fff', flexShrink: 0 }}>
                            {c.name?.[0] || 'C'}
                          </div>
                          <div>
                            <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>{c.name}</div>
                            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{c.email}</div>
                          </div>
                        </div>
                      </td>
                      <td style={{ padding: '12px', fontSize: 12, color: 'var(--text-muted)' }}>{c.city}</td>
                      <td style={{ padding: '12px', fontSize: 13, color: 'var(--text-secondary)', fontWeight: 500 }}>{c.total_orders}</td>
                      <td style={{ padding: '12px', fontSize: 13, color: c.total_returns > 5 ? 'var(--amber)' : 'var(--text-secondary)', fontWeight: 500 }}>{c.total_returns}</td>
                      <td style={{ padding: '12px', fontSize: 13, color: 'var(--green)', fontWeight: 500 }}>{formatMoney(c.clv)}</td>
                      <td style={{ padding: '12px', minWidth: 100 }}>
                        <RiskBar score={Number(c.fraud_score || 0)} size="sm" />
                      </td>
                      <td style={{ padding: '12px' }}>
                        <Badge variant={c.risk_level || 'low'}>{c.risk_level || 'low'}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </div>
  )
}

// Warehouses Page
export function WarehousesPage() {
  const [warehouses, setWarehouses] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => { api.getWarehouses().then(setWarehouses).catch(() => {}).finally(() => setLoading(false)) }, [])

  return (
    <div className="animate-in">
      <PageHeader title="Warehouses" subtitle="Manage your storage and dispatch locations" />
      {loading ? <LoadingCenter /> : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(300px,1fr))', gap: 16 }}>
          {warehouses.map(w => (
            <Card key={w.id} style={{ padding: 22 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 2 }}>{w.name}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{w.city}, {w.state} — {w.pincode}</div>
                </div>
                <Badge variant={w.is_active ? 'active' : 'inactive'} dot />
              </div>
              <div style={{ marginBottom: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Capacity used</span>
                  <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)' }}>{w.used_units?.toLocaleString()} / {w.capacity_units?.toLocaleString()}</span>
                </div>
                <div style={{ height: 6, background: 'var(--border)', borderRadius: 99 }}>
                  <div style={{ width: `${Math.round((w.used_units/w.capacity_units)*100)}%`, height: '100%', background: 'var(--brand)', borderRadius: 99, transition: 'width 0.4s ease' }} />
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                  {Math.round((w.used_units/w.capacity_units)*100)}% utilized
                </div>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {(w.zones || []).map(z => (
                  <span key={z} style={{ fontSize: 12, background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 20, padding: '2px 8px', color: 'var(--text-muted)', letterSpacing: '0.4px', fontWeight: 500 }}>{z}</span>
                ))}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

// AI Platform Page
export function AIPlatformPage() {
  const [models, setModels] = useState(null)
  const [insights, setInsights] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([api.getAiModels(), api.getAiInsights()])
      .then(([m, i]) => { setModels(m); setInsights(i) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <LoadingCenter text="Loading AI platform..." />

  return (
    <div className="animate-in">
      <PageHeader title="AI Platform" subtitle="Enterprise ML models powering your return intelligence" />

      {/* Model stats */}
      {models && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(160px,1fr))', gap: 14, marginBottom: 22 }}>
          {[
            { label: 'Model Version', value: models.model_version },
            { label: 'Algorithm', value: models.algorithm },
            { label: 'R² Score', value: models.r2_score },
            { label: 'MAE (INR)', value: `₹${models.mae}` },
            { label: 'Total Predictions', value: models.total_predictions },
            { label: 'Avg Latency', value: `${models.avg_latency_ms}ms` },
          ].map(({ label, value }) => (
            <Card key={label} style={{ padding: '16px 18px' }}>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', letterSpacing: '0.5px', fontWeight: 500, marginBottom: 8 }}>{label}</div>
              <div style={{ fontSize: 18, fontWeight: 500, color: 'var(--brand)' }}>{value}</div>
            </Card>
          ))}
        </div>
      )}

      {/* Active models */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
        <Card style={{ padding: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 14 }}>Active AI Models</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {(models?.models_active || []).map(m => (
              <div key={m} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 12px', background: 'var(--surface-2)', borderRadius: 8, border: '1px solid var(--border)' }}>
                <span style={{ fontSize: 13, color: 'var(--text-secondary)', fontWeight: 500 }}>
                  {m.replace(/_/g,' ').replace(/\b\w/g, c => c.toUpperCase())}
                </span>
                <Badge variant="active" dot>Live</Badge>
              </div>
            ))}
          </div>
        </Card>

        {insights && (
          <Card style={{ padding: 20 }}>
            <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 14 }}>AI Summary</div>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7, marginBottom: 16 }}>{insights.summary}</p>
            <div style={{ padding: '12px 14px', background: 'var(--green-subtle)', border: '1px solid var(--green-border)', borderRadius: 10 }}>
              <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--green)', letterSpacing: '0.5px', marginBottom: 4 }}>🌱 Carbon Insights</div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{insights.carbon_insights?.recommendation}</div>
              <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--green)', marginTop: 8 }}>
                {insights.carbon_insights?.total_kg} kg CO₂ · {insights.carbon_insights?.equivalent_trees} trees equivalent
              </div>
            </div>
          </Card>
        )}
      </div>

      {/* Recommendations */}
      {insights?.top_recommendations && (
        <Card style={{ padding: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 14 }}>AI Recommendations</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(240px,1fr))', gap: 14 }}>
            {insights.top_recommendations.map(r => (
              <div key={r.title} style={{ padding: '14px 16px', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                  <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>{r.title}</div>
                  <Badge variant={r.impact === 'high' ? 'reject' : r.impact === 'medium' ? 'charge_return_fee' : 'accept'}>{r.impact}</Badge>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.6 }}>{r.description}</div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}

// Settings Page
export function SettingsPage() {
  const [org, setOrg] = useState(null)
  const [apiKeys, setApiKeys] = useState([])
  const [members, setMembers] = useState([])
  const [auditLogs, setAuditLogs] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [newKeyName, setNewKeyName] = useState('')
  const [newKey, setNewKey] = useState(null)
  const [settings, setSettings] = useState({ risk_threshold: 50, notify_on_fraud: true, webhook_url: '' })
  // Previously every failure here (initial load, save, create key) was
  // swallowed with an empty catch {} - a failed save looked identical to a
  // successful one, since `saved` just silently stayed false. `error` now
  // surfaces whatever went wrong, same pattern as CustomersPage above.
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([api.getOrg(), api.getApiKeys(), api.getMembers(), api.getAuditLogs()])
      .then(([o, k, m, a]) => {
        setOrg(o); setApiKeys(k); setMembers(m); setAuditLogs(a)
        setSettings({ risk_threshold: o.risk_threshold || 50, notify_on_fraud: o.settings?.notify_on_fraud ?? true, webhook_url: o.settings?.webhook_url || '' })
      }).catch(e => setError(e.response?.data?.detail || 'Failed to load settings.')).finally(() => setLoading(false))
  }, [])

  async function saveSettings() {
    setSaving(true); setError('')
    try { await api.updateOrgSettings(settings); setSaved(true); setTimeout(() => setSaved(false), 2500) }
    catch (e) { setError(e.response?.data?.detail || 'Failed to save settings. Please try again.') }
    finally { setSaving(false) }
  }

  async function createKey() {
    if (!newKeyName.trim()) return
    setError('')
    try { const res = await api.createApiKey({ name: newKeyName }); setNewKey(res); setNewKeyName(''); setApiKeys(k => [...k, res]) }
    catch (e) { setError(e.response?.data?.detail || 'Failed to create API key. Please try again.') }
  }

  if (loading) return <LoadingCenter />

  return (
    <div className="animate-in">
      <PageHeader title="Settings" subtitle="Manage organization settings, API keys, and team members" />
      {error && <Alert type="error" style={{ marginBottom: 16 }}>{error}</Alert>}

      <div style={{ display: 'grid', gap: 16 }}>
        {/* Org info */}
        {org && (
          <Card style={{ padding: 22 }}>
            <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 16 }}>Organization</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              {[['Name', org.name], ['Email', org.contact_email], ['Platform', org.platform_type], ['Plan', org.plan_tier]].map(([l,v]) => (
                <div key={l}>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 4, letterSpacing: '0.4px', fontWeight: 500 }}>{l}</div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)', fontWeight: 500 }}>{v} {l === 'Plan' && <Badge variant={v}>{v}</Badge>}</div>
                </div>
              ))}
            </div>
          </Card>
        )}

        {/* Risk settings */}
        <Card style={{ padding: 22 }}>
          <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 16 }}>Risk & Routing Settings</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div>
              <label style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)', letterSpacing: '0.3px', display: 'block', marginBottom: 8 }}>
                Risk Threshold: <span style={{ color: 'var(--brand)' }}>{settings.risk_threshold}</span>
              </label>
              <input type="range" min={10} max={90} value={settings.risk_threshold} onChange={e => setSettings(s => ({ ...s, risk_threshold: Number(e.target.value) }))}
                style={{ width: '100%', accentColor: 'var(--brand)', cursor: 'pointer' }} />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                <span>10 (strict)</span><span>90 (lenient)</span>
              </div>
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: 13, color: 'var(--text-secondary)' }}>
              <input type="checkbox" checked={settings.notify_on_fraud} onChange={e => setSettings(s => ({ ...s, notify_on_fraud: e.target.checked }))} style={{ width: 16, height: 16, accentColor: 'var(--brand)', cursor: 'pointer' }} />
              Send notifications for high fraud score returns
            </label>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <label style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)' }}>Webhook URL (optional)</label>
              <input value={settings.webhook_url} onChange={e => setSettings(s => ({ ...s, webhook_url: e.target.value }))} placeholder="https://your-site.com/webhook"
                style={{ background: 'var(--surface-2)', border: '1px solid var(--border-2)', borderRadius: 'var(--r-md)', padding: '9px 12px', color: 'var(--text-primary)', fontSize: 13, outline: 'none', width: '100%', maxWidth: 400 }} />
            </div>
            <Button onClick={saveSettings} loading={saving} variant={saved ? 'success' : 'primary'} style={{ alignSelf: 'flex-start' }}>
              {saved ? '✓ Saved' : 'Save Settings'}
            </Button>
          </div>
        </Card>

        {/* API Keys */}
        <Card style={{ padding: 22 }}>
          <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 16 }}>API Keys</div>
          {newKey && (
            <Alert type="success" style={{ marginBottom: 14 }}>
              <div style={{ fontWeight: 500, marginBottom: 4 }}>New API key created — save it now!</div>
              <code style={{ fontSize: 12, wordBreak: 'break-all', background: 'var(--green-subtle)', padding: '4px 8px', borderRadius: 4, display: 'block' }}>{newKey.raw_api_key}</code>
            </Alert>
          )}
          <div style={{ display: 'flex', gap: 10, marginBottom: 14 }}>
            <input value={newKeyName} onChange={e => setNewKeyName(e.target.value)} placeholder="Key name (e.g. Production)"
              style={{ flex: 1, background: 'var(--surface-2)', border: '1px solid var(--border-2)', borderRadius: 'var(--r-md)', padding: '9px 12px', color: 'var(--text-primary)', fontSize: 13, outline: 'none' }} />
            <Button onClick={createKey} disabled={!newKeyName.trim()}>Create Key</Button>
          </div>
          {apiKeys.map((k, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 12px', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 8, marginBottom: 8 }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>{k.name}</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{k.prefix}••••••••••••</div>
              </div>
              <Badge variant={k.is_active ? 'active' : 'inactive'} dot>{k.is_active ? 'Active' : 'Inactive'}</Badge>
            </div>
          ))}
        </Card>

        {/* Team members */}
        <Card style={{ padding: 22 }}>
          <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 16 }}>Team Members</div>
          {members.map(m => (
            <div key={m.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 0', borderBottom: '1px solid var(--border)' }}>
              <div style={{ width: 34, height: 34, borderRadius: '50%', background: '#DE4B22', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 500, color: '#fff', flexShrink: 0 }}>
                {m.full_name?.[0] || 'U'}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>{m.full_name}</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{m.email}</div>
              </div>
              <Badge variant={m.role === 'org_admin' ? 'enterprise' : 'inactive'}>{m.role?.replace(/_/g,' ')}</Badge>
            </div>
          ))}
        </Card>

        {/* Audit logs */}
        {auditLogs.length > 0 && (
          <Card style={{ padding: 22 }}>
            <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 16 }}>Audit Log</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
              {auditLogs.slice(0, 10).map(log => (
                <div key={log.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderBottom: '1px solid var(--border)', fontSize: 12 }}>
                  <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                    <span style={{ fontSize: 12, background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 4, padding: '2px 6px', color: 'var(--text-muted)', letterSpacing: '0.3px', fontWeight: 500 }}>{log.action}</span>
                    <span style={{ color: 'var(--text-secondary)' }}>{log.detail}</span>
                  </div>
                  <span style={{ color: 'var(--text-muted)', whiteSpace: 'nowrap', marginLeft: 16 }}>{log.created_at ? new Date(log.created_at).toLocaleString('en-IN') : ''}</span>
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>
    </div>
  )
}
