/**
 * Money formatting — the single source of truth for the frontend.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * Before Phase 3 there were three separate `inr` helpers in three page files,
 * each with different rounding:
 *
 *   ReturnsList.jsx   maximumFractionDigits: 0   -> "₹1,500"
 *   NewReturn.jsx     maximumFractionDigits: 2   -> "₹1,500.50"
 *   Pages.jsx         toLocaleString()           -> "₹1,500.5"
 *
 * The same amount rendered three ways on three screens. Worse, they all took
 * a JS number, and JS numbers are IEEE-754 doubles — the exact type we removed
 * from the backend. Formatting exact server data through a float type puts the
 * bug back at the last step.
 *
 * The backend now sends every monetary value as:
 *
 *   { minor_units: 150050, currency: "INR",
 *     amount: "1500.50", formatted: "₹1,500.50" }
 *
 * Prefer `.formatted` when you just need to display it. Use the helpers here
 * when you need control over the presentation, or need to do arithmetic.
 */

// ISO-4217 exponents, mirroring backend/app/core/money.py MINOR_UNITS.
// If you add a currency here, add it there too — and vice versa.
const MINOR_UNITS = {
  INR: 2, USD: 2, EUR: 2, GBP: 2, AED: 2,
  JPY: 0, KWD: 3, BHD: 3, OMR: 3,
}

// Locale per currency, so Indian amounts get lakh/crore digit grouping
// (₹12,34,567.00) rather than the western grouping (₹1,234,567.00).
const LOCALES = {
  INR: 'en-IN', USD: 'en-US', EUR: 'de-DE', GBP: 'en-GB',
  AED: 'ar-AE', JPY: 'ja-JP', KWD: 'ar-KW', BHD: 'ar-BH', OMR: 'ar-OM',
}

const isMoneyObject = v =>
  v !== null && typeof v === 'object' && typeof v.minor_units === 'number'

/**
 * Format a money value for display.
 *
 * Accepts the server's money object. Also tolerates a bare number for
 * not-yet-migrated call sites, but treats that as major units and warns in
 * development — a bare number is a call site that still needs updating.
 *
 * @param {object|number|null} value
 * @param {{ compact?: boolean, decimals?: boolean, symbol?: boolean }} [opts]
 *   compact  — abbreviate large amounts (₹12.3L, ₹1.2Cr) for dashboard tiles
 *   decimals — show minor units. Defaults true; pass false for dense tables
 *   symbol   — include the currency symbol. Default true
 */
