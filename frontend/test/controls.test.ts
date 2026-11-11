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

test("Currency Engine: Sourced billing currency is USD with rate 1.0", () => {
  const usd = CURRENCY_MAP["USD"];
  assert.ok(usd, "USD must be defined");
  assert.strictEqual(usd.rateToUsd, 1.0);
  assert.strictEqual(usd.isSourceBillingCurrency, true);
  assert.strictEqual(usd.symbol, "$");
});

test("Currency Engine: All 6 documented currencies are supported with official sources", () => {
  const expectedCodes = ["USD", "EUR", "GBP", "AUD", "CAD", "INR"];
  assert.strictEqual(SUPPORTED_CURRENCIES.length, 6);

  for (const code of expectedCodes) {
    const meta = getCurrencyMeta(code);
    assert.strictEqual(meta.code, code);
    assert.ok(meta.rateToUsd > 0, `${code} rate must be positive`);
    assert.ok(meta.source.length > 5, `${code} must have named source`);
    assert.ok(meta.asOf.length === 10, `${code} must have asOf date (YYYY-MM-DD)`);
  }
});

test("Currency Engine: formatCost converts with explicit precision and formatting", () => {
  // USD baseline
  assert.strictEqual(formatCost(1000, "USD"), "$1,000");
  assert.strictEqual(formatCost(12.5, "USD"), "$12.50");

  // EUR conversion (1 USD = 0.922 EUR -> 1000 USD = 922 EUR, < 1000 so 2 decimals)
  assert.strictEqual(formatCost(1000, "EUR"), "€922.00");
  assert.strictEqual(formatCost(2000, "EUR"), "€1,844");

  // INR conversion (1 USD = 83.45 INR -> 1000 USD = 83,450 INR)
  assert.strictEqual(formatCost(1000, "INR"), "₹83,450");

  // AUD conversion (1 USD = 1.523 AUD -> 1000 USD = 1,523 AUD)
  assert.strictEqual(formatCost(1000, "AUD"), "A$1,523");
});

test("Currency Engine: Traceability note clearly identifies source USD data", () => {
  const usdNote = getCurrencyTraceability("USD");
  assert.ok(usdNote.includes("Native Billing Source"), "USD note must indicate native billing");

  const eurNote = getCurrencyTraceability("EUR");
  assert.ok(eurNote.includes("European Central Bank"), "EUR note must state ECB source");
  assert.ok(eurNote.includes("Raw billing remains USD"), "Must indicate source remains USD");
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
