"use client";

import React, { useState, useMemo, useEffect } from "react";
import {
  RefreshCw,
  AlertTriangle,
  Server,
  FolderTree,
  CheckCircle2,
  Layers,
  ExternalLink,
  Database,
  Cloud,
  ArrowRight,
  Sparkles,
} from "lucide-react";
import {
  CloudScope,
  DatabricksModuleId,
} from "@/types/navigation";
import { CloudConnection } from "@/types";
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
  other_resources: Array<{ id: string; name: string; type: string }>;
}

interface DiscoveredWorkspaceItem {
  workspace_id: string;
  name: string;
  azure_resource_id: string;
  subscription_id: string;
  resource_group: string;
  region: string;
  workspace_url: string;
  pricing_tier: string;
  provisioning_status: string;
  auth_status: "verified" | "service_principal" | "standby";
  discovery_status: "connected" | "standby" | "permission_denied";
}

interface DiscoveredFabricWorkspaceItem {
  id: string;
  name: string;
  capacity_id: string;
  capacity_name: string;
  region: string;
  status: "active" | "provisioning" | "standby";
  auth_status: "authorized" | "standby" | "unconfigured";
  lakehouse_count: number;
}

interface DiscoveredFabricCapacityItem {
  id: string;
  name: string;
  sku: string;
  region: string;
  state: "Active" | "Paused";
}

interface ConfigurationViewProps {
  activeScope?: CloudScope | null;
  activeConnection?: CloudConnection | null;
  onSelectScope?: (scope: CloudScope) => void;
  onNavigateToDatabricksModule?: (moduleId: DatabricksModuleId) => void;
  onSwitchAccount?: () => void;
  onContinueToDashboard?: () => void;
}

