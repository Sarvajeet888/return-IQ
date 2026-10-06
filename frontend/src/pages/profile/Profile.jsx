import React, { useState, useEffect } from 'react'
import { User, Lock, Shield, Trash2, RefreshCw, Check, AlertTriangle, Activity } from 'lucide-react'
import { api } from '../../utils/api.js'
import { Card, PageHeader, Button, Alert, LoadingCenter } from '../../components/ui/index.jsx'

function Section({ title, icon: Icon, children }) {
  return (
    <Card style={{ marginBottom: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20, paddingBottom: 14, borderBottom: '1px solid var(--border)' }}>
        <div style={{ width: 32, height: 32, borderRadius: 8, background: 'var(--brand-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Icon size={16} style={{ color: 'var(--brand)' }} />
        </div>
        <span style={{ fontSize: 15, fontWeight: 500, color: 'var(--text-primary)' }}>{title}</span>
      </div>
      {children}
    </Card>
  )
}

function Field({ label, children }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: 'var(--text-muted)', marginBottom: 6, letterSpacing: '0.5px' }}>{label}</label>
      {children}
    </div>
  )
}

function Input({ value, onChange, type = 'text', placeholder, disabled }) {
  return (
    <input
      type={type}
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      disabled={disabled}
      style={{
        width: '100%', padding: '9px 12px', borderRadius: 8,
        border: '1px solid var(--border-2)', background: 'var(--surface-2)',
        color: 'var(--text-primary)', fontSize: 13,
        outline: 'none', boxSizing: 'border-box',
        opacity: disabled ? 0.6 : 1,
      }}
    />
  )
}

export default function Profile() {
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [msg, setMsg] = useState({ type: '', text: '' })
  const [name, setName] = useState('')
  const [savingProfile, setSavingProfile] = useState(false)
  const [curPwd, setCurPwd] = useState('')
  const [newPwd, setNewPwd] = useState('')
  const [savingPwd, setSavingPwd] = useState(false)
  const [activity, setActivity] = useState([])
  const [actLoading, setActLoading] = useState(false)

  useEffect(() => {
    load()
  }, [])

  async function load() {
    try {
      const p = await api.getProfile()
      setProfile(p)
      setName(p.full_name || '')
    } catch (e) {
      setMsg({ type: 'error', text: e.message })
    } finally {
      setLoading(false)
    }
  }

  async function saveProfile() {
    setSavingProfile(true)
    setMsg({ type: '', text: '' })
    try {
      await api.updateProfile({ full_name: name })
      setMsg({ type: 'success', text: 'Profile updated successfully' })
      load()
    } catch (e) {
      setMsg({ type: 'error', text: e.response?.data?.detail || e.message })
    } finally {
      setSavingProfile(false)
    }
  }

  async function changePassword() {
    setSavingPwd(true)
    setMsg({ type: '', text: '' })
    try {
      await api.changePassword({ current_password: curPwd, new_password: newPwd })
      setMsg({ type: 'success', text: 'Password changed. You may need to log in again on other devices.' })
      setCurPwd(''); setNewPwd('')
    } catch (e) {
      setMsg({ type: 'error', text: e.response?.data?.detail || e.message })
    } finally {
      setSavingPwd(false)
    }
  }

  async function revokeSessions() {
    try {
      await api.revokeAllSessions()
      setMsg({ type: 'success', text: 'All other sessions revoked' })
    } catch (e) {
      setMsg({ type: 'error', text: e.message })
    }
  }

  async function loadActivity() {
    setActLoading(true)
    try {
      const logs = await api.getAccountActivity()
      setActivity(logs.slice(0, 20))
    } catch (e) { /* silent */ }
    finally { setActLoading(false) }
  }

  if (loading) return <LoadingCenter />

  return (
    <div className="animate-in" style={{ maxWidth: 680 }}>
      <PageHeader title="My Profile" subtitle="Manage your identity, password and sessions" />
      {msg.text && <Alert type={msg.type || 'info'} style={{ marginBottom: 20 }}>{msg.text}</Alert>}

      <Section title="Personal Information" icon={User}>
        <Field label="Full Name">
          <Input value={name} onChange={setName} placeholder="Your full name" />
        </Field>
        <Field label="Email">
          <Input value={profile?.email || ''} onChange={() => {}} disabled placeholder="email" />
        </Field>
        <Field label="Role">
          <Input value={profile?.role || ''} onChange={() => {}} disabled />
        </Field>
        <Button onClick={saveProfile} loading={savingProfile} icon={<Check size={14} />}>Save Changes</Button>
      </Section>

      <Section title="Change Password" icon={Lock}>
        <Field label="Current Password">
          <Input type="password" value={curPwd} onChange={setCurPwd} placeholder="Current password" />
        </Field>
        <Field label="New Password">
          <Input type="password" value={newPwd} onChange={setNewPwd} placeholder="Min 8 chars, 1 uppercase, 1 digit" />
        </Field>
        <Button onClick={changePassword} loading={savingPwd} disabled={!curPwd || !newPwd}>Update Password</Button>
      </Section>

      <Section title="Session Management" icon={Shield}>
        <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 16 }}>
          Last login: <strong>{profile?.last_login ? new Date(profile.last_login).toLocaleString() : 'N/A'}</strong>
          <br />
          Revoking all sessions will sign you out of every other device. You'll stay logged in here.
        </div>
        <Button variant="danger" onClick={revokeSessions} icon={<Shield size={14} />}>Revoke All Other Sessions</Button>
      </Section>

      <Section title="Account Activity" icon={Activity}>
        {activity.length === 0 ? (
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <Button variant="secondary" onClick={loadActivity} loading={actLoading} icon={<RefreshCw size={14} />}>Load Activity Log</Button>
          </div>
        ) : (
          <div>
            {activity.map((log, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0', borderBottom: i < activity.length - 1 ? '1px solid var(--border)' : 'none' }}>
                <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--brand)', flexShrink: 0 }} />
                <div style={{ flex: 1 }}>
                  <span style={{ fontSize: 13, color: 'var(--text-primary)', fontWeight: 500 }}>{log.action}</span>
                  {log.detail && <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 8 }}>{log.detail}</span>}
                </div>
                <span style={{ fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{new Date(log.created_at).toLocaleString()}</span>
              </div>
            ))}
          </div>
        )}
      </Section>

      <Section title="Danger Zone" icon={AlertTriangle}>
        <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 16 }}>
          Deleting your account will deactivate it immediately. Your data is retained for audit purposes.
        </div>
        <Button variant="danger" icon={<Trash2 size={14} />} onClick={async () => {
          if (window.confirm('Are you sure? This will deactivate your account.')) {
            try { await api.deleteAccount(); window.location.href = '/' } catch (e) { setMsg({ type: 'error', text: e.message }) }
          }
        }}>Delete My Account</Button>
      </Section>
    </div>
  )
}
