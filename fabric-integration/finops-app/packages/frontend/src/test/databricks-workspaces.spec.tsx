import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import React from "react";
import { DatabricksWorkspaceSelector } from "../components/DatabricksWorkspaceSelector";
import { DatabricksWorkspacesView } from "../components/DatabricksWorkspacesView";
import { DatabricksWorkspaceDetailView } from "../components/DatabricksWorkspaceDetailView";
import { DatabricksConnection, DatabricksWorkspaceDiscovery } from "@/types";

const mockConnections: DatabricksConnection[] = [
  {
    connection_id: "databricks-azure-dev",
    workspace_id: "642006393507276",
    workspace_name: "Azure Databricks Dev",
    workspace_url: "https://adb-642006393507276.16.azuredatabricks.net",
    cloud: "azure",
    region: "northcentralus",
    auth_method: "azure-cli / profile",
    profile_name: "azure-dev",
    status: "connected",
    last_connected_at: "2026-11-06T12:00:00Z",
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-06T12:00:00Z",
  },
  {
    connection_id: "databricks-finops-dev",
    workspace_id: "2250283018608626",
    workspace_name: "AWS Databricks FinOps",
    workspace_url: "https://dbc-8e061b63-c3bf.cloud.databricks.com",
    cloud: "aws",
    region: "us-east-1",
    auth_method: "cli-profile / oauth-sp",
    profile_name: "finops-dev",
    status: "auth_failed",
    last_connected_at: null,
    last_error: "No valid credentials found.",
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-06T12:00:00Z",
  },
];

const mockDiscovery: DatabricksWorkspaceDiscovery = {
  connection_id: "databricks-azure-dev",
  workspace_id: "642006393507276",
  workspace_name: "Azure Databricks Dev",
  workspace_url: "https://adb-642006393507276.16.azuredatabricks.net",
  cloud: "azure",
  overall_status: "completed",
  categories: {
    clusters: { category: "clusters", status: "available", resource_count: 1 },
    warehouses: { category: "warehouses", status: "available", resource_count: 1 },
    unity_catalog: { category: "unity_catalog", status: "permission_denied", resource_count: 0, error_message: "403 Forbidden" },
  },
  resources: [
    {
      id: "cl-1",
      name: "Compute Cluster 1",
      resource_type: "cluster",
      workspace_id: "642006393507276",
      status: "RUNNING",
      creator: "tester",
      source_api: "databricks-sdk/clusters",
      metadata: { spark_version: "14.3", num_workers: 2 },
      discovered_at: "2026-11-06T12:00:00Z",
    },
    {
      id: "wh-1",
      name: "Serverless SQL Warehouse",
      resource_type: "warehouse",
      workspace_id: "642006393507276",
      status: "RUNNING",
      creator: "tester",
      source_api: "databricks-sdk/warehouses",
      metadata: { cluster_size: "Small" },
      discovered_at: "2026-11-06T12:00:00Z",
    },
  ],
  total_resources_count: 2,
  discovered_at: "2026-11-06T12:00:00Z",
};

describe("Databricks Workspace Selector", () => {
  it("renders workspace dropdown with options and triggers change", () => {
    const onSelect = vi.fn();
    render(
      <DatabricksWorkspaceSelector
        connections={mockConnections}
        selectedWorkspaceId="all"
        onSelectWorkspace={onSelect}
      />
    );

    expect(screen.getByText(/All Workspaces \(2\)/)).toBeDefined();
    const select = screen.getByRole("combobox");
    fireEvent.change(select, { target: { value: "databricks-azure-dev" } });
    expect(onSelect).toHaveBeenCalledWith("databricks-azure-dev");
  });
});

describe("Databricks Workspace Details View", () => {
  it("renders workspace details with tabs and permission-denied notification", () => {
    const onBack = vi.fn();
    const onRefresh = vi.fn();

    render(
      <DatabricksWorkspaceDetailView
        connection={mockConnections[0]}
        discovery={mockDiscovery}
        isLoading={false}
        onBack={onBack}
        onRefresh={onRefresh}
      />
    );

    expect(screen.getByText("Azure Databricks Dev")).toBeDefined();
    expect(screen.getAllByText("Compute Clusters").length).toBeGreaterThan(0);
    expect(screen.getAllByText("SQL Warehouses").length).toBeGreaterThan(0);

    // Switch to clusters tab
    const clustersTab = screen.getByRole("button", { name: /Compute Clusters/ });
    fireEvent.click(clustersTab);
    expect(screen.getByText("Compute Cluster 1")).toBeDefined();

    // Switch to Unity Catalog tab with permission denied
    const ucTab = screen.getByRole("button", { name: /Unity Catalog/ });
    fireEvent.click(ucTab);
    expect(screen.getByText(/Permission Denied:/)).toBeDefined();
  });
});
