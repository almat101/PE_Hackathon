import http from "k6/http";
import { check, sleep, group } from "k6";
import { Counter, Rate, Trend } from "k6/metrics";

// ─────────────────────────────────────────────────────────────
// Custom metrics for detailed tracking
// ─────────────────────────────────────────────────────────────
const errorRate = new Rate("errors");
const healthLatency = new Trend("health_latency", true);
const shortenLatency = new Trend("shorten_latency", true);
const listUrlsLatency = new Trend("list_urls_latency", true);
const redirectLatency = new Trend("redirect_latency", true);
const requestCount = new Counter("total_requests");

// ─────────────────────────────────────────────────────────────
// Configuration
// ─────────────────────────────────────────────────────────────
const BASE_URL = __ENV.BASE_URL || "http://localhost";

export const options = {
  // ── Stages: ramp up to 50 VUs, hold, ramp down ──
  stages: [
    { duration: "10s", target: 25 },   // Ramp up to 25 users
    { duration: "10s", target: 50 },   // Ramp up to 50 users
    { duration: "30s", target: 50 },   // Hold at 50 concurrent users for 30s
    { duration: "10s", target: 0 },    // Ramp down to 0
  ],

  // ── Thresholds (pass/fail criteria) ──
  thresholds: {
    http_req_duration: [
      "p(95)<2000",   // 95% of requests must complete within 2s
      "p(99)<5000",   // 99% within 5s
    ],
    errors: ["rate<0.10"],            // Error rate must be below 10%
    http_req_failed: ["rate<0.10"],   // Built-in failure rate
  },
};

// ─────────────────────────────────────────────────────────────
// Setup: Runs once before the test to prepare test data
// ─────────────────────────────────────────────────────────────
export function setup() {
  // Create a few short URLs to use for redirect testing
  const shortCodes = [];

  for (let i = 0; i < 10; i++) {
    const payload = JSON.stringify({
      url: `https://example.com/test-page-${i}`,
    });

    const res = http.post(`${BASE_URL}/shorten`, payload, {
      headers: { "Content-Type": "application/json" },
    });

    if (res.status === 201) {
      const body = JSON.parse(res.body);
      shortCodes.push(body.short_code);
    }
  }

  console.log(`Setup: Created ${shortCodes.length} short URLs for testing`);
  return { shortCodes };
}

// ─────────────────────────────────────────────────────────────
// Main VU function: Each virtual user runs this repeatedly
// ─────────────────────────────────────────────────────────────
export default function (data) {
  // ── 1. Health Check (lightweight, every iteration) ──
  group("Health Check", () => {
    const res = http.get(`${BASE_URL}/health`);
    requestCount.add(1);
    healthLatency.add(res.timings.duration);

    const passed = check(res, {
      "health: status 200": (r) => r.status === 200,
      "health: body contains ok": (r) => r.body.includes("ok"),
    });

    errorRate.add(!passed);
  });

  sleep(0.1); // Small pause between groups

  // ── 2. Create Short URL (POST /shorten) ──
  group("Shorten URL", () => {
    const uniqueUrl = `https://example.com/load-test-${__VU}-${__ITER}-${Date.now()}`;
    const payload = JSON.stringify({ url: uniqueUrl });

    const res = http.post(`${BASE_URL}/shorten`, payload, {
      headers: { "Content-Type": "application/json" },
    });
    requestCount.add(1);
    shortenLatency.add(res.timings.duration);

    const passed = check(res, {
      "shorten: status 201": (r) => r.status === 201,
      "shorten: has short_code": (r) => {
        try {
          return JSON.parse(r.body).short_code !== undefined;
        } catch (e) {
          return false;
        }
      },
    });

    errorRate.add(!passed);

    // Save the short code for redirect testing
    if (res.status === 201) {
      try {
        const body = JSON.parse(res.body);
        data.shortCodes.push(body.short_code);
      } catch (e) {
        // Ignore push errors from concurrent access
      }
    }
  });

  sleep(0.1);

  // ── 3. List URLs (GET /urls) ──
  group("List URLs", () => {
    const res = http.get(`${BASE_URL}/urls?page=1&per_page=10`);
    requestCount.add(1);
    listUrlsLatency.add(res.timings.duration);

    const passed = check(res, {
      "list: status 200": (r) => r.status === 200,
      "list: returns array": (r) => {
        try {
          return Array.isArray(JSON.parse(r.body));
        } catch (e) {
          return false;
        }
      },
    });

    errorRate.add(!passed);
  });

  sleep(0.1);

  // ── 4. Redirect (GET /<short_code>) ──
  group("Redirect", () => {
    if (data.shortCodes && data.shortCodes.length > 0) {
      // Pick a random short code
      const idx = Math.floor(Math.random() * Math.min(data.shortCodes.length, 50));
      const code = data.shortCodes[idx];

      const res = http.get(`${BASE_URL}/${code}`, {
        redirects: 0, // Don't follow redirects — we want to measure our app only
      });
      requestCount.add(1);
      redirectLatency.add(res.timings.duration);

      const passed = check(res, {
        "redirect: status 302": (r) => r.status === 302,
        "redirect: has Location header": (r) => r.headers["Location"] !== undefined,
      });

      errorRate.add(!passed);
    }
  });

  sleep(0.3); // Simulate think time between actions
}

