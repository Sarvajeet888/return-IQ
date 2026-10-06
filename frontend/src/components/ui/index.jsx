/* ═══════════════════════════════════════════════════════════════════════════
   ui — the reusable component library.

   Every component here is generic. Nothing in this file knows about
   returns, predictions, or any single page. Page-specific composition
   belongs in the page, not here.

   Colour discipline (from the design system):
     Iron       = raw / unresolved / noise
     Vermillion = resolved / decision / signal
     Ash        = structure (rules, grids, borders)
   ═══════════════════════════════════════════════════════════════════════ */
import React, { useId } from 'react'
import { Loader2 } from 'lucide-react'

/* ── Panel ──────────────────────────────────────────────────────────────
   The base container. Flat, hairline border, no shadow. `title` renders a
   header row with a hairline under it; `action` sits opposite the title. */
export function Panel({ title, eyebrow, action, children, pad = true, style, ...props }) {
  return (
    <section
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--r-lg)',
        ...style,
      }}
      {...props}
    >
      {(title || action) && (
        <header
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            gap: 'var(--s3)', padding: '14px var(--s5)',
            borderBottom: '1px solid var(--border)',
          }}
        >
          <div style={{ minWidth: 0 }}>
            {eyebrow && <div className="eyebrow" style={{ marginBottom: 3 }}>{eyebrow}</div>}
            {title && (
              <h4 style={{ fontSize: 14, fontWeight: 500, letterSpacing: '-0.012em' }}>{title}</h4>
            )}
          </div>
          {action && <div style={{ flexShrink: 0 }}>{action}</div>}
        </header>
      )}
      <div style={pad ? { padding: 'var(--s5)' } : undefined}>{children}</div>
    </section>
  )
}

/* Card — kept as a thin alias so existing call sites keep working. */
export function Card({ children, style, ...props }) {
  return (
    <div
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--r-lg)',
        padding: 'var(--s5)',
        ...style,
      }}
      {...props}
    >
      {children}
    </div>
  )
}

/* ── Divider ──────────────────────────────────────────────────────────── */
export function Divider({ vertical = false, soft = false, style }) {
  return (
    <div
      role="separator"
      style={vertical
        ? { width: 1, alignSelf: 'stretch', background: soft ? 'var(--surface-3)' : 'var(--border)', ...style }
        : { height: 1, background: soft ? 'var(--surface-3)' : 'var(--border)', margin: 'var(--s4) 0', ...style }}
    />
  )
}

/* ── MonoValue ────────────────────────────────────────────────────────────
   Any figure the user might compare or copy. Tabular figures so columns of
   money line up. This is the workhorse of the whole data layer. */
export function MonoValue({ children, size = 13, color = 'var(--text-primary)', weight = 500, style }) {
  return (
    <span
      data-numeric=""
      style={{ fontSize: size, color, fontWeight: weight, whiteSpace: 'nowrap', ...style }}
    >
      {children}
    </span>
  )
}

/* ── Metric ───────────────────────────────────────────────────────────────
   A single figure with a label beneath it. Deliberately not a card: metrics
   sit in a bare grid divided by rules, so a row of them reads as one
   instrument panel rather than six floating boxes. */
