/**
 * PHASE 11 — page states.
 *
 * Phase 11 requires every screen to handle loading, empty, error and success.
 * Component tests do not catch failures at this level: the Phase 3 money
 * migration broke the dashboard's headline metrics into "₹NaN" and 53
 * component tests stayed green, because none of them rendered a page.
 *
 * These mock the API rather than the network so the assertions are about what
 * the user sees, not about axios.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '../utils/api.js'
import Dashboard from '../pages/dashboard/Dashboard.jsx'

// The auth context is incidental to what these tests check, so it is stubbed
// rather than wired up — otherwise every page test becomes a login test too.
vi.mock('../store/AuthContext.jsx', () => ({
  useAuth: () => ({ user: { full_name: 'Om Pilaji', role: 'org_admin' } }),
  AuthProvider: ({ children }) => children,
}))

const money = (minorUnits) => ({
  minor_units: minorUnits,
  currency: 'INR',
  amount: (minorUnits / 100).toFixed(2),
  formatted: null,
})

const dashboardPayload = {
  total_returns: 40,
  decisions: { accept: 25, reject: 8, refund_and_keep: 7 },
  avg_predicted_cost: money(45000),      // ₹450.00
  revenue_saved: money(1284500),         // ₹12,845.00
  avg_risk_score: 42.5,
  avg_fraud_score: 18.2,
  total_carbon_kg: 96.4,
  category_breakdown: [{ name: 'electronics', value: 12 }],
  courier_breakdown: [{ name: 'Delhivery', value: 20 }],
  monthly_trend: [{ month: '2026-07', count: 18 }],
  recent_returns: [
    {
      id: 'r1',
      platform_order_id: 'ORD-10001',
      sku: 'TSHIRT-L-RED',
      item_category: 'apparel',
      item_value: money(149900),          // ₹1,499.00
      prediction: { predicted_cost: money(32000), routing_decision: 'accept', risk_score: 22 },
    },
  ],
  kpis: {},
}

const renderDashboard = () =>
  render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>,
  )

describe('Dashboard states', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('shows a loading state before data arrives', () => {
    // Never resolving: the component must render something while in flight,
    // not a blank screen or a misleading zero.
    vi.spyOn(api, 'getDashboard').mockReturnValue(new Promise(() => {}))
    renderDashboard()
    expect(screen.getByText(/reading signal/i)).toBeInTheDocument()
  })

  it('renders money without producing NaN', async () => {
    // THE regression test for this phase.
    //
    // Dashboard.jsx carried its own `inr` helper doing Number(value), which
    // Phase 3 missed. Once the backend began sending
    // { minor_units, currency, ... }, Number(object) evaluated to NaN and the
    // headline metrics rendered "₹NaN". This asserts the absence of that
    // string anywhere on the page, so any future formatter drift fails here.
    vi.spyOn(api, 'getDashboard').mockResolvedValue(dashboardPayload)
    const { container } = renderDashboard()

    await waitFor(() => expect(screen.getByText(/value recovered/i)).toBeInTheDocument())

    // Plain containment, deliberately. I briefly weakened this to a regex
    // when it failed, which made it pass while a real NaN was still rendering
    // in the Fraud column — the weakened version proved nothing. Dumping the
    // actual DOM text found it. Keep this strict.
    const rendered = container.textContent
    expect(rendered).not.toContain('NaN')
    expect(rendered).not.toContain('undefined')
    expect(rendered).not.toContain('[object Object]')
  })

  it('formats the recovered value correctly', async () => {
    vi.spyOn(api, 'getDashboard').mockResolvedValue(dashboardPayload)
    const { container } = renderDashboard()
    await waitFor(() => expect(screen.getByText(/value recovered/i)).toBeInTheDocument())
    // ₹12,845 — Indian grouping, decimals dropped for the metric tile.
    expect(container.textContent).toContain('12,845')
  })

  it('shows an error state with a retry, not a blank page', async () => {
    const err = { response: { data: { detail: 'Could not reach the server' } } }
    const spy = vi.spyOn(api, 'getDashboard').mockRejectedValue(err)
    renderDashboard()

    await waitFor(() =>
      expect(screen.getByText('Could not reach the server')).toBeInTheDocument(),
    )

    // A dead end is not an error state. The user needs a way forward.
    const retry = screen.getByRole('button', { name: /try again/i })
    spy.mockResolvedValue(dashboardPayload)
    await userEvent.click(retry)
    await waitFor(() => expect(screen.getByText(/value recovered/i)).toBeInTheDocument())
  })

  it('handles an empty organization without crashing', async () => {
    // A brand-new merchant has no returns. This is the first screen they see,
    // so it must not look like a failure.
    vi.spyOn(api, 'getDashboard').mockResolvedValue({
      total_returns: 0,
      decisions: {},
      avg_predicted_cost: money(0),
      revenue_saved: money(0),
      avg_risk_score: 0,
      avg_fraud_score: 0,
      total_carbon_kg: 0,
      category_breakdown: [],
      courier_breakdown: [],
      monthly_trend: [],
      recent_returns: [],
      kpis: {},
    })

    const { container } = renderDashboard()
    await waitFor(() => expect(screen.getByText(/value recovered/i)).toBeInTheDocument())
    expect(container.textContent).not.toContain('NaN')
  })

  it('survives missing fields in the API response', async () => {
    // Defensive: a partial response from an older backend, or a field renamed
    // during a migration, must degrade rather than white-screen the page.
    vi.spyOn(api, 'getDashboard').mockResolvedValue({ total_returns: 3 })
    expect(() => renderDashboard()).not.toThrow()
    await waitFor(() => expect(screen.queryByText(/reading signal/i)).not.toBeInTheDocument())
  })
})
