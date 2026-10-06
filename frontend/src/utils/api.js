import axios from 'axios'

const BASE = '/api/v1'

// ── Access token: in-memory only ──────────────────────────────────────────────
// Never persisted to localStorage/sessionStorage - an XSS payload that can
// read localStorage can no longer walk off with a usable token. It lives
// only as long as this JS runtime does, which is why AuthContext does a
// silent refresh (via the httpOnly refresh cookie) on every app load.
let accessToken = null
export const setAccessToken = (token) => { accessToken = token }
export const getAccessToken = () => accessToken

// ── Non-sensitive display info + legacy API key (fine in localStorage) ───────
export const auth = {
  setUser: (user) => {
    if (user) localStorage.setItem('rl_user', JSON.stringify(user))
    else localStorage.removeItem('rl_user')
  },
  getUser: () => { try { return JSON.parse(localStorage.getItem('rl_user') || 'null') } catch { return null } },
  clear: () => {
    localStorage.removeItem('rl_user')
    localStorage.removeItem('rl_api_key')
  },
  isLoggedIn: () => !!getAccessToken(),
  // Backward-compat shim for any older call sites: sets the access token in
  // memory only. The refresh token argument (if any) is ignored - the
  // backend now sets/rotates it as an httpOnly cookie automatically, and
  // the frontend never reads or stores it.
  setTokens: (access) => setAccessToken(access),
}

// Legacy API key support (backward compat with v2)
export const setApiKey = (k) => localStorage.setItem('rl_api_key', k)
export const getApiKey = () => localStorage.getItem('rl_api_key') || ''

// ── Axios instance ─────────────────────────────────────────────────────────────
// withCredentials so the httpOnly rl_refresh_token cookie is sent/received
// on every request (login, refresh, logout all depend on this).
const client = axios.create({ baseURL: '/', withCredentials: true })

// Attach JWT or API key
client.interceptors.request.use((config) => {
  const token = getAccessToken()
  const apiKey = getApiKey()
  if (token) {
    config.headers['Authorization'] = `Bearer ${token}`
  } else if (apiKey) {
    config.headers['X-API-Key'] = apiKey
  }
  return config
})

const AUTH_ENDPOINTS = [`${BASE}/auth/login`, `${BASE}/auth/register`, `${BASE}/auth/refresh`]
const isAuthEndpoint = (url) => typeof url === 'string' && AUTH_ENDPOINTS.some((e) => url.includes(e))

// Single-flight refresh: if several requests 401 at once, only one
// POST /auth/refresh goes out and every retry waits on the same promise.
let refreshPromise = null
function refreshAccessToken() {
  if (!refreshPromise) {
    refreshPromise = axios
      .post(`${BASE}/auth/refresh`, null, { withCredentials: true })
      .then((res) => {
        setAccessToken(res.data.access_token)
        return res.data.access_token
      })
      .finally(() => { refreshPromise = null })
  }
  return refreshPromise
}

// Auto refresh on 401 (silent refresh via the httpOnly cookie)
client.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config
    if (err.response?.status === 401 && original && !original._retry && !isAuthEndpoint(original.url)) {
      original._retry = true
      try {
        const newToken = await refreshAccessToken()
        original.headers['Authorization'] = `Bearer ${newToken}`
        return client(original)
      } catch {
        setAccessToken(null)
        auth.clear()
        window.location.href = '/login'
      }
    }
    return Promise.reject(err)
  }
)

