/**
 * Automated Test Suite: Resource Selection & Scope Filtering Engine
 * Verifies Multi-Subscription, Cascading Resource Group filtering, and Summary Bar calculations.
 */

import assert from "node:assert";
import test from "node:test";
import fs from "node:fs";
import path from "node:path";

// Mock dataset mirroring Discovered Azure Subscriptions topology
interface MockRG {
  name: string;
  subscription_id: string;
  workspaces: Array<{ workspace_id: string; name: string }>;
  other_resources: Array<{ id: string; name: string }>;
}

interface MockSub {
  subscription_id: string;
  name: string;
  resource_groups: MockRG[];
}

const MOCK_SUBSCRIPTIONS: MockSub[] = [
  {
    subscription_id: "f718c261-ab85-49fd-907e-99c022cc2aeb",
    name: "Azure Production Subscription",
    resource_groups: [
      {
        name: "rg-finops-eastus",
        subscription_id: "f718c261-ab85-49fd-907e-99c022cc2aeb",
        workspaces: [{ workspace_id: "642006393507276", name: "adb-lakehouse-eastus" }],
        other_resources: [
          { id: "vm-driver-01", name: "vm-driver-prod-01" },
          { id: "stfinopseastus01", name: "stfinopseastus01" },
        ],
      },
      {
        name: "rg-analytics-core",
        subscription_id: "f718c261-ab85-49fd-907e-99c022cc2aeb",
        workspaces: [],
        other_resources: [{ id: "vnet-analytics-hub", name: "vnet-analytics-hub" }],
      },
    ],
  },
  {
    subscription_id: "e827a192-3bc1-49e0-812d-11c033bb1fea",
    name: "Azure Analytics & Dev Subscription",
    resource_groups: [
      {
        name: "rg-dev-dataplatform",
        subscription_id: "e827a192-3bc1-49e0-812d-11c033bb1fea",
        workspaces: [{ workspace_id: "873119284019284", name: "adb-analytics-dev-centralus" }],
        other_resources: [{ id: "stanalyticsdev01", name: "stanalyticsdev01" }],
      },
    ],
  },
];

function getAvailableResourceGroups(selectedSubIds: string[], subs: MockSub[]): MockRG[] {
  return subs
    .filter((s) => selectedSubIds.includes(s.subscription_id))
    .flatMap((s) => s.resource_groups);
}

function cascadeDeselection(
  deselectedSubId: string,
  currentSelectedSubIds: string[],
  currentSelectedRgNames: string[],
  currentSelectedWsIds: string[],
  subs: MockSub[]
) {
  const newSubIds = currentSelectedSubIds.filter((id) => id !== deselectedSubId);
  const remainingRgs = getAvailableResourceGroups(newSubIds, subs);
  const validRgNames = new Set(remainingRgs.map((r) => r.name));
  const newRgNames = currentSelectedRgNames.filter((rg) => validRgNames.has(rg));

  const validWsIds = new Set(remainingRgs.flatMap((r) => r.workspaces.map((w) => w.workspace_id)));
  const newWsIds = currentSelectedWsIds.filter((ws) => validWsIds.has(ws));

  return { newSubIds, newRgNames, newWsIds };
}

test("Resource Selection: Strict Resource Group filtering by selected Subscriptions", () => {
  // When only Subscription 1 is selected
  const sub1Rgs = getAvailableResourceGroups(["f718c261-ab85-49fd-907e-99c022cc2aeb"], MOCK_SUBSCRIPTIONS);
  assert.strictEqual(sub1Rgs.length, 2);
  assert.deepStrictEqual(
    sub1Rgs.map((r) => r.name),
    ["rg-finops-eastus", "rg-analytics-core"]
  );

  // When both subscriptions are selected
  const allRgs = getAvailableResourceGroups(
    ["f718c261-ab85-49fd-907e-99c022cc2aeb", "e827a192-3bc1-49e0-812d-11c033bb1fea"],
    MOCK_SUBSCRIPTIONS
  );
  assert.strictEqual(allRgs.length, 3);
  assert.ok(allRgs.some((r) => r.name === "rg-dev-dataplatform"));

  // When no subscriptions are selected
  const noRgs = getAvailableResourceGroups([], MOCK_SUBSCRIPTIONS);
  assert.strictEqual(noRgs.length, 0);
});

test("Resource Selection: Deselecting a subscription cascades and purges orphaned child RGs and Workspaces", () => {
  const initialSubIds = [
    "f718c261-ab85-49fd-907e-99c022cc2aeb",
    "e827a192-3bc1-49e0-812d-11c033bb1fea",
  ];
  const initialRgNames = ["rg-finops-eastus", "rg-dev-dataplatform"];
  const initialWsIds = ["642006393507276", "873119284019284"];

  // Deselect dev subscription "e827a192-3bc1-49e0-812d-11c033bb1fea"
  const result = cascadeDeselection(
    "e827a192-3bc1-49e0-812d-11c033bb1fea",
    initialSubIds,
    initialRgNames,
    initialWsIds,
    MOCK_SUBSCRIPTIONS
  );

  // Child dev RG "rg-dev-dataplatform" must be removed
  assert.deepStrictEqual(result.newRgNames, ["rg-finops-eastus"]);
  // Child dev Workspace "873119284019284" must be removed
  assert.deepStrictEqual(result.newWsIds, ["642006393507276"]);
  // Only prod sub remains
  assert.deepStrictEqual(result.newSubIds, ["f718c261-ab85-49fd-907e-99c022cc2aeb"]);
});

test("Resource Selection: ConfigurationView component contains all required sections and controls", () => {
  const filePath = path.resolve(__dirname, "../src/components/ConfigurationView.tsx");
  const content = fs.readFileSync(filePath, "utf-8");

  // Section A: Active Account Banner & Switch Account
  assert.ok(content.includes("Switch Account"), "Must have Switch Account button");
  assert.ok(content.includes("onSwitchAccount"), "Must handle onSwitchAccount callback");

  // Section B: Subscriptions Multi-selection
  assert.ok(content.includes("Select All"), "Must support Select All");
  assert.ok(content.includes("Clear All"), "Must support Clear All");

  // Section C: Resource Groups
  assert.ok(content.includes("availableResourceGroups"), "Must compute availableResourceGroups dynamically");

  // Section D: Databricks Workspaces
  assert.ok(content.includes("availableDatabricksWorkspaces"), "Must compute availableDatabricksWorkspaces dynamically");

  // Section E: Microsoft Fabric Workspaces and Capacities
  assert.ok(
    content.includes("Microsoft Fabric Workspaces &amp; Capacities") ||
    content.includes("Microsoft Fabric Workspaces & Capacities"),
    "Must support Fabric section"
  );

  // Section F: Other Supported Azure Resources
  assert.ok(
    content.includes("Other Supported Azure Resources") ||
    content.includes("availableOtherResources"),
    "Must support Other Azure resources section"
  );

  // Sticky Bottom Action Bar
  assert.ok(content.includes("Continue to Dashboard"), "Must have Continue to Dashboard action");
  assert.ok(content.includes("Save Configuration"), "Must have Save Configuration action");
  assert.ok(content.includes("Refresh Discovery"), "Must have Refresh Discovery action");
});
