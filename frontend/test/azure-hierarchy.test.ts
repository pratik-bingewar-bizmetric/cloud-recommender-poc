/**
 * Automated Test Suite: Cloud Connection & Azure Account Hierarchy
 * Verifies Top-Level Provider Classification and Service Integration Hierarchy.
 */

import assert from "node:assert";
import test from "node:test";
import fs from "node:fs";
import path from "node:path";
import { CloudConnection } from "../src/types";

test("Azure Hierarchy: ConnectCloudView filter tabs are limited to All, Azure, and Google Cloud", () => {
  const filePath = path.resolve(__dirname, "../src/components/ConnectCloudView.tsx");
  const content = fs.readFileSync(filePath, "utf-8");

  // Tabs must only include All Connections, Microsoft Azure, Google Cloud
  assert.ok(content.includes('label: "All Connections"'), "Must contain All Connections tab");
  assert.ok(content.includes('label: "Microsoft Azure"'), "Must contain Microsoft Azure tab");
  assert.ok(content.includes('label: "Google Cloud"'), "Must contain Google Cloud tab");

  // Standalone Databricks and Fabric tabs must NOT exist in the provider tabs
  assert.ok(
    !content.includes('{ id: "databricks", label: "Databricks" }'),
    "Databricks must NOT be a top-level provider tab"
  );
  assert.ok(
    !content.includes('{ id: "fabric", label: "Microsoft Fabric" }'),
    "Fabric must NOT be a top-level provider tab"
  );
});

test("Azure Hierarchy: Azure Account cards contain nested Service Integrations", () => {
  const filePath = path.resolve(__dirname, "../src/components/ConnectCloudView.tsx");
  const content = fs.readFileSync(filePath, "utf-8");

  // Service integrations are rendered from backend data; none are seeded client-side
  assert.ok(
    content.includes("service_integrations"),
    "Account cards must render nested service integrations from the backend response"
  );
  assert.ok(
    !content.includes("SEED_CONNECTIONS") && !content.includes("offline cache credentials"),
    "ConnectCloudView must not ship seeded accounts or fabricate offline validation success"
  );
});

test("Azure Hierarchy: Account cards expose copy-to-clipboard for Subscription ID", () => {
  const filePath = path.resolve(__dirname, "../src/components/ConnectCloudView.tsx");
  const content = fs.readFileSync(filePath, "utf-8");

  assert.ok(
    content.includes("copyToClipboard"),
    "ConnectCloudView must provide copy-to-clipboard functionality"
  );
  assert.ok(
    content.includes("Copy Subscription ID"),
    "ConnectCloudView must have 'Copy Subscription ID' accessible title"
  );
});

test("Azure Hierarchy: Selecting an account navigates directly to Configuration view", () => {
  const pagePath = path.resolve(__dirname, "../src/app/page.tsx");
  const content = fs.readFileSync(pagePath, "utf-8");

  // Verify onConnectionSelected sets activeView to "configuration"
  assert.ok(
    content.includes('setActiveView("configuration")'),
    "page.tsx must transition to 'configuration' view when account is selected"
  );
  // Verify provider is set to "azure"
  assert.ok(
    content.includes('provider: "azure"'),
    "page.tsx must set active provider to azure upon selecting Azure account"
  );
});

test("Azure Hierarchy: Google Cloud is preserved as an independent top-level provider", () => {
  const filePath = path.resolve(__dirname, "../src/components/ConnectCloudView.tsx");
  const content = fs.readFileSync(filePath, "utf-8");

  assert.ok(
    content.includes('"gcp"'),
    "ConnectCloudView must keep Google Cloud as an independent provider filter"
  );
  assert.ok(
    content.includes("organizations/") || content.includes("Organization ID:"),
    "ConnectCloudView must model Google Cloud organization/projects"
  );
});
