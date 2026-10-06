import React, { useEffect, useState } from 'react'
import { api } from '../../utils/api.js'
import { StatusDot } from '../ui/index.jsx'

/* ── StatusBar ────────────────────────────────────────────────────────────
   A thin dark rule pinned to the bottom of the shell. Graphite, mono, one
   line — the instrument strip of a control room. It reports on the system,
   never on the page, so it stays identical everywhere and becomes a fixed
   point the operator can trust.

   It reads the existing /health endpoint. No new API. */
export default function StatusBar() {
  const [health, setHealth] = useState(null)
  const [clock, setClock] = useState(() => new Date())

  useEffect(() => {
    let alive = true
    const check = () => api.health()
      .then(h => { if (alive) setHealth(h) })
      .catch(() => { if (alive) setHealth({ status: 'unreachable' }) })

    check()
    const poll = setInterval(check, 60000)
    const tick = setInterval(() => setClock(new Date()), 1000)
    return () => { alive = false; clearInterval(poll); clearInterval(tick) }
  }, [])

  const ok = health?.status === 'ok' || health?.status === 'healthy'
  const tone = health == null ? 'idle' : ok ? 'live' : 'down'
  const stateLabel = health == null ? 'connecting' : ok ? 'operational' : 'degraded'

  const cell = {
    display: 'inline-flex', alignItems: 'center', gap: 6,
    fontFamily: 'var(--font-mono)', fontSize: 10,
    letterSpacing: '0.06em', color: 'var(--text-on-dark)',
    opacity: 0.72, whiteSpace: 'nowrap',
  }

  return (
    <footer
      style={{
        position: 'sticky', bottom: 0, zIndex: 'var(--z-status)',
        height: 'var(--statusbar-h)', flexShrink: 0,
        display: 'flex', alignItems: 'center', gap: 'var(--s5)',
        padding: '0 var(--s6)',
        background: 'var(--graphite)',
        overflowX: 'auto',
      }}
    >
      <span style={{ ...cell, opacity: 1 }}>
        <StatusDot tone={tone} pulse={tone === 'live'} size={5} />
        system {stateLabel}
      </span>

      <span style={cell} className="hide-mobile">
        pipeline <span style={{ color: 'var(--brand-light)' }}>returns → signal → decision</span>
      </span>

      <span className="spacer" />

      {health?.version && (
        <span style={cell} className="hide-mobile">build {health.version}</span>
      )}
      <span style={cell}>
        {clock.toLocaleTimeString('en-IN', { hour12: false })} IST
      </span>
    </footer>
  )
}
