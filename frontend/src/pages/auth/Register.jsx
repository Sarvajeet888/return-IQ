import React, { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Mail, Lock, User, Building, ArrowRight } from 'lucide-react'
import { useAuth } from '../../store/AuthContext.jsx'
import { Alert, Button, Input, Select } from '../../components/ui/index.jsx'
import AuthLayout from './AuthLayout.jsx'

export default function Register() {
  const navigate = useNavigate()
  const { register } = useAuth()
  const [form, setForm] = useState({
    full_name: '', email: '', password: '', org_name: '', platform_type: 'shopify',
    // DPDP Act 2023: consent must be explicit and unambiguous. Defaults to
    // false and the submit button stays disabled until the user ticks it —
    // a pre-ticked box is not valid consent under the Act.
    accepted_terms: false, policy_version: '1.0',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }))

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      // Go through AuthContext's register() (same pattern as Login.jsx) so
      // the in-memory access token AND the React `user` state are both set.
      // Calling api.register() directly updated storage but never React
      // state, so RequireAuth bounced the user back to /login even though
      // registration had actually succeeded.
      await register(form)
      navigate('/dashboard')
    } catch (err) {
      setError(err.response?.data?.detail || 'Registration did not go through. Check the fields and try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Score your first return in the browser. No card, nothing to connect."
      footer={
        <>
          Already have an account? <Link to="/login" style={{ fontWeight: 500 }}>Sign in</Link>
        </>
      }
    >
      {error && <Alert type="error" style={{ marginBottom: 'var(--s4)' }}>{error}</Alert>}

      <form onSubmit={handleSubmit} className="stack">
        <Input label="Full name" type="text" value={form.full_name} onChange={set('full_name')}
          placeholder="Your name" icon={User} autoComplete="name" required />

        <Input label="Work email" type="email" value={form.email} onChange={set('email')}
          placeholder="you@company.com" icon={Mail} autoComplete="email" required />

        <Input label="Password" type="password" value={form.password} onChange={set('password')}
          placeholder="At least 8 characters" icon={Lock} autoComplete="new-password"
          hint="Needs 8+ characters, one uppercase letter, and one digit." required />

        <Input label="Company or store name" type="text" value={form.org_name} onChange={set('org_name')}
          placeholder="Sapna Collection" icon={Building} required />

        <Select label="Where you sell" value={form.platform_type} onChange={set('platform_type')}>
          {['shopify', 'woocommerce', 'magento', 'unicommerce', 'amazon', 'flipkart', 'meesho', 'custom']
            .map(p => <option key={p} value={p}>{p[0].toUpperCase() + p.slice(1)}</option>)}
        </Select>

        <label style={{
          display: 'flex', alignItems: 'flex-start', gap: 10, marginTop: 'var(--s2)',
          fontSize: 'var(--t-xs)', color: 'var(--text-secondary)', lineHeight: 1.6, cursor: 'pointer',
        }}>
          <input
            type="checkbox"
            checked={form.accepted_terms}
            onChange={e => setForm(f => ({ ...f, accepted_terms: e.target.checked }))}
            style={{ marginTop: 2, width: 15, height: 15, flexShrink: 0, cursor: 'pointer', accentColor: 'var(--vermillion)' }}
            required
          />
          <span>
            I agree to the{' '}
            <a href="/terms" target="_blank" rel="noopener noreferrer" style={{ fontWeight: 500 }}>Terms of Service</a>
            {' '}and{' '}
            <a href="/privacy" target="_blank" rel="noopener noreferrer" style={{ fontWeight: 500 }}>Privacy Policy</a>,
            and consent to my data being processed as described there.
          </span>
        </label>

        <Button type="submit" loading={loading} disabled={!form.accepted_terms}
          icon={<ArrowRight size={15} />} style={{ width: '100%' }}>
          Create account
        </Button>
      </form>
    </AuthLayout>
  )
}
