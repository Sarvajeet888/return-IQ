import React, { useState, useEffect } from 'react'
import { Shield, Users, Database, Activity, Settings, RefreshCw, BarChart2, Cpu, AlertTriangle, Check, X } from 'lucide-react'
import { api } from '../../utils/api.js'
import { Card, PageHeader, Button, Alert, LoadingCenter, Badge } from '../../components/ui/index.jsx'

function Tab({ label, active, onClick }) {
  return (
    <button onClick={onClick} style={{
      padding: '8px 18px', fontSize: 13, fontWeight: active ? 700 : 500,
      color: active ? 'var(--brand)' : 'var(--text-secondary)',
      background: 'none', border: 'none',
      borderBottom: active ? '2px solid var(--brand)' : '2px solid transparent',
      cursor: 'pointer', transition: 'all 0.15s',
    }}>{label}</button>
  )
}

function StatCard({ label, value, color = 'var(--brand)' }) {
  return (
    <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 10, padding: '16px 20px' }}>
      <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-muted)', letterSpacing: '0.5px', marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 500, color }}>{value ?? '—'}</div>
    </div>
  )
}

export default function AdminPanel() {
  const [tab, setTab] = useState('health')
  const [health, setHealth] = useState(null)
  const [dbStats, setDbStats] = useState(null)
  const [mlStats, setMlStats] = useState(null)
  const [users, setUsers] = useState([])
  const [auditLogs, setAuditLogs] = useState([])
  const [systemSettings, setSystemSettings] = useState([])
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState({ type: '', text: '' })

  useEffect(() => { loadTab(tab) }, [tab])

  async function loadTab(t) {
    setLoading(true); setMsg({ type: '', text: '' })
    try {
      if (t === 'health') {
        const [h, db, ml] = await Promise.all([api.getAdminHealth(), api.getDbStats(), api.getMlStats()])
        setHealth(h); setDbStats(db); setMlStats(ml)
      } else if (t === 'users') {
        setUsers(await api.getAllUsers())
      } else if (t === 'audit') {
        setAuditLogs(await api.getGlobalAuditLogs(100))
      } else if (t === 'settings') {
        setSystemSettings(await api.getSystemSettings())
      }
    } catch (e) {
      setMsg({ type: 'error', text: e.response?.data?.detail || e.message })
    } finally {
      setLoading(false)
    }
  }

  async function updateUserStatus(userId, status) {
    try {
      await api.updateUserStatus(userId, status)
      setMsg({ type: 'success', text: `User status updated to ${status}` })
      loadTab('users')
    } catch (e) {
      setMsg({ type: 'error', text: e.response?.data?.detail || e.message })
    }
  }

  return (
    <div className="animate-in">
      <PageHeader title="Admin Panel" subtitle="Super-admin system controls" actions={
        <Button variant="secondary" icon={<RefreshCw size={14} />} size="sm" onClick={() => loadTab(tab)}>Refresh</Button>
      } />
      {msg.text && <Alert type={msg.type || 'info'} style={{ marginBottom: 16 }}>{msg.text}</Alert>}

      <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid var(--border)', marginBottom: 24 }}>
        {[['health', 'Health & DB'], ['users', 'Users'], ['audit', 'Audit Logs'], ['settings', 'Settings']].map(([k, l]) => (
          <Tab key={k} label={l} active={tab === k} onClick={() => setTab(k)} />
        ))}
      </div>

      {loading ? <LoadingCenter /> : (
        <>
          {tab === 'health' && health && (
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
                <div style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--green)', }} />
                <span style={{ fontSize: 14, fontWeight: 500, color: 'var(--green)' }}>System Healthy</span>
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{new Date(health.timestamp).toLocaleString()}</span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 12, marginBottom: 24 }}>
                {dbStats && Object.entries(dbStats).map(([k, v]) => (
                  <StatCard key={k} label={k.replace(/_/g, ' ')} value={v} />
                ))}
              </div>

              {mlStats && (
                <Card>
                  <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 16 }}>ML Model Status</div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16 }}>
                    {Object.entries(mlStats).map(([modelKey, modelData]) => (
                      <div key={modelKey} style={{ background: 'var(--surface-2)', borderRadius: 10, padding: 16, border: '1px solid var(--border)' }}>
                        <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-muted)', letterSpacing: '0.02em', marginBottom: 8 }}>
                          {modelKey.replace(/_/g, ' ')}
                        </div>
                        {typeof modelData === 'object' ? Object.entries(modelData).map(([k, v]) => (
                          <div key={k} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
                            <span style={{ color: 'var(--text-secondary)' }}>{k}</span>
                            <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
                              {typeof v === 'boolean' ? (v ? '✅' : '❌') : String(v)}
                            </span>
                          </div>
                        )) : <div style={{ fontSize: 13, color: 'var(--text-primary)' }}>{String(modelData)}</div>}
                      </div>
                    ))}
                  </div>
                </Card>
              )}
            </div>
          )}

          {tab === 'users' && (
            <Card>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      {['Name', 'Email', 'Role', 'Status', 'Org ID', 'Actions'].map(h => (
                        <th key={h} style={{ textAlign: 'left', fontSize: 12, fontWeight: 500, color: 'var(--text-muted)', letterSpacing: '0.5px', padding: '10px 12px', borderBottom: '1px solid var(--border)', whiteSpace: 'nowrap' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {users.map(u => (
                      <tr key={u.id} style={{ borderBottom: '1px solid var(--border)' }}>
                        <td style={{ padding: '10px 12px', fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>{u.full_name}</td>
                        <td style={{ padding: '10px 12px', fontSize: 12, color: 'var(--text-secondary)' }}>{u.email}</td>
                        <td style={{ padding: '10px 12px' }}><Badge variant={u.role === 'super_admin' ? 'enterprise' : 'accept'}>{u.role}</Badge></td>
                        <td style={{ padding: '10px 12px' }}>
                          <Badge variant={u.status === 'active' ? 'active' : 'inactive'}>{u.status}</Badge>
                        </td>
                        <td style={{ padding: '10px 12px', fontSize: 12, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{u.org_id?.slice(0, 8)}…</td>
                        <td style={{ padding: '10px 12px' }}>
                          <div style={{ display: 'flex', gap: 6 }}>
                            {u.status !== 'active' && <Button size="sm" variant="success" onClick={() => updateUserStatus(u.id, 'active')}>Activate</Button>}
                            {u.status === 'active' && <Button size="sm" variant="danger" onClick={() => updateUserStatus(u.id, 'suspended')}>Suspend</Button>}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {tab === 'audit' && (
            <Card>
              <div style={{ overflowX: 'auto', maxHeight: 600, overflowY: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      {['Time', 'Org ID', 'User ID', 'Action', 'Detail'].map(h => (
                        <th key={h} style={{ textAlign: 'left', fontSize: 12, fontWeight: 500, color: 'var(--text-muted)', letterSpacing: '0.5px', padding: '10px 12px', borderBottom: '1px solid var(--border)', whiteSpace: 'nowrap', position: 'sticky', top: 0, background: 'var(--surface)' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {auditLogs.map((log, i) => (
                      <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                        <td style={{ padding: '8px 12px', fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{new Date(log.created_at).toLocaleString()}</td>
                        <td style={{ padding: '8px 12px', fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>{log.org_id?.slice(0, 8)}…</td>
                        <td style={{ padding: '8px 12px', fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>{log.user_id?.slice(0, 8) || '—'}…</td>
                        <td style={{ padding: '8px 12px', fontSize: 12, fontWeight: 500, color: 'var(--brand)' }}>{log.action}</td>
                        <td style={{ padding: '8px 12px', fontSize: 12, color: 'var(--text-secondary)', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{log.detail}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {tab === 'settings' && (
            <Card>
              {systemSettings.length === 0 ? (
                <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)', fontSize: 14 }}>
                  No system settings configured yet. Use PUT /api/v1/admin/system-settings/&#123;key&#125; to set values.
                </div>
              ) : (
                systemSettings.map((s, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 0', borderBottom: '1px solid var(--border)' }}>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{s.key}</div>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>Updated: {s.updated_at ? new Date(s.updated_at).toLocaleDateString() : '—'}</div>
                    </div>
                    <div style={{ fontSize: 13, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', background: 'var(--surface-2)', padding: '4px 10px', borderRadius: 6 }}>
                      {JSON.stringify(s.value)}
                    </div>
                  </div>
                ))
              )}
            </Card>
          )}
        </>
      )}
    </div>
  )
}
