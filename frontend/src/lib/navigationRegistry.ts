import {
  DatabricksModuleId,
  DatabricksSection,
  NavigationModule,
  CloudScope,
} from "@/types/navigation";

// Section A: WORKSPACE & OPERATIONS (Modules 1-11)
export const DATABRICKS_OPERATIONS_MODULES: NavigationModule[] = [
  // 1. Overview
  {
    id: "overview",
    title: "Workspace Overview",
    shortTitle: "Overview",
    description: "Core workspace identity, URL, cloud provider, tier, region, and discovery summary.",
    group: "Workspace & Operations",
    section: "operations",
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
    group: "Workspace & Operations",
    section: "operations",
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
    group: "Workspace & Operations",
    section: "operations",
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
    group: "Workspace & Operations",
    section: "operations",
    iconName: "Workflow",
    path: "/databricks/jobs",
  },
  // 5. Pipelines (Delta Live Tables)
  {
    id: "pipelines",
    title: "Pipelines (DLT)",
    shortTitle: "Pipelines",
    description: "Delta Live Tables pipelines, continuous vs triggered schedules, targets, and storage paths.",
    group: "Workspace & Operations",
    section: "operations",
    iconName: "GitBranch",
    path: "/databricks/pipelines",
  },
  // 6. Model Serving Endpoints
  {
    id: "serving",
    title: "Model Serving Endpoints",
    shortTitle: "Model Serving",
    description: "Discovered serving endpoints (27 endpoints), served entities, compute scale, and traffic routes.",
    group: "Workspace & Operations",
    section: "operations",
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
    group: "Workspace & Operations",
    section: "operations",
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
    group: "Workspace & Operations",
    section: "operations",
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
    group: "Workspace & Operations",
    section: "operations",
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
    group: "Workspace & Operations",
    section: "operations",
    iconName: "History",
    path: "/databricks/query-history",
  },
  // 11. Audit & Governance
  {
    id: "audit",
    title: "Audit & Governance",
    shortTitle: "Audit & Governance",
    description: "Access audit logs, credential audits, permission changes, and policy compliance enforcement.",
    group: "Workspace & Operations",
    section: "operations",
    iconName: "ShieldCheck",
    path: "/databricks/audit",
  },
];

