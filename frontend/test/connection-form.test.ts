import test from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { describeConnectionError } from "../src/lib/authErrors";

const err = (status: number, detail: Record<string, unknown>, message = "") => ({ status, detail, message });
const view = fs.readFileSync(path.resolve(__dirname, "../src/components/ConnectCloudView.tsx"), "utf8");
const api = fs.readFileSync(path.resolve(__dirname, "../src/lib/api.ts"), "utf8");

test("application sign-in failures are kept apart from cloud account failures", () => {
  assert.strictEqual(describeConnectionError(err(401, { message: "Authentication is required." })).kind, "application_auth");
  assert.strictEqual(describeConnectionError(err(403, { message: "requires FinOpsAdmin" })).kind, "application_permission");
  const cloud = describeConnectionError(err(400, { error_code: "INVALID_AZURE_CREDENTIALS", message: "The client secret is incorrect." }));
  assert.strictEqual(cloud.kind, "cloud_auth");
  assert.match(cloud.message, /client secret is incorrect/);
});

test("permission problems on the cloud account are shown separately and name the role", () => {
  const v = describeConnectionError(
    err(400, { error_code: "SUBSCRIPTION_NOT_ACCESSIBLE", message: "Cannot access the subscription.", required_permission: "Reader" }),
  );
  assert.strictEqual(v.kind, "cloud_permission");
  assert.match(v.message, /Required role: Reader/);
  assert.strictEqual(describeConnectionError(err(400, { error_code: "WRITE_PERMISSIONS_DETECTED", message: "write" })).kind, "cloud_permission");
});

test("validation, conflict and service errors", () => {
  const missing = describeConnectionError(err(422, { error_code: "MISSING_REQUIRED_FIELDS", message: "required", fields: ["azure_client_id"] }));
  assert.strictEqual(missing.kind, "validation");
  assert.deepStrictEqual(missing.fields, ["azure_client_id"]);
  assert.strictEqual(describeConnectionError(err(409, { error_code: "DUPLICATE_CONNECTION", message: "dup" })).kind, "conflict");
  const db = describeConnectionError(err(503, { error_code: "DATABASE_UNAVAILABLE", message: "Nothing was saved." }));
  assert.strictEqual(db.kind, "service");
  assert.match(db.title, /503/);
  assert.strictEqual(describeConnectionError(new Error("boom")).kind, "service");
});

test("the Add Connection form sends the credentials the backend requires (root cause of the HTTP 400)", () => {
  assert.match(view, /azure_client_id: newClientId\.trim\(\)/);
  assert.match(view, /azure_client_secret: newClientSecret/);
  assert.match(view, /auth_method: newAuthMethod/);
  assert.match(view, /type="password"/);
  assert.match(view, /<option value="service_principal">/);
});

test("secrets are cleared after submission, non-secret fields are kept after a failure", () => {
  assert.match(view, /setNewClientSecret\(""\);\s*\/\/ clear the secret immediately/);
  const catchBlock = view.slice(view.indexOf("// Keep every non-secret field"));
  assert.match(catchBlock.slice(0, 400), /setNewClientSecret\(""\)/);
  assert.doesNotMatch(catchBlock.slice(0, 400), /setNewConnName\(""\)|setNewTenantId\(""\)|setNewScopeId\(""\)/);
});

test("the secret is never persisted in browser storage by the form or the API client", () => {
  for (const source of [view, api]) {
    assert.doesNotMatch(source, /(local|session)Storage/);
  }
});

test("auth errors are displayed instead of failing silently", () => {
  assert.match(view, /data-testid="connection-form-error"/);
  assert.match(view, /describeConnectionError\(err\)/);
  assert.doesNotMatch(view, /if \(!newConnName\.trim\(\) \|\| !newScopeId\.trim\(\)\) return;/);
});

test("owned connections are deleted and edited on the server, not only in local state", () => {
  assert.match(view, /await deleteConnection\(target\.id\)/);
  assert.match(view, /await updateConnection\(editModalConnection\.id/);
  assert.match(api, /method: "PATCH"/);
  assert.match(api, /method: "DELETE"/);
});
