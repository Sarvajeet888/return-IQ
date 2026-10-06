import React, { createContext, useContext, useState, useEffect } from 'react'
import { auth, api, setAccessToken } from '../utils/api.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(false)       // login()/register() in flight
  const [bootstrapping, setBootstrapping] = useState(true) // initial session check on load

  // The access token only lives in memory, so a hard reload starts with
  // none. Try a silent refresh off the httpOnly cookie before deciding the
  // user is logged out - this is what lets a session survive a reload.
  useEffect(() => {
    let cancelled = false

    async function bootstrap() {
      try {
        const res = await api.refresh()
        if (cancelled) return
        setAccessToken(res.access_token)
        const u = await api.me()
        if (cancelled) return
        auth.setUser(u)
        setUser(u)
      } catch {
        // No valid session - the normal case for a first-time visitor.
        if (!cancelled) {
          setAccessToken(null)
          auth.clear()
          setUser(null)
        }
      } finally {
        if (!cancelled) setBootstrapping(false)
      }
    }

    bootstrap()
    return () => { cancelled = true }
  }, [])

  const login = async (email, password) => {
    setLoading(true)
    try {
      const res = await api.login({ email, password })
      setAccessToken(res.access_token)
      auth.setUser(res.user)
      setUser(res.user)
      return res
    } finally {
      setLoading(false)
    }
  }

  const register = async (data) => {
    setLoading(true)
    try {
      const res = await api.register(data)
      setAccessToken(res.access_token)
      auth.setUser(res.user)
      setUser(res.user)
      return res
    } finally {
      setLoading(false)
    }
  }

  const logout = async () => {
    try { await api.logout() } catch {}
    setAccessToken(null)
    auth.clear()
    setUser(null)
  }

  const refreshUser = async () => {
    try {
      const u = await api.me()
      auth.setUser(u)
      setUser(u)
    } catch {}
  }

  return (
    <AuthContext.Provider value={{ user, loading, bootstrapping, login, register, logout, refreshUser, isLoggedIn: !!user }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
