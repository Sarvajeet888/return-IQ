import React from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

/**
 * Catches render errors so a single broken page doesn't blank the whole app.
 *
 * Why this exists: the Customers page rendered as a completely empty black
 * screen with no message anywhere. The cause was `customers.map(...)` where
 * `customers` had become an object rather than an array (the API changed from
 * returning a bare list to a paginated `{ items, total, page }` object).
 *
 * React unmounts the entire tree when a render throws, so the result is a
 * blank page and a console error nobody looks at. A boundary turns that into
 * a visible, actionable message.
 */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    // Keep the full trace in the console for debugging.
    console.error('Render error caught by ErrorBoundary:', error, info)
  }

  render() {
    if (!this.state.error) return this.props.children

    return (
      <div style={{ padding: 40, maxWidth: 620, margin: '0 auto' }}>
        <div style={{
          background: 'var(--surface)', border: '1px solid var(--red-border)',
          borderRadius: 14, padding: 28,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
            <div style={{
              width: 38, height: 38, borderRadius: 10, background: 'var(--red-subtle)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
            }}>
              <AlertTriangle size={19} style={{ color: 'var(--red)' }} />
            </div>
            <div style={{ fontSize: 16, fontWeight: 500, color: 'var(--text-primary)' }}>
              This page failed to load
            </div>
          </div>

          <p style={{ fontSize: 13.5, color: 'var(--text-secondary)', lineHeight: 1.6, margin: '0 0 18px' }}>
            Something went wrong while rendering. The rest of the app is fine —
            use the sidebar to go elsewhere, or reload this page.
          </p>

          <pre style={{
            background: 'var(--surface-2)', border: '1px solid var(--border)',
            borderRadius: 8, padding: 14, fontSize: 12, color: 'var(--red)',
            overflow: 'auto', maxHeight: 180, margin: '0 0 18px',
            whiteSpace: 'pre-wrap', wordBreak: 'break-word',
          }}>
            {this.state.error?.message || String(this.state.error)}
          </pre>

          <button
            onClick={() => window.location.reload()}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 8,
              background: 'var(--brand)', color: '#fff', border: 'none',
              borderRadius: 8, padding: '10px 18px', fontSize: 13.5,
              fontWeight: 500, cursor: 'pointer',
            }}
          >
            <RefreshCw size={14} /> Reload page
          </button>
        </div>
      </div>
    )
  }
}