// Section B: FINOPS & COST INTELLIGENCE (Modules 12-21)
export const DATABRICKS_FINOPS_MODULES: NavigationModule[] = [
  // 12. Executive Overview
  {
    id: "exec_overview",
    title: "Executive Cost Overview",
    shortTitle: "Executive Overview",
    description: "Consolidated executive spend KPIs, total expenditure, DBU consumption, and cost drivers.",
    group: "FinOps & Cost Intelligence",
    section: "finops",
    iconName: "LayoutDashboard",
    path: "/databricks/finops/overview",
  },
  // 13. Cost Explorer
  {
    id: "cost_explorer",
    title: "Cost Explorer",
    shortTitle: "Cost Explorer",
    description: "Interactive daily and monthly spend trends, SKU-level breakdown, and billing ledgers.",
    group: "FinOps & Cost Intelligence",
    section: "finops",
    iconName: "TrendingDown",
    path: "/databricks/finops/cost-explorer",
  },
  // 14. Cost Allocation
  {
    id: "cost_allocation",
    title: "Cost Allocation",
    shortTitle: "Cost Allocation",
    description: "Cost attribution across workspaces, clusters, jobs, SQL warehouses, and projects.",
    group: "FinOps & Cost Intelligence",
    section: "finops",
    iconName: "FolderTree",
    path: "/databricks/finops/cost-allocation",
  },
  // 15. Cost & Billing
  {
    id: "cost_billing",
    title: "Cost & Billing",
    shortTitle: "Cost & Billing",
    description: "Enterprise billing records, rate card pricing, retractions, and reconciliation ledgers.",
    group: "FinOps & Cost Intelligence",
    section: "finops",
    iconName: "Coins",
    path: "/databricks/finops/billing",
  },
  // 16. Forecast & Budgets
  {
    id: "forecast",
    title: "Forecast & Budgets",
    shortTitle: "Forecast & Budgets",
    description: "Linear velocity expenditure projections, budget overruns, and scenario simulations.",
    group: "FinOps & Cost Intelligence",
    section: "finops",
    iconName: "ChartNoAxesCombined",
    path: "/databricks/finops/forecast",
  },
  // 17. Anomaly Detection
  {
    id: "anomaly",
    title: "Anomaly Detection",
    shortTitle: "Anomaly Detection",
    description: "Automated telemetry-backed cost spike identification and root cause analysis.",
    group: "FinOps & Cost Intelligence",
    section: "finops",
    iconName: "BellRing",
    path: "/databricks/finops/anomalies",
  },
  // 18. Optimization Advisor
  {
    id: "recommend",
    title: "Optimization Advisor",
    shortTitle: "Optimization Advisor",
    description: "Evidence-backed waste elimination, rightsizing recommendations, and lifecycle tracking.",
    group: "FinOps & Cost Intelligence",
    section: "finops",
    iconName: "Lightbulb",
    path: "/databricks/finops/optimization",
  },
  // 19. AI Economics
  {
    id: "ai_economics",
    title: "AI & Token Economics",
    shortTitle: "AI Economics",
    description: "Foundation model serving costs, input/output/cached token metrics, and unit economics.",
    group: "FinOps & Cost Intelligence",
    section: "finops",
    iconName: "Cpu",
    path: "/databricks/finops/ai-economics",
  },
  // 20. Governance & Policies
  {
    id: "governance",
    title: "Governance & Policies",
    shortTitle: "Governance & Policies",
    description: "Workspace policy compliance, auto-termination enforcement, and tagging governance.",
    group: "FinOps & Cost Intelligence",
    section: "finops",
    iconName: "ShieldCheck",
    path: "/databricks/finops/governance",
  },
  // 21. Reports & Audit
  {
    id: "reports",
    title: "Reports & Audit",
    shortTitle: "Reports & Audit",
    description: "Exportable audit logs, compliance evidence, CSV ledgers, and PDF reports.",
    group: "FinOps & Cost Intelligence",
    section: "finops",
    iconName: "History",
    path: "/databricks/finops/reports",
  },
];

// Unified 21-module registry in exact required order
export const DATABRICKS_MODULES: NavigationModule[] = [
  ...DATABRICKS_OPERATIONS_MODULES,
  ...DATABRICKS_FINOPS_MODULES,
];

export function getDatabricksModules(): NavigationModule[] {
  return DATABRICKS_MODULES;
}

export function getDatabricksOperationsModules(): NavigationModule[] {
  return DATABRICKS_OPERATIONS_MODULES;
}

export function getDatabricksFinOpsModules(): NavigationModule[] {
  return DATABRICKS_FINOPS_MODULES;
}

export function getDatabricksModuleById(id: DatabricksModuleId): NavigationModule | undefined {
  return DATABRICKS_MODULES.find((m) => m.id === id);
}

export function getDatabricksModulesBySection(): Record<DatabricksSection, NavigationModule[]> {
  return {
    operations: DATABRICKS_OPERATIONS_MODULES,
    finops: DATABRICKS_FINOPS_MODULES,
  };
}

export function getDatabricksModulesByGroup(): Record<string, NavigationModule[]> {
  const groups: Record<string, NavigationModule[]> = {
    "Workspace & Operations": DATABRICKS_OPERATIONS_MODULES,
    "FinOps & Cost Intelligence": DATABRICKS_FINOPS_MODULES,
  };
  return groups;
}

export function isDatabricksScope(scope: CloudScope | null | undefined): boolean {
  if (!scope) return false;
  return scope.provider === "databricks" || scope.scope_type === "databricks_workspace";
}
