import test from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import {
  FINANCIAL_UNAVAILABLE_MESSAGES,
  NO_DATA_LABEL,
  buildCanonicalFinancialSummary,
  financialErrorFromStatus,
  financialUnavailableReason,
  formatFinancialCurrency,
  isFixtureDataSource,
  percentOf,
  periodSuffix,
  toFiniteNumber,
} from "../src/lib/financials";

const SRC = path.resolve(__dirname, "../src");

function walk(dir: string, out: string[] = []): string[] {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else if (/\.(ts|tsx)$/.test(e.name)) out.push(p);
  }
  return out;
}

const HARDCODED = ["225.11", "118.27", "280.87", "84.27", "105.21", "91.25", "52.5%"];

// ---------------------------------------------------------------------------
// Hardcoded fallback values are gone from the whole frontend source tree
// ---------------------------------------------------------------------------
test("none of the known hardcoded financial figures remain in frontend source", () => {
  const offenders: string[] = [];
  for (const file of walk(SRC)) {
    const text = fs.readFileSync(file, "utf-8");
    for (const v of HARDCODED) {
      if (text.includes(v)) offenders.push(`${path.relative(SRC, file)}: ${v}`);
    }
  }
  assert.deepStrictEqual(offenders, []);
});

test("reference/fixture financial generators and fake scope names are removed", () => {
  const lib = fs.readFileSync(path.join(SRC, "lib/financials.ts"), "utf-8");
  assert.ok(!lib.includes("getAzureReferenceFinancials"));
  assert.ok(!lib.includes("getGcpReferenceFinancials"));
  for (const file of walk(path.join(SRC, "components"))) {
    const text = fs.readFileSync(file, "utf-8");
    assert.ok(!text.includes("sub-prod-enterprise-01"), `${file} references the fake scope`);
    assert.ok(!text.includes("Production Enterprise Subscription"), `${file} uses a fake scope name`);
  }
});

test("Dashboard no longer invents a trend from fixed multipliers or a synthetic budget", () => {
  const text = fs.readFileSync(path.join(SRC, "components/DashboardView.tsx"), "utf-8");
  assert.ok(!text.includes("0.76, 0.84"));
  assert.ok(!text.includes("base * 1.05"));
});

// ---------------------------------------------------------------------------
// Null is never zero
// ---------------------------------------------------------------------------
test("null, undefined and non-finite amounts render 'No data available', never $0.00", () => {
  for (const v of [null, undefined, Number.NaN, Number.POSITIVE_INFINITY]) {
    assert.strictEqual(formatFinancialCurrency(v), NO_DATA_LABEL);
  }
  assert.strictEqual(NO_DATA_LABEL, "No data available");
});

test("a confirmed real zero and real values still format normally", () => {
  assert.strictEqual(formatFinancialCurrency(0), "$0.00");
  assert.strictEqual(formatFinancialCurrency(12.5), "$12.50");
  assert.strictEqual(formatFinancialCurrency(1000), "$1,000.00"); // as reported, no FX
});

test("toFiniteNumber keeps null/empty/NaN as null and parses real strings", () => {
  assert.strictEqual(toFiniteNumber(null), null);
  assert.strictEqual(toFiniteNumber(undefined), null);
  assert.strictEqual(toFiniteNumber(""), null);
  assert.strictEqual(toFiniteNumber("abc"), null);
  assert.strictEqual(toFiniteNumber("12.50"), 12.5);
  assert.strictEqual(toFiniteNumber(0), 0);
  assert.strictEqual(percentOf(null, 10), null);
  assert.strictEqual(percentOf(5, 0), null);
  assert.strictEqual(percentOf(5, 20), 25);
});

// ---------------------------------------------------------------------------
// buildCanonicalFinancialSummary: no data => null (no reference figures), no mixing
// ---------------------------------------------------------------------------
const analysis = (over: Record<string, unknown> = {}) =>
  ({
    data_source: "live_authenticated",
    cost_breakdown: null,
    total_potential_monthly_savings: null,
    waste_findings: [],
    resources: [],
    ...over,
  }) as never;

test("no source data returns null for every provider (no reference summary)", () => {
  assert.strictEqual(buildCanonicalFinancialSummary("azure", "", ""), null);
  assert.strictEqual(buildCanonicalFinancialSummary("gcp", "", ""), null);
  assert.strictEqual(financialUnavailableReason(null, null, null), "NO_DATA");
});

test("fixture-labelled payloads are never shown as live financials", () => {
  for (const src of ["mock_fixture", "simulation_fixture", "ai_proposed"]) {
    assert.ok(isFixtureDataSource(src));
    const a = analysis({
      data_source: src,
      cost_breakdown: { total_monthly: "999.99" },
      total_potential_monthly_savings: "111.11",
    });
    assert.strictEqual(buildCanonicalFinancialSummary("azure", "s", "n", "30d", "USD", null, a), null);
    assert.strictEqual(financialUnavailableReason(null, a), "FIXTURE_DATA");
  }
  const overview = { data_source: "mock_fixture", kpis: { estimated_monthly_cost: "50.00" } } as never;
  assert.strictEqual(buildCanonicalFinancialSummary("azure", "s", "n", "30d", "USD", overview), null);
  assert.match(FINANCIAL_UNAVAILABLE_MESSAGES.FIXTURE_DATA, /Authentication required/);
});

