import test from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";

test("Unified Navigation: Standalone FinOps Application group is removed and unified under Databricks Workspace", () => {
  const sidebarPath = path.resolve(__dirname, "../src/components/Sidebar.tsx");
  const content = fs.readFileSync(sidebarPath, "utf-8");

  // Must contain main parent label 'Databricks Workspace'
  assert.ok(
    content.includes("Databricks Workspace"),
    "Sidebar.tsx must contain 'Databricks Workspace' as the main parent navigation label"
  );

  // Standalone 'FinOps Application' expandable parent button must be removed
  assert.ok(
    !content.includes('<span className="truncate">FinOps Application</span>'),
    "Sidebar.tsx must remove the standalone FinOps Application parent button"
  );

  // Connected workspace ID and status badge must be present in header area
  assert.ok(
    content.includes("Connected"),
    "Sidebar.tsx header area must display 'Connected' status badge"
  );
  assert.ok(
    content.includes("642006393507276"),
    "Sidebar.tsx header area must display connected workspace ID"
  );
});

test("Unified Navigation: Hierarchy contains two visually distinct section headings", () => {
  const sidebarPath = path.resolve(__dirname, "../src/components/Sidebar.tsx");
  const content = fs.readFileSync(sidebarPath, "utf-8");

  assert.ok(
    content.includes("WORKSPACE &amp; OPERATIONS") || content.includes("WORKSPACE & OPERATIONS"),
    "Sidebar.tsx must contain 'WORKSPACE & OPERATIONS' section heading"
  );
  assert.ok(
    content.includes("FINOPS &amp; COST INTELLIGENCE") || content.includes("FINOPS & COST INTELLIGENCE"),
    "Sidebar.tsx must contain 'FINOPS & COST INTELLIGENCE' section heading"
  );
});

test("Unified Navigation: Section A (Workspace & Operations) contains 11 modules in exact order", () => {
  const sidebarPath = path.resolve(__dirname, "../src/components/Sidebar.tsx");
  const content = fs.readFileSync(sidebarPath, "utf-8");

  const expectedOpsModules = [
    { id: "overview", label: "Overview" },
    { id: "clusters", label: "Clusters" },
    { id: "warehouses", label: "Warehouses" },
    { id: "jobs", label: "Jobs & Workflows" },
    { id: "pipelines", label: "Pipelines" },
    { id: "serving", label: "Model Serving" },
    { id: "catalog", label: "Unity Catalog" },
    { id: "apps", label: "Databricks Apps" },
    { id: "system_tables", label: "System Tables" },
    { id: "query_history", label: "Query History" },
    { id: "audit", label: "Audit & Governance" },
  ];

  let lastIndex = -1;
  for (const mod of expectedOpsModules) {
    const itemMatch = `id: "${mod.id}"`;
    const labelMatch = `label: "${mod.label}"`;
    const itemIdx = content.indexOf(itemMatch);
    const labelIdx = content.indexOf(labelMatch);

    assert.ok(itemIdx > 0, `Operations module ${mod.id} must be defined in Sidebar.tsx`);
    assert.ok(labelIdx > 0, `Operations module label ${mod.label} must be defined in Sidebar.tsx`);
    assert.ok(
      itemIdx > lastIndex,
      `Operations module ${mod.id} (${mod.label}) must appear in sequence after previous module`
    );
    lastIndex = itemIdx;
  }
});

