import test from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import {
  currencyColumnName,
  formatSourceMoney,
  singleCurrency,
  sourceCurrencyLabel,
  sourceCurrencyOf,
} from "../src/lib/billing";

const summary = (currency: string | null, per: Array<[string, number]> = []) => ({
  currency,
  spend_by_currency: per.map(([c, spend]) => ({ currency: c, spend })),
});

test("USD: dollar symbol only when the billed currency is USD", () => {
  const usd = sourceCurrencyOf(summary("USD", [["USD", 10]]));
  assert.deepStrictEqual([usd.code, usd.mixed], ["USD", false]);
  assert.strictEqual(formatSourceMoney(1234.5, usd), "$1,234.50");
});

test("non-USD: amount keeps its own currency code and is never shown with $ or converted", () => {
  const eur = sourceCurrencyOf(summary("EUR", [["EUR", 20]]));
  assert.strictEqual(formatSourceMoney(1234.5, eur), "1,234.50 EUR");
  assert.strictEqual(formatSourceMoney(100, singleCurrency("INR")), "100.00 INR"); // no FX applied
  assert.ok(!formatSourceMoney(50, eur).includes("$"));
});

test("mixed currencies: no amount is rendered, and the label says why", () => {
  const mixed = sourceCurrencyOf(summary(null, [["USD", 10], ["EUR", 20]]));
  assert.strictEqual(mixed.mixed, true);
  assert.strictEqual(mixed.code, null);
  assert.strictEqual(formatSourceMoney(30, mixed), "n/a (mixed currencies)");
  assert.ok(sourceCurrencyLabel(mixed).includes("USD, EUR"));
  assert.strictEqual(currencyColumnName(mixed), "mixed currencies");
});

test("unknown currency or missing amount is a dash, never a guessed dollar value", () => {
  const unknown = sourceCurrencyOf(null);
  assert.strictEqual(unknown.code, null);
  assert.strictEqual(formatSourceMoney(10, unknown), "-");
  assert.strictEqual(formatSourceMoney(null, singleCurrency("USD")), "-");
  assert.strictEqual(formatSourceMoney(NaN, singleCurrency("USD")), "-");
  assert.strictEqual(currencyColumnName(unknown), "currency unknown");
});

test("FinOps view no longer converts or assumes USD", () => {
  const src = fs.readFileSync(
    path.resolve(__dirname, "../src/components/FinOpsCommandCenterView.tsx"),
    "utf8"
  );
  // no client-side FX converter, no currency picker, no hardcoded dollar formatting of amounts
  assert.ok(!src.includes("@/lib/currency"));
  assert.ok(!src.includes("selectedCurrency"));
  assert.ok(!src.includes("SUPPORTED_CURRENCIES"));
  assert.ok(!/`\$\$\{/.test(src), "hardcoded $ template literal found");
  assert.ok(!src.includes("Cost (USD)"));
  assert.ok(src.includes("sourceCurrencyOf(billingSummary)"));
});
