import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import React from "react";
import { ConfigurationView } from "../components/ConfigurationView";
import * as api from "../lib/api";
import type {
  ScopeDiscoveryResponse,
  ResourceConfigurationResponse,
  ConfigurationStatusResponse,
  CloudConnection,
} from "../types";

describe("ConfigurationView Component", () => {
  const mockConnections: CloudConnection[] = [
    {
      id: "azure-f718c261",
      name: "Azure Production",
      provider: "azure",
      scope_id: "f718c261-ab85-49fd-907e-99c022cc2aeb",
      display_name: "Azure Production (f718c261)",
      status: "connected",
      auth_method: "service_principal",
      is_live: true,
      last_verified_at: "2026-11-06T00:00:00Z",
    },
    {
      id: "gcp-smart-expense",
      name: "Smart Expense GCP",
      provider: "gcp",
      scope_id: "smart-expense-gcp-prod",
      display_name: "Smart Expense GCP Production",
      status: "connected",
      auth_method: "service_account",
      is_live: false,
      last_verified_at: "2026-11-06T00:00:00Z",
    },
  ];

  const mockAzureDiscovery: ScopeDiscoveryResponse = {
    provider: "azure",
    connection_id: "azure-f718c261",
    status: "ready",
    status_message: "Discovered Azure topology with Databricks workspaces",
    last_discovered_at: "2026-11-06T05:00:00Z",
    total_discovered_resources: 4,
    databricks_workspaces_count: 1,
    tree: [
      {
        id: "sub-1",
        name: "Azure Enterprise Subscription",
        scope_type: "subscription",
        scope_identifier: "sub-1",
        children: [
          {
            id: "rg-analytics",
            name: "rg-analytics",
            scope_type: "resource_group",
            scope_identifier: "rg-analytics",
            parent_scope_identifier: "sub-1",
            region: "eastus",
            children: [
              {
                id: "adb-lakehouse",
                name: "adb-lakehouse-prod",
                scope_type: "databricks_workspace",
                scope_identifier: "/subscriptions/sub-1/resourceGroups/rg-analytics/providers/Microsoft.Databricks/workspaces/adb-lakehouse-prod",
                parent_scope_identifier: "rg-analytics",
                resource_type: "Microsoft.Databricks/workspaces",
                region: "eastus",
                is_leaf: true,
                metadata: {
                  workspace_url: "adb-123456789.14.azuredatabricks.net",
                  workspace_id: "123456789",
                  pricing_tier: "premium",
                },
              },
              {
                id: "st-lakehouse",
                name: "stlakehouseprod01",
                scope_type: "resource",
                scope_identifier: "/subscriptions/sub-1/resourceGroups/rg-analytics/providers/Microsoft.Storage/storageAccounts/stlakehouseprod01",
                parent_scope_identifier: "rg-analytics",
                resource_type: "Microsoft.Storage/storageAccounts",
                region: "eastus",
                is_leaf: true,
              },
            ],
          },
        ],
      },
    ],
  };

  const mockActiveConfig: ResourceConfigurationResponse = {
    configuration_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    connection_id: "azure-f718c261",
    provider: "azure",
    configuration_version: 1,
    active_status: "active",
    created_by: "system",
    created_at: "2026-11-06T00:00:00Z",
    updated_at: "2026-11-06T00:00:00Z",
    scope_items: [
      {
        item_id: "item-1",
        configuration_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        scope_type: "subscription",
        scope_identifier: "sub-1",
        display_name: "Azure Enterprise Subscription",
        selection_state: "all_children",
        metadata: {},
        created_at: "2026-11-06T00:00:00Z",
        updated_at: "2026-11-06T00:00:00Z",
      },
    ],
    total_items: 1,
  };

  const mockStatus: ConfigurationStatusResponse = {
    connection_id: "azure-f718c261",
    has_configuration: true,
    configuration_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    configuration_version: 1,
    active_status: "active",
    selected_resource_count: 2,
    databricks_workspaces_count: 1,
    ingestion_readiness: "ready",
    updated_at: "2026-11-06T00:00:00Z",
  };

  const mockReadiness: import("../types").IngestionReadinessResponse = {
    connection_id: "azure-f718c261",
    provider: "azure",
    readiness_state: "ready",
    can_start_ingestion: true,
    has_configuration: true,
    configuration_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    configuration_version: 1,
    selected_resource_count: 2,
    selected_workspace_count: 1,
    effective_resource_ids: ["res-adb", "res-stg"],
    effective_workspace_ids: ["res-adb"],
    details: "Ready for scope-aware ingestion.",
    missing_requirements: [],
    checked_at: "2026-11-06T00:00:00Z",
  };

  const mockRunResponse: import("../types").IngestionRunResponse = {
    run_id: "run-11223344-5566-7788-9900-aabbccddeeff",
    connection_id: "azure-f718c261",
    provider: "azure",
    configuration_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    configuration_version: 1,
    status: "completed",
    triggered_by: "user",
    started_at: "2026-11-06T05:00:00Z",
    completed_at: "2026-11-06T05:01:00Z",
    total_resources_scoped: 2,
    successful_resources_count: 2,
    failed_resources_count: 0,
    scope_snapshot: {},
    resource_statuses: [],
  };

  const mockRunSummary: import("../types").IngestionRunSummaryResponse = {
    run_id: "run-11223344-5566-7788-9900-aabbccddeeff",
    connection_id: "azure-f718c261",
    provider: "azure",
    configuration_version: 1,
    status: "completed",
    triggered_by: "user",
    started_at: "2026-11-06T05:00:00Z",
    completed_at: "2026-11-06T05:01:00Z",
    total_resources_scoped: 2,
    successful_resources_count: 2,
    failed_resources_count: 0,
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, "listConnections").mockResolvedValue(mockConnections);
    vi.spyOn(api, "discoverScopes").mockResolvedValue(mockAzureDiscovery);
    vi.spyOn(api, "getConfiguration").mockResolvedValue(mockActiveConfig);
    vi.spyOn(api, "getConfigurationStatus").mockResolvedValue(mockStatus);
    vi.spyOn(api, "checkIngestionReadiness").mockResolvedValue(mockReadiness);
    vi.spyOn(api, "listIngestionRuns").mockResolvedValue([mockRunSummary]);
    vi.spyOn(api, "triggerIngestionRun").mockResolvedValue(mockRunResponse);
    vi.spyOn(api, "saveConfiguration").mockResolvedValue({
      ...mockActiveConfig,
      configuration_version: 2,
    });
  });

  it("renders page header, subtitle, and provider selector tabs", async () => {
    render(<ConfigurationView />);

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /Multi-Cloud Resource Configuration/i })
      ).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: "Azure" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Google Cloud" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "AWS" })).toBeInTheDocument();
  });

  it("displays honest unsupported alert when AWS provider is clicked", async () => {
    render(<ConfigurationView />);

    await waitFor(() => {
      expect(screen.getByText("Azure Enterprise Subscription")).toBeInTheDocument();
    });

    const awsBtn = screen.getByRole("button", { name: /AWS/i });
    act(() => {
      fireEvent.click(awsBtn);
    });

    expect(screen.getByText(/AWS Provider Not Configured/i)).toBeInTheDocument();
    expect(
      screen.getByText(/AWS integration is currently absent in this deployment/i)
    ).toBeInTheDocument();
  });

  it("renders hierarchical tree with Databricks Workspaces highlighted with URL", async () => {
    render(<ConfigurationView />);

    await waitFor(() => {
      expect(screen.getByText("Azure Enterprise Subscription")).toBeInTheDocument();
    });

    expect(screen.getByText("rg-analytics")).toBeInTheDocument();
    expect(screen.getByText("adb-lakehouse-prod")).toBeInTheDocument();
    expect(screen.getByText("Databricks Workspace")).toBeInTheDocument();
    expect(screen.getByText("adb-123456789.14.azuredatabricks.net")).toBeInTheDocument();
  });

  it("filters tree nodes by search query", async () => {
    render(<ConfigurationView />);

    await waitFor(() => {
      expect(screen.getByText("adb-lakehouse-prod")).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/Filter by resource name, type, region/i);
    fireEvent.change(searchInput, { target: { value: "storageAccounts" } });

    expect(screen.getByText("stlakehouseprod01")).toBeInTheDocument();
  });

  it("invokes saveConfiguration and displays revision confirmation banner", async () => {
    render(<ConfigurationView />);

    await waitFor(() => {
      expect(screen.getByText("adb-lakehouse-prod")).toBeInTheDocument();
    });

    const saveBtn = screen.getByRole("button", { name: /Save Configuration/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(api.saveConfiguration).toHaveBeenCalledTimes(1);
    });

    expect(
      await screen.findByText(/Configuration Revision v2 saved successfully!/i)
    ).toBeInTheDocument();
  });

  it("handles Select All and Clear All quick actions", async () => {
    render(<ConfigurationView />);

    await waitFor(() => {
      expect(screen.getByText("adb-lakehouse-prod")).toBeInTheDocument();
    });

    const clearAllBtn = screen.getByRole("button", { name: /Clear All/i });
    fireEvent.click(clearAllBtn);

    expect(screen.getByText(/0 Selected/i)).toBeInTheDocument();

    const selectAllBtn = screen.getByRole("button", { name: /Select All/i });
    fireEvent.click(selectAllBtn);

    expect(screen.getByText(/2 Selected \(1 Workspaces\)/i)).toBeInTheDocument();
  });

  it("displays ingestion readiness badge and triggers ingestion run", async () => {
    render(<ConfigurationView />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Trigger Ingestion/i })).toBeInTheDocument();
    });

    // Check readiness badge rendered
    expect(screen.getByText("ready")).toBeInTheDocument();

    // Check history list rendered
    expect(screen.getByText(/Recent Ingestion Runs & Version Lineage/i)).toBeInTheDocument();
    expect(screen.getByText(/Scope v1/i)).toBeInTheDocument();

    const triggerBtn = screen.getByRole("button", { name: /Trigger Ingestion/i });
    fireEvent.click(triggerBtn);

    await waitFor(() => {
      expect(api.triggerIngestionRun).toHaveBeenCalledTimes(1);
    });

    expect(await screen.findByText(/Ingestion run run-1122/i)).toBeInTheDocument();
  });
});
