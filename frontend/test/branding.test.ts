/**
 * Automated Test Suite: Branding & Visual Identity
 * Verifies Cloud Connection Management & Header Redesign.
 */

import assert from "node:assert";
import test from "node:test";
import fs from "node:fs";
import path from "node:path";

test("Branding: Official Bizmetric logo asset exists in public directory", () => {
  const logoPath = path.resolve(__dirname, "../public/bizmetric-logo.png");
  assert.strictEqual(fs.existsSync(logoPath), true, "bizmetric-logo.png must exist in frontend/public");
  const stats = fs.statSync(logoPath);
  assert.ok(stats.size > 1000, "Bizmetric logo must be a valid non-empty image file");
});

test("Branding: Onboarding header in page.tsx displays official title and logo", () => {
  const pagePath = path.resolve(__dirname, "../src/app/page.tsx");
  const content = fs.readFileSync(pagePath, "utf-8");

  // Verify Bizmetric Logo is loaded with Next.js Image
  assert.ok(
    content.includes('src="/bizmetric-logo.png"'),
    "page.tsx must reference /bizmetric-logo.png"
  );
  assert.ok(
    content.includes('alt="Bizmetric Logo"'),
    "page.tsx must include accessible alt text for Bizmetric Logo"
  );

  // Verify platform title
  assert.ok(
    content.includes("FinOps &amp; Infrastructure Intelligence Platform") ||
    content.includes("FinOps & Infrastructure Intelligence Platform"),
    "page.tsx must display the exact platform title"
  );

  // Verify subtitle
  assert.ok(
    content.includes("Connect your cloud account to begin."),
    "page.tsx must display 'Connect your cloud account to begin.'"
  );

  // Verify Strictly Read-Only policy badge
  assert.ok(
    content.includes("Strictly Read-Only") && content.includes("Zero-Execution Policy"),
    "page.tsx must display the strictly read-only badge"
  );
});

test("Branding: Zero 'POC' badge text in Sidebar and Onboarding headers", () => {
  const sidebarPath = path.resolve(__dirname, "../src/components/Sidebar.tsx");
  const sidebarContent = fs.readFileSync(sidebarPath, "utf-8");

  // In Sidebar logo header, POC badge must be removed
  assert.ok(
    !sidebarContent.includes('>POC</span>'),
    "Sidebar.tsx must not contain a '>POC</span>' badge"
  );

  const pagePath = path.resolve(__dirname, "../src/app/page.tsx");
  const pageContent = fs.readFileSync(pagePath, "utf-8");
  assert.ok(
    !pageContent.includes('>POC</span>'),
    "page.tsx onboarding header must not contain a '>POC</span>' badge"
  );
});

test("Branding: Read-Only and Zero-Execution guarantees are prominently stated", () => {
  const connectPath = path.resolve(__dirname, "../src/components/ConnectCloudView.tsx");
  const connectContent = fs.readFileSync(connectPath, "utf-8");

  assert.ok(
    connectContent.includes("Strictly Read-Only") && connectContent.includes("Zero-Execution Policy"),
    "ConnectCloudView must emphasize Strictly Read-Only policy"
  );
  assert.ok(
    connectContent.includes("Reader") && connectContent.includes("Cost Management Reader"),
    "ConnectCloudView must specify Reader permissions only"
  );
});