export function Metric({ value, label, sub, delta, size = 'md', loading, tone = 'var(--text-primary)' }) {
  const fs = size === 'lg' ? 'var(--t-metric-lg)' : size === 'sm' ? 'var(--t-metric-sm)' : 'var(--t-metric)'
  const deltaNum = delta != null ? parseFloat(delta) : null
  const up = deltaNum > 0

  return (
    <div style={{ minWidth: 0 }}>
      {loading ? (
        <div className="skeleton" style={{ height: 30, width: '62%', marginBottom: 8 }} />
      ) : (
        <div
          data-numeric=""
          style={{ fontSize: fs, fontWeight: 500, lineHeight: 1.05, color: tone, letterSpacing: '-0.035em' }}
        >
          {value}
        </div>
      )}
      <div
        style={{
          marginTop: 'var(--s2)', fontSize: 'var(--t-xs)', color: 'var(--text-muted)',
          letterSpacing: '0.01em', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}
      >
        {label}
      </div>
      {(sub || (deltaNum != null && !Number.isNaN(deltaNum))) && (
        <div style={{ marginTop: 3, display: 'flex', alignItems: 'center', gap: 'var(--s2)' }}>
          {sub && <span style={{ fontSize: 'var(--t-micro)', color: 'var(--text-faint)' }}>{sub}</span>}
          {deltaNum != null && !Number.isNaN(deltaNum) && (
            <MonoValue size={11} color={up ? 'var(--green)' : 'var(--red)'}>
              {up ? '↑' : '↓'} {Math.abs(deltaNum)}%
            </MonoValue>
          )}
        </div>
      )}
    </div>
  )
}

/* MetricRow — metrics separated by vertical rules, not gaps. */
export function MetricRow({ children, columns = 'repeat(auto-fit, minmax(150px, 1fr))' }) {
  const items = React.Children.toArray(children)
  return (
    <div
      className="stagger"
      style={{
        display: 'grid', gridTemplateColumns: columns,
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 'var(--r-lg)', overflow: 'hidden',
      }}
    >
      {items.map((child, i) => (
        <div
          key={i}
          style={{
            '--i': i, padding: 'var(--s5)',
            borderLeft: i === 0 ? 'none' : '1px solid var(--border)',
          }}
        >
          {child}
        </div>
      ))}
    </div>
  )
}

/* StatCard — legacy alias, so pages not yet moved to Metric still render. */
export function StatCard({ label, value, sub, trend, loading }) {
  return (
    <Card>
      <Metric value={value} label={label} sub={sub} delta={trend} loading={loading} />
    </Card>
  )
}

/* ── SignalBar ────────────────────────────────────────────────────────────
   A horizontal bar reading noise -> signal. The track is the unresolved
   remainder; the fill is the resolved portion. */
export function SignalBar({ value = 0, max = 100, tone, height = 5, showValue = true, label }) {
  const pct = Math.max(0, Math.min(100, (Number(value) / max) * 100))
  const color = tone || (pct >= 70 ? 'var(--red)' : pct >= 40 ? 'var(--amber-fill)' : 'var(--green)')

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s3)', minWidth: 0 }}>
      {label && (
        <span style={{ fontSize: 'var(--t-xs)', color: 'var(--text-muted)', flexShrink: 0 }}>{label}</span>
      )}
      <div
        style={{
          flex: 1, height, background: 'var(--surface-3)',
          borderRadius: 'var(--r-pill)', overflow: 'hidden', minWidth: 40,
        }}
      >
        <div
          style={{
            width: `${pct}%`, height: '100%', background: color,
            borderRadius: 'var(--r-pill)',
            transition: 'width var(--d-slow) var(--ease-converge)',
          }}
        />
      </div>
      {showValue && (
        <MonoValue size={11} color={color} style={{ minWidth: 26, textAlign: 'right' }}>
          {Number(value).toFixed(0)}
        </MonoValue>
      )}
    </div>
  )
}

/* RiskBar — legacy alias for SignalBar. */
export function RiskBar({ score, size = 'md' }) {
  return <SignalBar value={score ?? 0} height={size === 'sm' ? 4 : 5} />
}

/* ── StatusDot ────────────────────────────────────────────────────────── */
const DOT_TONES = {
  live: 'var(--green)',
  signal: 'var(--vermillion)',
  idle: 'var(--iron)',
  warn: 'var(--amber-fill)',
  down: 'var(--red)',
}

export function StatusDot({ tone = 'idle', pulse = false, size = 6, label }) {
  const color = DOT_TONES[tone] || tone
  /* PHASE 48 — a bare coloured dot conveys its meaning through colour alone,
     which WCAG 1.4.1 prohibits: it is invisible to a screen reader and
     meaningless to a user with colour vision deficiency.

     When a visible `label` is supplied the text carries the meaning, so the
     dot is decorative and hidden. When there is no label, the tone name is
     the only thing distinguishing "healthy" from "failing", so it must be
     exposed via aria-label rather than left as an unlabelled span. */
  const dot = (
    <span
      className={pulse ? 'pulsing' : undefined}
      aria-hidden={label ? 'true' : undefined}
      role={label ? undefined : 'img'}
      aria-label={label ? undefined : `Status: ${tone}`}
      style={{ width: size, height: size, borderRadius: '50%', background: color, flexShrink: 0, display: 'inline-block' }}
    />
  )
  if (!label) return dot
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--s2)', fontSize: 'var(--t-xs)', color: 'var(--text-muted)' }}>
      {dot}
      {label}
    </span>
  )
}

