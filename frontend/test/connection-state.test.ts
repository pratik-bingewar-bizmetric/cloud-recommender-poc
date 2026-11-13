import test from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import {
  deriveConnectionView,
  environmentLabel,
  inventoryCount,
  toIndicatorStatus,
} from "../src/lib/connectionState";
import { createRefreshController, formatUpdatedAt } from "../src/lib/refreshScheduler";

const health = (over: Record<string, unknown> = {}) =>
  ({
    connection_id: "c",
    workspace_id: "w1",
    cloud: "azure",
    status: "connected",
    connection_state: "CONNECTED",
    workspace_name: "Dev",
    environment: "development",
    last_discovery_at: "2026-11-13T05:00:00Z",
    discovery_stale: false,
    sql_warehouse: { warehouse_id: "wh", warehouse_name: "Starter", state: "STOPPED", sql_available: false, message: "needs approval" },
    categories_summary: {},
    resource_counts_by_type: { cluster: 1, app: 3 },
    capabilities: [],
    limitations: [],
    ...over,
  }) as never;

test("one state: a stopped SQL warehouse never changes workspace connectivity", () => {
  const v = deriveConnectionView({ health: health(), loading: false, requestError: null });
  assert.strictEqual(v.state, "CONNECTED");
  assert.strictEqual(v.tone, "ok");
  assert.strictEqual(v.sqlWarehouse?.state, "STOPPED");
  assert.strictEqual(v.sqlWarehouse?.available, false);
  assert.strictEqual(toIndicatorStatus(v), "connected");
});

test("every surface gets identical output for identical input (same object semantics)", () => {
  const a = deriveConnectionView({ health: health(), loading: false, requestError: null });
  const b = deriveConnectionView({ health: health(), loading: false, requestError: null });
  assert.deepStrictEqual(a, b);
});

test("loading shows CHECKING only before the first response; errors are explicit", () => {
  assert.strictEqual(deriveConnectionView({ health: null, loading: true, requestError: null }).state, "CHECKING");
  const err = deriveConnectionView({ health: null, loading: false, requestError: "backend unreachable" });
  assert.strictEqual(err.state, "ERROR");
  assert.ok(err.reason?.includes("backend unreachable"));
  assert.strictEqual(deriveConnectionView({ health: null, loading: false, requestError: null, notConfigured: true }).state, "NOT_CONFIGURED");
});

test("permission / authentication failures map to explicit states", () => {
  assert.strictEqual(
    deriveConnectionView({ health: health({ connection_state: "ACCESS_DENIED", last_error: "PERMISSION_DENIED" }), loading: false, requestError: null }).state,
    "ACCESS_DENIED"
  );
  const auth = deriveConnectionView({ health: health({ connection_state: "AUTHENTICATION_REQUIRED" }), loading: false, requestError: null });
  assert.strictEqual(auth.state, "AUTHENTICATION_REQUIRED");
  assert.strictEqual(toIndicatorStatus(auth), "auth_failed");
});

test("legacy status maps when connection_state is absent", () => {
  assert.strictEqual(deriveConnectionView({ health: health({ connection_state: undefined, status: "ready_to_connect" }), loading: false, requestError: null }).state, "DISCONNECTED");
  assert.strictEqual(deriveConnectionView({ health: health({ connection_state: undefined, status: "auth_failed" }), loading: false, requestError: null }).state, "AUTHENTICATION_REQUIRED");
});

test("a failed refresh after success keeps the last state but marks it stale", () => {
  const v = deriveConnectionView({ health: health(), loading: false, requestError: "timeout" });
  assert.strictEqual(v.state, "CONNECTED");
  assert.strictEqual(v.stale, true);
  assert.strictEqual(deriveConnectionView({ health: health({ discovery_stale: true }), loading: false, requestError: null }).stale, true);
  assert.strictEqual(deriveConnectionView({ health: health(), loading: false, requestError: null }).stale, false);
});

