import test from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import {
  costBasisLabel,
  isInvoicedBasis,
  normalizePricePage,
  normalizeUsagePage,
} from "../src/lib/billing";

const rec = { record_id: "r1" } as never;
const price = { sku_name: "S" } as never;

test("usage: paginated envelope passes through unchanged", () => {
  const page = normalizeUsagePage({ total: 7, offset: 5, limit: 2, records: [rec, rec] });
  assert.deepStrictEqual([page.total, page.offset, page.limit, page.records.length], [7, 5, 2, 2]);
});

test("usage: legacy bare list is wrapped without breaking consumers", () => {
  const page = normalizeUsagePage([rec, rec, rec], 0, 50);
  assert.deepStrictEqual([page.total, page.offset, page.limit, page.records.length], [3, 0, 50, 3]);
});

test("usage: malformed or empty payloads degrade to an empty page, never throw", () => {
  for (const bad of [null, undefined, {}, { records: "x" }, 42]) {
    const page = normalizeUsagePage(bad);
    assert.strictEqual(page.records.length, 0);
    assert.strictEqual(page.total, 0);
  }
});

test("pricing: envelope and bare list are both accepted", () => {
  assert.strictEqual(normalizePricePage({ total: 9, records: [price] }).total, 9);
  assert.strictEqual(normalizePricePage([price, price]).total, 2);
  assert.strictEqual(normalizePricePage(null).records.length, 0);
});

test("cost basis: only AZURE_INVOICED reads as billed; unknown never does", () => {
  assert.strictEqual(costBasisLabel("LIST_PRICE_ESTIMATE"), "Estimated at list price");
  assert.strictEqual(costBasisLabel("AZURE_INVOICED"), "Billed (Azure)");
  assert.ok(!/billed/i.test(costBasisLabel("METERED_USAGE")));
  assert.ok(!/billed/i.test(costBasisLabel(undefined)));
  assert.ok(!/billed/i.test(costBasisLabel("SOMETHING_ELSE")));
  assert.strictEqual(isInvoicedBasis("LIST_PRICE_ESTIMATE"), false);
  assert.strictEqual(isInvoicedBasis("AZURE_INVOICED"), true);
});

test("api.ts requests the envelope and normalizes the response", () => {
  const src = fs.readFileSync(path.resolve(__dirname, "../src/lib/api.ts"), "utf8");
  assert.ok(src.includes('params.append("envelope", "true")'));
  assert.ok(src.includes("normalizeUsagePage("));
  assert.ok(src.includes("normalizePricePage("));
});