/* ── Badge ────────────────────────────────────────────────────────────────
   Flat, squared, hairline. A decision is the resolved state, so decisions
   carry weight; everything unresolved stays quiet. */
const BADGE_STYLES = {
  accept:            { bg: 'var(--green-subtle)',  color: 'var(--green)',  border: 'var(--green-border)',  label: 'Accept' },
  reject:            { bg: 'var(--red-subtle)',    color: 'var(--red)',    border: 'var(--red-border)',    label: 'Reject' },
  refund_and_keep:   { bg: 'var(--blue-subtle)',   color: 'var(--blue)',   border: 'var(--blue-border)',   label: 'Refund & keep' },
  charge_return_fee: { bg: 'var(--amber-subtle)',  color: 'var(--amber)',  border: 'var(--amber-border)',  label: 'Charge fee' },
  escalate:          { bg: 'var(--purple-subtle)', color: 'var(--purple)', border: 'var(--purple-border)', label: 'Escalate' },
  manual_review:     { bg: 'var(--amber-subtle)',  color: 'var(--amber)',  border: 'var(--amber-border)',  label: 'Manual review' },
  low:               { bg: 'var(--green-subtle)',  color: 'var(--green)',  border: 'var(--green-border)',  label: 'Low' },
  medium:            { bg: 'var(--amber-subtle)',  color: 'var(--amber)',  border: 'var(--amber-border)',  label: 'Medium' },
  high:              { bg: 'var(--red-subtle)',    color: 'var(--red)',    border: 'var(--red-border)',    label: 'High' },
  active:            { bg: 'var(--green-subtle)',  color: 'var(--green)',  border: 'var(--green-border)',  label: 'Active' },
  inactive:          { bg: 'var(--surface-2)',     color: 'var(--text-muted)', border: 'var(--border)',    label: 'Inactive' },
  signal:            { bg: 'var(--brand-subtle)',  color: 'var(--brand-dark)', border: 'var(--brand-border)', label: 'Resolved' },
  free:              { bg: 'var(--surface-2)',     color: 'var(--text-secondary)', border: 'var(--border)', label: 'Free' },
  enterprise:        { bg: 'var(--brand-subtle)',  color: 'var(--brand-dark)', border: 'var(--brand-border)', label: 'Enterprise' },
  neutral:           { bg: 'var(--surface-2)',     color: 'var(--text-secondary)', border: 'var(--border)', label: '—' },
}

export function Badge({ variant = 'neutral', children, dot = false }) {
  const s = BADGE_STYLES[variant] || BADGE_STYLES.neutral
  return (
    <span
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 5,
        padding: '2px 8px', borderRadius: 'var(--r-sm)',
        fontSize: 'var(--t-micro)', fontWeight: 500, letterSpacing: '0.01em',
        background: s.bg, color: s.color, border: `1px solid ${s.border}`,
        whiteSpace: 'nowrap',
      }}
    >
      {dot && <StatusDot tone={s.color} size={5} />}
      {children ?? s.label}
    </span>
  )
}

/* ── Button ───────────────────────────────────────────────────────────── */
const BTN_VARIANTS = {
  primary:   { bg: 'var(--brand)',        color: '#fff',                  border: 'var(--brand)',        hover: 'var(--brand-dark)' },
  secondary: { bg: 'var(--surface)',      color: 'var(--text-primary)',   border: 'var(--border-2)',     hover: 'var(--surface-2)' },
  ghost:     { bg: 'transparent',         color: 'var(--text-secondary)', border: 'transparent',         hover: 'var(--surface-2)' },
  danger:    { bg: 'var(--red-subtle)',   color: 'var(--red)',            border: 'var(--red-border)',   hover: 'rgba(163,46,28,0.16)' },
  success:   { bg: 'var(--green-subtle)', color: 'var(--green)',          border: 'var(--green-border)', hover: 'rgba(74,124,70,0.17)' },
  inverse:   { bg: 'var(--graphite)',     color: 'var(--bone)',           border: 'var(--graphite)',     hover: '#24272D' },
}