test("null source values stay null: no fallback constant, no zero, no invented category split", () => {
  const s = buildCanonicalFinancialSummary("azure", "sub-1", "Sub 1", "30d", "USD", null, analysis());
  assert.ok(s);
  assert.strictEqual(s.estimated_monthly_spend, null);
  assert.strictEqual(s.potential_monthly_savings, null);
  assert.strictEqual(s.projected_annual_savings, null);
  assert.strictEqual(s.savings_percentage_of_spend, null);
  assert.deepStrictEqual(s.categories, []);
  assert.deepStrictEqual(s.findings, []);
  assert.strictEqual(s.included_resources_count, 0);
  assert.strictEqual(s.actual_billed_monthly_spend, null);
});

test("empty billing response (no breakdown, overview without cost) yields null spend", () => {
  const overview = {
    data_source: "live_authenticated",
    kpis: { estimated_monthly_cost: null, potential_monthly_savings: null, total_resources: undefined },
  } as never;
  const s = buildCanonicalFinancialSummary("azure", "s", "n", "30d", "USD", overview, null);
  assert.ok(s);
  assert.strictEqual(s.estimated_monthly_spend, null);
  assert.strictEqual(s.included_resources_count, null);
  assert.strictEqual(FINANCIAL_UNAVAILABLE_MESSAGES.NO_BILLING_DATA, "No billing data available.");
});

test("real source data renders actual values and only the provider's own categories", () => {
  const a = analysis({
    cost_breakdown: { total_monthly: "100.00", compute: "60.00", storage: "40.00", database: null },
    total_potential_monthly_savings: "25.00",
  });
  const s = buildCanonicalFinancialSummary("azure", "sub-1", "Sub 1", "30d", "USD", null, a);
  assert.ok(s);
  assert.strictEqual(s.estimated_monthly_spend, 100);
  assert.strictEqual(s.potential_monthly_savings, 25);
  assert.strictEqual(s.projected_annual_savings, 300);
  assert.strictEqual(s.savings_percentage_of_spend, 25);
  assert.deepStrictEqual(
    s.categories.map((c) => [c.name, c.amount_usd, c.percentage_of_total]),
    [
      ["Compute", 60, 60],
      ["Storage", 40, 40],
    ]
  );
  assert.strictEqual(s.spend_basis, "estimated_public_list");
  assert.strictEqual(s.actual_billed_monthly_spend, null, "estimates are never presented as actual billing");
  assert.strictEqual(s.scope_id, "sub-1");
});

test("Azure and GCP figures are never mixed", () => {
  const a = analysis({ cost_breakdown: { total_monthly: "10.00" } });
  const az = buildCanonicalFinancialSummary("azure", "s", "n", "30d", "USD", null, a);
  const gcp = buildCanonicalFinancialSummary("gcp", "p", "n", "30d", "USD", null, a);
  assert.ok(az && gcp);
  assert.strictEqual(az.pricing_source, "Azure Retail Prices API");
  assert.strictEqual(gcp.pricing_source, "GCP Cloud Billing Catalog");
  assert.strictEqual(az.estimated_monthly_spend, 10);
  assert.strictEqual(gcp.estimated_monthly_spend, 10);
  // no source for the other provider => null, never the other provider's reference numbers
  assert.strictEqual(buildCanonicalFinancialSummary("gcp", "", ""), null);
});

test("unavailable-state messages cover auth, no billing, forecast and API error", () => {
  assert.match(FINANCIAL_UNAVAILABLE_MESSAGES.AUTHENTICATION_REQUIRED, /Authentication required/);
  assert.strictEqual(FINANCIAL_UNAVAILABLE_MESSAGES.FORECAST_UNAVAILABLE, "Forecast unavailable.");
  assert.match(FINANCIAL_UNAVAILABLE_MESSAGES.API_ERROR, /API error/);
  assert.strictEqual(FINANCIAL_UNAVAILABLE_MESSAGES.NO_DATA, NO_DATA_LABEL);
});

test("greenfield simulation stays labelled as a simulation, never as actual spend", () => {
  const cost = {
    total_monthly: "200.00",
    compute: "100.00",
    database: "50.00",
    storage: "30.00",
    ai: "10.00",
    networking: "5.00",
    other: "5.00",
    unpriced_component_count: 0,
  } as never;
  const s = buildCanonicalFinancialSummary("azure", "", "", "30d", "USD", null, null, cost);
  assert.ok(s);
  assert.strictEqual(s.data_provenance, "simulation_benchmark");
  assert.strictEqual(s.actual_billed_monthly_spend, null);
  assert.strictEqual(s.estimated_monthly_spend, 200);
  assert.strictEqual(
    buildCanonicalFinancialSummary("azure", "", "", "30d", "USD", null, null, { total_monthly: null } as never),
    null
  );
});

