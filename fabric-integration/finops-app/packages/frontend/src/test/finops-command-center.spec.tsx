import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { FinOpsCommandCenterView } from "@/components/FinOpsCommandCenterView";
import * as api from "@/lib/api";

vi.mock("@/lib/api", () => ({
  getFinOpsOverview: vi.fn(),
  getFinOpsCostExplorer: vi.fn(),
  getFinOpsCostAllocation: vi.fn(),
  getFinOpsComputeWarehouses: vi.fn(),
  getFinOpsAiEconomics: vi.fn(),
  getFinOpsDataStorage: vi.fn(),
  getFinOpsNetworkCloud: vi.fn(),
  getFinOpsOptimizationAdvisor: vi.fn(),
  recordFinOpsRecommendationAction: vi.fn(),
  getFinOpsForecastBudgets: vi.fn(),
  simulateFinOpsScenario: vi.fn(),
  getFinOpsAnomalyDetection: vi.fn(),
  getFinOpsGovernancePolicies: vi.fn(),
  getFinOpsShowbackChargeback: vi.fn(),
  getFinOpsWorkloadEconomics: vi.fn(),
  getFinOpsReportsAudit: vi.fn(),
  getFinOpsSettingsIntegrations: vi.fn(),
}));

import { FinOpsKpiMetric } from "@/types";

const mockKpi = (formatted_value: string, delta_label?: string): FinOpsKpiMetric => ({
  value: 0,
  formatted_value,
  unit: "USD",
  delta_label,
  status: "neutral",
  lineage: {
    source: "azure_system_billing",
    table: "system.billing.usage",
    method: "deterministic_sum",
    limitations: "Test mock",
    readiness_state: "ready",
  },
});