// ── API methods ───────────────────────────────────────────────────────────────
export const api = {
  // Auth
  login: (data) => client.post(`${BASE}/auth/login`, data).then(r => r.data),
  register: (data) => client.post(`${BASE}/auth/register`, data).then(r => r.data),
  refresh: () => client.post(`${BASE}/auth/refresh`).then(r => r.data),
  me: () => client.get(`${BASE}/auth/me`).then(r => r.data),
  logout: () => client.post(`${BASE}/auth/logout`).then(r => r.data),
  changePassword: (data) => client.post(`${BASE}/auth/change-password`, data).then(r => r.data),

  // Returns (JWT)
  createReturn: (data) => client.post(`${BASE}/returns`, data).then(r => r.data),
  getReturns: (params) => client.get(`${BASE}/returns`, { params }).then(r => r.data),
  getReturn: (id) => client.get(`${BASE}/returns/${id}`).then(r => r.data),
  updateReturnStatus: (id, data) => client.patch(`${BASE}/returns/${id}/status`, data).then(r => r.data),
  getDashboard: () => client.get(`${BASE}/returns/dashboard`).then(r => r.data),
  getAnalytics: () => client.get(`${BASE}/returns/analytics`).then(r => r.data),

  // Org
  getOrg: () => client.get(`${BASE}/org/`).then(r => r.data),
  updateOrgSettings: (data) => client.patch(`${BASE}/org/settings`, data).then(r => r.data),
  getApiKeys: () => client.get(`${BASE}/org/api-keys`).then(r => r.data),
  createApiKey: (data) => client.post(`${BASE}/org/api-keys`, data).then(r => r.data),
  getMembers: () => client.get(`${BASE}/org/members`).then(r => r.data),
  getAuditLogs: () => client.get(`${BASE}/org/audit-logs`).then(r => r.data),

  // Customers

  // Warehouses
  // NOTE: getCustomers / getCustomer / getNotifications used to be defined
  // here as well as further down. A JS object literal silently keeps the
  // LAST definition, so these were dead - and getCustomers' replacement
  // returns a paginated { items, total, page } object instead of an array,
  // which broke the Customers page with no error anywhere. Removed.
  getWarehouses: () => client.get(`${BASE}/warehouses`).then(r => r.data),

  // AI
  getAiModels: () => client.get(`${BASE}/ai/models`).then(r => r.data),
  getAiInsights: () => client.get(`${BASE}/ai/insights`).then(r => r.data),

  // Health & Setup
  health: () => client.get('/health').then(r => r.data),
  getDemoCredentials: () => client.get(`${BASE}/org/demo-key`).then(r => r.data),

  // External API (backward compat — uses X-API-Key)
  extCreateReturn: (data) => client.post(`${BASE}/ext/returns`, data).then(r => r.data),
  extGetDashboard: () => client.get(`${BASE}/ext/returns/dashboard`).then(r => r.data),
  extGetReturns: () => client.get(`${BASE}/ext/returns`).then(r => r.data),

  // ── Phase 5.1 — User profile ──────────────────────────────────────────────
  getProfile: () => client.get(`${BASE}/users/profile`).then(r => r.data),
  updateProfile: (data) => client.patch(`${BASE}/users/profile`, data).then(r => r.data),
  forgotPassword: (data) => client.post(`${BASE}/users/forgot-password`, data).then(r => r.data),
  resetPassword: (data) => client.post(`${BASE}/users/reset-password`, data).then(r => r.data),
  deleteAccount: () => client.delete(`${BASE}/users/account`).then(r => r.data),
  getSessions: () => client.get(`${BASE}/users/sessions`).then(r => r.data),
  revokeAllSessions: () => client.delete(`${BASE}/users/sessions`).then(r => r.data),
  getAccountActivity: () => client.get(`${BASE}/users/activity`).then(r => r.data),

  // ── Phase 5.2 — Org management ────────────────────────────────────────────
  inviteMember: (data) => client.post(`${BASE}/org/members/invite`, data).then(r => r.data),
  updateMemberRole: (id, data) => client.patch(`${BASE}/org/members/${id}/role`, data).then(r => r.data),
  removeMember: (id) => client.delete(`${BASE}/org/members/${id}`).then(r => r.data),
  updateBranding: (data) => client.patch(`${BASE}/org/branding`, data).then(r => r.data),
  getFeatureFlags: () => client.get(`${BASE}/org/feature-flags`).then(r => r.data),
  setFeatureFlag: (name, data) => client.put(`${BASE}/org/feature-flags/${name}`, data).then(r => r.data),

  // ── Phase 5.3 — Return management extensions ──────────────────────────────
  addReturnNote: (id, data) => client.post(`${BASE}/returns/${id}/notes`, data).then(r => r.data),
  getReturnNotes: (id) => client.get(`${BASE}/returns/${id}/notes`).then(r => r.data),
  getReturnTimeline: (id) => client.get(`${BASE}/returns/${id}/timeline`).then(r => r.data),
  uploadDocument: (id, formData) => client.post(`${BASE}/returns/${id}/documents`, formData, { headers: { 'Content-Type': 'multipart/form-data' } }).then(r => r.data),
  getDocuments: (id) => client.get(`${BASE}/returns/${id}/documents`).then(r => r.data),
  deleteDocument: (rid, did) => client.delete(`${BASE}/returns/${rid}/documents/${did}`).then(r => r.data),
  deleteReturn: (id) => client.delete(`${BASE}/returns/${id}`).then(r => r.data),
  bulkImportReturns: (data) => client.post(`${BASE}/returns/bulk`, data).then(r => r.data),
  confirmOutcome: (id, data) => client.patch(`${BASE}/returns/${id}/outcome`, data).then(r => r.data),

  // ── Phase 5.4 — Customer management ──────────────────────────────────────
  getCustomers: (params) => client.get(`${BASE}/customers/`, { params }).then(r => r.data),
  createCustomer: (data) => client.post(`${BASE}/customers/`, data).then(r => r.data),
  getCustomer: (id) => client.get(`${BASE}/customers/${id}`).then(r => r.data),
  updateCustomer: (id, data) => client.patch(`${BASE}/customers/${id}`, data).then(r => r.data),
  deleteCustomer: (id) => client.delete(`${BASE}/customers/${id}`).then(r => r.data),
  blacklistCustomer: (id, reason) => client.post(`${BASE}/customers/${id}/blacklist`, null, { params: { reason } }).then(r => r.data),
  getCustomerAnalytics: (id) => client.get(`${BASE}/customers/${id}/analytics`).then(r => r.data),
  exportCustomersCSV: () => client.get(`${BASE}/customers/export/csv`, { responseType: 'blob' }).then(r => r.data),

  // ── Phase 5.7 — Notifications ─────────────────────────────────────────────
  getNotifications: (params) => client.get(`${BASE}/notifications/`, { params }).then(r => r.data),
  getUnreadCount: () => client.get(`${BASE}/notifications/unread-count`).then(r => r.data),
  markNotificationsRead: (ids) => client.post(`${BASE}/notifications/mark-read`, { notification_ids: ids }).then(r => r.data),
  markAllNotificationsRead: () => client.post(`${BASE}/notifications/mark-all-read`).then(r => r.data),

  // ── Phase 5.9 — Reports ───────────────────────────────────────────────────
  getSummaryReport: (params) => client.get(`${BASE}/reports/summary`, { params }).then(r => r.data),
  getFraudReport: (params) => client.get(`${BASE}/reports/fraud`, { params }).then(r => r.data),
  getCarbonReport: (params) => client.get(`${BASE}/reports/carbon`, { params }).then(r => r.data),
  getCustomerReport: (params) => client.get(`${BASE}/reports/customers`, { params }).then(r => r.data),
  downloadReport: (type, params) => client.get(`${BASE}/reports/${type}`, { params: { ...params, format: 'csv' }, responseType: 'blob' }).then(r => r.data),

  // ── Phase 5.10 — Admin ────────────────────────────────────────────────────
  getAdminHealth: () => client.get(`${BASE}/admin/health`).then(r => r.data),
  getAllOrgs: () => client.get(`${BASE}/admin/orgs`).then(r => r.data),
  getAllUsers: () => client.get(`${BASE}/admin/users`).then(r => r.data),
  updateUserStatus: (id, status) => client.patch(`${BASE}/admin/users/${id}/status`, null, { params: { status } }).then(r => r.data),
  getSystemSettings: () => client.get(`${BASE}/admin/system-settings`).then(r => r.data),
  setSystemSetting: (key, data) => client.put(`${BASE}/admin/system-settings/${key}`, data).then(r => r.data),
  getGlobalAuditLogs: (limit) => client.get(`${BASE}/admin/audit-logs`, { params: { limit } }).then(r => r.data),
  getMlStats: () => client.get(`${BASE}/admin/ml-stats`).then(r => r.data),
  getDbStats: () => client.get(`${BASE}/admin/db-statistics`).then(r => r.data),

  // ── Phase 5.11 — AI UX ────────────────────────────────────────────────────
  getPredictionHistory: (params) => client.get(`${BASE}/ai/predictions/history`, { params }).then(r => r.data),
  explainPrediction: (id) => client.get(`${BASE}/ai/predictions/${id}/explain`).then(r => r.data),
  manualOverride: (id, data) => client.post(`${BASE}/ai/predictions/${id}/override`, data).then(r => r.data),
  submitFeedback: (data) => client.post(`${BASE}/ai/feedback`, data).then(r => r.data),
  getAiPerformance: () => client.get(`${BASE}/ai/performance`).then(r => r.data),

  // ── Phase 5.12 — Workflows ────────────────────────────────────────────────
  getWorkflowRules: () => client.get(`${BASE}/workflows/rules`).then(r => r.data),
  createWorkflowRule: (data) => client.post(`${BASE}/workflows/rules`, data).then(r => r.data),
  updateWorkflowRule: (id, data) => client.patch(`${BASE}/workflows/rules/${id}`, data).then(r => r.data),
  deleteWorkflowRule: (id) => client.delete(`${BASE}/workflows/rules/${id}`).then(r => r.data),
  getSlaList: (params) => client.get(`${BASE}/workflows/sla`, { params }).then(r => r.data),
  checkSlaBreaches: () => client.get(`${BASE}/workflows/sla/check-breaches`).then(r => r.data),
}
