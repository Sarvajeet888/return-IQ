import React, { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Mail, Lock, Eye, EyeOff, ArrowRight } from 'lucide-react'
import { useAuth } from '../../store/AuthContext.jsx'
import { api } from '../../utils/api.js'
import { Alert, Button, Input } from '../../components/ui/index.jsx'
import AuthLayout from './AuthLayout.jsx'

/* Auth flow untouched: login() from AuthContext, the demo-credentials
   endpoint, and the same fallback pair. Presentation only. */
export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ email: '', password: '' })
  const [showPw, setShowPw] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [demoLoading, setDemoLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      await login(form.email, form.password)
      navigate('/dashboard')
    } catch (err) {
      setError(err.response?.data?.detail || 'That email and password did not match. Check both and try again.')
    } finally {
      setLoading(false)
    }
  }

  async function fillDemo() {
    setDemoLoading(true)
    try {
      const res = await api.getDemoCredentials()
      const creds = res.demo_credentials
      setForm({ email: creds.email, password: creds.password })
    } catch {
      setForm({ email: 'admin@sapnacollection.com', password: 'Demo@12345' })
    } finally {
      setDemoLoading(false)
    }
  }

  return (
    <AuthLayout
      title="Sign in"
      subtitle="Pick up where your returns left off."
      footer={
        <>
          No account yet? <Link to="/register" style={{ fontWeight: 500 }}>Create one</Link>
        </>
      }
    >
      {error && <Alert type="error" style={{ marginBottom: 'var(--s4)' }}>{error}</Alert>}

      <form onSubmit={handleSubmit} className="stack">
        <Input
          label="Email"
          type="email"
          value={form.email}
          onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
          placeholder="you@company.com"
          icon={Mail}
          autoComplete="email"
          required
        />

        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <label className="label">Password</label>
          <div style={{ position: 'relative' }}>
            <Lock size={14} style={{
              position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)',
              color: 'var(--text-muted)', pointerEvents: 'none',
            }} />
            <input
              type={showPw ? 'text' : 'password'}
              value={form.password}
              onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
              placeholder="Your password"
              autoComplete="current-password"
              required
              style={{
                width: '100%', background: 'var(--bone)', border: '1px solid var(--border-2)',
                borderRadius: 'var(--r)', padding: '9px 38px 9px 34px',
                color: 'var(--text-primary)', fontSize: 'var(--t-sm)', outline: 'none',
                transition: 'var(--tr-color)',
              }}
              onFocus={e => { e.target.style.borderColor = 'var(--vermillion)' }}
              onBlur={e => { e.target.style.borderColor = 'var(--border-2)' }}
            />
            <button
              type="button"
              onClick={() => setShowPw(s => !s)}
              aria-label={showPw ? 'Hide password' : 'Show password'}
              style={{
                position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)',
                color: 'var(--text-muted)', display: 'flex', padding: 2,
              }}
            >
              {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          </div>
        </div>

        <Button type="submit" loading={loading} icon={<ArrowRight size={15} />} style={{ width: '100%' }}>
          Sign in
        </Button>
      </form>

      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s3)', margin: 'var(--s5) 0' }}>
        <div className="rule" style={{ flex: 1 }} />
        <span className="eyebrow">or</span>
        <div className="rule" style={{ flex: 1 }} />
      </div>

      <Button variant="secondary" onClick={fillDemo} loading={demoLoading} style={{ width: '100%' }}>
        Use the demo account
      </Button>

      <div style={{
        marginTop: 'var(--s4)', padding: 'var(--s3) var(--s4)',
        border: '1px solid var(--border)', borderRadius: 'var(--r)',
        background: 'var(--surface)',
      }}>
        <div className="eyebrow" style={{ marginBottom: 6 }}>Demo credentials</div>
        <div style={{ fontSize: 'var(--t-xs)', color: 'var(--text-muted)', lineHeight: 1.75 }}>
          <div>admin@sapnacollection.com</div>
          <div>Demo@12345</div>
        </div>
      </div>
    </AuthLayout>
  )
}
