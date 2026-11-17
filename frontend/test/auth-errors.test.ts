import test from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { describeAuthFailure } from "../src/lib/authErrors";

test("401 explains that the caller is not authenticated and how to fix local development", () => {
  const message = describeAuthFailure(401, "Authentication is required.");
  assert.ok(message);
  assert.match(message!, /Not authenticated \(HTTP 401\)/);
  assert.match(message!, /DEV_AUTH_ENABLED=true/);
  assert.match(message!, /FinOpsAdmin/);
});

test("401 does not repeat the hint when the backend already names DEV_AUTH_ENABLED", () => {
  const backend = "Authentication is required. Configure ENTRA_AUTH_ENABLED=true (or DEV_AUTH_ENABLED=true for local development only).";
  const message = describeAuthFailure(401, backend)!;
  assert.ok(message.includes(backend));
  assert.strictEqual(message.split("DEV_AUTH_ENABLED").length - 1, 1);
});

test("403 says authenticated but not authorized and includes the backend reason", () => {
  const message = describeAuthFailure(403, "This operation requires the application role ['FinOpsAdmin'].")!;
  assert.match(message, /Not authorized \(HTTP 403\)/);
  assert.match(message, /FinOpsAdmin/);
  assert.match(message, /signed in but lacks/);
});

test("other statuses are not rewritten", () => {
  for (const status of [200, 400, 404, 422, 500, 502]) {
    assert.strictEqual(describeAuthFailure(status, "x"), null);
  }
});

test("the API client uses the helper for failed responses", () => {
  const source = fs.readFileSync(path.resolve(__dirname, "../src/lib/api.ts"), "utf8");
  assert.match(source, /describeAuthFailure\(res\.status, detail\.message\)/);
  // no Authorization header is invented for local development: authentication stays server-side
  assert.doesNotMatch(source, /Authorization/);
});
