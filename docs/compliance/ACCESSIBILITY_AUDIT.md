# Accessibility Audit — ReturnIQ Enterprise

**Audit Date:** 1 August 2025
**Standard Reference:** WCAG 2.1 Level AA
**Audit Type:** Manual code review (automated tool testing requires a running browser)

---

## Summary

| Area | Status | Notes |
|---|---|---|
| Keyboard navigation | 🟡 Partial | Native buttons/inputs work; custom modal traps not implemented |
| Screen reader support | 🟡 Partial | Semantic HTML used; ARIA labels missing on icon-only buttons |
| Colour contrast | 🟡 Partial | CSS variables used; exact ratios need browser measurement |
| Focus indicators | 🟡 Partial | Browser default focus rings present; not styled in CSS |
| Form labels | 🟡 Partial | Labels present in custom components but not always linked via `htmlFor` |
| Error messages | 🟡 Partial | Errors shown visually; not always linked to inputs via `aria-describedby` |
| Responsive layout | ✅ Good | Grid layouts use `auto-fill` with `minmax`; sidebar collapses on mobile |
| Motion/animation | ✅ Good | Only CSS transitions (no forced animations); respects OS preference if added |

**Overall WCAG 2.1 AA status: 🟡 Partial — Not yet compliant. Remediation required before claiming accessibility.**

---

## Detailed Findings

### 1. Keyboard Navigation

**What works:**
- All `<button>`, `<input>`, `<select>`, `<textarea>` elements are natively focusable
- NavLink elements in the Sidebar are keyboard-accessible
- Tables with action buttons are keyboard-navigable

**What needs fixing:**
- Modal dialogs (e.g., workflow rule creation, invite member) do not trap focus —
  a screen keyboard user can tab out of the modal to behind-modal content
- No `Escape` key handler on modals to close them
- Custom `<button onClick>` divs found in some chart components — these need
  `role="button"` and `tabIndex={0}` with keyboard event handlers

**Remediation:**
```jsx
// Modal focus trap — add to every modal component
useEffect(() => {
  const handleKeyDown = (e) => { if (e.key === 'Escape') onClose() }
  document.addEventListener('keydown', handleKeyDown)
  return () => document.removeEventListener('keydown', handleKeyDown)
}, [onClose])
```

---

### 2. Screen Reader Support

**What works:**
- Semantic HTML elements used throughout (`<main>`, `<nav>`, `<table>`, `<thead>`,
  `<th>`, `<button>`)
- `<table>` headers use `<th>` elements
- Page titles conveyed via heading hierarchy

**What needs fixing:**
- Icon-only buttons (e.g., delete, refresh, toggle) have no accessible label:
  ```jsx
  // Current (inaccessible):
  <button onClick={onDelete}><Trash2 size={14} /></button>
  
  // Fixed:
  <button onClick={onDelete} aria-label="Delete rule"><Trash2 size={14} aria-hidden="true" /></button>
  ```
- Badge components output `<span>` with text content only — acceptable, but could
  add `role="status"` for live data badges
- Loading spinner has no `aria-live` region or `aria-label`
- `<RiskBar>` is a visual-only bar chart — needs an `aria-label` with the numeric value

---

### 3. Colour Contrast

The UI uses CSS custom properties (variables). The exact contrast ratios depend on
the values defined in `index.css`. The following needs verification with a browser
tool (e.g., Chrome DevTools accessibility panel):

| Element | CSS Variables | Action Required |
|---|---|---|
| Body text on background | `--text-primary` on `--bg` | Measure — target ≥4.5:1 |
| Secondary text | `--text-secondary` on `--surface` | Measure — likely borderline |
| Muted text | `--text-muted` on any background | High risk of failing 4.5:1 — may need to darken |
| Brand colour on white | `--brand-light` on `--surface` | Measure — purple tones can fail |
| Red/green status badges | `--red`, `--green` on badge backgrounds | Measure both foreground and background |

**Action required:** Run all pages through a contrast checker. `--text-muted` is most
likely to fail WCAG AA contrast requirements.

---

### 4. Form Labels

**What works:** Most form sections have visible label text above inputs.

**What needs fixing:**
- Labels are rendered as `<div>` or `<label>` but are not always connected to their
  input via `htmlFor` / `id` pairing:
  ```jsx
  // Current:
  <label style={{...}}>Email</label>
  <input type="email" value={email} ... />
  
  // Fixed:
  <label htmlFor="email-input" style={{...}}>Email</label>
  <input id="email-input" type="email" value={email} ... />
  ```
- Date filter inputs in the Reports page have labels but no `id` linking

---

### 5. Error Messages

**What works:** API errors are displayed in `<Alert>` components with colour coding.

**What needs fixing:**
- Error messages are not programmatically associated with the form field that caused them:
  ```jsx
  // Add to input when error exists:
  <input aria-describedby="email-error" ... />
  <div id="email-error" role="alert">{error}</div>
  ```
- `<Alert>` component should use `role="alert"` for dynamic error messages so screen
  readers announce them immediately without the user needing to navigate to them.

---

### 6. Responsive Layout

The layout uses CSS Grid with `auto-fill` / `minmax` — this is good for responsiveness.
The sidebar has a mobile-open state. No issues found in code review.

**Needs runtime testing** on actual mobile viewport (375px iPhone SE width).

---

## Remediation Priority

| Priority | Item | Effort |
|---|---|---|
| 🔴 | Add `aria-label` to all icon-only buttons | Low — 30–60 min |
| 🔴 | Add `role="alert"` to `<Alert>` component | Low — 5 min |
| 🔴 | Add `htmlFor` / `id` to all label/input pairs | Medium — 2–3 hours |
| 🟠 | Add modal focus trap + Escape key handler | Medium — 2 hours |
| 🟠 | Add `aria-live` region to loading spinner | Low — 15 min |
| 🟠 | Measure and fix colour contrast for muted text | Medium — depends on findings |
| 🟡 | Add `aria-label` with value to `<RiskBar>` | Low — 15 min |
| 🟡 | Test on mobile viewport and screen readers (VoiceOver/NVDA) | Medium — 4 hours |