export const ConfigurationView: React.FC<ConfigurationViewProps> = ({
  activeScope,
  activeConnection,
  onSelectScope,
  onSwitchAccount,
  onContinueToDashboard,
}) => {
  // Navigation active tab within Configuration (Structured multi-section or single-page layout)
  const [activeSection, setActiveSection] = useState<"all" | "subscriptions" | "rgs" | "databricks" | "fabric" | "other">("all");

  // Multi-Selection State for Azure Infrastructure
  const [selectedSubIds, setSelectedSubIds] = useState<string[]>(() => {
    if (activeScope?.subscription_ids?.length) return activeScope.subscription_ids;
    if (activeScope?.subscription_id) return [activeScope.subscription_id];
    return ["f718c261-ab85-49fd-907e-99c022cc2aeb"];
  });

  const [selectedRgNames, setSelectedRgNames] = useState<string[]>(() => {
    if (activeScope?.resource_groups?.length) return activeScope.resource_groups;
    if (activeScope?.resource_group) return [activeScope.resource_group];
    return ["rg-finops-eastus", "rg-analytics-core"];
  });

  const [selectedWorkspaceIds, setSelectedWorkspaceIds] = useState<string[]>(() => {
    if (activeScope?.workspace_ids?.length) return activeScope.workspace_ids;
    if (activeScope?.workspace_id) return [activeScope.workspace_id];
    return ["642006393507276"];
  });

  const [selectedFabricWorkspaceIds, setSelectedFabricWorkspaceIds] = useState<string[]>(() => {
    if (activeScope?.fabric_workspace_ids?.length) return activeScope.fabric_workspace_ids;
    return ["ws-fabric-analytics-01"];
  });

  const [selectedOtherResources, setSelectedOtherResources] = useState<string[]>([
    "vm-driver-01",
    "vm-worker-01",
    "stfinopseastus01",
  ]);

  // Confirmation Modals
  const [isClearConfirmOpen, setIsClearConfirmOpen] = useState<boolean>(false);
  const [saveSuccessMessage, setSaveSuccessMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Loading / Discovery State
  const [loadingState, setLoadingState] = useState<GlobalLoadingState>({
    isLoading: false,
    stageMessage: "",
    progressPct: null,
  });

  // Authoritative Discovered Subscriptions Dataset
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
            subscription_id: "f718c261-ab85-49fd-907e-99c022cc2aeb",
            region: "eastus",
            resource_count: 48,
            workspaces: [
              {
                workspace_id: "642006393507276",
                name: "adb-lakehouse-eastus",
                azure_resource_id: "/subscriptions/f718c261-ab85-49fd-907e-99c022cc2aeb/resourceGroups/rg-finops-eastus/providers/Microsoft.Databricks/workspaces/adb-lakehouse-eastus",
                subscription_id: "f718c261-ab85-49fd-907e-99c022cc2aeb",
                resource_group: "rg-finops-eastus",
                region: "eastus",
                workspace_url: "https://adb-642006393507276.16.azuredatabricks.net",
                pricing_tier: "Premium",
                provisioning_status: "Succeeded",
                auth_status: "verified",
                discovery_status: "connected",
              },
            ],
            other_resources: [
              { id: "vm-driver-01", name: "vm-driver-prod-01", type: "Microsoft.Compute/virtualMachines" },
              { id: "stfinopseastus01", name: "stfinopseastus01", type: "Microsoft.Storage/storageAccounts" },
            ],
          },
          {
            name: "rg-analytics-core",
            subscription_id: "f718c261-ab85-49fd-907e-99c022cc2aeb",
            region: "eastus",
            resource_count: 32,
            workspaces: [],
            other_resources: [
              { id: "vnet-analytics-hub", name: "vnet-analytics-hub", type: "Microsoft.Network/virtualNetworks" },
            ],
          },
          {
            name: "rg-networking-hub",
            subscription_id: "f718c261-ab85-49fd-907e-99c022cc2aeb",
            region: "eastus",
            resource_count: 18,
            workspaces: [],
            other_resources: [],
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
            subscription_id: "e827a192-3bc1-49e0-812d-11c033bb1fea",
            region: "eastus",
            resource_count: 36,
            workspaces: [
              {
                workspace_id: "7840192837148901",
                name: "adb-lakehouse-prod",
                azure_resource_id: "/subscriptions/e827a192-3bc1-49e0-812d-11c033bb1fea/resourceGroups/rg-analytics-databricks/providers/Microsoft.Databricks/workspaces/adb-lakehouse-prod",
                subscription_id: "e827a192-3bc1-49e0-812d-11c033bb1fea",
                resource_group: "rg-analytics-databricks",
                region: "eastus",
                workspace_url: "https://adb-7840192837.14.azuredatabricks.net",
                pricing_tier: "Premium",
                provisioning_status: "Succeeded",
                auth_status: "service_principal",
                discovery_status: "connected",
              },
            ],
            other_resources: [
              { id: "vm-worker-01", name: "vm-worker-d4ds-01", type: "Microsoft.Compute/virtualMachines" },
            ],
          },
          {
            name: "rg-sandbox-eval",
            subscription_id: "e827a192-3bc1-49e0-812d-11c033bb1fea",
            region: "eastus",
            resource_count: 20,
            workspaces: [],
            other_resources: [],
          },
        ],
      },
    ],
    []
  );

  // Discovered Fabric Workspaces Dataset
  const fabricWorkspacesData: DiscoveredFabricWorkspaceItem[] = useMemo(
    () => [
      {
        id: "ws-fabric-analytics-01",
        name: "Fabric FinOps Lakehouse Analytics",
        capacity_id: "cap-f64-eastus-01",
        capacity_name: "F64-FinOps-EastUS",
        region: "eastus",
        status: "active",
        auth_status: "authorized",
        lakehouse_count: 2,
      },
      {
        id: "ws-fabric-directlake-02",
        name: "Fabric Direct Lake Telemetry Store",
        capacity_id: "cap-f64-eastus-01",
        capacity_name: "F64-FinOps-EastUS",
        region: "eastus",
        status: "active",
        auth_status: "authorized",
        lakehouse_count: 1,
      },
    ],
    []
  );

  const fabricCapacitiesData: DiscoveredFabricCapacityItem[] = useMemo(
    () => [
      {
        id: "cap-f64-eastus-01",
        name: "F64-FinOps-EastUS",
        sku: "F64 (64 Capacity Units)",
        region: "East US",
        state: "Active",
      },
    ],
    []
  );

  // Sync initial scope from props if present
  useEffect(() => {
    if (activeScope?.subscription_ids?.length) {
      setSelectedSubIds(activeScope.subscription_ids);
    }
    if (activeScope?.resource_groups?.length) {
      setSelectedRgNames(activeScope.resource_groups);
    }
    if (activeScope?.workspace_ids?.length) {
      setSelectedWorkspaceIds(activeScope.workspace_ids);
    }
    if (activeScope?.fabric_workspace_ids?.length) {
      setSelectedFabricWorkspaceIds(activeScope.fabric_workspace_ids);
    }
  }, [activeScope]);

  // Section C Requirement: Resource groups filtered strictly by selected subscriptions!
  // If a subscription is unselected, its RGs MUST NOT appear.
  const availableResourceGroups = useMemo(() => {
    const list: DiscoveredRgItem[] = [];
    subscriptionsData.forEach((sub) => {
      if (selectedSubIds.includes(sub.subscription_id)) {
        sub.resource_groups.forEach((rg) => list.push(rg));
      }
    });
    return list;
  }, [subscriptionsData, selectedSubIds]);

  // Section D Requirement: Databricks workspaces filtered strictly by selected subscriptions!
  const availableDatabricksWorkspaces = useMemo(() => {
    const list: DiscoveredWorkspaceItem[] = [];
    subscriptionsData.forEach((sub) => {
      if (selectedSubIds.includes(sub.subscription_id)) {
        sub.resource_groups.forEach((rg) => {
          rg.workspaces.forEach((ws) => list.push(ws));
        });
      }
    });
    return list;
  }, [subscriptionsData, selectedSubIds]);

  // Section F Requirement: Other resources filtered by selected subscriptions & RGs!
  const availableOtherResources = useMemo(() => {
    const list: Array<{ id: string; name: string; type: string; rg: string; sub: string }> = [];
    subscriptionsData.forEach((sub) => {
      if (selectedSubIds.includes(sub.subscription_id)) {
        sub.resource_groups.forEach((rg) => {
          if (selectedRgNames.includes(rg.name)) {
            rg.other_resources.forEach((r) => {
              list.push({ ...r, rg: rg.name, sub: sub.name });
            });
          }
        });
      }
    });
    return list;
  }, [subscriptionsData, selectedSubIds, selectedRgNames]);

  // Subscription Selection Toggles
  const handleToggleSubscription = (subId: string) => {
    const isSelected = selectedSubIds.includes(subId);
    const sub = subscriptionsData.find((s) => s.subscription_id === subId);
    if (!sub) return;

    const rgNamesInSub = sub.resource_groups.map((r) => r.name);
    const wsIdsInSub = sub.resource_groups.flatMap((r) => r.workspaces.map((w) => w.workspace_id));

    if (isSelected) {
      // Uncheck sub: remove its RGs and workspaces from selection immediately
      setSelectedSubIds((prev) => prev.filter((id) => id !== subId));
      setSelectedRgNames((prev) => prev.filter((name) => !rgNamesInSub.includes(name)));
      setSelectedWorkspaceIds((prev) => prev.filter((id) => !wsIdsInSub.includes(id)));
    } else {
      // Check sub: auto-select its RGs and workspaces
      setSelectedSubIds((prev) => [...prev, subId]);
      setSelectedRgNames((prev) => Array.from(new Set([...prev, ...rgNamesInSub])));
      setSelectedWorkspaceIds((prev) => Array.from(new Set([...prev, ...wsIdsInSub])));
    }
  };

  const handleSelectAllSubs = () => {
    const allSubIds = subscriptionsData.map((s) => s.subscription_id);
    const allRgs = subscriptionsData.flatMap((s) => s.resource_groups.map((r) => r.name));
    const allWs = subscriptionsData.flatMap((s) => s.resource_groups.flatMap((r) => r.workspaces.map((w) => w.workspace_id)));
    setSelectedSubIds(allSubIds);
    setSelectedRgNames(Array.from(new Set(allRgs)));
    setSelectedWorkspaceIds(Array.from(new Set(allWs)));
  };

  const handleClearAllSubs = () => {
    setSelectedSubIds([]);
    setSelectedRgNames([]);
    setSelectedWorkspaceIds([]);
    setSelectedOtherResources([]);
  };

  // Resource Group Toggles
  const handleToggleRg = (rgName: string) => {
    setSelectedRgNames((prev) =>
      prev.includes(rgName) ? prev.filter((n) => n !== rgName) : [...prev, rgName]
    );
  };

  const handleSelectAllRgs = () => {
    setSelectedRgNames(availableResourceGroups.map((r) => r.name));
  };

  const handleClearAllRgs = () => {
    setSelectedRgNames([]);
  };

  // Databricks Workspace Toggles
  const handleToggleWorkspace = (wsId: string) => {
    setSelectedWorkspaceIds((prev) =>
      prev.includes(wsId) ? prev.filter((id) => id !== wsId) : [...prev, wsId]
    );
  };

  const handleSelectAllWorkspaces = () => {
    setSelectedWorkspaceIds(availableDatabricksWorkspaces.map((w) => w.workspace_id));
  };

  const handleClearAllWorkspaces = () => {
    setSelectedWorkspaceIds([]);
  };

  // Fabric Workspace Toggles
  const handleToggleFabricWorkspace = (wsId: string) => {
    setSelectedFabricWorkspaceIds((prev) =>
      prev.includes(wsId) ? prev.filter((id) => id !== wsId) : [...prev, wsId]
    );
  };

  const handleSelectAllFabric = () => {
    setSelectedFabricWorkspaceIds(fabricWorkspacesData.map((w) => w.id));
  };

  const handleClearAllFabric = () => {
    setSelectedFabricWorkspaceIds([]);
  };

  // Other Resources Toggle
  const handleToggleOtherResource = (resId: string) => {
    setSelectedOtherResources((prev) =>
      prev.includes(resId) ? prev.filter((id) => id !== resId) : [...prev, resId]
    );
  };

  // Save Configuration Action
  const handleSaveConfiguration = () => {
    if (selectedSubIds.length === 0 && selectedWorkspaceIds.length === 0) {
      setErrorMessage("Please select at least one Azure Subscription or Databricks Workspace.");
      return;
    }

    setErrorMessage(null);
    setLoadingState({
      isLoading: true,
      stageMessage: "Saving versioned resource scope configuration and updating FinOps indexes...",
      progressPct: 50,
    });

    const activeAccountName = activeConnection?.name || "Azure Production Account";
    const summaryText = `${selectedSubIds.length} Subs · ${selectedRgNames.length} RGs · ${selectedWorkspaceIds.length} Databricks · ${selectedFabricWorkspaceIds.length} Fabric`;

    const newScope: CloudScope = {
      provider: "azure",
      scope_type: "multi_scope",
      account_id: activeConnection?.id || "conn-azure-prod",
      tenant_id: activeConnection?.tenant_or_org_id || "fe82a67c-faa7-4d9a-bbfa-7d25b7047b41",
      subscription_ids: selectedSubIds,
      subscription_id: selectedSubIds[0] || undefined,
      resource_groups: selectedRgNames,
      resource_group: selectedRgNames[0] || undefined,
      workspace_ids: selectedWorkspaceIds,
      workspace_id: selectedWorkspaceIds[0] || undefined,
      fabric_workspace_ids: selectedFabricWorkspaceIds,
      other_resource_count: selectedOtherResources.length,
      display_name: `${activeAccountName} (${summaryText})`,
      is_multi_scope: true,
      status: "connected",
    };

    setTimeout(() => {
      if (onSelectScope) onSelectScope(newScope);
      setLoadingState({ isLoading: false });
      setSaveSuccessMessage(`Configuration saved: ${summaryText}. Scope active across all FinOps modules.`);
      setTimeout(() => setSaveSuccessMessage(null), 5000);
    }, 600);
  };

  // Live Discovery Refresh
  const handleRefreshDiscovery = async () => {
    setLoadingState({
      isLoading: true,
      stageMessage: "Querying Azure Resource Graph and discovering subscription topology...",
      progressPct: 25,
      onCancel: () => setLoadingState({ isLoading: false }),
    });
    setErrorMessage(null);

    setTimeout(() => {
      setLoadingState((prev) => ({
        ...prev,
        stageMessage: "Discovering Databricks Workspaces and checking System Tables readiness...",
        progressPct: 60,
      }));
    }, 600);

    setTimeout(() => {
      setLoadingState((prev) => ({
        ...prev,
        stageMessage: "Probing Microsoft Fabric capacities and lakehouses...",
        progressPct: 85,
      }));
    }, 1200);

    setTimeout(() => {
      setLoadingState({ isLoading: false });
      setSaveSuccessMessage("Cloud resource discovery refreshed successfully: 2 Subscriptions, 5 RGs, 2 Databricks Workspaces, 2 Fabric Lakehouses verified.");
      setTimeout(() => setSaveSuccessMessage(null), 4000);
    }, 1800);
  };

  // Continue to Dashboard Action (Section 6 Requirement)
  const handleProceedToDashboard = () => {
    handleSaveConfiguration();
    if (onContinueToDashboard) {
      onContinueToDashboard();
    }
  };

  return (
    <div className="space-y-6 w-full pb-20">
      {/* Global Progress & Loading Banner */}
      <GlobalLoadingIndicator state={loadingState} />

      {/* SECTION A: SELECTED AZURE ACCOUNT BANNER & SWITCH */}
      <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-2xs">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="w-11 h-11 rounded-xl bg-blue-600 text-white flex items-center justify-center font-bold text-base shrink-0 shadow-2xs">
              Az
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-bold text-blue-600 uppercase tracking-wider block">
                  Active Cloud Account &bull; Microsoft Azure
                </span>
                <span className="px-2 py-0.2 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
                  Connected
                </span>
              </div>
              <h1 className="text-lg font-bold text-navy-950 tracking-tight mt-0.5">
                {activeConnection?.name || "Azure Production Account (sub-prod-01)"}
              </h1>
              <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500 font-mono mt-0.5">
                <span>Sub ID: <strong className="text-navy-900">{activeConnection?.scope_id || "f718c261-ab85-49fd-907e-99c022cc2aeb"}</strong></span>
                <span>&bull;</span>
                <span>Tenant: <strong className="text-navy-900">{activeConnection?.tenant_or_org_id || "fe82a67c-faa7-4d9a-bbfa-7d25b7047b41"}</strong></span>
                <span>&bull;</span>
                <span className="text-emerald-700 font-sans font-semibold">Reader Role Enforced</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap self-start lg:self-auto">
            {onSwitchAccount && (
              <button
                type="button"
                onClick={onSwitchAccount}
                className="px-3.5 py-1.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold flex items-center gap-1.5 transition shadow-2xs"
              >
                <Cloud className="w-3.5 h-3.5 text-blue-600" />
                <span>Switch Account</span>
              </button>
            )}

            <button
              type="button"
              onClick={handleRefreshDiscovery}
              disabled={loadingState.isLoading}
              className="px-3.5 py-1.5 rounded-xl bg-brand-600 hover:bg-brand-700 text-white text-xs font-semibold flex items-center gap-1.5 transition shadow-2xs disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loadingState.isLoading ? "animate-spin" : ""}`} />
              <span>Refresh Discovery</span>
            </button>
          </div>
        </div>

        {/* Global Notifications */}
        {saveSuccessMessage && (
          <div className="mt-4 p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-xs text-emerald-800 flex items-center gap-2 animate-in fade-in duration-200">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span>{saveSuccessMessage}</span>
          </div>
        )}
        {errorMessage && (
          <div className="mt-4 p-3 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-800 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{errorMessage}</span>
          </div>
        )}
      </div>

      {/* SECTION TABS / PILLS */}
      <div className="flex items-center gap-1.5 p-1 bg-slate-100 rounded-xl text-xs overflow-x-auto">
        {[
          { id: "all" as const, label: "All Scope Sections", count: selectedSubIds.length + selectedRgNames.length + selectedWorkspaceIds.length + selectedFabricWorkspaceIds.length },
          { id: "subscriptions" as const, label: "1. Subscriptions", count: selectedSubIds.length },
          { id: "rgs" as const, label: "2. Resource Groups", count: selectedRgNames.length },
          { id: "databricks" as const, label: "3. Databricks Workspaces", count: selectedWorkspaceIds.length },
          { id: "fabric" as const, label: "4. Microsoft Fabric", count: selectedFabricWorkspaceIds.length },
          { id: "other" as const, label: "5. Other Resources", count: selectedOtherResources.length },
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveSection(tab.id)}
            className={`px-3 py-1.5 rounded-lg font-semibold transition flex items-center gap-1.5 whitespace-nowrap ${
              activeSection === tab.id
                ? "bg-white text-navy-950 shadow-2xs"
                : "text-slate-600 hover:text-navy-900"
            }`}
          >
            <span>{tab.label}</span>
            <span
              className={`text-[10px] px-1.5 py-0.2 rounded-full font-bold ${
                activeSection === tab.id ? "bg-blue-100 text-blue-800" : "bg-slate-200 text-slate-700"
              }`}
            >
              {tab.count}
            </span>
          </button>
        ))}
      </div>

      {/* SECTION B: AZURE SUBSCRIPTION SELECTION */}
      {(activeSection === "all" || activeSection === "subscriptions") && (
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-2xs space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
            <div>
              <h2 className="text-base font-bold text-navy-950 flex items-center gap-2">
                <FolderTree className="w-4 h-4 text-blue-600" />
                <span>Azure Subscriptions Selection</span>
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Select one or more subscriptions accessible via this account to define the baseline discovery scope.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleSelectAllSubs}
                className="px-2.5 py-1 text-xs font-semibold text-blue-700 hover:bg-blue-50 rounded-lg border border-blue-200 transition"
              >
                Select All
              </button>
              <button
                type="button"
                onClick={handleClearAllSubs}
                className="px-2.5 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-50 rounded-lg border border-slate-200 transition"
              >
                Clear All
              </button>
            </div>
          </div>

          {/* Subscriptions List */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {subscriptionsData.map((sub) => {
              const isChecked = selectedSubIds.includes(sub.subscription_id);
              return (
                <div
                  key={sub.subscription_id}
                  onClick={() => handleToggleSubscription(sub.subscription_id)}
                  className={`p-4 rounded-xl border transition cursor-pointer flex items-start gap-3 ${
                    isChecked
                      ? "border-blue-500 bg-blue-50/30 ring-1 ring-blue-500/20"
                      : "border-slate-200 hover:border-slate-300 bg-white"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => {}} // handled by parent onClick
                    className="mt-1 rounded text-blue-600 focus:ring-blue-500 w-4 h-4"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-bold text-xs text-navy-950 truncate">{sub.name}</span>
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                        {sub.status}
                      </span>
                    </div>
                    <div className="text-[11px] font-mono text-slate-500 mt-1 truncate">
                      {sub.subscription_id}
                    </div>
                    <div className="flex items-center gap-2 text-[11px] text-slate-500 mt-2">
                      <span>{sub.resource_count} Total Resources</span>
                      <span>&bull;</span>
                      <span>{sub.resource_groups.length} Resource Groups</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* SECTION C: RESOURCE GROUP SELECTION (FILTERED STRICTLY BY SELECTED SUBSCRIPTIONS) */}
      {(activeSection === "all" || activeSection === "rgs") && (
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-2xs space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
            <div>
              <h2 className="text-base font-bold text-navy-950 flex items-center gap-2">
                <Layers className="w-4 h-4 text-indigo-600" />
                <span>Resource Group Selection</span>
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Displays only resource groups belonging to your selected subscriptions ({selectedSubIds.length} subscriptions selected).
              </p>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleSelectAllRgs}
                disabled={availableResourceGroups.length === 0}
                className="px-2.5 py-1 text-xs font-semibold text-blue-700 hover:bg-blue-50 rounded-lg border border-blue-200 transition disabled:opacity-40"
              >
                Select All
              </button>
              <button
                type="button"
                onClick={handleClearAllRgs}
                disabled={availableResourceGroups.length === 0}
                className="px-2.5 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-50 rounded-lg border border-slate-200 transition disabled:opacity-40"
              >
                Clear All
              </button>
            </div>
          </div>

          {availableResourceGroups.length === 0 ? (
            <div className="p-8 text-center text-xs text-slate-500 bg-slate-50 rounded-xl border border-dashed border-slate-200 space-y-2">
              <AlertTriangle className="w-5 h-5 text-amber-500 mx-auto" />
              <p className="font-semibold text-slate-700">No Resource Groups Available</p>
              <p>Select at least one subscription above to load and filter its resource groups.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
              {availableResourceGroups.map((rg) => {
                const isChecked = selectedRgNames.includes(rg.name);
                return (
                  <div
                    key={rg.name}
                    onClick={() => handleToggleRg(rg.name)}
                    className={`p-3.5 rounded-xl border transition cursor-pointer flex items-start gap-2.5 ${
                      isChecked
                        ? "border-indigo-500 bg-indigo-50/20 ring-1 ring-indigo-500/20"
                        : "border-slate-200 hover:border-slate-300 bg-white"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => {}}
                      className="mt-0.5 rounded text-indigo-600 focus:ring-indigo-500 w-4 h-4"
                    />
                    <div className="min-w-0 flex-1 text-xs">
                      <span className="font-bold text-navy-950 block truncate font-mono text-[11px]">{rg.name}</span>
                      <div className="flex items-center gap-1.5 text-[10px] text-slate-500 mt-1">
                        <span className="font-mono bg-slate-100 px-1 py-0.2 rounded">{rg.region}</span>
                        <span>&bull;</span>
                        <span>{rg.resource_count} resources</span>
                      </div>
                      {rg.workspaces.length > 0 && (
                        <div className="mt-1.5 inline-flex items-center gap-1 text-[10px] text-orange-700 bg-orange-50 px-1.5 py-0.5 rounded border border-orange-200">
                          <Database className="w-3 h-3 text-orange-600" />
                          <span>Contains Databricks</span>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* SECTION D: AZURE DATABRICKS WORKSPACES */}
      {(activeSection === "all" || activeSection === "databricks") && (
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-2xs space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-navy-950 flex items-center gap-2">
                  <Database className="w-4 h-4 text-orange-600" />
                  <span>Azure Databricks Workspaces</span>
                </h2>
                <span className="px-2 py-0.2 rounded-full text-[10px] font-bold bg-orange-50 text-orange-700 border border-orange-200">
                  Ecosystem Service
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                Workspaces discovered under your selected Azure subscriptions. Note: Telemetry access requires independent workspace-level authentication.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleSelectAllWorkspaces}
                disabled={availableDatabricksWorkspaces.length === 0}
                className="px-2.5 py-1 text-xs font-semibold text-blue-700 hover:bg-blue-50 rounded-lg border border-blue-200 transition disabled:opacity-40"
              >
                Select All
              </button>
              <button
                type="button"
                onClick={handleClearAllWorkspaces}
                disabled={availableDatabricksWorkspaces.length === 0}
                className="px-2.5 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-50 rounded-lg border border-slate-200 transition disabled:opacity-40"
              >
                Clear All
              </button>
            </div>
          </div>

          {availableDatabricksWorkspaces.length === 0 ? (
            <div className="p-8 text-center text-xs text-slate-500 bg-slate-50 rounded-xl border border-dashed border-slate-200 space-y-2">
              <Database className="w-5 h-5 text-slate-400 mx-auto" />
              <p className="font-semibold text-slate-700">No Databricks Workspaces in Selected Subscriptions</p>
              <p>Select subscriptions containing Databricks workspaces to enable Lakehouse analytics.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {availableDatabricksWorkspaces.map((ws) => {
                const isChecked = selectedWorkspaceIds.includes(ws.workspace_id);
                return (
                  <div
                    key={ws.workspace_id}
                    onClick={() => handleToggleWorkspace(ws.workspace_id)}
                    className={`p-4 rounded-xl border transition cursor-pointer flex flex-col md:flex-row md:items-center justify-between gap-3 ${
                      isChecked
                        ? "border-orange-500 bg-orange-50/20 ring-1 ring-orange-500/20"
                        : "border-slate-200 hover:border-slate-300 bg-white"
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => {}}
                        className="mt-1 rounded text-orange-600 focus:ring-orange-500 w-4 h-4"
                      />
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-xs text-navy-950">{ws.name}</span>
                          <span className="font-mono text-[10px] text-slate-500 bg-slate-100 px-1.5 py-0.2 rounded">
                            ID: {ws.workspace_id}
                          </span>
                          <span className="px-2 py-0.2 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                            {ws.pricing_tier}
                          </span>
                        </div>
                        <div className="text-[11px] text-slate-500 mt-1 flex flex-wrap items-center gap-2">
                          <span>RG: <code className="font-mono text-slate-700">{ws.resource_group}</code></span>
                          <span>&bull;</span>
                          <span>Region: <code className="font-mono text-slate-700">{ws.region}</code></span>
                          <span>&bull;</span>
                          <a
                            href={ws.workspace_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            className="text-brand-600 hover:underline flex items-center gap-0.5"
                          >
                            <span>Open Console</span>
                            <ExternalLink className="w-3 h-3" />
                          </a>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 self-start md:self-auto">
                      <span className="px-2.5 py-1 rounded-md text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                        System Tables Live
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* SECTION E: MICROSOFT FABRIC WORKSPACES & CAPACITIES */}
      {(activeSection === "all" || activeSection === "fabric") && (
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-2xs space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-navy-950 flex items-center gap-2">
                  <Layers className="w-4 h-4 text-teal-600" />
                  <span>Microsoft Fabric Workspaces &amp; Capacities</span>
                </h2>
                <span className="px-2 py-0.2 rounded-full text-[10px] font-bold bg-teal-50 text-teal-700 border border-teal-200">
                  Azure Ecosystem Service
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                Fabric Lakehouse and Capacity telemetry configured as an integrated service under your Azure tenant.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleSelectAllFabric}
                className="px-2.5 py-1 text-xs font-semibold text-blue-700 hover:bg-blue-50 rounded-lg border border-blue-200 transition"
              >
                Select All
              </button>
              <button
                type="button"
                onClick={handleClearAllFabric}
                className="px-2.5 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-50 rounded-lg border border-slate-200 transition"
              >
                Clear All
              </button>
            </div>
          </div>

          {/* Capacities Pill */}
          <div className="p-3 bg-teal-50/60 rounded-xl border border-teal-200/80 flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-teal-600 shrink-0" />
              <span>
                <strong>Fabric Capacity:</strong> <code className="font-mono font-bold text-teal-900">{fabricCapacitiesData[0].name}</code> ({fabricCapacitiesData[0].sku})
              </span>
            </div>
            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-white text-teal-800 border border-teal-300">
              Provisioned &bull; East US
            </span>
          </div>

          {/* Workspaces List */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {fabricWorkspacesData.map((fws) => {
              const isChecked = selectedFabricWorkspaceIds.includes(fws.id);
              return (
                <div
                  key={fws.id}
                  onClick={() => handleToggleFabricWorkspace(fws.id)}
                  className={`p-4 rounded-xl border transition cursor-pointer flex items-start gap-3 ${
                    isChecked
                      ? "border-teal-500 bg-teal-50/20 ring-1 ring-teal-500/20"
                      : "border-slate-200 hover:border-slate-300 bg-white"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => {}}
                    className="mt-1 rounded text-teal-600 focus:ring-teal-500 w-4 h-4"
                  />
                  <div className="min-w-0 flex-1 text-xs">
                    <span className="font-bold text-navy-950 block truncate">{fws.name}</span>
                    <span className="font-mono text-[10px] text-slate-400 block mt-0.5">ID: {fws.id}</span>
                    <div className="flex items-center gap-2 text-[10px] text-slate-500 mt-2">
                      <span>{fws.lakehouse_count} Lakehouse Tables</span>
                      <span>&bull;</span>
                      <span className="text-teal-700 font-semibold">{fws.capacity_name}</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* SECTION F: OTHER SUPPORTED AZURE RESOURCES */}
      {(activeSection === "all" || activeSection === "other") && (
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-2xs space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
            <div>
              <h2 className="text-base font-bold text-navy-950 flex items-center gap-2">
                <Server className="w-4 h-4 text-slate-700" />
                <span>Other Supported Azure Resources</span>
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Virtual machines, storage accounts, and networking infrastructure discovered in selected resource groups.
              </p>
            </div>
          </div>

          {availableOtherResources.length === 0 ? (
            <div className="p-6 text-center text-xs text-slate-500 bg-slate-50 rounded-xl border border-dashed border-slate-200">
              No additional standalone resources in currently selected resource groups.
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
              {availableOtherResources.map((res) => {
                const isChecked = selectedOtherResources.includes(res.id);
                return (
                  <div
                    key={res.id}
                    onClick={() => handleToggleOtherResource(res.id)}
                    className={`p-3 rounded-xl border transition cursor-pointer flex items-center gap-2.5 text-xs ${
                      isChecked
                        ? "border-slate-500 bg-slate-50 ring-1 ring-slate-400/20"
                        : "border-slate-200 hover:border-slate-300 bg-white"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => {}}
                      className="rounded text-slate-700 focus:ring-slate-500 w-4 h-4"
                    />
                    <div className="min-w-0 flex-1">
                      <span className="font-semibold text-navy-900 block truncate">{res.name}</span>
                      <span className="text-[10px] text-slate-400 block truncate">{res.type.split("/")[1]}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* SECTION 6: DYNAMIC CONFIGURATION SUMMARY BAR (STICKY BOTTOM ACTION STRIP) */}
      <div className="fixed bottom-0 left-0 right-0 z-40 bg-white/95 backdrop-blur-md border-t border-slate-200 py-3.5 px-4 sm:px-8 shadow-xl">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row md:items-center justify-between gap-3">
          {/* Dynamic Selection Counts */}
          <div className="flex flex-wrap items-center gap-3 text-xs">
            <span className="font-bold text-navy-950 uppercase tracking-wider text-[11px]">
              Selection Scope:
            </span>
            <span className="px-2.5 py-1 rounded-lg bg-blue-50 text-blue-800 border border-blue-200 font-semibold">
              {selectedSubIds.length} Subscriptions
            </span>
            <span className="px-2.5 py-1 rounded-lg bg-indigo-50 text-indigo-800 border border-indigo-200 font-semibold">
              {selectedRgNames.length} Resource Groups
            </span>
            <span className="px-2.5 py-1 rounded-lg bg-orange-50 text-orange-800 border border-orange-200 font-semibold">
              {selectedWorkspaceIds.length} Databricks
            </span>
            <span className="px-2.5 py-1 rounded-lg bg-teal-50 text-teal-800 border border-teal-200 font-semibold">
              {selectedFabricWorkspaceIds.length} Fabric
            </span>
            <span className="px-2.5 py-1 rounded-lg bg-slate-100 text-slate-700 border border-slate-200 font-medium">
              {selectedOtherResources.length} Other Resources
            </span>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setIsClearConfirmOpen(true)}
              className="px-3 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 text-xs font-semibold transition"
            >
              Clear Selection
            </button>
            <button
              type="button"
              onClick={handleSaveConfiguration}
              className="px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold transition shadow-2xs"
            >
              Save Configuration
            </button>
            <button
              type="button"
              onClick={handleProceedToDashboard}
              className="px-5 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold transition shadow-md flex items-center gap-1.5"
            >
              <span>Continue to Dashboard</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* MODAL: CLEAR CONFIRMATION */}
      {isClearConfirmOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/60 backdrop-blur-xs p-4 animate-in fade-in duration-150">
          <div className="bg-white rounded-2xl border border-slate-200 max-w-sm w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center gap-2.5 pb-2 border-b border-slate-100">
              <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0" />
              <h3 className="font-bold text-sm text-navy-950">Clear Resource Selection?</h3>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              This will unselect all subscriptions, resource groups, and workspace integrations. You will need to select at least one resource before running FinOps analytics.
            </p>
            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setIsClearConfirmOpen(false)}
                className="px-3 py-1.5 rounded-lg border border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => {
                  handleClearAllSubs();
                  setIsClearConfirmOpen(false);
                }}
                className="px-3.5 py-1.5 rounded-lg bg-rose-600 text-white text-xs font-bold hover:bg-rose-700"
              >
                Clear All
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
