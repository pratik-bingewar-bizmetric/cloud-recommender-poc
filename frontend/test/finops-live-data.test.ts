import test from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import {
  dateInputToMs,
  fmtMoney,
  hasRealValue,
  kpiDisplay,
  statusLabel,
  unresolvedSections,
} from "../src/lib/finopsProvenance";

const metric = (over: Record<string, unknown>) =>
  ({
    value: null,
    formatted_value: "Awaiting billing data",
    unit: "USD",
    status: "BLOCKED_PENDING_APPROVAL",
    data_freshness: "x",
    source: "system.billing.usage",
    workspace_id: "w",
    configuration_version: 1,
    calculation_version: "v",
    coverage: 1,
    ...over,
  }) as never;

test("kpiDisplay never fabricates a value for blocked / unavailable metrics", () => {
  assert.strictEqual(kpiDisplay(metric({})), "-");
  assert.strictEqual(kpiDisplay(metric({ status: "INSUFFICIENT_HISTORY", formatted_value: "-" })), "-");
  assert.strictEqual(kpiDisplay(undefined, { error: true }), "-");
  assert.strictEqual(kpiDisplay(undefined, { loading: true }), "…");
  assert.ok(!kpiDisplay(metric({})).includes("$0"));
});

test("hasRealValue only accepts LIVE/CALCULATED/ESTIMATED values", () => {
  assert.strictEqual(hasRealValue(metric({ value: 5, status: "CALCULATED" })), true);
  assert.strictEqual(hasRealValue(metric({ value: 5, status: "BLOCKED_PENDING_APPROVAL" })), false);
  assert.strictEqual(hasRealValue(metric({ value: null, status: "LIVE" })), false);
});

test("fmtMoney treats null as unknown, never zero", () => {
  assert.strictEqual(fmtMoney(null), "-");
  assert.strictEqual(fmtMoney(undefined), "-");
  assert.strictEqual(fmtMoney(0), "$0");
});

test("statusLabel and unresolvedSections classify provenance", () => {
  assert.strictEqual(statusLabel("BLOCKED_PENDING_APPROVAL"), "BLOCKED");
  assert.strictEqual(statusLabel("NOT_AUTHORIZED"), "PERMISSION REQUIRED");
  const out = unresolvedSections({
    a: { classification: "LIVE", source: "s" },
    b: { classification: "CALCULATED", source: "s" },
    c: { classification: "BLOCKED_PENDING_APPROVAL", source: "s" },
  });
  assert.deepStrictEqual(out.map(([k]) => k), ["c"]);
});

test("dateInputToMs validates and converts date inputs", () => {
  assert.strictEqual(dateInputToMs("2026-11-01"), Date.UTC(2026, 10, 1));
  assert.strictEqual(dateInputToMs("2026-11-01", true), Date.UTC(2026, 10, 1, 23, 59, 59, 999));
  assert.strictEqual(dateInputToMs(""), null);
  assert.strictEqual(dateInputToMs("11/01/2026"), null);
});

test("dashboard source contains no retired mock figures or fixtures", () => {
  const files = [
    "components/FinOpsCommandCenterView.tsx",
    "components/DatabricksWorkspaceDetailView.tsx",
    "components/shared/KpiDetailDrawer.tsx",
    "components/shared/ResourceDetailDrawer.tsx",
    "components/shared/AnomalyDetailDrawer.tsx",
  ];
  const sentinels = [
    "$176,840",
    "$42,180",
    "$284,620",
    "$319,500",
    "$300,000",
    "$24,530",
    "$108,155",
    "88,420",
    "26.7236",
    "k0qfl59u",
    "createFallbackKpi",
    "panasonic-voice-agent-prod",
    "$760 / day",
  ];
  for (const f of files) {
    const text = fs.readFileSync(path.resolve(__dirname, "../src", f), "utf-8");
    for (const s of sentinels) {
      assert.ok(!text.includes(s), `${f} still contains retired mock value ${s}`);
    }
  }
});
