import test from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";

test("AI Panel Visibility: Exactly 1 mount of FinOpsAiAnalysisSection in FinOpsCommandCenterView.tsx", () => {
  const finopsViewPath = path.resolve(__dirname, "../src/components/FinOpsCommandCenterView.tsx");
  const content = fs.readFileSync(finopsViewPath, "utf-8");

  const matches = content.match(/<FinOpsAiAnalysisSection/g);
  assert.ok(matches, "FinOpsAiAnalysisSection must be rendered");
  assert.strictEqual(
    matches.length,
    1,
    `FinOpsAiAnalysisSection must appear exactly once across FinOpsCommandCenterView.tsx, but found ${matches.length}`
  );
});

test("AI Panel Visibility: FinOpsAiAnalysisSection is mounted exclusively on Executive Overview", () => {
  const finopsViewPath = path.resolve(__dirname, "../src/components/FinOpsCommandCenterView.tsx");
  const content = fs.readFileSync(finopsViewPath, "utf-8");

  // Locate the index of FinOpsAiAnalysisSection mount
  const mountIndex = content.indexOf("<FinOpsAiAnalysisSection");
  assert.ok(mountIndex !== -1, "Mount must exist");

  // The preceding module boundary must be activeModule === 'overview'
  const precedingText = content.slice(0, mountIndex);
  const allMatches = Array.from(precedingText.matchAll(/activeModule === ["']([^"']+)["']/g));
  const lastActiveModuleMatch = allMatches.pop();

  assert.ok(lastActiveModuleMatch, "Must be inside an activeModule condition");
  assert.strictEqual(
    lastActiveModuleMatch[1],
    "overview",
    `FinOpsAiAnalysisSection must be inside activeModule === 'overview', but was inside ${lastActiveModuleMatch[1]}`
  );
});

test("AI Panel Visibility: Panel is absent on all non-overview FinOps modules", () => {
  const finopsViewPath = path.resolve(__dirname, "../src/components/FinOpsCommandCenterView.tsx");
  const content = fs.readFileSync(finopsViewPath, "utf-8");

  const nonOverviewModules = [
    "cost",
    "allocation",
    "compute",
    "ai",
    "recommend",
    "forecast",
    "anomaly",
    "settings",
    "data",
    "network",
    "governance",
    "chargeback",
    "workloads",
    "reports",
  ];

  for (const mod of nonOverviewModules) {
    const modHeaderPattern = new RegExp(`activeModule === ["']${mod}["'][\\s\\S]*?(?:activeModule ===|\\n\\s*\\)\\s*\\}\\s*<\\/main>)`);
    const match = content.match(modHeaderPattern);
    if (match) {
      assert.ok(
        !match[0].includes("<FinOpsAiAnalysisSection"),
        `FinOpsAiAnalysisSection must NOT appear inside activeModule === '${mod}'`
      );
    }
  }
});

test("AI Panel Visibility: Panel is absent across all 11 Workspace & Operations modules", () => {
  const opsViewPath = path.resolve(__dirname, "../src/components/DatabricksWorkspaceDetailView.tsx");
  const content = fs.readFileSync(opsViewPath, "utf-8");

  assert.ok(
    !content.includes("<FinOpsAiAnalysisSection"),
    "DatabricksWorkspaceDetailView.tsx must contain 0 occurrences of FinOpsAiAnalysisSection"
  );
});

test("AI Panel Visibility: Executive Overview preserves decision actions, evidence modal, and navigation", () => {
  const finopsViewPath = path.resolve(__dirname, "../src/components/FinOpsCommandCenterView.tsx");
  const content = fs.readFileSync(finopsViewPath, "utf-8");

  // Verify the Executive Overview mount retains props
  assert.ok(
    content.includes('moduleId="overview"'),
    "FinOpsAiAnalysisSection must pass moduleId='overview'"
  );
  assert.ok(
    content.includes("onDecisionAction={handleDecisionAction}"),
    "FinOpsAiAnalysisSection must wire onDecisionAction"
  );
  assert.ok(
    content.includes("onViewEvidence="),
    "FinOpsAiAnalysisSection must wire onViewEvidence"
  );
  assert.ok(
    content.includes("decisions="),
    "FinOpsAiAnalysisSection must pass decisions"
  );
});