test("Unified Navigation: Section B (FinOps & Cost Intelligence) contains 10 modules in exact order with Executive Overview", () => {
  const sidebarPath = path.resolve(__dirname, "../src/components/Sidebar.tsx");
  const content = fs.readFileSync(sidebarPath, "utf-8");

  const expectedFinOpsModules = [
    { id: "overview", label: "Executive Overview" },
    { id: "cost", label: "Cost Explorer" },
    { id: "allocation", label: "Cost Allocation" },
    { id: "chargeback", label: "Cost & Billing" },
    { id: "forecast", label: "Forecast & Budgets" },
    { id: "anomaly", label: "Anomaly Detection" },
    { id: "recommend", label: "Optimization Advisor" },
    { id: "ai", label: "AI Economics" },
    { id: "governance", label: "Governance & Policies" },
    { id: "reports", label: "Reports & Audit" },
  ];

  let lastIndex = -1;
  for (const mod of expectedFinOpsModules) {
    const itemMatch = `id: "${mod.id}"`;
    const labelMatch = `label: "${mod.label}"`;
    const itemIdx = content.indexOf(itemMatch, content.indexOf("finopsIntelligenceNav"));
    const labelIdx = content.indexOf(labelMatch, content.indexOf("finopsIntelligenceNav"));

    assert.ok(itemIdx > 0, `FinOps module ${mod.id} must be defined in Sidebar.tsx`);
    assert.ok(labelIdx > 0, `FinOps module label ${mod.label} must be defined in Sidebar.tsx`);
    assert.ok(
      itemIdx > lastIndex,
      `FinOps module ${mod.id} (${mod.label}) must appear in sequence after previous module`
    );
    lastIndex = itemIdx;
  }
});

test("Unified Navigation: Forecast & Budgets and Optimization Advisor icons are certified", () => {
  const sidebarPath = path.resolve(__dirname, "../src/components/Sidebar.tsx");
  const content = fs.readFileSync(sidebarPath, "utf-8");

  assert.ok(
    content.includes("ChartNoAxesCombined"),
    "Sidebar.tsx must import and use ChartNoAxesCombined for Forecast & Budgets"
  );
  assert.ok(
    content.includes("Lightbulb"),
    "Sidebar.tsx must import and use Lightbulb for Optimization Advisor"
  );

  const forecastMatch = content.match(
    /id:\s*"forecast",[\s\S]*?label:\s*"Forecast & Budgets",[\s\S]*?icon:\s*<ChartNoAxesCombined/
  );
  assert.ok(forecastMatch, "Forecast & Budgets must map id 'forecast' and ChartNoAxesCombined icon");

  const advisorMatch = content.match(
    /id:\s*"recommend",[\s\S]*?label:\s*"Optimization Advisor",[\s\S]*?icon:\s*<Lightbulb/
  );
  assert.ok(advisorMatch, "Optimization Advisor must map id 'recommend' and Lightbulb icon");
});

test("Unified View: FinOpsCommandCenterView implements Forecast & Budgets functionality", () => {
  const viewPath = path.resolve(__dirname, "../src/components/FinOpsCommandCenterView.tsx");
  const content = fs.readFileSync(viewPath, "utf-8");

  assert.ok(
    content.includes('activeModule === "forecast"'),
    "FinOpsCommandCenterView must implement activeModule === 'forecast'"
  );
  assert.ok(
    content.includes("Approved monthly budget"),
    "Forecast view must display Approved monthly budget"
  );
  assert.ok(
    content.includes("Forecast month-end"),
    "Forecast view must display Forecast month-end spend"
  );
  assert.ok(
    content.includes("Budget burn and forecast pace"),
    "Forecast view must display budget burn chart"
  );
  assert.ok(
    content.includes("Scenario simulator"),
    "Forecast view must display scenario simulator sliders"
  );
  assert.ok(
    content.includes("Scope Budget Controls & Threshold Tracking"),
    "Forecast view must display scope budget controls table"
  );
});

test("Unified View: FinOpsCommandCenterView implements Optimization Advisor functionality", () => {
  const viewPath = path.resolve(__dirname, "../src/components/FinOpsCommandCenterView.tsx");
  const content = fs.readFileSync(viewPath, "utf-8");

  assert.ok(
    content.includes('activeModule === "recommend"'),
    "FinOpsCommandCenterView must implement activeModule === 'recommend'"
  );
  assert.ok(
    content.includes("Potential monthly savings"),
    "Optimization Advisor must display Potential monthly savings"
  );
  assert.ok(
    content.includes("Quick wins"),
    "Optimization Advisor must display Quick wins"
  );
  assert.ok(
    content.includes("Awaiting approval"),
    "Optimization Advisor must display Awaiting approval"
  );
  assert.ok(
    content.includes("Verified realized savings"),
    "Optimization Advisor must display Verified realized savings"
  );
  assert.ok(
    content.includes("Approve for change"),
    "Optimization Advisor must provide decision actions"
  );
  assert.ok(
    content.includes("View evidence"),
    "Optimization Advisor must provide evidence viewing"
  );
});
