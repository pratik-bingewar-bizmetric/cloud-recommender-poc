import { describe, expect, it } from "vitest";
import {
  INR_EXCHANGE_RATE,
  formatFinancialCurrency,
  getAzureReferenceFinancials,
  getGcpReferenceFinancials,
  buildCanonicalFinancialSummary,
} from "../lib/financials";
import type { CostBreakdown, SubscriptionOrProjectAnalysis } from "../types";

describe("FinOps Financial Calculations and Invariants", () => {
  describe("formatFinancialCurrency", () => {
    it("formats USD currency with default 2 decimals and dollar prefix", () => {
      expect(formatFinancialCurrency(225.11, "USD")).toBe("$225.11");
      expect(formatFinancialCurrency(0, "USD")).toBe("$0.00");
      expect(formatFinancialCurrency(1234567.89, "USD")).toBe("$1,234,567.89");
    });

    it("formats USD with custom decimals", () => {
      expect(formatFinancialCurrency(225.11, "USD", 0)).toBe("$225");
      expect(formatFinancialCurrency(225.116, "USD", 3)).toBe("$225.116");
    });

    it("converts USD to INR using official fixed rate (83.15) with zero decimals", () => {
      expect(INR_EXCHANGE_RATE).toBe(83.15);
      // 225.11 * 83.15 = 18717.8965 -> rounded to 18,718
      const formatted = formatFinancialCurrency(225.11, "INR");
      expect(formatted).toBe("₹18,718");
      expect(formatFinancialCurrency(100, "INR")).toBe("₹8,315");
      expect(formatFinancialCurrency(0, "INR")).toBe("₹0");
    });

    it("handles negative amounts safely", () => {
      const formattedNegative = formatFinancialCurrency(-50, "USD");
      expect(formattedNegative).toContain("50.00");
    });
  });

  describe("getAzureReferenceFinancials benchmark", () => {
    const azure = getAzureReferenceFinancials("30d", "USD");

    it("satisfies the Category Spend Invariant (Total Spend = sum of categories)", () => {
      const categorySum = azure.categories.reduce(
        (sum, cat) => sum + cat.amount_usd,
        0
      );
      expect(categorySum).toBeCloseTo(azure.estimated_monthly_spend, 2);
      expect(azure.estimated_monthly_spend).toBe(225.11);
    });

    it("satisfies the Potential Savings Invariant (Total Savings = sum of findings)", () => {
      const findingsSum = azure.findings.reduce(
        (sum, f) => sum + f.potential_monthly_savings,
        0
      );
      expect(findingsSum).toBeCloseTo(azure.potential_monthly_savings, 2);
      expect(azure.potential_monthly_savings).toBe(118.27);
    });

    it("enforces Savings <= Spend invariant", () => {
      expect(azure.potential_monthly_savings).toBeLessThanOrEqual(
        azure.estimated_monthly_spend
      );
    });

    it("calculates Annual Savings as exactly 12x monthly potential savings", () => {
      const expectedAnnual = Number(
        (azure.potential_monthly_savings * 12).toFixed(2)
      );
      expect(azure.projected_annual_savings).toBe(expectedAnnual);
      expect(azure.projected_annual_savings).toBe(1419.24);
    });

    it("computes savings percentage of total spend accurately", () => {
      const expectedPct = Number(
        (
          (azure.potential_monthly_savings / azure.estimated_monthly_spend) *
          100
        ).toFixed(1)
      );
      expect(azure.savings_percentage_of_spend).toBe(expectedPct);
      expect(azure.savings_percentage_of_spend).toBe(52.5);
    });

    it("contains expected categories and findings structure", () => {
      expect(azure.categories.length).toBe(5);
      expect(azure.findings.length).toBe(5);
      expect(azure.provider).toBe("azure");
      expect(azure.data_provenance).toBe("verified_pricing_catalog");
      expect(azure.pricing_source).toBe("Azure Retail Prices API (Public Tier)");
    });

    it("reflects currency parameter when INR requested", () => {
      const azureInr = getAzureReferenceFinancials("30d", "INR");
      expect(azureInr.currency).toBe("INR");
      expect(azureInr.exchange_rate).toBe(83.15);
    });
  });

  describe("getGcpReferenceFinancials benchmark", () => {
    const gcp = getGcpReferenceFinancials("30d", "USD");

    it("satisfies Category Spend Invariant for GCP", () => {
      const categorySum = gcp.categories.reduce(
        (sum, cat) => sum + cat.amount_usd,
        0
      );
      expect(categorySum).toBeCloseTo(gcp.estimated_monthly_spend, 2);
      expect(gcp.estimated_monthly_spend).toBe(280.87);
    });

    it("satisfies Potential Savings Invariant for GCP", () => {
      const findingsSum = gcp.findings.reduce(
        (sum, f) => sum + f.potential_monthly_savings,
        0
      );
      expect(findingsSum).toBeCloseTo(gcp.potential_monthly_savings, 2);
      expect(gcp.potential_monthly_savings).toBe(84.27);
    });

    it("calculates Annual Savings as 12x monthly savings for GCP", () => {
      expect(gcp.projected_annual_savings).toBe(
        Number((84.27 * 12).toFixed(2))
      );
      expect(gcp.projected_annual_savings).toBe(1011.24);
    });

    it("computes savings percentage correctly for GCP", () => {
      const expectedPct = Number(((84.27 / 280.87) * 100).toFixed(1));
      expect(gcp.savings_percentage_of_spend).toBe(expectedPct);
      expect(gcp.savings_percentage_of_spend).toBe(30.0);
    });
  });

  describe("buildCanonicalFinancialSummary dynamic reconciliation", () => {
    it("falls back to Azure benchmark when no live data or greenfield cost provided", () => {
      const summary = buildCanonicalFinancialSummary(
        "azure",
        "sub-test",
        "Test Azure Sub"
      );
      expect(summary.provider).toBe("azure");
      expect(summary.estimated_monthly_spend).toBe(225.11);
      expect(summary.potential_monthly_savings).toBe(118.27);
    });

    it("falls back to GCP benchmark when provider is gcp", () => {
      const summary = buildCanonicalFinancialSummary(
        "gcp",
        "proj-test",
        "Test GCP Project"
      );
      expect(summary.provider).toBe("gcp");
      expect(summary.estimated_monthly_spend).toBe(280.87);
      expect(summary.potential_monthly_savings).toBe(84.27);
    });

    it("faithfully maps live subscription analysis data and scales categories", () => {
      const mockAnalysis: SubscriptionOrProjectAnalysis = {
        scope_id: "sub-live-1",
        scope_name: "Live Subscription",
        scope_type: "azure_subscription",
        provider: "azure",
        analyzed_at: new Date().toISOString(),
        assumptions: [],
        access_limitations: [],
        hierarchy_nodes: [],
        data_source: "mock_fixture",
        spend_label: "estimated_public_list_pricing",
        resource_count: 1,
        group_count: 1,
        groups: [],
        resources: [],
        pricing_provenance: [],
        architecture_mermaid: "",
        recommendations: [],
        cost_breakdown: {
          compute: "100.00",
          database: "50.00",
          storage: "30.00",
          networking: "10.00",
          ai: "10.00",
          other: "0.00",
          subtotal: "200.00",
          verified_subtotal: "200.00",
          safety_buffer_amount: "0.00",
          total_monthly: "200.00",
          total_five_month: "1000.00",
          total_annual: "2400.00",
          is_complete: true,
          estimate_status: "complete",
        },
        total_potential_monthly_savings: "40.00",
        waste_findings: [
          {
            id: "wf-1",
            provider: "azure",
            scope_id: "sub-live-1",
            native_resource_type: "Microsoft.Compute/virtualMachines",
            spend_basis: "catalog_estimate",
            resource_id: "res-1",
            resource_name: "vm-idle",
            category: "idle_compute",
            severity: "high",
            title: "Idle VM",
            description: "VM has 1% CPU utilization",
            evidence: "1% CPU",
            current_monthly_spend: "50.00",
            potential_monthly_savings: "40.00",
            confidence: "high",
            group_name: "rg-prod",
            remediation_recommendation: "Stop VM",
            pre_remediation_considerations: ["Check build agent"],
          },
        ],
        technical_debt_items: [],
      };

      const summary = buildCanonicalFinancialSummary(
        "azure",
        "sub-live-1",
        "Live Subscription",
        "30d",
        "USD",
        null,
        mockAnalysis
      );

      expect(summary.estimated_monthly_spend).toBe(200.0);
      expect(summary.potential_monthly_savings).toBe(40.0);
      expect(summary.projected_annual_savings).toBe(480.0);
      expect(summary.savings_percentage_of_spend).toBe(20.0);
      expect(summary.findings_count).toBe(1);
      expect(summary.findings[0].id).toBe("wf-1");
      expect(summary.findings[0].category).toBe("Idle Compute");
    });

    it("reconciles greenfield architecture proposed cost breakdown", () => {
      const mockGreenfieldCost: CostBreakdown = {
        compute: "200.00",
        database: "150.00",
        storage: "50.00",
        ai: "100.00",
        networking: "30.00",
        other: "20.00",
        subtotal: "550.00",
        verified_subtotal: "550.00",
        safety_buffer_amount: "82.50",
        total_monthly: "632.50",
        total_five_month: "3162.50",
        total_annual: "7590.00",
        is_complete: true,
        estimate_status: "complete",
        unpriced_component_count: 0,
      };

      const summary = buildCanonicalFinancialSummary(
        "azure",
        "greenfield-scope",
        "AI Proposed Architecture",
        "30d",
        "USD",
        null,
        null,
        mockGreenfieldCost
      );

      expect(summary.estimated_monthly_spend).toBe(632.5);
      // 18% rightsizing savings on rawSpend (632.50 * 0.18 = 113.85)
      expect(summary.potential_monthly_savings).toBe(113.85);
      expect(summary.projected_annual_savings).toBe(
        Number((113.85 * 12).toFixed(2))
      );
      expect(summary.savings_percentage_of_spend).toBe(18.0);
      expect(summary.findings.length).toBe(2);
      expect(summary.findings[0].title).toContain("Autoscale");
      expect(summary.findings[1].title).toContain("Blob Inactivity");
    });

    it("handles zero spend without divide-by-zero or NaN in savings percentage", () => {
      const zeroCost: CostBreakdown = {
        compute: "0.00",
        database: "0.00",
        storage: "0.00",
        ai: "0.00",
        networking: "0.00",
        other: "0.00",
        subtotal: "0.00",
        safety_buffer_amount: "0.00",
        total_monthly: "0.00",
        total_five_month: "0.00",
        total_annual: "0.00",
        is_complete: true,
      };

      const summary = buildCanonicalFinancialSummary(
        "azure",
        "zero-scope",
        "Zero Scope",
        "30d",
        "USD",
        null,
        null,
        zeroCost
      );

      expect(summary.estimated_monthly_spend).toBe(0);
      expect(Number.isNaN(summary.savings_percentage_of_spend)).toBe(false);
      expect(Number.isFinite(summary.savings_percentage_of_spend)).toBe(true);
    });
  });
});
