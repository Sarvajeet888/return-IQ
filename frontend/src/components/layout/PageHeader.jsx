import React from 'react'

/* ── PageHeader ───────────────────────────────────────────────────────────
   Every page opens the same way: a mono eyebrow naming the section, the
   title, and a rule underneath. The rule is the structural device that ties
   the header to the content below it — nothing floats free of a rule in
   this system. */
export default function PageHeader({ title, subtitle, eyebrow, actions }) {
  return (
    <header style={{ marginBottom: 'var(--s6)' }}>
      <div
        style={{
          display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between',
          gap: 'var(--s5)', flexWrap: 'wrap', paddingBottom: 'var(--s4)',
        }}
      >
        <div style={{ minWidth: 0 }}>
          {eyebrow && <div className="eyebrow" style={{ marginBottom: 'var(--s2)' }}>{eyebrow}</div>}
          <h1 style={{ fontSize: 'var(--t-h2)' }}>{title}</h1>
          {subtitle && (
            <p style={{ fontSize: 'var(--t-sm)', color: 'var(--text-muted)', marginTop: 5, maxWidth: '62ch' }}>
              {subtitle}
            </p>
          )}
        </div>
        {actions && (
          <div style={{ display: 'flex', gap: 'var(--s2)', flexShrink: 0 }}>{actions}</div>
        )}
      </div>
      <div className="rule" />
    </header>
  )
}
