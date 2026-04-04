/**
 * k6 Load Test — URL Shortener
 * Modern scenarios API for realistic traffic patterns
 * 
 * Usage:
 *   k6 run k6/load_test.js
 *   k6 run -e BASE_URL=http://localhost k6/load_test.js
 *   k6 run --out json=results.json k6/load_test.js
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:80";

// Custom metrics
const errorRate = new Rate("errors");
const requestLatency = new Trend("request_latency", true);
const shortenLatency = new Trend("shorten_latency", true);
const redirectLatency = new Trend("redirect_latency", true);

/**
 * Scenarios Configuration
 * Three independent scenarios for different traffic patterns
 */
export const options = {
  scenarios: {
    // Bronze: Health check baseline (constant 5 VUs)
    health_checks: {
      executor: "constant-vus",
      vus: 5,
      duration: "2m",
      exec: "healthCheck",
    },

    // Bronze/Silver: URL shortening with ramping load
    url_shortening: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "30s", target: 10 }, // Ramp: 0->10 VUs
        { duration: "30s", target: 50 }, // Bronze: 50 concurrent
        { duration: "1m", target: 200 }, // Silver: 200 concurrent
        { duration: "1m", target: 500 }, // Gold: 500 concurrent
        { duration: "30s", target: 0 }, // Cool down
      ],
      exec: "shortenAndRedirect",
    },

    // Gold: Spike test — sudden traffic burst
    spike_test: {
      executor: "ramping-vus",
      startVUs: 0,
      startTime: "3m30s", // Start after ramp phase
      stages: [
        { duration: "5s", target: 300 }, // Sudden spike: 0->300
        { duration: "30s", target: 300 }, // Hold spike
        { duration: "5s", target: 0 }, // Drop
      ],
      exec: "shortenAndRedirect",
    },
  },

  // Test passes if thresholds are met
  thresholds: {
    http_req_duration: ["p(95)<3000"], // Silver: p95 < 3s
    http_req_failed: ["rate<0.05"], // Gold: <5% error rate
    errors: ["rate<0.05"],
  },
};

/**
 * Health Check Function
 * Simple baseline to verify service is up
 */
export function healthCheck() {
  const res = http.get(`${BASE_URL}/health`);
  const ok = check(res, {
    "health 200": (r) => r.status === 200,
    "health json": (r) => r.body.includes("status"),
  });
  if (!ok) errorRate.add(1);
  sleep(1);
}

/**
 * Main Load Test: Shorten URL → Redirect
 * Simulates realistic user: shortens a URL, then follows the redirect
 */
export function shortenAndRedirect() {
  // Step 1: Create a short URL with unique path to avoid collisions
  const payload = JSON.stringify({
    url: `https://example.com/path/${Date.now()}/${Math.random()}`,
  });

  const shortenRes = http.post(`${BASE_URL}/shorten`, payload, {
    headers: { "Content-Type": "application/json" },
  });

  shortenLatency.add(shortenRes.timings.duration);

  const shortenOk = check(shortenRes, {
    "shorten 201": (r) => r.status === 201,
    "shorten json": (r) => r.body.includes("short_code"),
  });

  if (!shortenOk) {
    errorRate.add(1);
    sleep(0.5);
    return;
  }

  // Step 2: Parse response and redirect through short code
  const body = JSON.parse(shortenRes.body);
  const shortCode = body.short_code;

  const redirectRes = http.get(`${BASE_URL}/${shortCode}`, {
    redirects: 0, // Don't follow redirects — we want to see the 302
  });

  redirectLatency.add(redirectRes.timings.duration);

  const redirectOk = check(redirectRes, {
    "redirect 302": (r) => r.status === 302,
  });

  if (!redirectOk) {
    errorRate.add(1);
  }

  // Think time: realistic user delays between actions
  sleep(0.3 + Math.random() * 0.4);
}

/**
 * Setup Function (runs once at start)
 * Could seed test data here if needed
 */
export function setup() {
  // Optional: pre-populate some test data
  // Not used here to keep it simple
}

/**
 * Teardown Function (runs once at end)
 */
export function teardown(data) {
  // Optional: cleanup after test
  // Not used here
}
