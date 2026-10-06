import React from 'react'
import { useLocation, Link } from 'react-router-dom'
import { Menu, Plus } from 'lucide-react'
import { NAV } from './Sidebar.jsx'
import { StatusDot } from '../ui/index.jsx'

/* Resolve the current route to its section + page name, so the topbar can
   say where you are without every page having to declare it. */
function useCrumbs() {
  const { pathname } = useLocation()
  for (const group of NAV) {
    const hit = group.items.find(i => i.to === pathname)
    if (hit) return { section: group.section, page: hit.label }
  }
  return { section: 'ReturnIQ', page: pathname.replace('/', '') || 'Overview' }
}

export default function Topbar({ onOpenMenu }) {
  const { section, page } = useCrumbs()

  return (
    <header
      style={{
        position: 'sticky', top: 0, zIndex: 'var(--z-topbar)',
        height: 'var(--topbar-h)', flexShrink: 0,
        display: 'flex', alignItems: 'center', gap: 'var(--s3)',
        padding: '0 var(--s6)',
        background: 'var(--bg)',
        borderBottom: '1px solid var(--border)',
      }}
    >
      <button
        className="only-mobile"
        onClick={onOpenMenu}
        aria-label="Open menu"
        style={{ color: 'var(--text-secondary)', display: 'flex', padding: 2 }}
      >
        <Menu size={18} strokeWidth={1.6} />
      </button>

      {/* Location — mono section, then the page in text. Reads like a
          coordinate rather than a breadcrumb trail. */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--s2)', minWidth: 0 }}>
        <span className="eyebrow hide-mobile">{section}</span>
        <span className="hide-mobile" style={{ color: 'var(--border-2)', fontSize: 11 }}>/</span>
        <span
          style={{
            fontSize: 'var(--t-sm)', fontWeight: 500, color: 'var(--text-primary)',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}
        >
          {page}
        </span>
      </div>

      <div className="spacer" />

      <StatusDot tone="live" pulse label="Model online" />

      <div style={{ width: 1, height: 18, background: 'var(--border)' }} className="hide-mobile" />

      <Link
        to="/new-return"
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          fontSize: 'var(--t-xs)', fontWeight: 500,
          color: 'var(--text-primary)', padding: '5px 11px',
          border: '1px solid var(--border-2)', borderRadius: 'var(--r)',
          background: 'var(--surface)', transition: 'var(--tr-color)',
        }}
        onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface-2)' }}
        onMouseLeave={e => { e.currentTarget.style.background = 'var(--surface)' }}
      >
        <Plus size={13} strokeWidth={2} />
        <span className="hide-mobile">New return</span>
      </Link>
    </header>
  )
}
