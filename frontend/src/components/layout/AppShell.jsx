import React, { useState } from 'react'
import { useLocation } from 'react-router-dom'
import Sidebar from './Sidebar.jsx'
import Topbar from './Topbar.jsx'
import StatusBar from './StatusBar.jsx'
import ErrorBoundary from '../ErrorBoundary.jsx'

/* ── AppShell ─────────────────────────────────────────────────────────────
       Sidebar + Topbar + Page + Status bar

   Routing, auth, and data fetching are all untouched by this component —
   it only arranges what already exists.

   The ErrorBoundary sits INSIDE the page region so the sidebar survives a
   page crash and the operator can navigate away instead of staring at a
   blank screen. The page is keyed on pathname so the enter animation
   replays on navigation. */
export default function AppShell({ children }) {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const { pathname } = useLocation()

  return (
    <div className="shell">
      <Sidebar
        collapsed={collapsed}
        setCollapsed={setCollapsed}
        mobileOpen={mobileOpen}
        setMobileOpen={setMobileOpen}
      />

      <div className="shell__main">
        <Topbar onOpenMenu={() => setMobileOpen(true)} />

        <main className="shell__page">
          <div key={pathname} className="page-enter">
            <ErrorBoundary>{children}</ErrorBoundary>
          </div>
        </main>

        <StatusBar />
      </div>
    </div>
  )
}
