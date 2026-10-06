import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Key, Zap, Copy, Check, Terminal } from 'lucide-react'
import { api, setApiKey, getApiKey, auth } from '../../utils/api.js'
import { useAuth } from '../../store/AuthContext.jsx'
import { Card, Button, Alert, Input, PageHeader } from '../../components/ui/index.jsx'

export default function Setup() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [demoData, setDemoData] = useState(null)
  const [manualKey, setManualKey] = useState(getApiKey())
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState('')
  const [autoLogging, setAutoLogging] = useState(false)

  async function fetchDemo() {
    setLoading(true); setError('')
    try {
      const res = await api.getDemoCredentials()
      setDemoData(res)
      setApiKey(res.demo_api_key)
    } catch (e) {
      setError('Backend not running. Start it: cd backend && python -m uvicorn app.main:app --reload')
    } finally { setLoading(false) }
  }

  async function autoLogin() {
    if (!demoData) return
    setAutoLogging(true)
    try {
      await login(demoData.demo_credentials.email, demoData.demo_credentials.password)
      navigate('/dashboard')
    } catch (e) {
      setError('Auto-login failed: ' + (e.response?.data?.detail || e.message))
    } finally { setAutoLogging(false) }
  }

  function copy(text) {
    navigator.clipboard.writeText(text); setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  function saveKey() { setApiKey(manualKey); navigate('/dashboard') }

  return (
    <div className="animate-in">
      <PageHeader title="API Setup & Demo" subtitle="Configure your connection to the ReturnIQ backend" />

      {error && <Alert type="error" style={{ marginBottom: 16 }}>{error}</Alert>}

      <div style={{ display: 'grid', gap: 16, maxWidth: 640 }}>
        <Card style={{ padding: 24 }}>
          <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 8 }}>
            <Zap size={16} style={{ color: 'var(--brand)' }} /> Quick Demo Setup
          </div>
          <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 18 }}>
            Fetch demo credentials from the backend and auto-login in one click.
          </p>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <Button onClick={fetchDemo} loading={loading} icon={<Key size={14} />}>
              Get Demo Credentials
            </Button>
            {demoData && (
              <Button onClick={autoLogin} loading={autoLogging} variant="success">
                ⚡ Auto-Login & Go
              </Button>
            )}
          </div>

          {demoData && (
            <div style={{ marginTop: 18 }}>
              <Alert type="success" style={{ marginBottom: 12 }}>
                <div style={{ fontWeight: 500, marginBottom: 8 }}>Demo credentials ready!</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
                  <div>📧 Email: <code style={{ color: 'var(--text-primary)', background: 'var(--green-subtle)', padding: '1px 6px', borderRadius: 4 }}>{demoData.demo_credentials?.email}</code></div>
                  <div>🔑 Password: <code style={{ color: 'var(--text-primary)', background: 'var(--green-subtle)', padding: '1px 6px', borderRadius: 4 }}>{demoData.demo_credentials?.password}</code></div>
                </div>
              </Alert>
              <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 10, padding: '12px 14px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                  <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-muted)' }}>API Key (for external integrations)</span>
                  <button onClick={() => copy(demoData.demo_api_key)} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
                    {copied ? <Check size={12} color="var(--green)" /> : <Copy size={12} />} {copied ? 'Copied!' : 'Copy'}
                  </button>
                </div>
                <code style={{ fontSize: 12, color: 'var(--brand)', wordBreak: 'break-all' }}>{demoData.demo_api_key}</code>
              </div>
            </div>
          )}
        </Card>

        <Card style={{ padding: 24 }}>
          <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 8 }}>
            <Key size={16} style={{ color: 'var(--brand)' }} /> Use Existing API Key
          </div>
          <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>Paste an existing key to use it for API calls (X-API-Key header).</p>
          <div style={{ display: 'flex', gap: 10 }}>
            <input value={manualKey} onChange={e => setManualKey(e.target.value)} placeholder="rl_live_..."
              style={{ flex: 1, background: 'var(--surface-2)', border: '1px solid var(--border-2)', borderRadius: 'var(--r-md)', padding: '9px 12px', color: 'var(--text-primary)', fontSize: 13, outline: 'none', fontFamily: 'var(--font-mono)' }} />
            <Button onClick={saveKey} disabled={!manualKey}>Save</Button>
          </div>
        </Card>

        <Card style={{ padding: 24 }}>
          <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
            <Terminal size={16} style={{ color: 'var(--brand)' }} /> How to Run
          </div>
          <div style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 10, padding: '16px 18px', fontFamily: 'var(--font-mono)', fontSize: 12, lineHeight: 2, color: 'var(--text-secondary)' }}>
            <div style={{ color: 'var(--text-muted)' }}># 1. Start the backend</div>
            <div>cd rl_enterprise/backend</div>
            <div>pip install -r requirements.txt</div>
            <div>python -m uvicorn app.main:app --reload</div>
            <br />
            <div style={{ color: 'var(--text-muted)' }}># 2. Start the frontend (new terminal)</div>
            <div>cd rl_enterprise/frontend</div>
            <div>npm install && npm run dev</div>
            <br />
            <div style={{ color: 'var(--text-muted)' }}># 3. Open browser</div>
            <div>http://localhost:5173 → Login → Done!</div>
          </div>
        </Card>
      </div>
    </div>
  )
}
