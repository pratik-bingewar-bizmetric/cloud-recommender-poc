export type CloudScopeType =
  | "azure_subscription"
  | "azure_resource_group"
  | "databricks_workspace"
  | "databricks_resource"
  | "multi_scope"
  | "all";

export type ChildResourceType =
  | "cluster"
  | "warehouse"
  | "job"
  | "pipeline"
  | "serving_endpoint"
  | "catalog"
  | "app";

export interface ChildResourceScope {
  resource_type: ChildResourceType;
  resource_id: string;
  resource_name: string;
  metadata?: Record<string, unknown>;
}

export interface CloudScope {
  provider: "azure" | "databricks" | "aws" | "gcp" | "mixed";
  scope_type: CloudScopeType;
  account_id?: string;
  tenant_id?: string;
  subscription_id?: string;
  subscription_ids?: string[];
  subscription_name?: string;
  resource_group?: string;
  resource_groups?: string[];
  workspace_id?: string;
  workspace_ids?: string[];
  workspace_name?: string;
  workspace_url?: string;
  fabric_workspace_ids?: string[];
  fabric_capacity_ids?: string[];
  other_resource_count?: number;
  region?: string;
  display_name: string;
  resource_count?: number;
  status?: string;
  last_discovered_at?: string;
  selected_child_resource?: ChildResourceScope | null;
  is_multi_scope?: boolean;
}

export type DatabricksModuleId =
  | "overview"
  | "clusters"
  | "warehouses"
  | "jobs"
  | "pipelines"
  | "serving"
  | "catalog"
  | "apps"
  | "system_tables"
  | "query_history"
  | "ai_economics"
  | "audit"
  | "billing"
  | "discovery_history";

export type DatabricksModuleGroup =
  | "Overview"
  | "Compute & Data"
  | "AI & Models"
  | "Governance & Cost"
  | "System Diagnostics";

export interface NavigationModule {
  id: DatabricksModuleId;
  title: string;
  shortTitle: string;
  description: string;
  group: DatabricksModuleGroup;
  iconName: string;
  path: string;
  badge?: string;
  badgeColor?: "blue" | "emerald" | "amber" | "purple" | "slate";
  requiredCapability?: string;
}

export interface ResourceScope {
  id: string;
  type: string;
  name: string;
  parent_id?: string | null;
  region?: string;
  status?: string;
  metadata?: Record<string, unknown>;
}

export interface ModuleCapability {
  module_id: string;
  supported: boolean;
  requires_permission?: string;
  status: "available" | "permission_denied" | "unsupported" | "stopped";
  reason?: string;
}

