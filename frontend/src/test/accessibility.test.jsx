/**
 * PHASE 48 — accessibility.
 *
 * Every test here corresponds to a defect found by reading the actual
 * component source, not to a generic "is it accessible" checklist. The
 * headline one is the DataTable keyboard lockout: clickable rows were
 * mouse-only, so a keyboard user could not open a return at all.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import {
  DataTable, Tabs, LoadingCenter, Spinner, StatusDot, Button,
} from '../components/ui/index.jsx'

const COLUMNS = [
  { key: 'id', header: 'ID' },
  { key: 'sku', header: 'SKU' },
]
const ROWS = [
  { id: 'r1', sku: 'KURTA-M' },
  { id: 'r2', sku: 'SHIRT-L' },
]

// ─────────────────── the keyboard lockout (the serious one) ─────────────────

describe('DataTable keyboard access', () => {
  it('makes clickable rows reachable by keyboard', () => {
    // THE defect. <tr onClick> with no tabIndex and no key handler is a
    // complete functional lockout for anyone who cannot use a mouse — not a
    // screen-reader nicety.
    const onRowClick = vi.fn()
    render(<DataTable columns={COLUMNS} rows={ROWS} onRowClick={onRowClick} />)

    const rows = screen.getAllByRole('button')
    expect(rows.length).toBe(2)
    rows.forEach(row => expect(row).toHaveAttribute('tabIndex', '0'))
  })

  it('activates a row with Enter', () => {
    const onRowClick = vi.fn()
    render(<DataTable columns={COLUMNS} rows={ROWS} onRowClick={onRowClick} />)

    fireEvent.keyDown(screen.getAllByRole('button')[0], { key: 'Enter' })
    expect(onRowClick).toHaveBeenCalledWith(ROWS[0])
  })

  it('activates a row with Space', () => {
    // Space is what people actually press on something announced as a
    // button. Supporting only Enter would half-fix the problem.
    const onRowClick = vi.fn()
    render(<DataTable columns={COLUMNS} rows={ROWS} onRowClick={onRowClick} />)

    fireEvent.keyDown(screen.getAllByRole('button')[1], { key: ' ' })
    expect(onRowClick).toHaveBeenCalledWith(ROWS[1])
  })

  it('does not activate on an unrelated key', () => {
    const onRowClick = vi.fn()
    render(<DataTable columns={COLUMNS} rows={ROWS} onRowClick={onRowClick} />)

    fireEvent.keyDown(screen.getAllByRole('button')[0], { key: 'a' })
    expect(onRowClick).not.toHaveBeenCalled()
  })

  it('leaves non-clickable rows out of the tab order', () => {
    // A table nobody can click should not trap a keyboard user tabbing
    // through dozens of inert rows to reach the next real control.
    render(<DataTable columns={COLUMNS} rows={ROWS} />)
    expect(screen.queryAllByRole('button')).toHaveLength(0)
  })

  it('exposes which row is selected', () => {
    render(
      <DataTable columns={COLUMNS} rows={ROWS} onRowClick={() => {}} selectedKey="r2" />
    )
    const rows = screen.getAllByRole('button')
    expect(rows[0]).toHaveAttribute('aria-selected', 'false')
    expect(rows[1]).toHaveAttribute('aria-selected', 'true')
  })
})

// ──────────────────────────── tab semantics ────────────────────────────────

describe('Tabs semantics', () => {
  const TABS = [['a', 'Overview'], ['b', 'Details']]

  it('announces itself as a tab group', () => {
    render(<Tabs tabs={TABS} active="a" onChange={() => {}} />)
    expect(screen.getByRole('tablist')).toBeTruthy()
    expect(screen.getAllByRole('tab')).toHaveLength(2)
  })

  it('exposes the selected tab beyond colour alone', () => {
    // The active state was conveyed purely by text colour and a vermillion
    // underline — invisible to assistive tech, and to anyone who cannot
    // distinguish that underline.
    render(<Tabs tabs={TABS} active="b" onChange={() => {}} />)
    const tabs = screen.getAllByRole('tab')
    expect(tabs[0]).toHaveAttribute('aria-selected', 'false')
    expect(tabs[1]).toHaveAttribute('aria-selected', 'true')
  })
})

// ─────────────────────────── loading announcements ─────────────────────────

describe('Loading states are announced', () => {
  it('announces that content is loading', () => {
    // Without this the page simply went silent while data loaded, which is
    // indistinguishable from the application having frozen.
    render(<LoadingCenter text="Loading returns" />)
    const status = screen.getByRole('status')
    expect(status).toHaveAttribute('aria-live', 'polite')
    expect(status.textContent).toContain('Loading returns')
  })

  it('hides the decorative spinner from assistive tech', () => {
    // A spinning border conveys nothing to a screen reader; the text next to
    // it carries the meaning. Announcing both would be redundant noise.
    const { container } = render(<Spinner />)
    expect(container.firstChild).toHaveAttribute('aria-hidden', 'true')
  })

  it('announces a button that is working', () => {
    render(<Button loading>Save</Button>)
    expect(screen.getByRole('status').textContent).toContain('Working')
  })

  it('does not announce anything when the button is idle', () => {
    // A live region that is always present would be noise. It must appear
    // only when there is something to say.
    render(<Button>Save</Button>)
    expect(screen.queryByRole('status')).toBeNull()
  })
})

// ────────────────────── colour is not the only signal ──────────────────────

describe('StatusDot does not rely on colour alone', () => {
  it('labels a bare dot for assistive tech', () => {
    // WCAG 1.4.1: a bare coloured dot is meaningless to a screen reader and
    // to a user with colour vision deficiency.
    render(<StatusDot tone="critical" />)
    expect(screen.getByRole('img')).toHaveAttribute('aria-label', 'Status: critical')
  })

  it('hides the dot when a visible text label already carries the meaning', () => {
    // Otherwise the same status is announced twice.
    const { container } = render(<StatusDot tone="healthy" label="Healthy" />)
    expect(screen.queryByRole('img')).toBeNull()
    expect(container.textContent).toContain('Healthy')
    expect(container.querySelector('[aria-hidden="true"]')).toBeTruthy()
  })
})

// ─────────────────────────── icons are decorative ──────────────────────────

describe('Button icons', () => {
  it('hides the icon so the label is not announced twice', () => {
    const { container } = render(
      <Button icon={<svg data-testid="icon" />}>Refresh</Button>
    )
    const hidden = container.querySelector('[aria-hidden="true"]')
    expect(hidden).toBeTruthy()
    expect(hidden.querySelector('[data-testid="icon"]')).toBeTruthy()
  })

  it('keeps the visible text as the accessible name', () => {
    render(<Button icon={<svg />}>Refresh</Button>)
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeTruthy()
  })
})