export function formatMoney(value, opts = {}) {
  const { compact = false, decimals = true, symbol = true } = opts

  if (value === null || value === undefined) return '—'

  let minorUnits
  let currency = 'INR'

  if (isMoneyObject(value)) {
    minorUnits = value.minor_units
    currency = value.currency || 'INR'
    // Fast path: the server already rendered it exactly how we'd render it.
    if (compact === false && decimals === true && symbol === true && value.formatted) {
      return value.formatted
    }
  } else if (typeof value === 'number') {
    if (import.meta.env?.DEV) {
      console.warn(
        '[formatMoney] received a bare number, not a money object. This call ' +
        'site still needs migrating to the Phase 3 money wire format.',
        value,
      )
    }
    minorUnits = Math.round(value * 100)
  } else {
    return '—'
  }

  const exponent = MINOR_UNITS[currency] ?? 2
  const locale = LOCALES[currency] || 'en-IN'
  const major = minorUnits / 10 ** exponent

  if (compact) return formatCompact(major, currency, locale, symbol)

  const fractionDigits = decimals ? exponent : 0
  return new Intl.NumberFormat(locale, {
    style: symbol ? 'currency' : 'decimal',
    currency,
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(major)
}

/**
 * Abbreviate large amounts for dashboard tiles, using the Indian numbering
 * system for INR (thousand → lakh → crore) because "₹4.8L" is what an Indian
 * merchant reads fluently, not "₹480K".
 */
function formatCompact(major, currency, locale, symbol) {
  const sign = major < 0 ? '-' : ''
  const abs = Math.abs(major)
  const prefix = symbol ? symbolFor(currency) : ''

  if (currency === 'INR') {
    if (abs >= 1e7) return `${sign}${prefix}${(abs / 1e7).toFixed(2)}Cr`
    if (abs >= 1e5) return `${sign}${prefix}${(abs / 1e5).toFixed(2)}L`
    if (abs >= 1e3) return `${sign}${prefix}${(abs / 1e3).toFixed(1)}K`
  } else {
    if (abs >= 1e9) return `${sign}${prefix}${(abs / 1e9).toFixed(2)}B`
    if (abs >= 1e6) return `${sign}${prefix}${(abs / 1e6).toFixed(2)}M`
    if (abs >= 1e3) return `${sign}${prefix}${(abs / 1e3).toFixed(1)}K`
  }
  return `${sign}${prefix}${abs.toFixed(0)}`
}

export function symbolFor(currency = 'INR') {
  return ({
    INR: '₹', USD: '$', EUR: '€', GBP: '£',
    AED: 'AED ', JPY: '¥', KWD: 'KD ', BHD: 'BD ', OMR: 'OMR ',
  })[currency] || `${currency} `
}

/**
 * Convert user input (a string from a text field) into the MoneyIn shape the
 * API expects. Deliberately keeps the amount as a *string* — routing it
 * through parseFloat first would reintroduce the precision loss at the very
 * boundary we are trying to protect.
 *
 * @returns {{ amount: string, currency: string }|null} null if unparseable
 */
export function toMoneyIn(input, currency = 'INR') {
  if (input === null || input === undefined || input === '') return null
  const cleaned = String(input).replace(/[,\s₹$€£]/g, '')
  if (!/^-?\d+(\.\d+)?$/.test(cleaned)) return null
  return { amount: cleaned, currency }
}

/** Exact comparison, for sorting tables without a float round-trip. */
export function compareMoney(a, b) {
  const av = isMoneyObject(a) ? a.minor_units : 0
  const bv = isMoneyObject(b) ? b.minor_units : 0
  return av - bv
}

/** Sum an array of money objects exactly. Returns a money-shaped object. */
export function sumMoney(values, currency = 'INR') {
  const items = (values || []).filter(isMoneyObject)
  const cur = items[0]?.currency || currency
  const mismatch = items.find(v => v.currency !== cur)
  if (mismatch) {
    throw new Error(
      `sumMoney: refusing to add ${mismatch.currency} to ${cur}. ` +
      'Group by currency before summing.',
    )
  }
  const total = items.reduce((acc, v) => acc + v.minor_units, 0)
  return {
    minor_units: total,
    currency: cur,
    amount: (total / 10 ** (MINOR_UNITS[cur] ?? 2)).toFixed(MINOR_UNITS[cur] ?? 2),
    formatted: formatMoney({ minor_units: total, currency: cur }),
  }
}

/**
 * Format a numeric score/measurement for display, degrading to an em dash
 * instead of "NaN" when the value is absent.
 *
 * PHASE 11: seven call sites across four pages did `Number(x).toFixed(1)`
 * directly. When the field was missing — an older prediction row, a partial
 * API response, a model that did not emit that score — this rendered the
 * literal string "NaN" in the operations table. A warehouse manager reading
 * "NaN" in a Fraud column has no way to tell whether that means zero risk,
 * high risk, or a broken page, so they either ignore the column or escalate
 * a non-issue. An em dash says "not measured", which is the truth.
 *
 * Deliberately NOT defaulting to 0. Showing 0.0 for a missing fraud score
 * would assert the item is safe, which is a stronger and more dangerous claim
 * than admitting the value is unknown.
 */
export function formatScore(value, { decimals = 1, suffix = '' } = {}) {
  if (value === null || value === undefined || value === '') return '—'
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  return `${n.toFixed(decimals)}${suffix}`
}

/** Percentage from a 0–1 fraction, safe against missing values. */
export function formatPercent(fraction, { decimals = 1 } = {}) {
  if (fraction === null || fraction === undefined || fraction === '') return '—'
  const n = Number(fraction)
  if (!Number.isFinite(n)) return '—'
  return `${(n * 100).toFixed(decimals)}%`
}
