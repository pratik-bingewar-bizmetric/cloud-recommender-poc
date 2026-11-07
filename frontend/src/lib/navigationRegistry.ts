import {
  DatabricksModuleId,
  DatabricksModuleGroup,
  NavigationModule,
  CloudScope,
} from "@/types/navigation";

export const DATABRICKS_MODULES: NavigationModule[] = [
  // 1. Overview
  {
    id: "overview",
    title: "Workspace Overview",
    shortTitle: "Overview",
    description: "Core workspace identity, URL, cloud provider, tier, region, and discovery summary.",
    group: "Overview",
    iconName: "LayoutDashboard",
    path: "/databricks/overview",
    badge: "Connected",
    badgeColor: "emerald",
  },
  // 2. Compute Clusters
  {
    id: "clusters",
    title: "Compute Clusters",
    shortTitle: "Clusters",
    description: "All-purpose and job clusters, runtime versions, node types, autoscaling, and termination rules.",
    group: "Compute & Data",
    iconName: "Cpu",
    path: "/databricks/clusters",
    badge: "Inventory",
    badgeColor: "blue",
  },
  // 3. SQL Warehouses
  {
    id: "warehouses",
    title: "SQL Warehouses",
    shortTitle: "Warehouses",
    description: "Serverless and classic SQL warehouses, cluster sizing, auto-stop policies, and stopped status.",
    group: "Compute & Data",
    iconName: "Database",
    path: "/databricks/warehouses",
    badge: "STOPPED",
    badgeColor: "slate",
  },
  // 4. Jobs & Workflows
  {
    id: "jobs",
    title: "Jobs & Workflows",
    shortTitle: "Jobs & Workflows",
    description: "Multi-task workflows, schedule triggers, execution history, duration, and task definitions.",
    group: "Compute & Data",
    iconName: "Workflow",
    path: "/databricks/jobs",
  },
  // 5. Pipelines (Delta Live Tables)
  {
    id: "pipelines",
    title: "Pipelines (DLT)",
    shortTitle: "Pipelines",
    description: "Delta Live Tables pipelines, continuous vs triggered schedules, targets, and storage paths.",
    group: "Compute & Data",
    iconName: "GitBranch",
    path: "/databricks/pipelines",
  },
  // 6. Model Serving Endpoints
  {
    id: "serving",
    title: "Model Serving Endpoints",
    shortTitle: "Model Serving",
    description: "Discovered serving endpoints (27 endpoints), served entities, compute scale, and traffic routes.",
    group: "AI & Models",
    iconName: "Sparkles",
    path: "/databricks/serving",
    badge: "27 Models",
    badgeColor: "purple",
  },
  // 7. Unity Catalog
  {
    id: "catalog",
    title: "Unity Catalog",
    shortTitle: "Unity Catalog",
    description: "Complete 3-level namespace hierarchy: Metastores -> Catalogs -> Schemas -> Tables & Views.",
    group: "Compute & Data",
    iconName: "FolderTree",
    path: "/databricks/catalog",
    badge: "Governance",
    badgeColor: "emerald",
  },
  // 8. Databricks Apps
  {
    id: "apps",
    title: "Databricks Apps",
    shortTitle: "Databricks Apps",
    description: "Discovered applications (e.g. cost-monitor, finops-agent, lakehouse-optimizer) and runtime states.",
    group: "Compute & Data",
    iconName: "Server",
    path: "/databricks/apps",
    badge: "3 Discovered",
    badgeColor: "blue",
  },
  // 9. System Tables Diagnostics
  {
    id: "system_tables",
    title: "System Tables",
    shortTitle: "System Tables",
    description: "Diagnostic coverage across 10 system tables with clear schema metadata vs query availability distinction.",
    group: "System Diagnostics",
    iconName: "Terminal",
    path: "/databricks/system-tables",
    badge: "10 Tables",
    badgeColor: "amber",
  },
  // 10. Query History
  {
    id: "query_history",
    title: "Query History",
    shortTitle: "Query History",
    description: "SQL execution log, statement runtimes, query performance, and user attribution metrics.",
    group: "System Diagnostics",
    iconName: "History",
    path: "/databricks/query-history",
  },
  // 11. AI & Token Economics
  {
    id: "ai_economics",
    title: "AI & Token Economics",
    shortTitle: "AI Economics",
    description: "Model token consumption, throughput, latency, DBRX/Llama costs, and prompt-to-completion ratios.",
    group: "AI & Models",
    iconName: "Coins",
    path: "/databricks/ai-economics",
    badge: "FinOps",
    badgeColor: "purple",
  },
  // 12. Audit & Governance
  {
    id: "audit",
    title: "Audit & Governance",
    shortTitle: "Audit Log",
    description: "Access audit logs, credential audits, permission changes, and policy compliance enforcement.",
    group: "Governance & Cost",
    iconName: "ShieldCheck",
    path: "/databricks/audit",
  },
  // 13. Cost & Billing
  {
    id: "billing",
    title: "Cost & Billing",
    shortTitle: "Cost & Billing",
    description: "DBU consumption trends, SKU cost allocations, daily/monthly spend, and budget forecasts.",
    group: "Governance & Cost",
    iconName: "TrendingDown",
    path: "/databricks/billing",
  },
  // 14. Discovery History
  {
    id: "discovery_history",
    title: "Discovery History",
    shortTitle: "Discovery History",
    description: "Chronological ledger of discovery runs, resource deltas, sync durations, and error logs.",
    group: "System Diagnostics",
    iconName: "Clock",
    path: "/databricks/discovery-history",
  },
];

export function getDatabricksModules(): NavigationModule[] {
  return DATABRICKS_MODULES;
}

export function getDatabricksModuleById(id: DatabricksModuleId): NavigationModule | undefined {
  return DATABRICKS_MODULES.find((m) => m.id === id);
}

export function getDatabricksModulesByGroup(): Record<DatabricksModuleGroup, NavigationModule[]> {
  const groups: Record<DatabricksModuleGroup, NavigationModule[]> = {
    Overview: [],
    "Compute & Data": [],
    "AI & Models": [],
    "Governance & Cost": [],
    "System Diagnostics": [],
  };

  for (const mod of DATABRICKS_MODULES) {
    if (groups[mod.group]) {
      groups[mod.group].push(mod);
    }
  }

  return groups;
}

export function isDatabricksScope(scope: CloudScope | null | undefined): boolean {
  if (!scope) return false;
  return scope.provider === "databricks" || scope.scope_type === "databricks_workspace";
}

