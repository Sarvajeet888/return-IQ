/**
 * PHASE 10 — money.js
 *
 * These guard the display end of the Phase 3 migration. Getting exact integer
 * paise into the database is only half the job: if the frontend routes those
 * values back through a JS number, the precision is lost at the last step and
 * the user sees a wrong figure regardless of what the database holds.
 */
import { describe, expect, it, vi } from 'vitest'
import {
  compareMoney,
  formatMoney,
  sumMoney,
  symbolFor,
  toMoneyIn,
} from '../utils/money'

const inr = (minor) => ({
  minor_units: minor,
  currency: 'INR',
  amount: (minor / 100).toFixed(2),
  formatted: null, // force the formatter to compute rather than pass through
})

describe('formatMoney', () => {
  it('uses the server-rendered string when there is one', () => {
    // The fast path. The server already knows the currency exponent and
    // grouping rules, so re-deriving them client-side is wasted work and a
    // second place for the two to disagree.
    const value = { minor_units: 150050, currency: 'INR', amount: '1500.50', formatted: '₹1,500.50' }
    expect(formatMoney(value)).toBe('₹1,500.50')
  })

  it('formats INR with Indian digit grouping', () => {
    // 12,34,567 — not 1,234,567. An Indian merchant reads lakh grouping
    // fluently and stumbles over the western form.
    expect(formatMoney(inr(123456700))).toBe('₹12,34,567.00')
  })

  it('renders JPY without decimals', () => {
    // Assuming 2 decimal places everywhere would show ¥15.00 for ¥1,500.
    const jpy = { minor_units: 1500, currency: 'JPY', amount: '1500', formatted: null }
    // Note the character: Intl's ja-JP output uses the FULLWIDTH yen sign
    // U+FFE5 (￥), not U+00A5 (¥). They look nearly identical in most fonts
    // and are not equal. Worth pinning, because a future refactor that
    // hand-rolls the symbol would produce the halfwidth one and silently
    // change what Japanese users see.
    expect(formatMoney(jpy)).toBe('\uFFE51,500')
  })

  it('handles negative amounts', () => {
    expect(formatMoney(inr(-30000))).toBe('-₹300.00')
  })

  it('shows an em dash for null rather than ₹0.00', () => {
    // "No data" and "zero rupees" are different facts. Rendering an unknown
    // discrepancy as ₹0.00 would tell a merchant their books balance.
    expect(formatMoney(null)).toBe('—')
    expect(formatMoney(undefined)).toBe('—')
  })

  it('formats zero as an actual amount', () => {
    expect(formatMoney(inr(0))).toBe('₹0.00')
  })

  it('can drop decimals for dense tables', () => {
    expect(formatMoney(inr(150050), { decimals: false })).toBe('₹1,501')
  })

  it('abbreviates using lakh and crore for INR', () => {
    expect(formatMoney(inr(48000000), { compact: true })).toBe('₹4.80L')
    // 1,500,000,000 paise = ₹1,50,00,000 = ₹1.5 crore. (My first draft of
    // this test asserted ₹15.00Cr — off by 10x. The code was right.)
    expect(formatMoney(inr(1500000000), { compact: true })).toBe('₹1.50Cr')
  })

  it('abbreviates using M and B for non-INR currencies', () => {
    const usd = (m) => ({ minor_units: m, currency: 'USD', amount: '', formatted: null })
    expect(formatMoney(usd(500000000), { compact: true })).toBe('$5.00M')
  })

  it('warns when handed a bare number instead of a money object', () => {
    // A bare number is a call site that has not been migrated. It still
    // renders — breaking a page over a formatting detail would be worse —
    // but it must be findable.
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const result = formatMoney(1500.5)
    expect(result).toContain('1,500.50')
    if (import.meta.env.DEV) expect(warn).toHaveBeenCalled()
  })
})

describe('toMoneyIn', () => {
  it('keeps the amount as a string', () => {
    // The whole point. parseFloat here would reintroduce the precision loss
    // at the exact boundary Phase 3 exists to protect.
    const result = toMoneyIn('1500.50')
    expect(result).toEqual({ amount: '1500.50', currency: 'INR' })
    expect(typeof result.amount).toBe('string')
  })

  it('strips symbols and separators a user might paste in', () => {
    expect(toMoneyIn('₹1,500.50')).toEqual({ amount: '1500.50', currency: 'INR' })
  })

  it('rejects unparseable input rather than guessing', () => {
    expect(toMoneyIn('abc')).toBeNull()
    expect(toMoneyIn('12.34.56')).toBeNull()
    expect(toMoneyIn('')).toBeNull()
    expect(toMoneyIn(null)).toBeNull()
  })

  it('accepts negative amounts', () => {
    expect(toMoneyIn('-300')).toEqual({ amount: '-300', currency: 'INR' })
  })
})

describe('sumMoney', () => {
  it('sums exactly in minor units', () => {
    // The float version of this — 19.99 × 3 — gives 59.970000000000006.
    const total = sumMoney([inr(1999), inr(1999), inr(1999)])
    expect(total.minor_units).toBe(5997)
    expect(total.amount).toBe('59.97')
  })

  it('refuses to add different currencies', () => {
    const usd = { minor_units: 100, currency: 'USD', amount: '1.00', formatted: null }
    expect(() => sumMoney([inr(100), usd])).toThrow(/refusing to add/i)
  })

  it('returns zero for an empty list', () => {
    expect(sumMoney([]).minor_units).toBe(0)
  })

  it('ignores non-money entries rather than coercing them', () => {
    expect(sumMoney([inr(100), null, undefined, 'nonsense']).minor_units).toBe(100)
  })
})

describe('compareMoney', () => {
  it('sorts on exact integers, with no float round-trip', () => {
    const values = [inr(300), inr(100), inr(200)]
    const sorted = [...values].sort(compareMoney)
    expect(sorted.map((v) => v.minor_units)).toEqual([100, 200, 300])
  })
})

describe('symbolFor', () => {
  it('knows the supported currencies', () => {
    expect(symbolFor('INR')).toBe('₹')
    expect(symbolFor('USD')).toBe('$')
    expect(symbolFor('JPY')).toBe('¥')
  })

  it('falls back to the code itself for anything unknown', () => {
    // Better to show "XYZ 100" than a wrong symbol.
    expect(symbolFor('XYZ')).toBe('XYZ ')
  })
})
