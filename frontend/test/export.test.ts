/**
 * Automated Test Suite: Compliant Binary PDF & RFC 4180 CSV Export
 * Verifies Milestone 3J.5 / Part E Remediation.
 */

import assert from "node:assert";
import test from "node:test";
import { generatePdfDocument, FinOpsReportData } from "../src/lib/pdfGenerator";
import {
  generateCsvString,
  escapeCsvCell,
  CsvColumn,
} from "../src/lib/csvGenerator";

test("PDF Export: generatePdfDocument generates spec-compliant %PDF-1.4 binary", () => {
  const reportData: FinOpsReportData = {
    title: "Bizmetric FinOps Command Center Report",
    reportType: "Executive Cost Snapshot",
    scopeId: "adb-642006393507276",
    generatedAt: "Nov 8, 2026 12:41 UTC",
    currency: "USD",
    kpis: [
      { label: "Total Net Spend", value: "$176,840" },
      { label: "Total DBU Consumed", value: "88,420 DBU" },
      { label: "Identified Inactive Warehouses", value: "1 Stopped" },
    ],
    summaryRows: [
      ["Target Cloud Scope", "adb-642006393507276"],
      ["Compliance Audit", "ISO 27001 & SOC-2 Type II Read-Only Telemetry"],
    ],
  };

  const pdfBytes = generatePdfDocument(reportData);
  assert.ok(pdfBytes instanceof Uint8Array, "Must return Uint8Array binary");
  assert.ok(pdfBytes.length > 500, "PDF must have non-trivial size");

  // Convert to string for structural spec checks
  const pdfString = Buffer.from(pdfBytes).toString("latin1");

  // 1. Header check: starts with %PDF-1.4
  assert.ok(pdfString.startsWith("%PDF-1.4\n"), "Must start with %PDF-1.4 header");

  // 2. Binary marker comment check (PDF spec recommendation)
  assert.ok(pdfString.includes("%\xE2\xE3\xCF\xD3\n"), "Must include binary comment marker");

  // 3. Structural objects check
  assert.ok(pdfString.includes("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>"), "Must have /Catalog");
  assert.ok(pdfString.includes("2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>"), "Must have /Pages");
  assert.ok(pdfString.includes("/Type /Page /Parent 2 0 R"), "Must have /Page");
  assert.ok(pdfString.includes("stream\n"), "Must have content stream");
  assert.ok(pdfString.includes("endstream\n"), "Must have endstream");

  // 4. Content verification
  assert.ok(pdfString.includes("BIZMETRIC FINOPS COMMAND CENTER REPORT"), "Must embed report title");
  assert.ok(pdfString.includes("adb-642006393507276"), "Must embed scope ID");
  assert.ok(pdfString.includes("Total Net Spend"), "Must embed KPI labels");

  // 5. Cross-reference table & trailer check
  assert.ok(pdfString.includes("xref\n0 7\n"), "Must contain xref table with 7 objects");
  assert.ok(pdfString.includes("trailer\n<< /Size 7 /Root 1 0 R >>"), "Must contain trailer pointing to Root 1 0 R");
  assert.ok(pdfString.includes("startxref\n"), "Must contain startxref pointer");
  assert.ok(pdfString.endsWith("%%EOF\n"), "Must terminate with %%EOF marker");
});

test("CSV Export: escapeCsvCell complies with RFC 4180 rules", () => {
  // Plain string needs no quotes
  assert.strictEqual(escapeCsvCell("AzureDatabricks"), "AzureDatabricks");

  // String with comma must be wrapped in quotes
  assert.strictEqual(escapeCsvCell("Compute, Storage"), '"Compute, Storage"');

  // String with quotes must be escaped with double quotes
  assert.strictEqual(escapeCsvCell('Serverless "Starter" Warehouse'), '"Serverless ""Starter"" Warehouse"');

  // String with newline must be wrapped in quotes
  assert.strictEqual(escapeCsvCell("Line 1\nLine 2"), '"Line 1\nLine 2"');

  // Numbers and nulls
  assert.strictEqual(escapeCsvCell(1234.56), "1234.56");
  assert.strictEqual(escapeCsvCell(null), "");
  assert.strictEqual(escapeCsvCell(undefined), "");
});

test("CSV Export: generateCsvString formats rows with headers and comments", () => {
  interface BillingItem {
    sku: string;
    quantity: number;
    amount: number;
  }

  const items: BillingItem[] = [
    { sku: "Standard_D4ds_v5", quantity: 120, amount: 240.5 },
    { sku: "Premium Storage, LRS", quantity: 500, amount: 75.0 },
  ];

  const columns: CsvColumn<BillingItem>[] = [
    { header: "SKU Name", accessor: (r) => r.sku },
    { header: "Quantity", accessor: (r) => r.quantity },
    { header: "Amount ($)", accessor: (r) => r.amount },
  ];

  const metadata = [
    "Scope: adb-642006393507276",
    "Generated: Nov 8, 2026 12:41 UTC",
  ];

  const csv = generateCsvString(items, columns, metadata);

  assert.ok(csv.includes("# Scope: adb-642006393507276\r\n"), "Must include metadata comment");
  assert.ok(csv.includes("SKU Name,Quantity,Amount ($)\r\n"), "Must include CSV header");
  assert.ok(csv.includes("Standard_D4ds_v5,120,240.5\r\n"), "Must include unquoted row");
  assert.ok(csv.includes('"Premium Storage, LRS",500,75'), "Must include properly quoted row with comma");
});
