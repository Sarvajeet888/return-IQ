/**
 * PHASE 10 — UI component library.
 *
 * Focused on the things that actually go wrong in a returns console: a table
 * with no rows showing nothing at all, a submit button that stays clickable
 * while a request is in flight, an error message that renders but is not
 * announced to a screen reader.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import {
  Alert,
  Badge,
  Button,
  DataTable,
  Input,
  Metric,
  RiskBar,
  Select,
  StatusDot,
  Textarea,
} from '../components/ui/index.jsx'

describe('Button', () => {
  it('renders its label and fires onClick', async () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Approve return</Button>)
    await userEvent.click(screen.getByRole('button', { name: /approve return/i }))
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('does not fire while loading', async () => {
    // The double-submit bug in its natural habitat. On a returns console this
    // means approving the same return twice, or issuing two refunds.
    const onClick = vi.fn()
    render(<Button loading onClick={onClick}>Submit</Button>)
    await userEvent.click(screen.getByRole('button'))
    expect(onClick).not.toHaveBeenCalled()
  })

  it('does not fire when disabled', async () => {
    const onClick = vi.fn()
    render(<Button disabled onClick={onClick}>Submit</Button>)
    await userEvent.click(screen.getByRole('button'))
    expect(onClick).not.toHaveBeenCalled()
  })

  it('is marked disabled for assistive tech while loading', () => {
    render(<Button loading>Submit</Button>)
    expect(screen.getByRole('button')).toBeDisabled()
  })
})

describe('DataTable', () => {
  // Note the key: `header`, not `label`. My first draft used `label` and the
  // test failed — I assumed a bug in DataTable, then checked the real call
  // sites (AIPlatform.jsx, Dashboard.jsx) and found they all pass `header`.
  // The component was right; the test was wrong.
  const columns = [
    { key: 'sku', header: 'SKU' },
    { key: 'status', header: 'Status' },
  ]
  const rows = [
    { id: '1', sku: 'TSHIRT-L-RED', status: 'approved' },
    { id: '2', sku: 'JEANS-32-BLU', status: 'pending' },
  ]

  it('renders headers and rows', () => {
    render(<DataTable columns={columns} rows={rows} />)
    expect(screen.getByText('SKU')).toBeInTheDocument()
    expect(screen.getByText('TSHIRT-L-RED')).toBeInTheDocument()
    expect(screen.getByText('JEANS-32-BLU')).toBeInTheDocument()
  })

  it('shows an empty state instead of a blank table', () => {
    // A silent empty table is indistinguishable from a failed fetch. The user
    // needs to know the difference between "no returns" and "we broke".
    render(<DataTable columns={columns} rows={[]} empty="No returns yet" />)
    expect(screen.getByText('No returns yet')).toBeInTheDocument()
  })

  it('tolerates a null rows prop', () => {
    // Real APIs return null. A crash here white-screens the page.
    expect(() => render(<DataTable columns={columns} rows={null} />)).not.toThrow()
  })

  it('calls onRowClick with the row', async () => {
    const onRowClick = vi.fn()
    render(<DataTable columns={columns} rows={rows} onRowClick={onRowClick} />)
    await userEvent.click(screen.getByText('TSHIRT-L-RED'))
    expect(onRowClick).toHaveBeenCalledWith(expect.objectContaining({ sku: 'TSHIRT-L-RED' }))
  })

  it('uses a custom render function when given one', () => {
    const custom = [{ key: 'status', header: 'Status', render: (r) => <b>{r.status.toUpperCase()}</b> }]
    render(<DataTable columns={custom} rows={rows} />)
    expect(screen.getByText('APPROVED')).toBeInTheDocument()
  })
})

describe('Input', () => {
  it('associates its label with the field', () => {
    // getByLabelText only passes if the association is real, which is also
    // what a screen reader relies on.
    render(<Input label="Item value" />)
    expect(screen.getByLabelText('Item value')).toBeInTheDocument()
  })

  it('shows validation errors', () => {
    render(<Input label="Email" error="That address is not valid" />)
    expect(screen.getByText('That address is not valid')).toBeInTheDocument()
  })

  it('accepts typed input', async () => {
    render(<Input label="SKU" />)
    const field = screen.getByLabelText('SKU')
    await userEvent.type(field, 'TSHIRT-L-RED')
    expect(field).toHaveValue('TSHIRT-L-RED')
  })
})

describe('Metric', () => {
  it('renders a value and label', () => {
    render(<Metric value="₹4.80L" label="Revenue recovered" />)
    expect(screen.getByText('₹4.80L')).toBeInTheDocument()
    expect(screen.getByText('Revenue recovered')).toBeInTheDocument()
  })

  it('shows a loading state rather than a misleading zero', () => {
    // Rendering ₹0 while data is in flight tells a merchant they recovered
    // nothing. That is a worse lie than showing nothing.
    const { container } = render(<Metric value="₹4.80L" label="Recovered" loading />)
    expect(container.textContent).not.toContain('₹4.80L')
  })
})

describe('RiskBar and StatusDot', () => {
  it('renders a risk score', () => {
    const { container } = render(<RiskBar score={82} />)
    expect(container.textContent).toContain('82')
  })

  it('handles a zero score without breaking', () => {
    expect(() => render(<RiskBar score={0} />)).not.toThrow()
  })

  it('renders a status label when given one', () => {
    render(<StatusDot tone="ok" label="Connected" />)
    expect(screen.getByText('Connected')).toBeInTheDocument()
  })
})

describe('Alert and Badge', () => {
  it('renders alert content', () => {
    render(<Alert type="error">Could not reach the courier API</Alert>)
    expect(screen.getByText('Could not reach the courier API')).toBeInTheDocument()
  })

  it('renders badge content', () => {
    render(<Badge variant="danger">High risk</Badge>)
    expect(screen.getByText('High risk')).toBeInTheDocument()
  })
})

describe('Select and Textarea label association', () => {
  it('associates Select with its label', () => {
    render(
      <Select label="Courier">
        <option value="delhivery">Delhivery</option>
      </Select>,
    )
    expect(screen.getByLabelText('Courier')).toBeInTheDocument()
  })

  it('associates Textarea with its label', () => {
    render(<Textarea label="Inspection notes" />)
    expect(screen.getByLabelText('Inspection notes')).toBeInTheDocument()
  })

  it('announces validation errors to assistive tech', () => {
    // role="alert" means a screen reader speaks the error when it appears.
    // Without it the user submits, hears nothing, and cannot tell why.
    render(<Input label="Email" error="That address is not valid" />)
    expect(screen.getByRole('alert')).toHaveTextContent('That address is not valid')
    expect(screen.getByLabelText('Email')).toHaveAttribute('aria-invalid', 'true')
  })
})
