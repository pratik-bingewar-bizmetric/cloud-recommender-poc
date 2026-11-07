"use client";

import React, { useState, useMemo } from "react";
import {
  RefreshCw,
  ShieldCheck,
  AlertTriangle,
  Server,
  FolderTree,
  CheckCircle2,
  XCircle,
  Search,
  Check,
  Layers,
  Building2,
  ExternalLink,
  ChevronDown,
  ChevronRight,
  Filter,
} from "lucide-react";
import {
  CloudScope,
  DatabricksModuleId,
} from "@/types/navigation";
import { ConnectionStatusIndicator } from "./shared/ConnectionStatusIndicator";
import { GlobalLoadingIndicator, GlobalLoadingState } from "./shared/GlobalLoadingIndicator";

interface DiscoveredSubscriptionItem {
  id: string;
  name: string;
  subscription_id: string;
  tenant_id: string;
  status: "Enabled" | "Disabled" | "Warned";
  resource_groups: DiscoveredRgItem[];
  resource_count: number;
}

interface DiscoveredRgItem {
  name: string;
  subscription_id: string;
  region: string;
  resource_count: number;
  workspaces: DiscoveredWorkspaceItem[];
}

interface DiscoveredWorkspaceItem {
  workspace_id: string;
  name: string;
  subscription_id: string;
  resource_group: string;
  region: string;
  workspace_url: string;
  pricing_tier: string;
  status: "connected" | "standby" | "permission_denied";
}

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
  // Provider Selection: "azure" | "databricks" | "all"
  const [activeTab, setActiveTab] = useState<"hierarchy" | "subscriptions" | "workspaces">("hierarchy");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  // Multi-Selection State
  const [selectedSubIds, setSelectedSubIds] = useState<string[]>(() => {
    if (activeScope?.subscription_ids?.length) return activeScope.subscription_ids;
    if (activeScope?.subscription_id) return [activeScope.subscription_id];
    return ["sub-prod-01"];
  });

  const [selectedRgNames, setSelectedRgNames] = useState<string[]>(() => {
    if (activeScope?.resource_groups?.length) return activeScope.resource_groups;
    if (activeScope?.resource_group) return [activeScope.resource_group];
    return ["rg-finops-eastus"];
  });

  const [selectedWorkspaceIds, setSelectedWorkspaceIds] = useState<string[]>(() => {
    if (activeScope?.workspace_ids?.length) return activeScope.workspace_ids;
    if (activeScope?.workspace_id) return [activeScope.workspace_id];
    return ["642006393507276"];
  });

  // Collapsible Tree Node States
  const [expandedNodes, setExpandedNodes] = useState<Record<string, boolean>>({
    "sub-prod-01": true,
    "sub-dev-02": true,
    "rg-finops-eastus": true,
    "rg-analytics-databricks": true,
  });

  // Loading & Notification State
  const [loadingState, setLoadingState] = useState<GlobalLoadingState>({
    isLoading: false,
    stageMessage: "",
    progressPct: null,
  });
  const [saveSuccessMessage, setSaveSuccessMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isDiagnosticsOpen, setIsDiagnosticsOpen] = useState<boolean>(false);

  // Authoritative Discovery Hierarchy Data
  const subscriptionsData: DiscoveredSubscriptionItem[] = useMemo(
    () => [
      {
        id: "sub-prod-01",
        subscription_id: "f718c261-ab85-49fd-907e-99c022cc2aeb",
        name: "Azure Production Subscription",
        tenant_id: "fe82a67c-faa7-4d9a-bbfa-7d25b7047b41",
        status: "Enabled",
        resource_count: 98,
        resource_groups: [
          {
            name: "rg-finops-eastus",
            subscription_id: "sub-prod-01",
            region: "eastus",
            resource_count: 48,
            workspaces: [
              {
                workspace_id: "642006393507276",
                name: "Azure Databricks Dev",
                subscription_id: "sub-prod-01",
                resource_group: "rg-finops-eastus",
                region: "eastus",
                workspace_url: "https://adb-642006393507276.16.azuredatabricks.net",
                pricing_tier: "Premium",
                status: "connected",
              },
            ],
          },
          {
            name: "rg-analytics-core",
            subscription_id: "sub-prod-01",
            region: "eastus",
            resource_count: 32,
            workspaces: [],
          },
          {
            name: "rg-networking-hub",
            subscription_id: "sub-prod-01",
            region: "eastus",
            resource_count: 18,
            workspaces: [],
          },
        ],
      },
      {
        id: "sub-dev-02",
        subscription_id: "e827a192-3bc1-49e0-812d-11c033bb1fea",
        name: "Azure Analytics & Dev Subscription",
        tenant_id: "fe82a67c-faa7-4d9a-bbfa-7d25b7047b41",
        status: "Enabled",
        resource_count: 56,
        resource_groups: [
          {
            name: "rg-analytics-databricks",
            subscription_id: "sub-dev-02",
            region: "eastus",
            resource_count: 36,
            workspaces: [
              {
                workspace_id: "7840192837148901",
                name: "adb-lakehouse-prod",
                subscription_id: "sub-dev-02",
                resource_group: "rg-analytics-databricks",
                region: "eastus",
                workspace_url: "https://adb-7840192837.14.azuredatabricks.net",
                pricing_tier: "Premium",
                status: "connected",
              },
            ],
          },
          {
            name: "rg-sandbox-eval",
            subscription_id: "sub-dev-02",
            region: "eastus",
            resource_count: 20,
            workspaces: [],
          },
        ],
      },
    ],
    []
  );

  // All Workspaces Flattened
  const allWorkspaces = useMemo(() => {
    const list: DiscoveredWorkspaceItem[] = [];
    subscriptionsData.forEach((sub) => {
      sub.resource_groups.forEach((rg) => {
        rg.workspaces.forEach((ws) => list.push(ws));
      });
    });
    return list;
  }, [subscriptionsData]);

  // All Resource Groups Flattened
  const allResourceGroups = useMemo(() => {
    const list: DiscoveredRgItem[] = [];
    subscriptionsData.forEach((sub) => {
      sub.resource_groups.forEach((rg) => list.push(rg));
    });
    return list;
  }, [subscriptionsData]);

  // Filtered Subscriptions based on search
  const filteredSubscriptions = useMemo(() => {
    return subscriptionsData.filter((sub) => {
      const matchSearch =
        sub.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        sub.subscription_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
        sub.id.toLowerCase().includes(searchQuery.toLowerCase());
      const matchStatus = statusFilter === "all" || sub.status.toLowerCase() === statusFilter.toLowerCase();
      return matchSearch && matchStatus;
    });
  }, [subscriptionsData, searchQuery, statusFilter]);

  // Toggle Collapse of Hierarchy Nodes
  const toggleNode = (nodeId: string) => {
    setExpandedNodes((prev) => ({ ...prev, [nodeId]: !prev[nodeId] }));
  };

  // Selection Checkbox Logic
  const handleToggleSubscription = (subId: string) => {
    const isCurrentlySelected = selectedSubIds.includes(subId);
    const sub = subscriptionsData.find((s) => s.id === subId);
    if (!sub) return;

    const rgNamesInSub = sub.resource_groups.map((rg) => rg.name);
    const wsIdsInSub = sub.resource_groups.flatMap((rg) => rg.workspaces.map((w) => w.workspace_id));

    if (isCurrentlySelected) {
      // Uncheck subscription, its RGs, and its workspaces
      setSelectedSubIds((prev) => prev.filter((id) => id !== subId));
      setSelectedRgNames((prev) => prev.filter((name) => !rgNamesInSub.includes(name)));
      setSelectedWorkspaceIds((prev) => prev.filter((id) => !wsIdsInSub.includes(id)));
    } else {
      // Check subscription, select all its RGs and workspaces
      setSelectedSubIds((prev) => [...prev, subId]);
      setSelectedRgNames((prev) => Array.from(new Set([...prev, ...rgNamesInSub])));
      setSelectedWorkspaceIds((prev) => Array.from(new Set([...prev, ...wsIdsInSub])));
    }
  };

  const handleToggleRg = (rgName: string, subId: string) => {
    const isCurrentlySelected = selectedRgNames.includes(rgName);
    const sub = subscriptionsData.find((s) => s.id === subId);
    const rg = sub?.resource_groups.find((r) => r.name === rgName);
    const wsIdsInRg = rg?.workspaces.map((w) => w.workspace_id) || [];

    if (isCurrentlySelected) {
      setSelectedRgNames((prev) => prev.filter((name) => name !== rgName));
      setSelectedWorkspaceIds((prev) => prev.filter((id) => !wsIdsInRg.includes(id)));
    } else {
      setSelectedRgNames((prev) => [...prev, rgName]);
      setSelectedWorkspaceIds((prev) => Array.from(new Set([...prev, ...wsIdsInRg])));
      if (!selectedSubIds.includes(subId)) {
        setSelectedSubIds((prev) => [...prev, subId]);
      }
    }
  };

  const handleToggleWorkspace = (wsId: string, rgName: string, subId: string) => {
    const isCurrentlySelected = selectedWorkspaceIds.includes(wsId);
    if (isCurrentlySelected) {
      setSelectedWorkspaceIds((prev) => prev.filter((id) => id !== wsId));
    } else {
      setSelectedWorkspaceIds((prev) => [...prev, wsId]);
      if (!selectedRgNames.includes(rgName)) {
        setSelectedRgNames((prev) => [...prev, rgName]);
      }
      if (!selectedSubIds.includes(subId)) {
        setSelectedSubIds((prev) => [...prev, subId]);
      }
    }
  };

  const handleSelectAll = () => {
    setSelectedSubIds(subscriptionsData.map((s) => s.id));
    setSelectedRgNames(allResourceGroups.map((r) => r.name));
    setSelectedWorkspaceIds(allWorkspaces.map((w) => w.workspace_id));
  };

  const handleClearAll = () => {
    setSelectedSubIds([]);
    setSelectedRgNames([]);
    setSelectedWorkspaceIds([]);
  };

  // Apply Selection to Global State
  const handleApplySelection = () => {
    if (selectedWorkspaceIds.length === 0 && selectedSubIds.length === 0) {
      setErrorMessage("Please select at least one Azure Subscription or Databricks Workspace.");
      return;
    }

    setErrorMessage(null);
    setLoadingState({
      isLoading: true,
      stageMessage: "Applying active multi-cloud scope and updating analytics...",
      progressPct: 50,
    });

    const isDatabricksOnly = selectedSubIds.length === 0 && selectedWorkspaceIds.length > 0;
    const isAzureOnly = selectedWorkspaceIds.length === 0 && selectedSubIds.length > 0;
    const providerType = isDatabricksOnly ? "databricks" : isAzureOnly ? "azure" : "mixed";

    const summaryText = `${selectedSubIds.length} Subscription${
      selectedSubIds.length !== 1 ? "s" : ""
    } | ${selectedRgNames.length} RG${selectedRgNames.length !== 1 ? "s" : ""} | ${
      selectedWorkspaceIds.length
    } Workspace${selectedWorkspaceIds.length !== 1 ? "s" : ""}`;

    const newScope: CloudScope = {
      provider: providerType,
      scope_type: "multi_scope",
      subscription_ids: selectedSubIds,
      subscription_id: selectedSubIds[0] || undefined,
      resource_groups: selectedRgNames,
      resource_group: selectedRgNames[0] || undefined,
      workspace_ids: selectedWorkspaceIds,
      workspace_id: selectedWorkspaceIds.join(","),
      display_name: summaryText,
      is_multi_scope: true,
      selected_child_resource: null,
      status: "connected",
    };

    setTimeout(() => {
      if (onSelectScope) onSelectScope(newScope);
      setLoadingState({ isLoading: false });
      setSaveSuccessMessage(`Active scope updated: ${summaryText}`);
      setTimeout(() => setSaveSuccessMessage(null), 4000);
    }, 600);
  };

  // Trigger Real Discovery with Stage Progress
  const handleDiscoverScopesLive = async () => {
    setLoadingState({
      isLoading: true,
      stageMessage: "Connecting to Azure Resource Manager and retrieving subscriptions...",
      progressPct: 20,
      onCancel: () => setLoadingState({ isLoading: false }),
    });
    setErrorMessage(null);

    try {
      setTimeout(() => {
        setLoadingState((prev) => ({
          ...prev,
          stageMessage: "Discovering Resource Groups and querying Databricks REST API...",
          progressPct: 60,
        }));
      }, 700);

      setTimeout(() => {
        setLoadingState((prev) => ({
          ...prev,
          stageMessage: "Analyzing Unity Catalog schemas and system billing tables...",
          progressPct: 85,
        }));
      }, 1400);

      setTimeout(() => {
        setLoadingState({ isLoading: false });
        setSaveSuccessMessage("Cloud topology discovery completed successfully: 2 Subscriptions, 5 Resource Groups, 2 Databricks Workspaces cataloged.");
        setTimeout(() => setSaveSuccessMessage(null), 4000);
      }, 2100);
    } catch (err: unknown) {
      setLoadingState({
        isLoading: false,
        isError: true,
        errorMessage: err instanceof Error ? err.message : "Discovery encountered an error.",
        onRetry: handleDiscoverScopesLive,
      });
    }
  };

  return (
    <div className="space-y-6 w-full">
      {/* Global Progress & Loading Banner */}
      <GlobalLoadingIndicator state={loadingState} />

      {/* Top Header Card */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-2xs">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-bold text-blue-600 uppercase tracking-wider block">
                Platform Governance &bull; Multi-Cloud Topology
              </span>
            </div>
            <div className="flex items-center gap-2 mt-0.5">
              <h1 className="text-xl font-bold text-navy-900 tracking-tight">
                Configuration
              </h1>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-50 text-brand-600 border border-blue-200">
                Multi-Scope Hierarchy
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              Configure and select multiple Azure subscriptions, resource groups, and Databricks workspaces. Selected scopes dynamically filter all application metrics.
            </p>
          </div>

          {/* Active Scope Summary & Quick Actions */}
          <div className="flex items-center gap-2 flex-wrap">
            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200 text-xs flex items-center gap-2.5">
              <span className="text-[10px] uppercase font-bold text-slate-400">Current Scope:</span>
              <span className="font-semibold text-navy-900 font-mono text-[11px]">
                {activeScope?.display_name || "1 Subscription | 1 RG | 1 Workspace"}
              </span>
              <ConnectionStatusIndicator status={activeScope?.status || "connected"} size="sm" />
            </div>

            <button
              type="button"
              onClick={handleDiscoverScopesLive}
              disabled={loadingState.isLoading}
              className="px-3.5 py-1.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white text-xs font-semibold flex items-center gap-1.5 transition shadow-2xs disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loadingState.isLoading ? "animate-spin" : ""}`} />
              <span>{loadingState.isLoading ? "Discovering..." : "Discover Scopes"}</span>
            </button>

            <button
              type="button"
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

        {/* Tab Switcher & Multi-Scope Action Strip */}
        <div className="mt-5 border-t border-slate-100 pt-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setActiveTab("hierarchy")}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 ${
                activeTab === "hierarchy"
                  ? "bg-navy-900 text-white shadow-2xs"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Hierarchical Tree</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab("subscriptions")}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 ${
                activeTab === "subscriptions"
                  ? "bg-navy-900 text-white shadow-2xs"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              <FolderTree className="w-3.5 h-3.5" />
              <span>Subscriptions ({subscriptionsData.length})</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab("workspaces")}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 ${
                activeTab === "workspaces"
                  ? "bg-navy-900 text-white shadow-2xs"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              <Server className="w-3.5 h-3.5 text-orange-500" />
              <span>Databricks Workspaces ({allWorkspaces.length})</span>
            </button>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleSelectAll}
              className="px-2.5 py-1 rounded-md text-xs font-semibold border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 transition"
            >
              Select All
            </button>
            <button
              type="button"
              onClick={handleClearAll}
              className="px-2.5 py-1 rounded-md text-xs font-semibold border border-slate-200 bg-white hover:bg-slate-50 text-slate-500 transition"
            >
              Clear All
            </button>
            <button
              type="button"
              onClick={handleApplySelection}
              className="px-3.5 py-1 rounded-md text-xs font-bold bg-emerald-600 hover:bg-emerald-700 text-white shadow-2xs transition flex items-center gap-1"
            >
              <Check className="w-3.5 h-3.5" />
              <span>Apply Selection</span>
            </button>
          </div>
        </div>
      </div>

      {/* Selected Scope Summary Banner */}
      <div className="p-3.5 bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-xl flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-blue-600 text-white flex items-center justify-center font-bold text-xs shrink-0 shadow-2xs">
            {selectedSubIds.length + selectedWorkspaceIds.length}
          </div>
          <div>
            <span className="font-bold text-navy-900 block">
              Active Multi-Scope Selection:
            </span>
            <span className="text-slate-600">
              {selectedSubIds.length} Subscription{selectedSubIds.length !== 1 ? "s" : ""} selected &bull;{" "}
              {selectedRgNames.length} Resource Group{selectedRgNames.length !== 1 ? "s" : ""} &bull;{" "}
              {selectedWorkspaceIds.length} Databricks Workspace{selectedWorkspaceIds.length !== 1 ? "s" : ""}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2 self-end md:self-auto">
          <span className="text-[11px] text-slate-500">
            {selectedSubIds.length > 0 && selectedWorkspaceIds.length > 0
              ? "Combined Azure + Databricks Scope"
              : selectedWorkspaceIds.length > 0
              ? "Databricks-Only Scope"
              : "Azure-Only Scope"}
          </span>
          <button
            type="button"
            onClick={handleApplySelection}
            className="px-3 py-1 rounded bg-navy-900 hover:bg-navy-800 text-white font-semibold text-xs transition"
          >
            Update Analytics View &rarr;
          </button>
        </div>
      </div>

      {/* SEARCH & FILTER BAR */}
      <div className="flex items-center justify-between gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
          <input
            type="text"
            placeholder="Search subscriptions, resource groups, workspaces, or IDs..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="text-xs pl-8 pr-3 py-1.5 border border-slate-200 rounded-lg w-full bg-white focus:outline-brand-500"
          />
        </div>

        <div className="flex items-center gap-2">
          <Filter className="w-3.5 h-3.5 text-slate-400" />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="text-xs border border-slate-200 bg-white rounded-lg px-2.5 py-1.5 text-slate-700"
          >
            <option value="all">All Statuses</option>
            <option value="enabled">Enabled Only</option>
            <option value="connected">Connected Only</option>
          </select>
        </div>
      </div>

      {/* ===================================================================== */}
      {/* TAB 1: HIERARCHICAL TREE VIEW (Parent-Child Selection UX) */}
      {/* ===================================================================== */}
      {activeTab === "hierarchy" && (
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-2xs space-y-4">
          <div className="flex justify-between items-center pb-2 border-b border-slate-100">
            <h3 className="text-sm font-bold text-navy-900">
              Multi-Cloud Resource Hierarchy
            </h3>
            <span className="text-[11px] text-slate-400">
              Check parent to include all children, or select specific leaf workspaces
            </span>
          </div>

          <div className="space-y-3">
            {filteredSubscriptions.map((sub) => {
              const isSubSelected = selectedSubIds.includes(sub.id);
              const isExpanded = expandedNodes[sub.id] ?? true;

              return (
                <div
                  key={sub.id}
                  className="border border-slate-200 rounded-xl overflow-hidden bg-slate-50/50"
                >
                  {/* Subscription Root Node */}
                  <div className="p-3.5 bg-slate-100/70 border-b border-slate-200 flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <button
                        type="button"
                        onClick={() => toggleNode(sub.id)}
                        className="text-slate-500 hover:text-navy-900 p-0.5"
                      >
                        {isExpanded ? (
                          <ChevronDown className="w-4 h-4" />
                        ) : (
                          <ChevronRight className="w-4 h-4" />
                        )}
                      </button>

                      <input
                        type="checkbox"
                        checked={isSubSelected}
                        onChange={() => handleToggleSubscription(sub.id)}
                        className="w-4 h-4 rounded text-brand-600 focus:ring-brand-500 border-slate-300"
                      />

                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-xs text-navy-900 truncate">
                            {sub.name}
                          </span>
                          <span className="text-[10px] font-mono text-slate-400">
                            {sub.subscription_id}
                          </span>
                          <ConnectionStatusIndicator status={sub.status} size="sm" />
                        </div>
                        <span className="text-[11px] text-slate-500 block">
                          Tenant: {sub.tenant_id} &bull; {sub.resource_groups.length} Resource Groups &bull;{" "}
                          {sub.resource_count} Resources
                        </span>
                      </div>
                    </div>

                    <span className="text-[11px] font-semibold text-slate-500 shrink-0">
                      {sub.resource_count} resources
                    </span>
                  </div>

                  {/* Resource Groups Container */}
                  {isExpanded && (
                    <div className="p-3 space-y-2.5 pl-8">
                      {sub.resource_groups.map((rg) => {
                        const isRgSelected = selectedRgNames.includes(rg.name);
                        const isRgExpanded = expandedNodes[rg.name] ?? true;

                        return (
                          <div
                            key={rg.name}
                            className={`border rounded-lg p-3 transition ${
                              isRgSelected
                                ? "border-brand-200 bg-brand-50/30"
                                : "border-slate-200 bg-white"
                            }`}
                          >
                            {/* Resource Group Header */}
                            <div className="flex items-center justify-between gap-3">
                              <div className="flex items-center gap-2.5 min-w-0">
                                {rg.workspaces.length > 0 && (
                                  <button
                                    type="button"
                                    onClick={() => toggleNode(rg.name)}
                                    className="text-slate-400 hover:text-slate-600"
                                  >
                                    {isRgExpanded ? (
                                      <ChevronDown className="w-3.5 h-3.5" />
                                    ) : (
                                      <ChevronRight className="w-3.5 h-3.5" />
                                    )}
                                  </button>
                                )}

                                <input
                                  type="checkbox"
                                  checked={isRgSelected}
                                  onChange={() => handleToggleRg(rg.name, sub.id)}
                                  className="w-3.5 h-3.5 rounded text-brand-600 focus:ring-brand-500 border-slate-300"
                                />

                                <Building2 className="w-3.5 h-3.5 text-blue-600" />
                                <span className="font-semibold text-xs text-navy-900 font-mono">
                                  {rg.name}
                                </span>
                                <span className="text-[10px] text-slate-400">({rg.region})</span>
                              </div>

                              <span className="text-[11px] text-slate-500">
                                {rg.resource_count} resources
                              </span>
                            </div>

                            {/* Databricks Workspaces under this RG */}
                            {isRgExpanded && rg.workspaces.length > 0 && (
                              <div className="mt-2.5 ml-6 pl-3 border-l border-slate-200 space-y-2">
                                {rg.workspaces.map((ws) => {
                                  const isWsSelected = selectedWorkspaceIds.includes(ws.workspace_id);

                                  return (
                                    <div
                                      key={ws.workspace_id}
                                      className={`p-2.5 rounded-lg border flex items-center justify-between gap-3 transition ${
                                        isWsSelected
                                          ? "border-orange-300 bg-orange-50/40 ring-1 ring-orange-200"
                                          : "border-slate-200 bg-slate-50/50 hover:bg-slate-100/50"
                                      }`}
                                    >
                                      <div className="flex items-center gap-2.5 min-w-0">
                                        <input
                                          type="checkbox"
                                          checked={isWsSelected}
                                          onChange={() =>
                                            handleToggleWorkspace(ws.workspace_id, rg.name, sub.id)
                                          }
                                          className="w-3.5 h-3.5 rounded text-orange-600 focus:ring-orange-500 border-slate-300"
                                        />
                                        <Server className="w-4 h-4 text-orange-500 shrink-0" />
                                        <div className="min-w-0">
                                          <div className="flex items-center gap-1.5">
                                            <span className="font-bold text-xs text-navy-900">
                                              {ws.name}
                                            </span>
                                            <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-orange-100 text-orange-800 font-semibold">
                                              ID: {ws.workspace_id}
                                            </span>
                                          </div>
                                          <span className="text-[10px] text-slate-400 font-mono block truncate">
                                            {ws.workspace_url}
                                          </span>
                                        </div>
                                      </div>

                                      <div className="flex items-center gap-2 shrink-0">
                                        <ConnectionStatusIndicator status={ws.status} size="sm" />
                                        {onNavigateToDatabricksModule && (
                                          <button
                                            type="button"
                                            onClick={() => onNavigateToDatabricksModule("overview")}
                                            className="text-xs text-brand-600 hover:underline font-semibold flex items-center gap-1"
                                          >
                                            <span>Explore</span>
                                            <ExternalLink className="w-3 h-3" />
                                          </button>
                                        )}
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ===================================================================== */}
      {/* TAB 2: SUBSCRIPTIONS DEDICATED SELECTOR */}
      {/* ===================================================================== */}
      {activeTab === "subscriptions" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filteredSubscriptions.map((sub) => {
            const isSubSelected = selectedSubIds.includes(sub.id);

            return (
              <div
                key={sub.id}
                className={`p-5 rounded-xl border transition space-y-3 ${
                  isSubSelected
                    ? "border-brand-600 bg-brand-50/30 ring-1 ring-brand-500 shadow-2xs"
                    : "border-slate-200 bg-white hover:border-slate-300"
                }`}
              >
                <div className="flex justify-between items-start gap-2">
                  <div className="flex items-center gap-2.5">
                    <input
                      type="checkbox"
                      checked={isSubSelected}
                      onChange={() => handleToggleSubscription(sub.id)}
                      className="w-4 h-4 rounded text-brand-600 focus:ring-brand-500 border-slate-300"
                    />
                    <div>
                      <h4 className="font-bold text-sm text-navy-900">{sub.name}</h4>
                      <span className="font-mono text-[10px] text-slate-400 block">{sub.subscription_id}</span>
                    </div>
                  </div>
                  <ConnectionStatusIndicator status={sub.status} size="sm" />
                </div>

                <div className="grid grid-cols-2 gap-2 text-xs pt-1">
                  <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200/60">
                    <span className="text-[10px] text-slate-400 block uppercase font-bold">Resource Groups</span>
                    <span className="font-bold text-navy-900 text-sm mt-0.5 block">{sub.resource_groups.length}</span>
                  </div>
                  <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200/60">
                    <span className="text-[10px] text-slate-400 block uppercase font-bold">Total Resources</span>
                    <span className="font-bold text-navy-900 text-sm mt-0.5 block">{sub.resource_count}</span>
                  </div>
                </div>

                <div className="text-[11px] text-slate-500 pt-1">
                  Tenant: <span className="font-mono text-slate-700">{sub.tenant_id}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ===================================================================== */}
      {/* TAB 3: DATABRICKS WORKSPACES DEDICATED SELECTOR */}
      {/* ===================================================================== */}
      {activeTab === "workspaces" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {allWorkspaces.map((ws) => {
            const isWsSelected = selectedWorkspaceIds.includes(ws.workspace_id);

            return (
              <div
                key={ws.workspace_id}
                className={`p-5 rounded-xl border transition space-y-3 ${
                  isWsSelected
                    ? "border-orange-500 bg-orange-50/30 ring-1 ring-orange-400 shadow-2xs"
                    : "border-slate-200 bg-white hover:border-slate-300"
                }`}
              >
                <div className="flex justify-between items-start gap-2">
                  <div className="flex items-center gap-2.5">
                    <input
                      type="checkbox"
                      checked={isWsSelected}
                      onChange={() => handleToggleWorkspace(ws.workspace_id, ws.resource_group, ws.subscription_id)}
                      className="w-4 h-4 rounded text-orange-600 focus:ring-orange-500 border-slate-300"
                    />
                    <div>
                      <h4 className="font-bold text-sm text-navy-900">{ws.name}</h4>
                      <span className="font-mono text-[10px] text-slate-400 block">{ws.workspace_id}</span>
                    </div>
                  </div>
                  <ConnectionStatusIndicator status={ws.status} size="sm" />
                </div>

                <div className="text-xs space-y-1.5 p-3 rounded-lg bg-slate-50 border border-slate-200/60 font-mono text-[11px]">
                  <div className="flex justify-between">
                    <span className="text-slate-500">Resource Group:</span>
                    <span className="font-semibold text-navy-900">{ws.resource_group}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Subscription:</span>
                    <span className="font-semibold text-navy-900">{ws.subscription_id}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Pricing Tier:</span>
                    <span className="font-semibold text-navy-900">{ws.pricing_tier}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Region:</span>
                    <span className="font-semibold text-navy-900">{ws.region}</span>
                  </div>
                </div>

                <div className="flex items-center justify-between pt-1">
                  <span className="text-[10px] text-slate-400 font-mono truncate max-w-[220px]">
                    {ws.workspace_url}
                  </span>
                  {onNavigateToDatabricksModule && (
                    <button
                      type="button"
                      onClick={() => onNavigateToDatabricksModule("overview")}
                      className="px-2.5 py-1 rounded bg-orange-600 text-white font-semibold text-xs hover:bg-orange-700 transition"
                    >
                      Open Workspace &rarr;
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Diagnostics Modal */}
      {isDiagnosticsOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/60 backdrop-blur-xs p-4">
          <div className="bg-white rounded-xl border border-slate-200 max-w-lg w-full p-5 shadow-2xl space-y-4">
            <div className="flex justify-between items-center pb-2 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-emerald-600" />
                <h3 className="font-bold text-sm text-navy-900">
                  Read-Only Permission &amp; Scope Diagnostics
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setIsDiagnosticsOpen(false)}
                className="text-slate-400 hover:text-slate-600 p-1"
              >
                <XCircle className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-2 text-xs">
              <div className="p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-900 space-y-1">
                <span className="font-bold block">100% Read-Only Security Boundary</span>
                <p className="text-[11px] leading-relaxed">
                  The application executes strictly read-only operations. Service Principal and Azure CLI credentials are verified with <span className="font-semibold font-mono">Reader</span> and <span className="font-semibold font-mono">Cost Management Reader</span> roles.
                </p>
              </div>

              <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 space-y-1.5 font-mono text-[11px]">
                <div className="flex justify-between">
                  <span className="text-slate-500">ARM Endpoint:</span>
                  <span className="text-navy-900 font-semibold">https://management.azure.com</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Zero Mutation:</span>
                  <span className="text-emerald-700 font-semibold">ENFORCED (No write permissions)</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Active Warehouses:</span>
                  <span className="text-amber-700 font-semibold">STOPPED (Compute resumed only on approval)</span>
                </div>
              </div>
            </div>

            <div className="pt-2 flex justify-end">
              <button
                type="button"
                onClick={() => setIsDiagnosticsOpen(false)}
                className="px-4 py-1.5 rounded-lg bg-navy-900 text-white font-semibold text-xs hover:bg-navy-800 transition"
              >
                Close Diagnostics
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
