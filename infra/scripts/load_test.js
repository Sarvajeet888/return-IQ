// ReturnIQ Enterprise — Load Test (Phase 8.11)
//
// Install k6: https://k6.io/docs/get-started/installation/
//
// Run:
//   k6 run --env BASE_URL=https://your-domain.com infra/scripts/load_test.js
//
// Smoke test (1 user, 1 min):
//   k6 run --vus 1 --duration 1m --env BASE_URL=http://localhost load_test.js
//
// Find the breaking point:
//   k6 run --env SCENARIO=stress --env BASE_URL=http://localhost load_test.js

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost';
const SCENARIO = __ENV.SCENARIO || 'load';

// Custom metrics
const errorRate = new Rate('errors');
const predictionLatency = new Trend('prediction_latency_ms');

// ── Scenarios ─────────────────────────────────────────────────────────────────

const scenarios = {
  // Normal expected load
  load: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: '1m', target: 20 },   // ramp up to 20 users
      { duration: '3m', target: 20 },   // stay at 20
      { duration: '1m', target: 50 },   // ramp to 50
      { duration: '3m', target: 50 },   // stay at 50
      { duration: '1m', target: 0 },    // ramp down
    ],
  },

  // Find the breaking point
  stress: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: '2m', target: 50 },
      { duration: '2m', target: 100 },
      { duration: '2m', target: 200 },
      { duration: '2m', target: 400 },
      { duration: '2m', target: 0 },
    ],
  },

  // Sudden traffic spike (e.g. flash sale return surge)
  spike: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: '30s', target: 10 },
      { duration: '10s', target: 300 },  // sudden spike
      { duration: '1m',  target: 300 },
      { duration: '30s', target: 10 },
      { duration: '30s', target: 0 },
    ],
  },
};

export const options = {
  scenarios: { [SCENARIO]: scenarios[SCENARIO] },

  thresholds: {
    // 95% of requests must complete under 2 seconds
    http_req_duration: ['p(95)<2000'],
    // Error rate must stay below 1%
    errors: ['rate<0.01'],
    // ML predictions specifically should stay under 1s at p95
    prediction_latency_ms: ['p(95)<1000'],
  },
};

// ── Setup: log in once and share the token ───────────────────────────────────

export function setup() {
  const loginRes = http.post(
    `${BASE_URL}/api/v1/auth/login`,
    JSON.stringify({
      email: __ENV.TEST_EMAIL || 'loadtest@returniq.in',
      password: __ENV.TEST_PASSWORD || 'LoadTest123',
    }),
    { headers: { 'Content-Type': 'application/json' } }
  );

  if (loginRes.status !== 200) {
    throw new Error(
      `Setup failed: could not log in (status ${loginRes.status}). ` +
      `Create a test account first, or pass TEST_EMAIL / TEST_PASSWORD.`
    );
  }

  return { token: loginRes.json('access_token') };
}

// ── Main test ─────────────────────────────────────────────────────────────────

const CATEGORIES = ['Electronics', 'Apparel', 'Footwear', 'Home', 'Beauty'];
const COURIERS = ['BlueDart', 'Delhivery', 'Ekart', 'DTDC', 'XpressBees', 'Shadowfax'];
const REASONS = ['defective', 'wrong_item', 'size_fit', 'changed_mind', 'damaged_in_transit'];

function randomFrom(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

export default function (data) {
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${data.token}`,
  };

  // ── Group 1: Read-heavy dashboard traffic (most common in real use) ────────
  group('dashboard_reads', () => {
    const dashRes = http.get(`${BASE_URL}/api/v1/returns/dashboard`, { headers });
    check(dashRes, { 'dashboard 200': (r) => r.status === 200 }) || errorRate.add(1);

    const listRes = http.get(`${BASE_URL}/api/v1/returns?page=1&page_size=20`, { headers });
    check(listRes, { 'returns list 200': (r) => r.status === 200 }) || errorRate.add(1);

    const notifRes = http.get(`${BASE_URL}/api/v1/notifications/unread-count`, { headers });
    check(notifRes, { 'notifications 200': (r) => r.status === 200 }) || errorRate.add(1);
  });

  sleep(1);

  // ── Group 2: The core ML prediction path (the expensive one) ──────────────
  group('return_prediction', () => {
    const payload = JSON.stringify({
      platform_order_id: `LOAD-${__VU}-${__ITER}-${Date.now()}`,
      customer_identifier: `loadtest_customer_${__VU}@test.com`,
      sku: `SKU-LOAD-${Math.floor(Math.random() * 1000)}`,
      item_category: randomFrom(CATEGORIES),
      item_value: Math.floor(Math.random() * 50000) + 500,
      origin_pincode: '400001',
      destination_pincode: '560001',
      weight_grams: Math.floor(Math.random() * 5000) + 100,
      volumetric_weight_grams: Math.floor(Math.random() * 6000) + 100,
      return_reason_code: randomFrom(REASONS),
      courier: randomFrom(COURIERS),
      payment_mode: Math.random() > 0.5 ? 'Prepaid' : 'COD',
      fragile: Math.random() > 0.7,
      festive: false,
      condition: 'good',
    });

    const start = Date.now();
    const res = http.post(`${BASE_URL}/api/v1/returns`, payload, { headers });
    const latency = Date.now() - start;

    predictionLatency.add(latency);

    const ok = check(res, {
      'prediction 201': (r) => r.status === 201 || r.status === 200,
      'has routing_decision': (r) => {
        try {
          return r.json('prediction.routing_decision') !== undefined;
        } catch { return false; }
      },
      'latency under 2s': () => latency < 2000,
    });

    if (!ok) errorRate.add(1);
  });

  sleep(2);

  // ── Group 3: Analytics (heavy aggregation queries) ────────────────────────
  group('analytics', () => {
    const res = http.get(`${BASE_URL}/api/v1/returns/analytics`, { headers });
    check(res, { 'analytics 200': (r) => r.status === 200 }) || errorRate.add(1);
  });

  sleep(1);
}

// ── Teardown ──────────────────────────────────────────────────────────────────

export function teardown(data) {
  console.log('Load test complete.');
  console.log('Note: this test created real return records in the database.');
  console.log('Clean them up with: DELETE FROM return_requests WHERE platform_order_id LIKE \'LOAD-%\';');
}
