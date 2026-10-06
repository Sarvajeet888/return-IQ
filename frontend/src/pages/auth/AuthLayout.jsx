import React from 'react'
import { Link } from 'react-router-dom'

/* ── AuthLayout ───────────────────────────────────────────────────────────
   Shared frame for sign in and registration, so the two pages cannot drift
   apart. The covariance motif sits behind everything at low opacity — the
   same mark used in the sidebar and on the landing page, so arriving here
   from any of them feels continuous. */
export default function AuthLayout({ title, subtitle, children, footer }) {
  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'var(--bg)', padding: 'var(--s6)', position: 'relative',
    }}>
      <div className="covariance-bg" aria-hidden="true"
        style={{ position: 'fixed', inset: 0, pointerEvents: 'none' }} />

      <div className="animate-in" style={{ width: '100%', maxWidth: 400, position: 'relative' }}>

        {/* Brand */}
        <Link to="/" style={{
          display: 'flex', alignItems: 'center', gap: 10,
          marginBottom: 'var(--s8)', color: 'inherit',
        }}>
          <svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true">
            <ellipse cx="12" cy="12" rx="10.5" ry="6.5" fill="none" stroke="var(--border-2)" strokeWidth="1" />
            <ellipse cx="12" cy="12" rx="6" ry="3.6" fill="none" stroke="var(--iron)" strokeWidth="1" />
            <circle cx="12" cy="12" r="2.4" fill="var(--vermillion)" />
          </svg>
          <div style={{ lineHeight: 1.25 }}>
            <div style={{ fontFamily: 'var(--font-heading)', fontSize: 15, fontWeight: 700, letterSpacing: '-0.02em' }}>
              ReturnIQ
            </div>
            <div className="eyebrow" style={{ fontSize: 9.5 }}>Signal over noise</div>
          </div>
        </Link>

        <h1 style={{ fontSize: 'var(--t-h2)', marginBottom: 6 }}>{title}</h1>
        {subtitle && (
          <p style={{ fontSize: 'var(--t-sm)', color: 'var(--text-muted)', marginBottom: 'var(--s6)' }}>
            {subtitle}
          </p>
        )}

        <div className="rule" style={{ marginBottom: 'var(--s6)' }} />

        {children}

        {footer && (
          <p style={{ fontSize: 'var(--t-xs)', color: 'var(--text-muted)', marginTop: 'var(--s6)' }}>
            {footer}
          </p>
        )}
      </div>
    </div>
  )
}