describe("FinOpsCommandCenterView Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    vi.mocked(api.getFinOpsOverview).mockResolvedValue({
      kpis: {
        total_spend: mockKpi("$284,620", "↑ 8.4% vs previous period"),
        databricks_spend: mockKpi("$176,840", "↑ 5.2% vs previous period"),
        ai_spend: mockKpi("$38,460", "↑ 18.7% vs previous period"),
        savings_opportunity: mockKpi("$31,280", "11.0% of total spend"),
        forecast_spend: mockKpi("$319,500", "↑ $19.5K above budget"),
        anomalies: mockKpi("7", "3 high severity · 4 medium"),
      },
      spend_trend: [],
      spend_composition: [],
      top_cost_drivers: [
        {
          driver: "Serverless Starter Warehouse",
          workspace_owner: "adb-642006393507276 · Data Platform",
          spend: 42180,
          formatted_spend: "$42,180",
          change: "+21%",
          signal: "Review",
        },
      ],
      decisions_requiring_attention: [
        {
          id: "dec-01",
          priority: 1,
          title: "Downsize Serverless Starter Warehouse",
          description: "Average utilization is 18%",
          estimated_savings_monthly: 8400,
          formatted_savings: "$8,400 / mo",
          impact: "High impact",
          status: "Approval required",
          confidence_pct: 91,
          effort: "Low",
          owner: "Data Platform",
          evidence: "Average utilization is 18%",
        },
      ],
      global_filters: {},
    });

    vi.mocked(api.getFinOpsCostExplorer).mockResolvedValue({
      kpis: {
        gross_consumption: mockKpi("$176,840"),
        effective_rate: mockKpi("$0.148"),
        unallocated_spend: mockKpi("$12,480"),
        credits_discounts: mockKpi("$8,260"),
      },
      daily_trend: [],
      cost_by_product_family: [],
      billing_ledger: [
        {
          date: "Nov 04",
          product: "SQL Warehouse",
          sku: "SQL Serverless",
          workspace: "adb-642006393507276",
          usage_qty: 18420,
          unit: "DBU",
          list_cost: 18420,
          effective_cost: 16578,
          owner_tag: "data-platform",
          allocation_status: "Allocated",
        },
      ],
    });

    vi.mocked(api.getFinOpsOptimizationAdvisor).mockResolvedValue({
      kpis: {
        potential_savings: mockKpi("$31,280"),
        quick_wins: mockKpi("12"),
        awaiting_approval: mockKpi("8"),
        realized_savings: mockKpi("$8,420"),
      },
      recommendations: [
        {
          id: "dec-01",
          priority: 1,
          title: "Downsize Serverless Starter Warehouse",
          description: "Average utilization is 18%",
          estimated_savings_monthly: 8400,
          formatted_savings: "$8,400 / mo",
          impact: "High impact",
          status: "Approval required",
          confidence_pct: 91,
          effort: "Low",
          owner: "Data Platform",
          evidence: "Average utilization is 18%",
        },
      ],
    });

    vi.mocked(api.recordFinOpsRecommendationAction).mockResolvedValue({
      id: "dec-01",
      priority: 1,
      title: "Downsize Serverless Starter Warehouse",
      description: "Average utilization is 18%",
      estimated_savings_monthly: 8400,
      formatted_savings: "$8,400 / mo",
      impact: "High impact",
      status: "Approved",
      confidence_pct: 91,
      effort: "Low",
      owner: "Data Platform",
      evidence: "Average utilization is 18%",
    });
  });

  it("renders Executive Cost Overview with 6 certified KPI cards", async () => {
    render(
      <FinOpsCommandCenterView
        activeModule="overview"
        onSelectModule={vi.fn()}
        selectedWorkspaceId="databricks-azure-dev"
      />
    );

    expect(screen.getByText("Executive Cost Overview")).toBeInTheDocument();
    expect(screen.getByText("FinOps Command Center · Azure Databricks")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("$284,620")).toBeInTheDocument();
      expect(screen.getByText("$176,840")).toBeInTheDocument();
      expect(screen.getByText("$38,460")).toBeInTheDocument();
      expect(screen.getByText("$31,280")).toBeInTheDocument();
      expect(screen.getByText("$319,500")).toBeInTheDocument();
      expect(screen.getByText("7")).toBeInTheDocument();
    });
  });

  it("renders Cost Explorer with billing ledger and CSV export trigger", async () => {
    render(
      <FinOpsCommandCenterView
        activeModule="cost"
        onSelectModule={vi.fn()}
        selectedWorkspaceId="databricks-azure-dev"
      />
    );

    expect(screen.getByText("Cost Explorer")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Gross consumption")).toBeInTheDocument();
      expect(screen.getByText("SQL Serverless")).toBeInTheDocument();
      expect(screen.getByText("adb-642006393507276")).toBeInTheDocument();
    });

    const downloadBtn = screen.getByText("Download CSV");
    expect(downloadBtn).toBeInTheDocument();
  });

  it("handles recommendation action click in Optimization Advisor", async () => {
    render(
      <FinOpsCommandCenterView
        activeModule="recommend"
        onSelectModule={vi.fn()}
        selectedWorkspaceId="databricks-azure-dev"
      />
    );

    await waitFor(() => {
      expect(screen.getAllByText("Downsize Serverless Starter Warehouse").length).toBeGreaterThan(0);
    });

    const approveBtn = screen.getByText("Approve for change");
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(api.recordFinOpsRecommendationAction).toHaveBeenCalledWith("dec-01", "Approved");
    });
  });

  it("opens and closes evidence detail modal", async () => {
    render(
      <FinOpsCommandCenterView
        activeModule="recommend"
        onSelectModule={vi.fn()}
        selectedWorkspaceId="databricks-azure-dev"
      />
    );

    await waitFor(() => {
      expect(screen.getByText("View evidence")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("View evidence"));

    expect(screen.getAllByText("Downsize Serverless Starter Warehouse").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Average utilization is 18%").length).toBeGreaterThan(0);

    // Close modal
    fireEvent.click(screen.getByText("Close"));
  });
});