// ---------------------------------------------------------------------------
// Gap closure: HTTP error states for the Cost & Waste analysis call
// ---------------------------------------------------------------------------
test("HTTP 401 maps to the authentication-required message", () => {
  const e = financialErrorFromStatus(401, "azure");
  assert.strictEqual(e.reason, "AUTHENTICATION_REQUIRED");
  assert.strictEqual(e.message, "Authentication required — run az login.");
  assert.match(financialErrorFromStatus(401, "gcp").message, /gcloud auth login/);
});

test("HTTP 403 maps to the access-denied message", () => {
  const e = financialErrorFromStatus(403, "azure");
  assert.strictEqual(e.reason, "ACCESS_DENIED");
  assert.strictEqual(e.message, "Access denied — check your Azure permissions.");
  assert.match(financialErrorFromStatus(403, "gcp").message, /GCP permissions/);
});

test("other failures give a generic error state with only the status code", () => {
  for (const status of [400, 404, 500, 502, 503]) {
    const e = financialErrorFromStatus(status, "azure");
    assert.strictEqual(e.reason, "API_ERROR");
    assert.ok(e.message.includes(`HTTP ${status}`));
  }
  for (const status of [null, undefined, 0]) {
    const e = financialErrorFromStatus(status, "azure");
    assert.strictEqual(e.reason, "API_ERROR");
    assert.match(e.message, /network error/);
  }
});

test("error messages never contain tokens, bearer strings or stack traces", () => {
  for (const status of [401, 403, 500, null]) {
    for (const provider of ["azure", "gcp"] as const) {
      const m = financialErrorFromStatus(status, provider).message;
      assert.ok(!/bearer|token|secret|traceback|at \w+\.|\n/i.test(m), m);
    }
  }
});

test("empty successful response reads 'No billing data available.'", () => {
  assert.strictEqual(FINANCIAL_UNAVAILABLE_MESSAGES.NO_BILLING_DATA, "No billing data available.");
});

test("Monitoring keeps only the HTTP status of a failed analysis call and passes it to Cost & Waste", () => {
  const text = fs.readFileSync(path.join(SRC, "components/SectionCentralizedMonitoring.tsx"), "utf-8");
  assert.ok(text.includes("setAnalysisError({ status: err instanceof ApiError ? err.status : null })"));
  assert.ok(text.includes("analysisError={analysisError}"));
  const waste = fs.readFileSync(path.join(SRC, "components/SectionCostWaste.tsx"), "utf-8");
  assert.ok(waste.includes("financialErrorFromStatus(analysisError.status, provider)"));
  assert.ok(!waste.includes("analysisError.message"), "raw error text must not be rendered");
});

// ---------------------------------------------------------------------------
// Gap closure: /mo and /yr suffixes only next to real values
// ---------------------------------------------------------------------------
test("period suffix is dropped when the value is unavailable and kept for real values", () => {
  for (const v of [null, undefined, Number.NaN, Number.POSITIVE_INFINITY]) {
    assert.strictEqual(periodSuffix(v, "/mo"), "");
    assert.strictEqual(periodSuffix(v, "/yr"), "");
  }
  assert.strictEqual(periodSuffix(12.5, "/mo"), "/mo");
  assert.strictEqual(periodSuffix(300, "/yr"), "/yr");
});

test("a legitimate zero keeps both its $0.00 formatting and its suffix", () => {
  assert.strictEqual(formatFinancialCurrency(0), "$0.00");
  assert.strictEqual(periodSuffix(0, "/mo"), "/mo");
});

test("financial cards render suffixes through periodSuffix, never as bare literals next to a value", () => {
  const files = ["DashboardView", "SectionCostWaste", "FinancialKpiDrawer"];
  for (const f of files) {
    const text = fs.readFileSync(path.join(SRC, `components/${f}.tsx`), "utf-8");
    assert.ok(text.includes("periodSuffix("), `${f} must use periodSuffix`);
    // The only literal "/mo" after a formatted value is the Dashboard's "Save up to" label, which is
    // rendered only in the branch where the savings value is known (guarded by `=== null`).
    const withoutGuarded = text.replace(
      /savingsAmount === null\s*\? `Savings: \$\{NO_DATA_LABEL\}`\s*: `Save up to \$\{formatFinancialCurrency\([^)]*\)\}\/mo[^`]*`/,
      ""
    );
    assert.ok(!/formatFinancialCurrency\([^)]*\)\}\/mo/.test(withoutGuarded), `${f} has a bare /mo after a formatted value`);
  }
});

test("Cost & Waste never claims zero findings or zero opportunities when the analysis did not return", () => {
  const waste = fs.readFileSync(path.join(SRC, "components/SectionCostWaste.tsx"), "utf-8");
  assert.ok(waste.includes("const analysisAvailable = analysisData !== null;"));
  // the 'nothing found' sentence and the numeric counts are only reachable when the analysis returned
  assert.ok(/analysisAvailable\s*\?\s*"Zero unattached disks/.test(waste));
  assert.ok(waste.includes("analysisAvailable ? rawFindings.length + techDebtItems.length : NO_DATA_LABEL"));
});
