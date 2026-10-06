import React, { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Package, PlusCircle, BarChart3, Users, Warehouse,
  Brain, LogOut, PanelLeft, X, Key, Zap, FileText, UserCircle, ShieldCheck,
} from 'lucide-react'
import { useAuth } from '../../store/AuthContext.jsx'

/* ── Navigation ───────────────────────────────────────────────────────────
   Same routes as before — only the grouping language changed. Sections are
   named for what the operator is doing, not for how the app is built:
   they watch the control room, work the returns, read the intelligence,
   run the operations. */
export const NAV = [
  { section: 'Control room', items: [
    { to: '/dashboard', icon: LayoutDashboard, label: 'Overview' },
    { to: '/analytics',  icon: BarChart3,      label: 'Analytics' },
  ]},
  { section: 'Returns', items: [
    { to: '/returns',    icon: Package,    label: 'All returns' },
    { to: '/new-return', icon: PlusCircle, label: 'New return' },
  ]},
  { section: 'Intelligence', items: [
    { to: '/ai',        icon: Brain,    label: 'Models' },
    { to: '/workflows', icon: Zap,      label: 'Workflows' },
    { to: '/reports',   icon: FileText, label: 'Reports' },
  ]},
  { section: 'Operations', items: [
    { to: '/customers',  icon: Users,     label: 'Customers' },
    { to: '/warehouses', icon: Warehouse, label: 'Warehouses' },
  ]},
  { section: 'Account', items: [
    { to: '/profile', icon: UserCircle,  label: 'Profile' },
    { to: '/admin',   icon: ShieldCheck, label: 'Admin' },
    { to: '/setup',   icon: Key,         label: 'API keys' },
  ]},
]

const ROLE_TONE = {
  super_admin: 'var(--red)',
  org_admin: 'var(--vermillion)',
  warehouse_manager: 'var(--amber)',
  viewer: 'var(--text-muted)',
}

/* ── Mark ─────────────────────────────────────────────────────────────────
   The covariance ellipse tightening onto a point: the brand motif reduced
   to 16px. Two rings and a dot — noise, convergence, estimate. */
function Mark({ size = 22 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" style={{ flexShrink: 0 }}>
      <ellipse cx="12" cy="12" rx="10.5" ry="6.5" fill="none" stroke="var(--border-2)" strokeWidth="1" />
      <ellipse cx="12" cy="12" rx="6" ry="3.6" fill="none" stroke="var(--iron)" strokeWidth="1" />
      <circle cx="12" cy="12" r="2.4" fill="var(--vermillion)" />
    </svg>
  )
}

function NavItem({ to, icon: Icon, label, collapsed, onNavigate }) {
  return (
    <NavLink
      to={to}
      onClick={onNavigate}
      title={collapsed ? label : undefined}
      style={({ isActive }) => ({
        position: 'relative',
        display: 'flex', alignItems: 'center', gap: 10,
        padding: collapsed ? '7px 0' : '6px 10px 6px 12px',
        justifyContent: collapsed ? 'center' : 'flex-start',
        fontSize: 'var(--t-sm)', fontWeight: isActive ? 500 : 400,
        color: isActive ? 'var(--text-primary)' : 'var(--text-muted)',
        background: 'transparent',
        borderRadius: 'var(--r-sm)',
        transition: 'var(--tr-color)',
      })}
      onMouseEnter={e => { e.currentTarget.style.color = 'var(--text-primary)' }}
      onMouseLeave={e => {
        const on = e.currentTarget.getAttribute('aria-current') === 'page'
        e.currentTarget.style.color = on ? 'var(--text-primary)' : 'var(--text-muted)'
      }}
    >
      {({ isActive }) => (
        <>
          {/* Active marker: a short Vermillion rule, not a filled card. */}
          {isActive && !collapsed && (
            <span
              aria-hidden="true"
              style={{
                position: 'absolute', left: 0, top: '50%', transform: 'translateY(-50%)',
                width: 2, height: 15, background: 'var(--vermillion)', borderRadius: 1,
              }}
            />
          )}
          <Icon size={15} strokeWidth={1.6} style={{ flexShrink: 0, opacity: isActive ? 1 : 0.75 }} />
          {!collapsed && <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</span>}
        </>
      )}
    </NavLink>
  )
}

