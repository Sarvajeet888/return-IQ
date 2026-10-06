import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './store/AuthContext.jsx'
import AppShell from './components/layout/AppShell.jsx'
import Landing from './pages/Landing.jsx'
import Login from './pages/auth/Login.jsx'
import Register from './pages/auth/Register.jsx'
import Dashboard from './pages/dashboard/Dashboard.jsx'
import ReturnsList from './pages/returns/ReturnsList.jsx'
import NewReturn from './pages/returns/NewReturn.jsx'
import Analytics from './pages/analytics/Analytics.jsx'
import { CustomersPage, WarehousesPage } from './pages/misc/Pages.jsx'
import Setup from './pages/settings/Setup.jsx'
import Profile from './pages/profile/Profile.jsx'
import AdminPanel from './pages/admin/AdminPanel.jsx'
import Workflows from './pages/workflows/Workflows.jsx'
import Reports from './pages/reports/Reports.jsx'
import AIPlatform from './pages/ai/AIPlatform.jsx'
import { LoadingCenter } from './components/ui/index.jsx'
import './index.css'

function RequireAuth({ children }) {
  const { isLoggedIn, bootstrapping } = useAuth()
  if (bootstrapping) return <LoadingCenter text="Loading..." />
  if (!isLoggedIn) return <Navigate to="/login" replace />
  return children
}

function AppLayout({ children }) {
  return <AppShell>{children}</AppShell>
}

function Protected({ children }) {
  return <RequireAuth><AppLayout>{children}</AppLayout></RequireAuth>
}

function AppRoutes() {
  const { isLoggedIn, bootstrapping } = useAuth()
  return (
    <Routes>
      {/* Public */}
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={!bootstrapping && isLoggedIn ? <Navigate to="/dashboard" replace /> : <Login />} />
      <Route path="/register" element={!bootstrapping && isLoggedIn ? <Navigate to="/dashboard" replace /> : <Register />} />

      {/* Protected */}
      <Route path="/dashboard"   element={<Protected><Dashboard /></Protected>} />
      <Route path="/returns"     element={<Protected><ReturnsList /></Protected>} />
      <Route path="/new-return"  element={<Protected><NewReturn /></Protected>} />
      <Route path="/analytics"   element={<Protected><Analytics /></Protected>} />
      <Route path="/customers"   element={<Protected><CustomersPage /></Protected>} />
      <Route path="/warehouses"  element={<Protected><WarehousesPage /></Protected>} />
      <Route path="/ai"          element={<Protected><AIPlatform /></Protected>} />
      <Route path="/workflows"   element={<Protected><Workflows /></Protected>} />
      <Route path="/reports"     element={<Protected><Reports /></Protected>} />
      <Route path="/admin"       element={<Protected><AdminPanel /></Protected>} />
      <Route path="/profile"     element={<Protected><Profile /></Protected>} />
      <Route path="/setup"       element={<AppLayout><Setup /></AppLayout>} />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  )
}