test("environment comes from the workspace, never a free default", () => {
  assert.strictEqual(environmentLabel("development"), "Development");
  assert.strictEqual(environmentLabel("production"), "Production");
  assert.strictEqual(environmentLabel(null), "-");
  assert.strictEqual(deriveConnectionView({ health: health(), loading: false, requestError: null }).environment, "development");
});

test("inventory counts: '-' when unknown, real zero only when discovery succeeded", () => {
  assert.strictEqual(inventoryCount(null, "app"), null);
  assert.strictEqual(inventoryCount(health(), "app"), 3);
  assert.strictEqual(inventoryCount(health(), "pipeline"), 0);
  assert.strictEqual(
    inventoryCount(health({ status: "connection_error", last_discovery_at: null, last_verified_at: null }), "app"),
    null
  );
});

test("refresh controller is single-flight and tracks staleness", async () => {
  let t = 1_000;
  let calls = 0;
  let release: () => void = () => {};
  const gate = new Promise<void>((r) => { release = r; });
  const c = createRefreshController(
    async () => { calls++; await gate; },
    { staleAfterMs: 5_000, now: () => t }
  );
  const first = c.run();
  assert.strictEqual(await c.run(), false); // overlapping call skipped
  assert.strictEqual(c.status().inFlight, true);
  release();
  assert.strictEqual(await first, true);
  assert.strictEqual(calls, 1);
  assert.strictEqual(c.status().lastSuccessAt, 1_000);
  assert.strictEqual(c.status().stale, false);
  t = 20_000;
  assert.strictEqual(c.status().stale, true); // too old is stale, not "current"
});

test("failed refresh records the error, keeps last success, and recovers", async () => {
  let t = 100;
  let fail = false;
  const c = createRefreshController(async () => { if (fail) throw new Error("boom"); }, { staleAfterMs: 60_000, now: () => t });
  assert.strictEqual(await c.run(), true);
  fail = true;
  t = 200;
  assert.strictEqual(await c.run(), false);
  const s = c.status();
  assert.strictEqual(s.lastError, "boom");
  assert.strictEqual(s.lastSuccessAt, 100);
  assert.strictEqual(s.lastAttemptAt, 200);
  assert.strictEqual(s.stale, true);
  fail = false;
  t = 300;
  assert.strictEqual(await c.run(), true);
  assert.strictEqual(c.status().stale, false);
  assert.strictEqual(c.status().lastSuccessAt, 300);
});

test("formatUpdatedAt is deterministic UTC and '-' when unknown", () => {
  assert.strictEqual(formatUpdatedAt(null), "-");
  assert.strictEqual(formatUpdatedAt(Date.UTC(2026, 10, 13, 5, 0, 0)), "2026-11-13 05:00:00 UTC");
});

test("no component hardcodes a workspace, environment or mock connection", () => {
  const read = (f: string) => fs.readFileSync(path.resolve(__dirname, "../src", f), "utf-8");
  const finops = read("components/FinOpsCommandCenterView.tsx");
  assert.ok(!finops.includes('useState<string>("Production")'), "environment must come from the workspace");
  assert.ok(!finops.includes("Fallback local formula"));
  const connect = read("components/ConnectCloudView.tsx");
  for (const s of ["f718c261-ab85-49fd-907e-99c022cc2aeb", "98 Resources discovered", "verified offline mode"]) {
    assert.ok(!connect.includes(s), `ConnectCloudView still contains fabricated data: ${s}`);
  }
  const config = read("components/ConfigurationView.tsx");
  for (const s of ["adb-lakehouse-eastus", "Fabric FinOps Lakehouse Analytics", "rg-finops-eastus"]) {
    assert.ok(!config.includes(s), `ConfigurationView still contains fabricated data: ${s}`);
  }
  const page = read("app/page.tsx");
  assert.ok(!page.includes('environment: "Production"'));
  assert.ok(!page.includes("source_availability"));
});