export function Button({ variant = 'primary', size = 'md', loading, disabled, icon, children, style, ...props }) {
  const v = BTN_VARIANTS[variant] || BTN_VARIANTS.primary
  const pad = size === 'sm' ? '5px 11px' : size === 'lg' ? '12px 24px' : '8px 15px'
  const fs = size === 'sm' ? 'var(--t-xs)' : size === 'lg' ? 'var(--t-body)' : 'var(--t-sm)'
  const off = disabled || loading

  return (
    <button
      disabled={off}
      style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 7,
        // PHASE 48: establishes the positioning context for the visually
        // hidden loading announcement below. Without it that absolutely
        // positioned span anchors to the nearest positioned ancestor (often
        // the page), which can produce a stray 1px scroll artefact far from
        // the button it belongs to.
        position: 'relative',
        padding: pad, fontSize: fs, fontWeight: 500, letterSpacing: '-0.005em',
        borderRadius: 'var(--r)', border: `1px solid ${v.border}`,
        background: v.bg, color: v.color,
        cursor: off ? 'not-allowed' : 'pointer', opacity: disabled ? 0.45 : 1,
        transition: 'var(--tr-color)', userSelect: 'none', whiteSpace: 'nowrap',
        ...style,
      }}
      onMouseEnter={e => { if (!off) e.currentTarget.style.background = v.hover }}
      onMouseLeave={e => { e.currentTarget.style.background = v.bg }}
      {...props}
    >
      {loading
        ? <Loader2 size={14} aria-hidden="true" style={{ animation: 'spin 0.7s linear infinite' }} />
        : (icon ? <span aria-hidden="true" style={{ display: 'inline-flex' }}>{icon}</span> : null)}
      {children}
      {/* PHASE 48 — the loading state is conveyed visually by a spinner and
          by the button being disabled. Neither is announced, so a screen
          reader user pressing Save hears nothing and has no way to know the
          request is in flight. This announces it once, politely, and is
          visually hidden so it changes nothing on screen. */}
      {loading && (
        <span
          role="status"
          aria-live="polite"
          style={{
            position: 'absolute', width: 1, height: 1, padding: 0, margin: -1,
            overflow: 'hidden', clip: 'rect(0 0 0 0)', whiteSpace: 'nowrap', border: 0,
          }}
        >
          Working
        </span>
      )}
    </button>
  )
}

/* ── Field wrapper ────────────────────────────────────────────────────── */
function Field({ label, error, hint, children, controlId }) {
  // PHASE 10/48: the label used to be a bare <label> with no htmlFor, so it
  // was visually adjacent to the input but not programmatically associated
  // with it. A screen reader announced "edit text, blank" — the user could
  // see a form they could not use.
  //
  // The error text is wired via aria-describedby and role="alert" so a
  // validation failure is announced rather than only rendered. Someone using
  // a screen reader would otherwise submit, hear nothing, and have no idea
  // why the form did not go through.
  const errorId = error ? `${controlId}-error` : undefined
  const hintId = !error && hint ? `${controlId}-hint` : undefined

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
      {label && <label className="label" htmlFor={controlId}>{label}</label>}
      {typeof children === 'function'
        ? children({ id: controlId, 'aria-describedby': errorId || hintId, 'aria-invalid': !!error })
        : children}
      {error
        ? <span id={errorId} role="alert" style={{ fontSize: 'var(--t-micro)', color: 'var(--red)' }}>{error}</span>
        : hint && <span id={hintId} style={{ fontSize: 'var(--t-micro)', color: 'var(--text-faint)' }}>{hint}</span>}
    </div>
  )
}

