import http from "k6/http";
import { check, sleep, group } from "k6";
import { Counter, Rate, Trend } from "k6/metrics";
import { textSummary } from "https://jslib.k6.io/k6-summary/0.0.3/index.js";

// ─────────────────────────────────────────────────────────────
// Custom metrics
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
  // ── Stages: ramp up to 200 VUs, hold, ramp down ──
  stages: [
    { duration: "15s", target: 50 },    // Warm up to 50
    { duration: "15s", target: 100 },   // Ramp to 100
    { duration: "15s", target: 200 },   // Ramp to 200 concurrent users
    { duration: "30s", target: 200 },   // Hold at 200 for 30s (steady state)
    { duration: "15s", target: 0 },     // Ramp down
  ],

  // ── Silver tier threshold: under 3 seconds ──
  thresholds: {
    http_req_duration: [
      "p(95)<3000",   // 95% of requests must complete within 3s
      "p(99)<5000",   // 99% within 5s
    ],
    errors: ["rate<0.10"],
    http_req_failed: ["rate<0.10"],
  },
};

// ─────────────────────────────────────────────────────────────
// Setup: Create test data
// ─────────────────────────────────────────────────────────────
export function setup() {
  const shortCodes = [];

  for (let i = 0; i < 20; i++) {
    const payload = JSON.stringify({
      url: "https://example.com/test-page-" + i,
    });

    const res = http.post(BASE_URL + "/shorten", payload, {
      headers: { "Content-Type": "application/json" },
    });

    if (res.status === 201) {
      try {
        var body = JSON.parse(res.body);
        shortCodes.push(body.short_code);
      } catch (e) {
        // ignore
      }
    }
  }

  console.log("Setup: Created " + shortCodes.length + " short URLs for testing");
  return { shortCodes: shortCodes };
}

// ─────────────────────────────────────────────────────────────
// Main VU function
// ─────────────────────────────────────────────────────────────
export default function (data) {
  // ── 1. Health Check ──
  group("Health Check", function () {
    var res = http.get(BASE_URL + "/health");
    requestCount.add(1);
    healthLatency.add(res.timings.duration);

    var passed = check(res, {
      "health: status 200": function (r) { return r.status === 200; },
      "health: body ok": function (r) { return r.body.indexOf("ok") !== -1; },
    });
    errorRate.add(!passed);
  });

  sleep(0.1);

  // ── 2. Shorten URL ──
  group("Shorten URL", function () {
    var uniqueUrl = "https://example.com/load-" + __VU + "-" + __ITER + "-" + Date.now();
    var payload = JSON.stringify({ url: uniqueUrl });

    var res = http.post(BASE_URL + "/shorten", payload, {
      headers: { "Content-Type": "application/json" },
    });
    requestCount.add(1);
    shortenLatency.add(res.timings.duration);

    var passed = check(res, {
      "shorten: status 201": function (r) { return r.status === 201; },
      "shorten: has short_code": function (r) {
        try {
          return JSON.parse(r.body).short_code !== undefined;
        } catch (e) {
          return false;
        }
      },
    });
    errorRate.add(!passed);
  });

  sleep(0.1);

  // ── 3. List URLs ──
  group("List URLs", function () {
    var res = http.get(BASE_URL + "/urls?page=1&per_page=10");
    requestCount.add(1);
    listUrlsLatency.add(res.timings.duration);

    var passed = check(res, {
      "list: status 200": function (r) { return r.status === 200; },
      "list: returns array": function (r) {
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

  // ── 4. Redirect ──
  group("Redirect", function () {
    if (data.shortCodes && data.shortCodes.length > 0) {
      var idx = Math.floor(Math.random() * Math.min(data.shortCodes.length, 20));
      var code = data.shortCodes[idx];

      var res = http.get(BASE_URL + "/" + code, { redirects: 0 });
      requestCount.add(1);
      redirectLatency.add(res.timings.duration);

      var passed = check(res, {
        "redirect: status 302": function (r) { return r.status === 302; },
        "redirect: has Location": function (r) { return r.headers["Location"] !== undefined; },
      });
      errorRate.add(!passed);
    }
  });

  sleep(0.2);
}

// ─────────────────────────────────────────────────────────────
// Summary
// ─────────────────────────────────────────────────────────────
export function handleSummary(data) {
  var now = new Date().toISOString();

  console.log("\n" + "=".repeat(60));
  console.log(" LOAD TEST RESULTS — 200 Concurrent Users (Silver)");
  console.log("  " + now);
  console.log("=".repeat(60));

  if (data.metrics.http_req_duration) {
    var d = data.metrics.http_req_duration.values;
    console.log("\n Response Time (Latency):");
    console.log("   avg .... " + d.avg.toFixed(2) + "ms");
    console.log("   min .... " + d.min.toFixed(2) + "ms");
    console.log("   med .... " + d.med.toFixed(2) + "ms");
    console.log("   p90 .... " + d["p(90)"].toFixed(2) + "ms");
    console.log("   p95 .... " + d["p(95)"].toFixed(2) + "ms  <-- SILVER TARGET < 3000ms");
    console.log("   max .... " + d.max.toFixed(2) + "ms");
  }

  if (data.metrics.http_req_failed) {
    var errRate = data.metrics.http_req_failed.values.rate;
    console.log("\n Error Rate: " + (errRate * 100).toFixed(2) + "%");
  }

  if (data.metrics.http_reqs) {
    console.log("\n Total HTTP Requests: " + data.metrics.http_reqs.values.count);
    console.log("   Requests/sec: " + data.metrics.http_reqs.values.rate.toFixed(2));
  }

  var endpoints = [
    { name: "Health Check", key: "health_latency" },
    { name: "Shorten URL", key: "shorten_latency" },
    { name: "List URLs", key: "list_urls_latency" },
    { name: "Redirect", key: "redirect_latency" },
  ];

  console.log("\n Per-Endpoint p95 Latency:");
  for (var i = 0; i < endpoints.length; i++) {
    var ep = endpoints[i];
    if (data.metrics[ep.key]) {
      var p95 = data.metrics[ep.key].values["p(95)"];
      console.log("   " + ep.name + ": " + p95.toFixed(2) + "ms");
    }
  }

  console.log("\n" + "=".repeat(60));

  return {
    "k6/results/silver-200vus-results.json": JSON.stringify(data, null, 2),
    stdout: textSummary(data, { indent: "  ", enableColors: true }),
  };
}
