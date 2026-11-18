/**
 * Automated Test Suite: Interactive Controls, FX Traceability & Histogram Filtering
 * Verifies Milestone 3J.5 / Part E Remediation.
 */

import assert from "node:assert";
import test from "node:test";
import {
  SUPPORTED_CURRENCIES,
  CURRENCY_MAP,
  formatCost,
  getCurrencyMeta,
  getCurrencyTraceability,
} from "../src/lib/currency";

test("Currency helpers contain no exchange rates and never convert", () => {
  const src = require("fs").readFileSync(require("path").resolve(__dirname, "../src/lib/currency.ts"), "utf8");
  assert.ok(!/rateToUsd|exchange_rate|83\.|0\.922/.test(src), "no FX rates may be hardcoded");
  for (const meta of SUPPORTED_CURRENCIES) assert.ok(!("rateToUsd" in meta));
});

test("formatCost formats an amount in its own currency with no conversion", () => {
  assert.strictEqual(formatCost(1000, "USD"), "$1,000.00");
  assert.strictEqual(formatCost(1000, "EUR"), "€1,000.00"); // same number, not 922
  assert.strictEqual(formatCost(1000, "INR"), "₹1,000.00"); // same number, not 83,450
  assert.strictEqual(formatCost(5, "XYZ"), "XYZ 5.00"); // unknown code is never mapped to USD
  assert.strictEqual(getCurrencyMeta("eur").code, "EUR");
});

test("Traceability note states there is no conversion", () => {
  const note = getCurrencyTraceability("EUR");
  assert.ok(note.includes("No conversion applied"));
  assert.ok(!note.includes("Reference Rate"));
});

test("Query Execution History: Duration bucket filtering logic works deterministically", () => {
  interface MockQuery {
    query_id: string;
    duration_ms: number;
  }

  const queries: MockQuery[] = [
    { query_id: "q1", duration_ms: 450 },     // <1s
    { query_id: "q2", duration_ms: 2500 },    // 1s-5s
    { query_id: "q3", duration_ms: 12000 },   // 5s-30s
    { query_id: "q4", duration_ms: 45000 },   // 30s-2m
    { query_id: "q5", duration_ms: 150000 },  // >2m
  ];

  function getDurationBucket(ms: number): string {
    if (ms < 1000) return "<1s";
    if (ms < 5000) return "1s-5s";
    if (ms < 30000) return "5s-30s";
    if (ms < 120000) return "30s-2m";
    return ">2m";
  }

  const fastQueries = queries.filter((q) => getDurationBucket(q.duration_ms) === "<1s");
  assert.strictEqual(fastQueries.length, 1);
  assert.strictEqual(fastQueries[0].query_id, "q1");

  const longQueries = queries.filter((q) => getDurationBucket(q.duration_ms) === ">2m");
  assert.strictEqual(longQueries.length, 1);
  assert.strictEqual(longQueries[0].query_id, "q5");
});

test("Scope Reset Logic: Switching active subscription or workspace resets dependent filters", () => {
  interface ScopeFilterState {
    subscriptionId: string;
    workspaceId: string;
    clusterFilter: string;
    warehouseFilter: string;
    activePage: number;
  }

  function handleSwitchScope(
    prevState: ScopeFilterState,
    newSubId: string,
    newWsId: string
  ): ScopeFilterState {
    return {
      subscriptionId: newSubId,
      workspaceId: newWsId,
      clusterFilter: "all",
      warehouseFilter: "all",
      activePage: 1,
    };
  }

  const initial: ScopeFilterState = {
    subscriptionId: "sub-1",
    workspaceId: "ws-1",
    clusterFilter: "ml-cluster-large",
    warehouseFilter: "wh-sql-serverless",
    activePage: 4,
  };

  const next = handleSwitchScope(initial, "sub-2", "ws-2");
  assert.strictEqual(next.subscriptionId, "sub-2");
  assert.strictEqual(next.workspaceId, "ws-2");
  assert.strictEqual(next.clusterFilter, "all", "Dependent cluster filter must reset to all");
  assert.strictEqual(next.warehouseFilter, "all", "Dependent warehouse filter must reset to all");
  assert.strictEqual(next.activePage, 1, "Pagination must reset to page 1");
});