// ─────────────────────────────────────────────────────────────
// Teardown: Summary output
// ─────────────────────────────────────────────────────────────
export function handleSummary(data) {
  // Print a clean summary to stdout
  const now = new Date().toISOString();
  
  console.log("\n" + "═".repeat(60));
  console.log(" LOAD TEST RESULTS — 50 Concurrent Users");
  console.log("  " + now);
  console.log("═".repeat(60));

  if (data.metrics.http_req_duration) {
    const d = data.metrics.http_req_duration.values;
    console.log("\n Response Time (Latency):");
    console.log(`   avg .... ${d.avg.toFixed(2)}ms`);
    console.log(`   min .... ${d.min.toFixed(2)}ms`);
    console.log(`   med .... ${d.med.toFixed(2)}ms`);
    console.log(`   p90 .... ${d["p(90)"].toFixed(2)}ms`);
    console.log(`   p95 .... ${d["p(95)"].toFixed(2)}ms  ← BASELINE`);
    if (d["p(99)"]) {
      console.log(`   p99 .... ${d["p(99)"].toFixed(2)}ms`);
    }
    console.log(`   max .... ${d.max.toFixed(2)}ms`);
  }

  if (data.metrics.http_req_failed) {
    const errRate = data.metrics.http_req_failed.values.rate;
    console.log(`\n Error Rate: ${(errRate * 100).toFixed(2)}%`);
  }

  if (data.metrics.http_reqs) {
    console.log(`\n Total HTTP Requests: ${data.metrics.http_reqs.values.count}`);
    console.log(`   Requests/sec: ${data.metrics.http_reqs.values.rate.toFixed(2)}`);
  }

  // Per-endpoint latency
  const endpoints = [
    { name: "Health Check", key: "health_latency" },
    { name: "Shorten URL", key: "shorten_latency" },
    { name: "List URLs", key: "list_urls_latency" },
    { name: "Redirect", key: "redirect_latency" },
  ];

  console.log("\n Per-Endpoint p95 Latency:");
  for (const ep of endpoints) {
    if (data.metrics[ep.key]) {
      const p95 = data.metrics[ep.key].values["p(95)"];
      console.log(`   ${ep.name.padEnd(15)} ${p95.toFixed(2)}ms`);
    }
  }

  console.log("\n" + "═".repeat(60));

  // Also write JSON report to file
  return {
    "k6/results/load-test-results.json": JSON.stringify(data, null, 2),
    stdout: textSummary(data, { indent: "  ", enableColors: true }),
  };
}

// Import the built-in text summary
import { textSummary } from "https://jslib.k6.io/k6-summary/0.0.3/index.js";