const CONTROL_BASE = {
  width: '100%',
  background: 'var(--bone)',
  border: '1px solid var(--border-2)',
  borderRadius: 'var(--r)',
  padding: '9px 11px',
  color: 'var(--text-primary)',
  fontSize: 'var(--t-sm)',
  outline: 'none',
  transition: 'var(--tr-color)',
}

export function Input({ id, label, error, hint, icon: Icon, style, ...props }) {
  // useId gives a stable, collision-free id even when the same field appears
  // twice on a page (e.g. a filter panel and a modal both with "SKU").
  const generated = useId()
  const controlId = id || props.name || generated
  return (
    <Field label={label} error={error} hint={hint} controlId={controlId}>
      <div style={{ position: 'relative' }}>
        {Icon && (
          <Icon
            size={14}
            style={{
              position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)',
              color: 'var(--text-muted)', pointerEvents: 'none',
            }}
          />
        )}
        <input
          id={controlId}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${controlId}-error` : (hint ? `${controlId}-hint` : undefined)}
          style={{
            ...CONTROL_BASE,
            borderColor: error ? 'var(--red)' : 'var(--border-2)',
            paddingLeft: Icon ? 34 : 11,
            ...style,
          }}
          onFocus={e => { e.target.style.borderColor = 'var(--vermillion)' }}
          onBlur={e => { e.target.style.borderColor = error ? 'var(--red)' : 'var(--border-2)' }}
          {...props}
        />
      </div>
    </Field>
  )
}

export function Select({ id, label, error, hint, children, style, ...props }) {
  const generated = useId()
  const controlId = id || props.name || generated
  return (
    <Field label={label} error={error} hint={hint} controlId={controlId}>
      <select
        id={controlId}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${controlId}-error` : (hint ? `${controlId}-hint` : undefined)}
        style={{ ...CONTROL_BASE, cursor: 'pointer', ...style }}
        onFocus={e => { e.target.style.borderColor = 'var(--vermillion)' }}
        onBlur={e => { e.target.style.borderColor = 'var(--border-2)' }}
        {...props}
      >
        {children}
      </select>
    </Field>
  )
}

