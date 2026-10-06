# Cookie Policy — ReturnIQ Enterprise

**Effective Date:** 1 August 2025
**Version:** 1.0

---

## 1. What Are Cookies?

Cookies are small text files placed on your device by a website. ReturnIQ uses a minimal
cookie approach — we set only what is technically necessary to operate the platform
securely.

---

## 2. Cookies We Set

### 2.1 Essential Cookie — `rl_refresh_token`

| Attribute | Value |
|---|---|
| **Name** | `rl_refresh_token` |
| **Purpose** | Maintains your login session without storing your access token in localStorage (which is vulnerable to XSS attacks) |
| **Type** | Session / Authentication |
| **Duration** | 7 days (reset on each silent refresh) |
| **HttpOnly** | Yes — cannot be read by JavaScript |
| **Secure** | Yes — transmitted over HTTPS only |
| **SameSite** | Lax — sent on same-site navigation, not on cross-site requests |
| **Can be disabled?** | No. Disabling this cookie means you cannot log in. |

This is the **only** cookie ReturnIQ currently sets.

---

## 3. Cookies We Do NOT Set

| Type | Status |
|---|---|
| Analytics cookies (Google Analytics, Mixpanel, etc.) | ❌ Not used |
| Advertising / tracking cookies | ❌ Not used |
| Third-party social media pixels | ❌ Not used |
| Fingerprinting or supercookies | ❌ Not used |

---

## 4. Local Storage & Session Storage

ReturnIQ's frontend stores **no data** in `localStorage` or `sessionStorage`.

The access token (JWT) is stored **in browser memory only** (a JavaScript module-level
variable). It is automatically cleared when the browser tab is closed. This is a
deliberate security choice — memory-only storage is not accessible to third-party scripts
or browser extensions.

---

## 5. Your Choices

Because we only use a single essential cookie required for login, there is no "accept"
or "decline" decision to make for non-essential cookies — there are none.

You can clear the `rl_refresh_token` cookie at any time in your browser settings. Doing
so will sign you out. You can also sign out explicitly using the logout function in the
app, which both clears the cookie and revokes the token server-side.

---

## 6. Future Cookie Use

If ReturnIQ adds analytics or non-essential cookies in the future, we will:
- Update this policy with at least 14 days notice
- Add a consent banner to the application
- Not set non-essential cookies until explicit consent is given

---

## 7. Contact

Questions about this policy: privacy@returniq.in
