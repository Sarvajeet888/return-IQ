/**
 * PHASE 10 — token storage.
 *
 * The property under test is a security decision the codebase already got
 * right: the access token lives in memory only, never in localStorage or
 * sessionStorage. An XSS payload can read browser storage; it cannot read a
 * module-scoped variable that is never written anywhere persistent.
 *
 * That property is invisible in the code — it looks like an ordinary `let` —
 * so it is exactly the kind of thing a well-meaning refactor breaks. Someone
 * fixing "the session doesn't survive a reload" by reaching for localStorage
 * would be making a reasonable-looking change that quietly removes the
 * protection. These tests make that change fail.
 */
import { beforeEach, describe, expect, it } from 'vitest'
import { auth, getAccessToken, setAccessToken, setApiKey } from '../utils/api'

describe('access token storage', () => {
  beforeEach(() => {
    setAccessToken(null)
    localStorage.clear()
    sessionStorage.clear()
  })

  it('round-trips in memory', () => {
    setAccessToken('token-abc123')
    expect(getAccessToken()).toBe('token-abc123')
  })

  it('never writes the token to localStorage', () => {
    setAccessToken('super-secret-jwt-value')

    const dumped = JSON.stringify(localStorage)
    expect(dumped).not.toContain('super-secret-jwt-value')
    expect(localStorage.length).toBe(0)
  })

  it('never writes the token to sessionStorage', () => {
    setAccessToken('super-secret-jwt-value')
    expect(JSON.stringify(sessionStorage)).not.toContain('super-secret-jwt-value')
    expect(sessionStorage.length).toBe(0)
  })

  it('does not survive a page reload, by design', () => {
    // Simulating a reload: the JS runtime is replaced, so module state is
    // gone. The session is restored instead by a silent refresh against the
    // httpOnly cookie, which JS cannot read at all.
    setAccessToken('token-abc123')
    setAccessToken(null) // stand-in for a fresh runtime
    expect(getAccessToken()).toBeNull()
  })

  it('reports logged-out when there is no token', () => {
    expect(auth.isLoggedIn()).toBe(false)
    setAccessToken('t')
    expect(auth.isLoggedIn()).toBe(true)
  })
})

describe('non-sensitive user display data', () => {
  beforeEach(() => {
    localStorage.clear()
    setAccessToken(null)
  })

  it('stores display fields in localStorage so the UI can render before bootstrap', () => {
    // This is fine to persist: a name and role are not credentials, and
    // having them avoids a blank header on every reload.
    auth.setUser({ id: 'u1', full_name: 'Om Pilaji', role: 'org_admin' })
    expect(auth.getUser()).toEqual({ id: 'u1', full_name: 'Om Pilaji', role: 'org_admin' })
  })

  it('survives corrupted localStorage instead of crashing the app', () => {
    // A truncated or hand-edited value must not white-screen the app on load.
    localStorage.setItem('rl_user', '{not valid json')
    expect(auth.getUser()).toBeNull()
  })

  it('returns null when nothing is stored', () => {
    expect(auth.getUser()).toBeNull()
  })

  it('clear() removes the user and the legacy API key', () => {
    auth.setUser({ id: 'u1' })
    setApiKey('rl_live_something')
    auth.clear()
    expect(localStorage.getItem('rl_user')).toBeNull()
    expect(localStorage.getItem('rl_api_key')).toBeNull()
  })

  it('setUser(null) removes the entry rather than storing "null"', () => {
    auth.setUser({ id: 'u1' })
    auth.setUser(null)
    expect(localStorage.getItem('rl_user')).toBeNull()
  })
})