export function Textarea({ id, label, error, hint, style, ...props }) {
  const generated = useId()
  const controlId = id || props.name || generated
  return (
    <Field label={label} error={error} hint={hint} controlId={controlId}>
      <textarea
        id={controlId}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${controlId}-error` : (hint ? `${controlId}-hint` : undefined)}
        style={{ ...CONTROL_BASE, resize: 'vertical', lineHeight: 1.55, fontFamily: 'inherit', ...style }}
        onFocus={e => { e.target.style.borderColor = 'var(--vermillion)' }}
        onBlur={e => { e.target.style.borderColor = error ? 'var(--red)' : 'var(--border-2)' }}
        {...props}
      />
    </Field>
  )
}

export function Checkbox({ label, ...props }) {
  return (
    <label
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 'var(--s2)',
        fontSize: 'var(--t-sm)', color: 'var(--text-secondary)',
        cursor: 'pointer', userSelect: 'none',
      }}
    >
      <input type="checkbox" style={{ width: 15, height: 15, accentColor: 'var(--vermillion)', cursor: 'pointer' }} {...props} />
      {label}
    </label>
  )
}

/* ── Tabs — a rule with one segment resolved in Vermillion ───────────── */
export function Tabs({ tabs, active, onChange }) {
  /* PHASE 48 — these were plain buttons in a div. A screen reader announced
     them individually with no indication they formed a group, and no
     indication of which one was currently selected: the active state was
     conveyed purely by colour and a coloured bottom border, both invisible
     to assistive tech and to anyone who cannot distinguish the vermillion
     underline. */
  return (
    <div
      role="tablist"
      style={{ display: 'flex', gap: 0, borderBottom: '1px solid var(--border)', overflowX: 'auto' }}
    >
      {tabs.map(([key, label]) => {
        const on = active === key
        return (
          <button
            key={key}
            role="tab"
            aria-selected={on}
            onClick={() => onChange(key)}
            style={{
              padding: '9px 16px', fontSize: 'var(--t-sm)', fontWeight: 500,
              color: on ? 'var(--text-primary)' : 'var(--text-muted)',
              borderBottom: `2px solid ${on ? 'var(--vermillion)' : 'transparent'}`,
              marginBottom: -1, transition: 'var(--tr-color)', whiteSpace: 'nowrap',
            }}
          >
            {label}
          </button>
        )
      })}
    </div>
  )
}

/* ── DataTable ────────────────────────────────────────────────────────────
   Columns: [{ key, header, width, align, render(row), mono, wrap, maxWidth }]
   Rules between rows, no zebra striping, no vertical borders. */
export function DataTable({ columns, rows, rowKey = (r, i) => r.id ?? i, onRowClick, selectedKey, empty, dense = false }) {
  if (!rows || rows.length === 0) return empty || <EmptyState title="No data" />

  const cellPad = dense ? '7px 12px' : '10px 12px'

  return (
    <div className="scroll-x">
      <table>
        <thead>
          <tr>
            {columns.map(c => (
              <th
                key={c.key}
                style={{
                  textAlign: c.align || 'left',
                  fontSize: 'var(--t-micro)', fontWeight: 500,
                  color: 'var(--text-muted)', letterSpacing: '0.06em',
                  textTransform: 'uppercase',
                  padding: '9px 12px', whiteSpace: 'nowrap',
                  borderBottom: '1px solid var(--border-2)',
                  width: c.width, background: 'var(--surface)',
                  position: 'sticky', top: 0, zIndex: 1,
                }}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const key = rowKey(row, i)
            const on = selectedKey != null && selectedKey === key
            return (
              <tr
                key={key}
                /* PHASE 48 — keyboard access.
                   These rows were mouse-only: onClick with no tabIndex and no
                   key handler, so a keyboard user could not open a return
                   from the returns list at all. That is not a screen-reader
                   nicety, it is a complete functional lockout for anyone who
                   cannot use a mouse (including users with motor
                   impairments and anyone on a broken trackpad).

                   role="button" rather than leaving it a bare row: the row
                   IS the control here, and announcing it as a table row
                   gives no indication it can be activated. */
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                tabIndex={onRowClick ? 0 : undefined}
                role={onRowClick ? 'button' : undefined}
                aria-selected={onRowClick ? on : undefined}
                onKeyDown={onRowClick ? (e) => {
                  /* Enter AND Space. Space is what people actually press on
                     something announced as a button, and the default Space
                     behaviour is to scroll the page -- so it must be
                     prevented or activating a row also jumps the viewport. */
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    onRowClick(row)
                  }
                } : undefined}
                style={{
                  cursor: onRowClick ? 'pointer' : 'default',
                  background: on ? 'var(--brand-subtle)' : 'transparent',
                  borderBottom: '1px solid var(--border)',
                  transition: 'background var(--d-instant) var(--ease-linear)',
                  boxShadow: on ? 'inset 2px 0 0 var(--vermillion)' : 'none',
                }}
                onMouseEnter={e => { if (!on) e.currentTarget.style.background = 'var(--surface-2)' }}
                onMouseLeave={e => { if (!on) e.currentTarget.style.background = 'transparent' }}
              >
                {columns.map(c => (
                  <td
                    key={c.key}
                    data-numeric={c.mono ? '' : undefined}
                    style={{
                      padding: cellPad, fontSize: 'var(--t-xs)',
                      color: 'var(--text-secondary)', textAlign: c.align || 'left',
                      whiteSpace: c.wrap ? 'normal' : 'nowrap',
                      maxWidth: c.maxWidth,
                      overflow: c.maxWidth ? 'hidden' : undefined,
                      textOverflow: c.maxWidth ? 'ellipsis' : undefined,
                    }}
                  >
                    {c.render ? c.render(row) : (row[c.key] ?? '—')}
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

/* ── Alert — left rule in the status colour, no icon, no pill ────────── */
const ALERT_STYLES = {
  error:   { color: 'var(--red)',   bg: 'var(--red-subtle)' },
  success: { color: 'var(--green)', bg: 'var(--green-subtle)' },
  info:    { color: 'var(--blue)',  bg: 'var(--blue-subtle)' },
  warning: { color: 'var(--amber)', bg: 'var(--amber-subtle)' },
}

export function Alert({ type = 'info', children, style }) {
  const s = ALERT_STYLES[type] || ALERT_STYLES.info
  return (
    <div
      role={type === 'error' ? 'alert' : 'status'}
      style={{
        padding: '11px 14px', background: s.bg, color: s.color,
        borderLeft: `2px solid ${s.color}`, borderRadius: '0 var(--r) var(--r) 0',
        fontSize: 'var(--t-sm)', lineHeight: 1.55, ...style,
      }}
    >
      {children}
    </div>
  )
}

/* ── Spinner / loading ────────────────────────────────────────────────── */
export function Spinner({ size = 18, color = 'var(--vermillion)' }) {
  /* PHASE 48 — aria-hidden, deliberately.
     The spinner itself is pure decoration: a spinning border conveys nothing
     to a screen reader. The ANNOUNCEMENT belongs on the container that also
     holds the text (see LoadingCenter), so a user hears "Loading" once
     rather than hearing an unlabelled graphic. Marking it hidden here
     prevents it being announced as a stray empty element. */
  return (
    <div
      aria-hidden="true"
      style={{
        width: size, height: size,
        border: '2px solid var(--surface-3)', borderTopColor: color,
        borderRadius: '50%', animation: 'spin 0.7s linear infinite', flexShrink: 0,
      }}
    />
  )
}

export function LoadingCenter({ text = 'Loading' }) {
  /* PHASE 48 — role="status" + aria-live="polite".
     Without this, a screen reader user got NO announcement that anything was
     happening: the page simply went silent while data loaded, which is
     indistinguishable from the application having frozen.

     "polite" rather than "assertive" on purpose -- a loading notice should
     wait for a natural pause rather than interrupting whatever the user is
     currently having read to them. */
  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        gap: 'var(--s3)', padding: '80px 0', color: 'var(--text-muted)',
      }}
    >
      <Spinner />
      <span className="eyebrow">{text}</span>
    </div>
  )
}

/* ── EmptyState — an empty screen is an invitation to act ────────────── */
export function EmptyState({ icon: Icon, title, description, action }) {
  return (
    <div
      style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        justifyContent: 'center', padding: 'var(--s9) var(--s6)', textAlign: 'center',
      }}
    >
      {Icon && <Icon size={26} style={{ color: 'var(--border-2)', marginBottom: 'var(--s4)' }} />}
      <div style={{ fontSize: 'var(--t-sm)', fontWeight: 500, color: 'var(--text-secondary)' }}>{title}</div>
      {description && (
        <div style={{ fontSize: 'var(--t-xs)', color: 'var(--text-muted)', maxWidth: 300, marginTop: 6 }}>
          {description}
        </div>
      )}
      {action && <div style={{ marginTop: 'var(--s5)' }}>{action}</div>}
    </div>
  )
}

/* ── Tooltip ──────────────────────────────────────────────────────────── */
export function Tooltip({ label, children }) {
  const [open, setOpen] = React.useState(false)
  return (
    <span
      style={{ position: 'relative', display: 'inline-flex' }}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      {children}
      <span
        role="tooltip"
        style={{
          position: 'absolute', bottom: '100%', left: '50%',
          transform: `translateX(-50%) translateY(${open ? '-6px' : '-2px'})`,
          background: 'var(--graphite)', color: 'var(--bone)',
          padding: '4px 9px', borderRadius: 'var(--r-sm)',
          fontSize: 'var(--t-micro)', whiteSpace: 'nowrap',
          pointerEvents: 'none', opacity: open ? 1 : 0,
          transition: 'opacity var(--d-fast) var(--ease-linear), transform var(--d-fast) var(--ease-converge)',
          zIndex: 100,
        }}
      >
        {label}
      </span>
    </span>
  )
}

/* PageHeader lives with the shell, but is re-exported here so pages keep a
   single import surface. */
export { default as PageHeader } from '../layout/PageHeader.jsx'
