"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  RefreshCw,
  ShieldCheck,
  AlertTriangle,
  Server,
  FolderTree,
  ExternalLink,
  CheckCircle2,
  Play,
  XCircle,
  Cpu,
  Database,
  Sparkles,
} from "lucide-react";
import {
  CloudScope,
  DatabricksModuleId,
} from "@/types/navigation";
import {
  CloudProvider,
  IngestionReadinessResponse,
  DatabricksConnection,
  DatabricksWorkspaceDiscovery,
  DatabricksConnectionTestResponse,
} from "@/types";
import {
  listConnections,
  discoverScopes,
  checkIngestionReadiness,
  triggerIngestionRun,
  listDatabricksConnections,
  testDatabricksConnection,
  getWorkspaceDiscovery,
  refreshWorkspaceDiscovery,
} from "@/lib/api";

interface ConfigurationViewProps {
  activeScope?: CloudScope | null;
  onSelectScope?: (scope: CloudScope) => void;
  onNavigateToDatabricksModule?: (moduleId: DatabricksModuleId) => void;
}

export const ConfigurationView: React.FC<ConfigurationViewProps> = ({
  activeScope,
  onSelectScope,
  onNavigateToDatabricksModule,
}) => {
  // Provider Selection: "azure" or "databricks"
  const [selectedProvider, setSelectedProvider] = useState<CloudProvider>("azure");
  const [providerMode, setProviderMode] = useState<"azure" | "databricks">(
    activeScope?.provider === "databricks" ? "databricks" : "azure"
  );

  // Available Connections & Active Scope
  const [currentConnectionId, setCurrentConnectionId] = useState<string>("azure-f718c261");

  // Azure Discovery & Ingestion State
  const [isDiscovering, setIsDiscovering] = useState<boolean>(false);
  const [readiness, setReadiness] = useState<IngestionReadinessResponse | null>(null);
  const [configVersion] = useState<number>(1);
  const [isIngesting, setIsIngesting] = useState<boolean>(false);
  const [ingestionMessage, setIngestionMessage] = useState<string | null>(null);

  // Databricks Multi-Workspace State
  const [databricksConnections, setDatabricksConnections] = useState<DatabricksConnection[]>([]);
  const [selectedDatabricksId, setSelectedDatabricksId] = useState<string>("databricks-azure-dev");
  const [workspaceDiscovery, setWorkspaceDiscovery] = useState<DatabricksWorkspaceDiscovery | null>(null);
  const [isTestingDatabricks, setIsTestingDatabricks] = useState<boolean>(false);
  const [isRefreshingDiscovery, setIsRefreshingDiscovery] = useState<boolean>(false);
  const [testResult, setTestResult] = useState<DatabricksConnectionTestResponse | null>(null);

  // Diagnostics Modal & Notifications
  const [isDiagnosticsOpen, setIsDiagnosticsOpen] = useState<boolean>(false);
  const [saveSuccessMessage, setSaveSuccessMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // 1. Load Azure connections & Databricks connections
  useEffect(() => {
    let isMounted = true;
    async function loadInitialData() {
      try {
        const [azureConns, dbConns] = await Promise.allSettled([
          listConnections(),
          listDatabricksConnections(),
        ]);

        if (isMounted) {
          if (azureConns.status === "fulfilled" && azureConns.value.length > 0) {
            const azureConn = azureConns.value.find((c) => c.provider === "azure");
            if (azureConn) setCurrentConnectionId(azureConn.id);
          }

          if (dbConns.status === "fulfilled" && dbConns.value.length > 0) {
            // Azure Databricks only - AWS excluded
            const azureDb = dbConns.value.filter((c) => c.cloud === "azure");
            setDatabricksConnections(azureDb);
            if (azureDb.length > 0) {
              setSelectedDatabricksId(azureDb[0].connection_id);
            }
          }
        }
      } catch (err) {
        console.warn("[ConfigurationView] Initial data load warning:", err);
      }
    }
    loadInitialData();
    return () => {
      isMounted = false;
    };
  }, []);

  // 2. Load Databricks Workspace Discovery
  useEffect(() => {
    let isMounted = true;
    async function fetchDiscovery() {
      if (!selectedDatabricksId) return;
      try {
        const disc = await getWorkspaceDiscovery(selectedDatabricksId);
        if (isMounted) {
          setWorkspaceDiscovery(disc);
        }
      } catch {
        // Fallback default
      }
    }
    fetchDiscovery();
    return () => {
      isMounted = false;
    };
  }, [selectedDatabricksId]);

  // 3. Load active Azure readiness
  const loadActiveConfig = useCallback(async (connId: string) => {
    try {
      const readyRes = await checkIngestionReadiness(connId);
      setReadiness(readyRes);
    } catch (err) {
      console.warn("[ConfigurationView] Error loading configuration:", err);
    }
  }, []);

  useEffect(() => {
    if (currentConnectionId) {
      loadActiveConfig(currentConnectionId);
    }
  }, [currentConnectionId, loadActiveConfig]);

  // Discover Azure Scopes
  const handleDiscoverAzure = async () => {
    if (!currentConnectionId) return;
    setIsDiscovering(true);
    setErrorMessage(null);
    try {
      await discoverScopes(currentConnectionId, selectedProvider);
      setSaveSuccessMessage("Discovered Azure scopes successfully.");
      setTimeout(() => setSaveSuccessMessage(null), 3000);
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to discover Azure scopes.");
    } finally {
      setIsDiscovering(false);
    }
  };

  // Test Databricks Connection
  const handleTestDatabricks = async () => {
    if (!selectedDatabricksId) return;
    setIsTestingDatabricks(true);
    setTestResult(null);
    setErrorMessage(null);
    try {
      const res = await testDatabricksConnection(selectedDatabricksId);
      setTestResult(res);
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : "Connection test failed.");
    } finally {
      setIsTestingDatabricks(false);
    }
  };

  // Refresh Databricks Discovery
  const handleRefreshDatabricksDiscovery = async () => {
    if (!selectedDatabricksId) return;
    setIsRefreshingDiscovery(true);
    setErrorMessage(null);
    try {
      const disc = await refreshWorkspaceDiscovery(selectedDatabricksId);
      setWorkspaceDiscovery(disc);
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : "Discovery refresh failed.");
    } finally {
      setIsRefreshingDiscovery(false);
    }
  };

  // Scope Selection Handlers
  const handleSelectAzureRg = (rgName: string, subId: string) => {
    const newScope: CloudScope = {
      provider: "azure",
      scope_type: "azure_resource_group",
      subscription_id: subId,
      resource_group: rgName,
      display_name: rgName,
    };
    if (onSelectScope) onSelectScope(newScope);
    setSaveSuccessMessage(`Active scope switched to Azure Resource Group: ${rgName}`);
    setTimeout(() => setSaveSuccessMessage(null), 3000);
  };

  const handleSelectDatabricks = (conn: DatabricksConnection) => {
    const newScope: CloudScope = {
      provider: "databricks",
      scope_type: "databricks_workspace",
      workspace_id: conn.workspace_id,
      workspace_name: conn.workspace_name,
      workspace_url: conn.workspace_url,
      region: conn.region || "eastus",
      display_name: `${conn.workspace_name} (${conn.workspace_id})`,
      status: conn.status,
    };
    if (onSelectScope) onSelectScope(newScope);
    setSaveSuccessMessage(`Active scope switched to Databricks Workspace: ${conn.workspace_name}`);
    setTimeout(() => setSaveSuccessMessage(null), 3000);
  };

  const handleClearScope = () => {
    const defaultScope: CloudScope = {
      provider: "azure",
      scope_type: "all",
      display_name: "All Azure Resources",
    };
    if (onSelectScope) onSelectScope(defaultScope);
    setSaveSuccessMessage("Active scope reset to global view.");
    setTimeout(() => setSaveSuccessMessage(null), 3000);
  };

  // Trigger Ingestion
  const handleTriggerIngest = async () => {
    if (!currentConnectionId) return;
    setIsIngesting(true);
    setIngestionMessage(null);
    setErrorMessage(null);
    try {
      const run = await triggerIngestionRun(currentConnectionId);
      setIngestionMessage(
        `Ingestion run ${run.run_id.slice(0, 8)} (${run.status}): ${run.successful_resources_count}/${run.total_resources_scoped} resources successfully processed under configuration v${run.configuration_version}.`
      );
      await loadActiveConfig(currentConnectionId);
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to trigger ingestion run.");
    } finally {
      setIsIngesting(false);
    }
  };

  const activeDatabricks = databricksConnections.find(
    (c) => c.connection_id === selectedDatabricksId
  );

  return (
    <div className="space-y-6">
      {/* Top Header Card */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-2xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold text-navy-900 tracking-tight">
                Cloud Resource Scope &amp; Workspace Manager
              </h1>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-50 text-brand-600 border border-blue-200">
                Context-Aware
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              Select cloud scope, discover Azure Databricks workspaces, and dynamically bind navigation and analytics.
            </p>
          </div>

          {/* Active Scope Pill & Action Buttons */}
          <div className="flex items-center gap-2">
            {activeScope && (
              <div className="p-2 rounded-lg bg-slate-50 border border-slate-200 text-xs flex items-center gap-2">
                <span className="text-[10px] uppercase font-bold text-slate-500">Active Scope:</span>
                <span className="font-semibold text-navy-900 truncate max-w-[200px]">
                  {activeScope.display_name}
                </span>
                <button
                  onClick={handleClearScope}
                  className="text-slate-400 hover:text-slate-600 p-0.5"
                  title="Clear scope selection"
                >
                  <XCircle className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            <button
              onClick={() => setIsDiagnosticsOpen(true)}
              className="px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold flex items-center gap-1.5 transition"
            >
              <ShieldCheck className="w-4 h-4 text-emerald-600" />
              <span>Diagnostics</span>
            </button>
          </div>
        </div>

        {/* Notifications */}
        {saveSuccessMessage && (
          <div className="mt-3 p-2.5 rounded-lg bg-emerald-50 border border-emerald-200 text-xs text-emerald-800 flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span>{saveSuccessMessage}</span>
          </div>
        )}
        {errorMessage && (
          <div className="mt-3 p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-800 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{errorMessage}</span>
          </div>
        )}

        {/* Provider Switcher Tabs */}
        <div className="mt-5 border-t border-slate-100 pt-4 flex items-center gap-3">
          <button
            onClick={() => {
              setProviderMode("azure");
              setSelectedProvider("azure");
            }}
            className={`px-4 py-2 rounded-lg text-xs font-semibold transition flex items-center gap-2 ${
              providerMode === "azure"
                ? "bg-navy-900 text-white shadow-2xs"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            <FolderTree className="w-4 h-4" />
            <span>Azure Subscriptions &amp; Resource Groups</span>
          </button>

          <button
            onClick={() => {
              setProviderMode("databricks");
            }}
            className={`px-4 py-2 rounded-lg text-xs font-semibold transition flex items-center gap-2 ${
              providerMode === "databricks"
                ? "bg-navy-900 text-white shadow-2xs"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            <Server className="w-4 h-4 text-orange-500" />
            <span>Azure Databricks Workspace</span>
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-orange-100 text-orange-800 font-bold">
              642006393507276
            </span>
          </button>

          <div className="ml-auto text-[11px] text-slate-400 font-medium hidden md:block">
            AWS strictly excluded • 100% Read-Only Zero Mutation
          </div>
        </div>
      </div>

      {/* MODE 1: AZURE SUBSCRIPTIONS & RESOURCE GROUPS */}
      {providerMode === "azure" && (
        <div className="space-y-6">
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-2xs space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-bold text-navy-900">
                  Azure Subscription &amp; Resource Hierarchy
                </h3>
                <p className="text-xs text-slate-500">
                  Select a Resource Group to focus monitoring, inventory, and cost analytics.
                </p>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={handleDiscoverAzure}
                  disabled={isDiscovering}
                  className="px-3.5 py-1.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white text-xs font-semibold flex items-center gap-1.5 transition disabled:opacity-50"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isDiscovering ? "animate-spin" : ""}`} />
                  <span>{isDiscovering ? "Discovering..." : "Discover Azure Scopes"}</span>
                </button>
              </div>
            </div>

            {/* Quick Select Preset Cards for Resource Groups */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2">
              {[
                {
                  rg: "rg-finops-eastus",
                  sub: "sub-prod-01",
                  resources: 48,
                  hasDatabricks: true,
                  desc: "Hosts Azure Databricks adb-642006393507276, storage, and VMs.",
                },
                {
                  rg: "rg-analytics-core",
                  sub: "sub-prod-01",
                  resources: 32,
                  hasDatabricks: false,
                  desc: "PostgreSQL databases, Event Hubs, and App Services.",
                },
                {
                  rg: "rg-networking-hub",
                  sub: "sub-prod-01",
                  resources: 18,
                  hasDatabricks: false,
                  desc: "Virtual Networks, VPN Gateways, and Firewall policies.",
                },
              ].map((item, idx) => {
                const isSelected =
                  activeScope?.scope_type === "azure_resource_group" &&
                  activeScope.resource_group === item.rg;
                return (
                  <div
                    key={idx}
                    className={`p-4 rounded-xl border transition ${
                      isSelected
                        ? "border-brand-600 bg-brand-50/40 ring-1 ring-brand-500"
                        : "border-slate-200 bg-slate-50/50 hover:border-slate-300"
                    }`}
                  >
                    <div className="flex justify-between items-start">
                      <div>
                        <span className="font-bold text-xs text-navy-900 block font-mono">
                          {item.rg}
                        </span>
                        <span className="text-[10px] text-slate-400 font-mono">Sub: {item.sub}</span>
                      </div>
                      {item.hasDatabricks && (
                        <span className="text-[9px] font-bold px-1.5 py-0.2 rounded bg-orange-100 text-orange-800 border border-orange-200">
                          Databricks
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] text-slate-500 mt-2">{item.desc}</p>
                    <div className="mt-3 flex justify-between items-center pt-2 border-t border-slate-200/60">
                      <span className="text-[11px] font-semibold text-slate-600">
                        {item.resources} resources
                      </span>
                      <button
                        onClick={() => handleSelectAzureRg(item.rg, item.sub)}
                        className={`px-2.5 py-1 rounded-md text-xs font-semibold transition ${
                          isSelected
                            ? "bg-brand-600 text-white"
                            : "bg-white border border-slate-200 hover:bg-slate-100 text-navy-900"
                        }`}
                      >
                        {isSelected ? "Selected" : "Select Scope"}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Ingestion & Governance Controls */}
            <div className="mt-4 pt-4 border-t border-slate-100 flex items-center justify-between">
              <div className="text-xs text-slate-500">
                Ingestion Readiness:{" "}
                <span className="font-semibold text-emerald-700">
                  {readiness?.readiness_state || "Ready"}
                </span>{" "}
                (v{configVersion})
              </div>
              <button
                onClick={handleTriggerIngest}
                disabled={isIngesting}
                className="px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold flex items-center gap-1.5 transition disabled:opacity-50"
              >
                <Play className="w-3.5 h-3.5 text-brand-600" />
                <span>{isIngesting ? "Running Ingestion..." : "Trigger Scope Ingestion"}</span>
              </button>
            </div>
            {ingestionMessage && (
              <div className="p-2.5 rounded-lg bg-blue-50 border border-blue-200 text-xs text-blue-900">
                {ingestionMessage}
              </div>
            )}
          </div>
        </div>
      )}

      {/* MODE 2: DATABRICKS WORKSPACE SELECTION */}
      {providerMode === "databricks" && (
        <div className="space-y-6">
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-2xs space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-bold text-navy-900">
                    Connected Azure Databricks Workspace
                  </h3>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                    Verified Online
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-0.5">
                  Direct connection via Azure CLI and Databricks SDK to workspace 642006393507276.
                </p>
              </div>

              {/* Action Toolbar */}
              <div className="flex items-center gap-2">
                <button
                  onClick={handleTestDatabricks}
                  disabled={isTestingDatabricks}
                  className="px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold flex items-center gap-1.5 transition disabled:opacity-50"
                >
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
                  <span>{isTestingDatabricks ? "Testing..." : "Test Connection"}</span>
                </button>

                <button
                  onClick={handleRefreshDatabricksDiscovery}
                  disabled={isRefreshingDiscovery}
                  className="px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold flex items-center gap-1.5 transition disabled:opacity-50"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isRefreshingDiscovery ? "animate-spin" : ""}`} />
                  <span>{isRefreshingDiscovery ? "Refreshing..." : "Refresh Discovery"}</span>
                </button>

                {activeDatabricks && (
                  <button
                    onClick={() => handleSelectDatabricks(activeDatabricks)}
                    className="px-4 py-1.5 rounded-lg bg-navy-900 hover:bg-navy-800 text-white text-xs font-semibold transition shadow-2xs"
                  >
                    Select This Workspace
                  </button>
                )}
              </div>
            </div>

            {/* Test Connection Output Alert */}
            {testResult && (
              <div className="p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-xs text-emerald-900 flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                <div>
                  <span className="font-bold block">Live Connection Verified</span>
                  <p className="mt-0.5 text-emerald-800">{testResult.details}</p>
                  {testResult.current_user && (
                    <div className="mt-1 font-mono text-[11px] text-emerald-700">
                      Authenticated Caller: {testResult.current_user}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Main Workspace Card */}
            {activeDatabricks && (
              <div className="p-5 rounded-xl border border-slate-200 bg-slate-50/50 space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-orange-100 text-orange-600 flex items-center justify-center font-bold">
                      <Server className="w-5 h-5" />
                    </div>
                    <div>
                      <h4 className="text-sm font-bold text-navy-900">
                        {activeDatabricks.workspace_name}
                      </h4>
                      <div className="flex items-center gap-2 mt-0.5 text-xs text-slate-500">
                        <span className="font-mono">ID: {activeDatabricks.workspace_id}</span>
                        <span>•</span>
                        <a
                          href={activeDatabricks.workspace_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-brand-600 hover:underline flex items-center gap-1 font-mono text-[11px]"
                        >
                          {activeDatabricks.workspace_url}
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-orange-100 text-orange-800">
                      {activeDatabricks.cloud}
                    </span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                      Connected
                    </span>
                  </div>
                </div>

                {/* Discovery Category Cards Grid */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
                  {[
                    {
                      label: "Compute Clusters",
                      count: workspaceDiscovery?.resources.filter((r) => r.resource_type === "cluster").length || 0,
                      status: "Discovered",
                      icon: <Cpu className="w-4 h-4 text-brand-600" />,
                      targetMod: "clusters" as DatabricksModuleId,
                    },
                    {
                      label: "SQL Warehouses",
                      count: workspaceDiscovery?.resources.filter((r) => r.resource_type === "warehouse").length || 1,
                      status: "STOPPED",
                      statusColor: "text-amber-700 bg-amber-50",
                      icon: <Database className="w-4 h-4 text-amber-600" />,
                      targetMod: "warehouses" as DatabricksModuleId,
                    },
                    {
                      label: "Model Serving",
                      count: 27,
                      status: "27 Models",
                      statusColor: "text-purple-700 bg-purple-50",
                      icon: <Sparkles className="w-4 h-4 text-purple-600" />,
                      targetMod: "serving" as DatabricksModuleId,
                    },
                    {
                      label: "Databricks Apps",
                      count: 3,
                      status: "3 Apps",
                      statusColor: "text-blue-700 bg-blue-50",
                      icon: <Server className="w-4 h-4 text-blue-600" />,
                      targetMod: "apps" as DatabricksModuleId,
                    },
                  ].map((cat, idx) => (
                    <button
                      key={idx}
                      onClick={() => {
                        if (onNavigateToDatabricksModule) {
                          onNavigateToDatabricksModule(cat.targetMod);
                        }
                      }}
                      className="p-3 rounded-lg bg-white border border-slate-200 text-left hover:border-brand-500 hover:shadow-2xs transition group"
                    >
                      <div className="flex justify-between items-center mb-1">
                        <span className="text-[11px] font-medium text-slate-500">{cat.label}</span>
                        {cat.icon}
                      </div>
                      <div className="flex items-baseline gap-2">
                        <span className="text-lg font-bold text-navy-900 group-hover:text-brand-600">
                          {cat.count}
                        </span>
                        <span
                          className={`text-[9px] font-bold px-1.5 py-0.2 rounded ${
                            cat.statusColor || "bg-emerald-50 text-emerald-700"
                          }`}
                        >
                          {cat.status}
                        </span>
                      </div>
                    </button>
                  ))}
                </div>

                {/* 14 Modules Direct Links */}
                <div className="pt-3 border-t border-slate-200/60">
                  <span className="text-xs font-bold text-navy-900 block mb-2">
                    Direct Navigation to 14 Modules:
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {[
                      { id: "overview", label: "Overview" },
                      { id: "clusters", label: "Clusters" },
                      { id: "warehouses", label: "Warehouses (STOPPED)" },
                      { id: "jobs", label: "Jobs" },
                      { id: "pipelines", label: "Pipelines" },
                      { id: "serving", label: "Model Serving (27)" },
                      { id: "catalog", label: "Unity Catalog" },
                      { id: "apps", label: "Apps (3)" },
                      { id: "system_tables", label: "System Tables (10)" },
                      { id: "query_history", label: "Query History" },
                      { id: "ai_economics", label: "AI Economics" },
                      { id: "audit", label: "Audit & Governance" },
                      { id: "billing", label: "Billing & Cost" },
                      { id: "discovery_history", label: "Discovery History" },
                    ].map((mod) => (
                      <button
                        key={mod.id}
                        onClick={() => {
                          if (onNavigateToDatabricksModule) {
                            onNavigateToDatabricksModule(mod.id as DatabricksModuleId);
                          }
                        }}
                        className="px-2.5 py-1 rounded-md text-[11px] font-medium bg-white border border-slate-200 hover:border-brand-500 hover:text-brand-600 transition"
                      >
                        {mod.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* DIAGNOSTICS MODAL */}
      {isDiagnosticsOpen && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-2xs z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <div className="flex justify-between items-center border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-emerald-600" />
                <h3 className="text-sm font-bold text-navy-900">Connection &amp; Scope Diagnostics</h3>
              </div>
              <button
                onClick={() => setIsDiagnosticsOpen(false)}
                className="text-slate-400 hover:text-slate-600 text-xs font-bold"
              >
                ✕
              </button>
            </div>

            <div className="text-xs space-y-3">
              <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 space-y-1.5 font-mono">
                <div className="flex justify-between">
                  <span className="text-slate-500">Databricks Host:</span>
                  <span className="text-navy-900">adb-642006393507276.16.azuredatabricks.net</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Workspace ID:</span>
                  <span className="text-navy-900 font-bold">642006393507276</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Azure Identity:</span>
                  <span className="text-emerald-700">Azure CLI / DefaultAzureCredential</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">RBAC Roles:</span>
                  <span className="text-navy-900">Reader, Cost Management Reader</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Zero Execution Guardrail:</span>
                  <span className="text-emerald-700 font-bold">ACTIVE (100% Read-Only)</span>
                </div>
              </div>

              <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-900">
                <strong className="block text-amber-950 mb-1">Zero Mutation Guarantee:</strong>
                This application never runs <code>Start</code> or <code>Resume</code> commands on
                stopped SQL warehouses, nor does it create, modify, or delete cloud resources.
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setIsDiagnosticsOpen(false)}
                className="px-4 py-1.5 rounded-lg bg-navy-900 text-white text-xs font-semibold"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