function SidebarBody({ collapsed, setCollapsed, onNavigate }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  async function handleLogout() {
    await logout()
    navigate('/login')
  }

  return (
    <div
      style={{
        display: 'flex', flexDirection: 'column', height: '100%',
        background: 'var(--surface)', borderRight: '1px solid var(--border)',
      }}
    >
      {/* Brand */}
      <div
        style={{
          display: 'flex', alignItems: 'center', gap: 9,
          padding: collapsed ? '0 0 0 0' : '0 var(--s4)',
          justifyContent: collapsed ? 'center' : 'flex-start',
          height: 'var(--topbar-h)', flexShrink: 0,
          borderBottom: '1px solid var(--border)',
        }}
      >
        <Mark />
        {!collapsed && (
          <div style={{ minWidth: 0, lineHeight: 1.2 }}>
            <div style={{ fontFamily: 'var(--font-heading)', fontSize: 14, fontWeight: 700, letterSpacing: '-0.02em' }}>
              ReturnIQ
            </div>
            <div className="eyebrow" style={{ fontSize: 9, letterSpacing: '0.14em' }}>Signal over noise</div>
          </div>
        )}
        {!collapsed && (
          <button
            onClick={() => setCollapsed(true)}
            aria-label="Collapse sidebar"
            style={{ marginLeft: 'auto', color: 'var(--text-faint)', display: 'flex', padding: 3, transition: 'var(--tr-color)' }}
            onMouseEnter={e => { e.currentTarget.style.color = 'var(--text-primary)' }}
            onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-faint)' }}
          >
            <PanelLeft size={15} strokeWidth={1.6} />
          </button>
        )}
      </div>

      {/* Nav */}
      <nav className="scroll-y" style={{ flex: 1, padding: 'var(--s4) var(--s3)' }}>
        {collapsed && (
          <button
            onClick={() => setCollapsed(false)}
            aria-label="Expand sidebar"
            style={{ display: 'flex', margin: '0 auto var(--s4)', color: 'var(--text-faint)', padding: 3 }}
          >
            <PanelLeft size={15} strokeWidth={1.6} />
          </button>
        )}

        {NAV.map(({ section, items }, si) => (
          <div key={section} style={{ marginBottom: 'var(--s5)' }}>
            {collapsed ? (
              si > 0 && <div className="rule rule--soft" style={{ margin: '0 8px var(--s3)' }} />
            ) : (
              <div
                className="eyebrow"
                style={{ padding: '0 0 var(--s2) 12px', fontSize: 9.5, letterSpacing: '0.15em' }}
              >
                {section}
              </div>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
              {items.map(item => (
                <NavItem key={item.to} {...item} collapsed={collapsed} onNavigate={onNavigate} />
              ))}
            </div>
          </div>
        ))}
      </nav>

      {/* User */}
      <div style={{ padding: 'var(--s3)', borderTop: '1px solid var(--border)', flexShrink: 0 }}>
        {!collapsed && user && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '0 4px var(--s3)' }}>
            <div
              style={{
                width: 26, height: 26, borderRadius: '50%', flexShrink: 0,
                background: 'var(--surface-3)', border: '1px solid var(--border-2)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 11, fontWeight: 500, color: 'var(--text-secondary)',
              }}
            >
              {(user.full_name?.[0] || user.email?.[0] || 'U').toUpperCase()}
            </div>
            <div style={{ flex: 1, minWidth: 0, lineHeight: 1.3 }}>
              <div style={{ fontSize: 'var(--t-xs)', color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {user.full_name || 'User'}
              </div>
              <div style={{ fontSize: 10, color: ROLE_TONE[user.role] || 'var(--text-muted)', letterSpacing: '0.04em' }}>
                {user.role?.replace(/_/g, ' ')}
              </div>
            </div>
          </div>
        )}
        <button
          onClick={handleLogout}
          style={{
            display: 'flex', alignItems: 'center', gap: 9, width: '100%',
            padding: '6px 12px', borderRadius: 'var(--r-sm)',
            justifyContent: collapsed ? 'center' : 'flex-start',
            color: 'var(--text-muted)', fontSize: 'var(--t-sm)',
            transition: 'var(--tr-color)',
          }}
          onMouseEnter={e => { e.currentTarget.style.color = 'var(--red)' }}
          onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-muted)' }}
        >
          <LogOut size={15} strokeWidth={1.6} />
          {!collapsed && 'Sign out'}
        </button>
      </div>
    </div>
  )
}

export default function Sidebar({ collapsed, setCollapsed, mobileOpen, setMobileOpen }) {
  return (
    <>
      <aside className="shell__sidebar hide-mobile" data-collapsed={String(collapsed)}>
        <SidebarBody collapsed={collapsed} setCollapsed={setCollapsed} />
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div
          className="only-mobile"
          style={{ position: 'fixed', inset: 0, zIndex: 'var(--z-overlay)', display: 'flex' }}
        >
          <div style={{ width: 250, height: '100%' }} className="slide-in">
            <SidebarBody collapsed={false} setCollapsed={() => {}} onNavigate={() => setMobileOpen(false)} />
          </div>
          <div
            onClick={() => setMobileOpen(false)}
            style={{ flex: 1, background: 'rgba(21,23,27,0.5)' }}
          />
          <button
            onClick={() => setMobileOpen(false)}
            aria-label="Close menu"
            style={{ position: 'absolute', top: 14, right: 14, color: 'var(--bone)' }}
          >
            <X size={20} />
          </button>
        </div>
      )}
    </>
  )
}
