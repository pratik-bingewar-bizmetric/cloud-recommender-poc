"use client";

import React, { useState, useEffect, useMemo, useCallback } from "react";
import {
  Layers,
  Search,
  CheckSquare,
  Square,
  MinusSquare,
  ChevronRight,
  ChevronDown,
  RefreshCw,
  Save,
  ShieldCheck,
  AlertTriangle,
  Database,
  Cloud,
  Server,
  FolderTree,
  ExternalLink,
  CheckCircle2,
  Sparkles,
  SlidersHorizontal,
  Play,
  RotateCcw,
  History,
  Clock,
  XCircle,
} from "lucide-react";
import {
  CloudConnection,
  CloudProvider,
  ScopeDiscoveryNode,
  ScopeDiscoveryResponse,
  ConfiguredScopeItemCreate,
  ResourceConfigurationResponse,
  ConfigurationStatusResponse,
  IngestionReadinessResponse,
  IngestionRunSummaryResponse,
} from "@/types";
import {
  listConnections,
  discoverScopes,
  getConfiguration,
  saveConfiguration,
  getConfigurationStatus,
  checkIngestionReadiness,
  triggerIngestionRun,
  listIngestionRuns,
  retryIngestionRun,
} from "@/lib/api";

interface ConfigurationViewProps {
  activeConnection?: CloudConnection | null;
  onSelectConnection?: (conn: CloudConnection) => void;
}

export const ConfigurationView: React.FC<ConfigurationViewProps> = ({
  activeConnection,
  onSelectConnection,
}) => {
  // Provider and Connection State
  const [selectedProvider, setSelectedProvider] = useState<CloudProvider>("azure");
  const [availableConnections, setAvailableConnections] = useState<CloudConnection[]>([]);
  const [currentConnectionId, setCurrentConnectionId] = useState<string>(
    activeConnection?.id || "azure-f718c261"
  );

  // Discovery & Configuration Data
  const [isDiscovering, setIsDiscovering] = useState<boolean>(false);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [discoveryResponse, setDiscoveryResponse] = useState<ScopeDiscoveryResponse | null>(null);
  const [configStatus, setConfigStatus] = useState<ConfigurationStatusResponse | null>(null);
  const [configVersion, setConfigVersion] = useState<number>(1);
  const [saveSuccessMessage, setSaveSuccessMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Ingestion State (Phase 2C)
  const [readiness, setReadiness] = useState<IngestionReadinessResponse | null>(null);
  const [ingestionRuns, setIngestionRuns] = useState<IngestionRunSummaryResponse[]>([]);
  const [isIngesting, setIsIngesting] = useState<boolean>(false);
  const [ingestionMessage, setIngestionMessage] = useState<string | null>(null);

  // Tree UI State
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  
  // Selection State: Map of scope_identifier -> "included" | "excluded" | "all_children"
  const [selectionMap, setSelectionMap] = useState<Map<string, "included" | "excluded" | "all_children">>(
    new Map()
  );

  // Load available connections
  useEffect(() => {
    let isMounted = true;
    async function fetchConnections() {
      try {
        const conns = await listConnections();
        if (isMounted) {
          setAvailableConnections(conns);
          const matching = conns.find((c) => c.provider === selectedProvider);
          if (matching && (!currentConnectionId || !conns.some((c) => c.id === currentConnectionId))) {
            setCurrentConnectionId(matching.id);
          }
        }
      } catch (err: any) {
        console.warn("[ConfigurationView] Failed to load connections:", err);
      }
    }
    fetchConnections();
    return () => {
      isMounted = false;
    };
  }, [selectedProvider]);

  // Synchronize when activeConnection prop changes
  useEffect(() => {
    if (activeConnection) {
      setCurrentConnectionId(activeConnection.id);
      setSelectedProvider(activeConnection.provider);
    }
  }, [activeConnection]);

  // Fetch active configuration and status for connection
  const loadActiveConfig = useCallback(async (connId: string) => {
    try {
      const [cfg, stat, readyRes, runsRes] = await Promise.allSettled([
        getConfiguration(connId),
        getConfigurationStatus(connId),
        checkIngestionReadiness(connId),
        listIngestionRuns(connId, 10),
      ]);

      if (stat.status === "fulfilled") {
        setConfigStatus(stat.value);
      }

      if (readyRes.status === "fulfilled") {
        setReadiness(readyRes.value);
      }

      if (runsRes.status === "fulfilled") {
        setIngestionRuns(runsRes.value);
      }

      if (cfg.status === "fulfilled" && cfg.value) {
        setConfigVersion(cfg.value.configuration_version);
        const newMap = new Map<string, "included" | "excluded" | "all_children">();
        for (const it of cfg.value.scope_items) {
          newMap.set(it.scope_identifier, it.selection_state as any);
        }
        setSelectionMap(newMap);
      } else {
        // No saved configuration yet
        setConfigVersion(1);
      }
    } catch (err) {
      console.warn("[ConfigurationView] Error loading configuration:", err);
    }
  }, []);

  // Trigger scope-aware ingestion
  const handleTriggerIngest = async () => {
    if (!currentConnectionId) return;
    setIsIngesting(true);
    setIngestionMessage(null);
    setErrorMessage(null);
    try {
      const run = await triggerIngestionRun(currentConnectionId);
      setIngestionMessage(
        `Ingestion run ${run.run_id.slice(0, 8)} (${run.status}) completed: ${run.successful_resources_count} of ${run.total_resources_scoped} resources successfully ingested under configuration v${run.configuration_version}.`
      );
      await loadActiveConfig(currentConnectionId);
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to execute ingestion run.");
    } finally {
      setIsIngesting(false);
    }
  };

  // Retry failed run
  const handleRetryIngest = async (runId: string) => {
    setIsIngesting(true);
    setIngestionMessage(null);
    setErrorMessage(null);
    try {
      const run = await retryIngestionRun(runId);
      setIngestionMessage(
        `Retry for run ${runId.slice(0, 8)} finished with status ${run.status} (${run.successful_resources_count}/${run.total_resources_scoped} succeeded).`
      );
      await loadActiveConfig(currentConnectionId);
    } catch (err: any) {
      setErrorMessage(err.message || "Retry failed.");
    } finally {
      setIsIngesting(false);
    }
  };

  // Perform resource discovery
  const handleDiscover = useCallback(
    async (connId: string, provider: string) => {
      setIsDiscovering(true);
      setErrorMessage(null);
      setSaveSuccessMessage(null);
      try {
        const resp = await discoverScopes(connId, provider);
        setDiscoveryResponse(resp);

        // Auto-expand root subscriptions
        const rootIds = new Set<string>();
        for (const root of resp.tree) {
          rootIds.add(root.id);
          for (const child of root.children || []) {
            rootIds.add(child.id);
          }
        }
        setExpandedNodes(rootIds);

        // Load existing active configuration
        await loadActiveConfig(connId);
      } catch (err: any) {
        setErrorMessage(err.message || "Failed to discover cloud resources.");
      } finally {
        setIsDiscovering(false);
      }
    },
    [loadActiveConfig]
  );

  // Trigger discovery on mount or connection change
  useEffect(() => {
    if (currentConnectionId) {
      handleDiscover(currentConnectionId, selectedProvider);
    }
  }, [currentConnectionId, selectedProvider, handleDiscover]);

  // Toggle tree node expansion
  const toggleExpand = (nodeId: string) => {
    setExpandedNodes((prev) => {
      const next = new Set(prev);
      if (next.has(nodeId)) {
        next.delete(nodeId);
      } else {
        next.add(nodeId);
      }
      return next;
    });
  };

  const expandAll = () => {
    if (!discoveryResponse) return;
    const all = new Set<string>();
    function collect(nodes: ScopeDiscoveryNode[]) {
      for (const n of nodes) {
        all.add(n.id);
        if (n.children && n.children.length > 0) {
          collect(n.children);
        }
      }
    }
    collect(discoveryResponse.tree);
    setExpandedNodes(all);
  };

  const collapseAll = () => {
    setExpandedNodes(new Set());
  };

  // Helper to collect all leaf resources under a node
  const collectLeaves = useCallback((node: ScopeDiscoveryNode): ScopeDiscoveryNode[] => {
    let leaves: ScopeDiscoveryNode[] = [];
    if (node.is_leaf || !node.children || node.children.length === 0) {
      leaves.push(node);
    } else {
      for (const ch of node.children) {
        leaves = leaves.concat(collectLeaves(ch));
      }
    }
    return leaves;
  }, []);

  // Determine effective node check state: "checked" | "unchecked" | "indeterminate"
  const getNodeCheckState = useCallback(
    (node: ScopeDiscoveryNode): "checked" | "unchecked" | "indeterminate" => {
      const directState = selectionMap.get(node.scope_identifier);
      if (directState === "excluded") return "unchecked";
      if (directState === "all_children") return "checked";

      // If it's a leaf
      if (node.is_leaf || !node.children || node.children.length === 0) {
        if (directState === "included") return "checked";
        return "unchecked";
      }

      // If parent container: aggregate children
      const leaves = collectLeaves(node);
      if (leaves.length === 0) return "unchecked";

      let checkedCount = 0;
      for (const lf of leaves) {
        const lfState = selectionMap.get(lf.scope_identifier);
        if (lfState === "included" || directState === "all_children") {
          if (lfState !== "excluded") checkedCount++;
        }
      }

      if (checkedCount === 0) return "unchecked";
      if (checkedCount === leaves.length) return "checked";
      return "indeterminate";
    },
    [selectionMap, collectLeaves]
  );

  // Toggle node selection
  const handleToggleSelect = (node: ScopeDiscoveryNode) => {
    const currentState = getNodeCheckState(node);
    const nextMap = new Map(selectionMap);

    if (currentState === "checked") {
      // Deselect node and descendants
      nextMap.set(node.scope_identifier, "excluded");
      const leaves = collectLeaves(node);
      for (const lf of leaves) {
        nextMap.set(lf.scope_identifier, "excluded");
      }
    } else {
      // Select node and descendants
      if (node.is_leaf) {
        nextMap.set(node.scope_identifier, "included");
      } else {
        nextMap.set(node.scope_identifier, "all_children");
        const leaves = collectLeaves(node);
        for (const lf of leaves) {
          nextMap.set(lf.scope_identifier, "included");
        }
      }
    }
    setSelectionMap(nextMap);
  };

  // Select All discovered resources
  const handleSelectAll = () => {
    if (!discoveryResponse) return;
    const nextMap = new Map<string, "included" | "excluded" | "all_children">();
    function markAll(nodes: ScopeDiscoveryNode[]) {
      for (const n of nodes) {
        if (n.is_leaf) {
          nextMap.set(n.scope_identifier, "included");
        } else {
          nextMap.set(n.scope_identifier, "all_children");
        }
        if (n.children) markAll(n.children);
      }
    }
    markAll(discoveryResponse.tree);
    setSelectionMap(nextMap);
  };

  // Clear All selections
  const handleClearAll = () => {
    setSelectionMap(new Map());
  };

  // Compute selected counts
  const { selectedCount, selectedWorkspacesCount } = useMemo(() => {
    if (!discoveryResponse) return { selectedCount: 0, selectedWorkspacesCount: 0 };
    let resCount = 0;
    let wsCount = 0;

    function evaluate(nodes: ScopeDiscoveryNode[], parentAll: boolean) {
      for (const n of nodes) {
        const state = selectionMap.get(n.scope_identifier);
        const isExcluded = state === "excluded";
        const isAll = state === "all_children";
        const isIncluded = state === "included" || (parentAll && !isExcluded);

        if (n.is_leaf && isIncluded && !isExcluded) {
          resCount++;
          if (n.scope_type === "databricks_workspace" || n.resource_type === "Microsoft.Databricks/workspaces") {
            wsCount++;
          }
        }

        if (n.children && n.children.length > 0) {
          evaluate(n.children, isAll || parentAll);
        }
      }
    }

    evaluate(discoveryResponse.tree, false);
    return { selectedCount: resCount, selectedWorkspacesCount: wsCount };
  }, [discoveryResponse, selectionMap]);

  // Flatten nodes for filter matching
  const filterMatchesNode = useCallback(
    (node: ScopeDiscoveryNode, query: string): boolean => {
      if (!query.trim()) return true;
      const q = query.toLowerCase();
      const nameMatch = node.name.toLowerCase().includes(q);
      const typeMatch = (node.resource_type || node.scope_type || "").toLowerCase().includes(q);
      const regionMatch = (node.region || "").toLowerCase().includes(q);
      if (nameMatch || typeMatch || regionMatch) return true;

      // Match if any child matches
      if (node.children) {
        return node.children.some((child) => filterMatchesNode(child, query));
      }
      return false;
    },
    []
  );

  // Save active configuration
  const handleSaveConfiguration = async () => {
    if (!currentConnectionId || !discoveryResponse) return;
    setIsSaving(true);
    setErrorMessage(null);
    setSaveSuccessMessage(null);

    try {
      const itemsToPersist: ConfiguredScopeItemCreate[] = [];

      // Collect all nodes into items
      function harvest(nodes: ScopeDiscoveryNode[]) {
        for (const n of nodes) {
          const state = selectionMap.get(n.scope_identifier);
          if (state) {
            itemsToPersist.push({
              scope_type: n.scope_type,
              scope_identifier: n.scope_identifier,
              parent_scope_identifier: n.parent_scope_identifier || null,
              display_name: n.name,
              resource_type: n.resource_type || null,
              region: n.region || null,
              selection_state: state,
              metadata: n.metadata || {},
            });
          }
          if (n.children) harvest(n.children);
        }
      }

      harvest(discoveryResponse.tree);

      const resp = await saveConfiguration({
        connection_id: currentConnectionId,
        provider: selectedProvider,
        created_by: "finops-architect",
        scope_items: itemsToPersist,
      });

      setConfigVersion(resp.configuration_version);
      setSaveSuccessMessage(
        `Configuration Revision v${resp.configuration_version} saved successfully! ${selectedCount} resources (${selectedWorkspacesCount} Databricks workspaces) registered as active ingestion scope.`
      );

      // Refresh status
      const stat = await getConfigurationStatus(currentConnectionId);
      setConfigStatus(stat);
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to persist resource configuration.");
    } finally {
      setIsSaving(false);
    }
  };

  // Recursive Tree Node Renderer
  const renderTreeNode = (node: ScopeDiscoveryNode, depth: number = 0) => {
    if (!filterMatchesNode(node, searchQuery)) {
      return null;
    }

    const isLeaf = node.is_leaf || !node.children || node.children.length === 0;
    const isExpanded = expandedNodes.has(node.id);
    const checkState = getNodeCheckState(node);
    const isDatabricks =
      node.scope_type === "databricks_workspace" ||
      node.resource_type === "Microsoft.Databricks/workspaces";

    return (
      <div key={node.id} className="select-none">
        <div
          className={`flex items-center gap-2 py-1.5 px-2 rounded-lg hover:bg-slate-50 transition text-xs group ${
            isDatabricks ? "bg-red-50/40 border border-red-100/60 my-0.5" : ""
          }`}
          style={{ paddingLeft: `${Math.max(depth * 18 + 8, 8)}px` }}
        >
          {/* Expand/Collapse Toggle */}
          {!isLeaf ? (
            <button
              type="button"
              onClick={() => toggleExpand(node.id)}
              className="p-0.5 text-slate-400 hover:text-navy-900 rounded transition"
              aria-label={isExpanded ? "Collapse" : "Expand"}
            >
              {isExpanded ? (
                <ChevronDown className="w-3.5 h-3.5" />
              ) : (
                <ChevronRight className="w-3.5 h-3.5" />
              )}
            </button>
          ) : (
            <div className="w-4 h-4 shrink-0" />
          )}

          {/* Selection Checkbox */}
          <button
            type="button"
            onClick={() => handleToggleSelect(node)}
            className="text-slate-500 hover:text-brand-600 focus:outline-hidden transition shrink-0"
            aria-label={`Select ${node.name}`}
          >
            {checkState === "checked" ? (
              <CheckSquare className="w-4 h-4 text-brand-600 fill-brand-50" />
            ) : checkState === "indeterminate" ? (
              <MinusSquare className="w-4 h-4 text-brand-600 fill-brand-50" />
            ) : (
              <Square className="w-4 h-4 text-slate-300 group-hover:text-slate-400" />
            )}
          </button>

          {/* Node Icon */}
          <span className="shrink-0 text-slate-400">
            {node.scope_type === "subscription" ? (
              <Cloud className="w-3.5 h-3.5 text-blue-500" />
            ) : node.scope_type === "resource_group" ? (
              <FolderTree className="w-3.5 h-3.5 text-amber-500" />
            ) : isDatabricks ? (
              <Database className="w-3.5 h-3.5 text-red-600 font-bold" />
            ) : (
              <Server className="w-3.5 h-3.5 text-slate-400" />
            )}
          </span>

          {/* Name & Scope Type */}
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <span
              className={`font-medium truncate ${
                isDatabricks ? "text-red-950 font-semibold" : "text-navy-900"
              }`}
            >
              {node.name}
            </span>

            {/* Databricks Workspace Badge */}
            {isDatabricks && (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.2 rounded text-[10px] font-bold bg-red-100 text-red-800 border border-red-200">
                <Sparkles className="w-2.5 h-2.5" />
                Databricks Workspace
              </span>
            )}

            {/* Workspace URL where available */}
            {node.metadata?.workspace_url && (
              <span className="text-[10px] text-slate-400 truncate max-w-xs font-mono">
                {node.metadata.workspace_url}
              </span>
            )}

            {/* Region badge */}
            {node.region && (
              <span className="text-[10px] text-slate-400 px-1 py-0.2 rounded bg-slate-100 border border-slate-200 shrink-0">
                {node.region}
              </span>
            )}
          </div>

          {/* Resource count badge for parent scopes */}
          {!isLeaf && node.children && node.children.length > 0 && (
            <span className="text-[10px] font-medium text-slate-400 px-1.5 py-0.2 rounded bg-slate-100">
              {node.children.length} {node.scope_type === "subscription" ? "groups" : "items"}
            </span>
          )}
        </div>

        {/* Recursive Children */}
        {!isLeaf && isExpanded && node.children && (
          <div className="space-y-0.5">
            {node.children.map((child) => renderTreeNode(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {/* Header & Status Section */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 pb-4 border-b border-slate-200">
        <div>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-brand-50 text-brand-700 flex items-center justify-center font-bold">
              <SlidersHorizontal className="w-4 h-4" />
            </div>
            <h1 className="text-xl sm:text-2xl font-bold text-navy-900 tracking-tight">
              Multi-Cloud Resource Configuration
            </h1>
          </div>
          <p className="text-xs text-navy-600 mt-1 max-w-2xl leading-relaxed">
            Discover and configure the target ingestion scope across subscriptions, resource groups,
            assets, and Azure Databricks workspaces. Selections directly govern the Databricks Apps FinOps
            pipeline.
          </p>
        </div>

        {/* Action Controls: Discover, Save, & Trigger Ingestion */}
        <div className="flex items-center gap-2 self-start md:self-auto flex-wrap">
          <button
            type="button"
            onClick={() => handleDiscover(currentConnectionId, selectedProvider)}
            disabled={isDiscovering || isIngesting}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-white hover:bg-slate-50 text-navy-700 text-xs font-medium border border-slate-200 shadow-2xs transition disabled:opacity-60"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isDiscovering ? "animate-spin" : ""}`} />
            <span>{isDiscovering ? "Discovering..." : "Rediscover"}</span>
          </button>

          <button
            type="button"
            onClick={handleSaveConfiguration}
            disabled={isSaving || isDiscovering || isIngesting || selectedProvider === "aws"}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-brand-600 hover:bg-brand-700 text-white text-xs font-semibold shadow-2xs transition disabled:opacity-50"
          >
            <Save className={`w-3.5 h-3.5 ${isSaving ? "animate-spin" : ""}`} />
            <span>{isSaving ? "Saving Scope..." : `Save Configuration (v${configVersion})`}</span>
          </button>

          <button
            type="button"
            onClick={handleTriggerIngest}
            disabled={
              isIngesting ||
              isSaving ||
              isDiscovering ||
              selectedProvider === "aws" ||
              !readiness?.can_start_ingestion
            }
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold shadow-2xs transition disabled:opacity-50"
            title={readiness?.details || "Trigger scope-aware ingestion"}
          >
            <Play className={`w-3.5 h-3.5 ${isIngesting ? "animate-spin" : ""}`} />
            <span>{isIngesting ? "Ingesting..." : "Trigger Ingestion"}</span>
          </button>
        </div>
      </div>

      {/* Provider Selector Tabs */}
      <div className="flex items-center gap-2 p-1 bg-slate-100 rounded-lg border border-slate-200 max-w-md">
        <button
          type="button"
          onClick={() => setSelectedProvider("azure")}
          className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md text-xs font-medium transition ${
            selectedProvider === "azure"
              ? "bg-white text-navy-900 shadow-2xs font-semibold"
              : "text-navy-600 hover:text-navy-900"
          }`}
        >
          <Cloud className="w-3.5 h-3.5 text-blue-600" />
          <span>Azure</span>
        </button>

        <button
          type="button"
          onClick={() => setSelectedProvider("gcp")}
          className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md text-xs font-medium transition ${
            selectedProvider === "gcp"
              ? "bg-white text-navy-900 shadow-2xs font-semibold"
              : "text-navy-600 hover:text-navy-900"
          }`}
        >
          <Cloud className="w-3.5 h-3.5 text-emerald-600" />
          <span>Google Cloud</span>
        </button>

        <button
          type="button"
          onClick={() => setSelectedProvider("aws")}
          className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md text-xs font-medium transition ${
            selectedProvider === "aws"
              ? "bg-white text-navy-900 shadow-2xs font-semibold"
              : "text-navy-600 hover:text-navy-900"
          }`}
        >
          <Cloud className="w-3.5 h-3.5 text-amber-600" />
          <span>AWS</span>
        </button>
      </div>

      {/* Alerts & Messages */}
      {saveSuccessMessage && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg flex items-start gap-2.5 text-xs text-emerald-900">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
          <div className="flex-1 font-medium">{saveSuccessMessage}</div>
        </div>
      )}

      {ingestionMessage && (
        <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg flex items-start gap-2.5 text-xs text-blue-900">
          <Sparkles className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
          <div className="flex-1 font-medium">{ingestionMessage}</div>
        </div>
      )}

      {errorMessage && (
        <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg flex items-start gap-2.5 text-xs text-rose-900">
          <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
          <div className="flex-1 font-medium">{errorMessage}</div>
        </div>
      )}

      {/* AWS Unsupported Banner */}
      {selectedProvider === "aws" && (
        <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl flex items-start gap-3 text-xs text-amber-900">
          <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
          <div>
            <div className="font-semibold text-sm">AWS Provider Not Configured</div>
            <p className="mt-1 leading-relaxed text-amber-800">
              AWS integration is currently absent in this deployment. The resource configuration engine
              maintains a provider-neutral abstraction, but live AWS API discovery and IAM credentials
              have not been onboarded.
            </p>
          </div>
        </div>
      )}

      {/* Main Configuration Card */}
      {selectedProvider !== "aws" && (
        <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
          {/* Card Controls Bar */}
          <div className="p-4 border-b border-slate-200 bg-slate-50/50 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            {/* Connection Selector */}
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-navy-700">Connection:</span>
              <select
                value={currentConnectionId}
                onChange={(e) => {
                  setCurrentConnectionId(e.target.value);
                  const found = availableConnections.find((c) => c.id === e.target.value);
                  if (found && onSelectConnection) onSelectConnection(found);
                }}
                className="text-xs bg-white border border-slate-300 rounded-md px-2.5 py-1.5 text-navy-900 font-medium focus:ring-1 focus:ring-brand-500 focus:outline-hidden"
              >
                {availableConnections
                  .filter((c) => c.provider === selectedProvider)
                  .map((conn) => (
                    <option key={conn.id} value={conn.id}>
                      {conn.name} ({conn.scope_id || conn.id})
                    </option>
                  ))}
                {availableConnections.filter((c) => c.provider === selectedProvider).length === 0 && (
                  <option value={currentConnectionId}>Default {selectedProvider} Scope</option>
                )}
              </select>
            </div>

            {/* Ingestion Readiness Badge */}
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500">Readiness:</span>
              <span
                className={`text-[10px] font-bold px-2.5 py-0.5 rounded-full uppercase tracking-wider ${
                  (readiness?.readiness_state || configStatus?.ingestion_readiness) === "ready"
                    ? "bg-emerald-100 text-emerald-800 border border-emerald-200"
                    : (readiness?.readiness_state || configStatus?.ingestion_readiness) === "no_resources_selected" || (readiness?.readiness_state || configStatus?.ingestion_readiness) === "no_selection"
                    ? "bg-amber-100 text-amber-800 border border-amber-200"
                    : (readiness?.readiness_state || configStatus?.ingestion_readiness) === "permission_denied"
                    ? "bg-rose-100 text-rose-800 border border-rose-200"
                    : "bg-slate-100 text-slate-600 border border-slate-200"
                }`}
                title={readiness?.details || "Ingestion pipeline readiness status"}
              >
                {readiness?.readiness_state || configStatus?.ingestion_readiness || "not_configured"}
              </span>
            </div>
          </div>

          {/* Tree Toolbar: Search, Select All, Clear All, Counts */}
          <div className="p-3 border-b border-slate-200 flex flex-col md:flex-row md:items-center md:justify-between gap-3">
            {/* Search Input */}
            <div className="relative flex-1 max-w-sm">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
              <input
                type="text"
                placeholder="Filter by resource name, type, region..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full text-xs pl-8 pr-3 py-1.5 border border-slate-200 rounded-lg focus:outline-hidden focus:border-brand-500 bg-white"
              />
            </div>

            {/* Quick Actions & Counter */}
            <div className="flex items-center gap-2 flex-wrap">
              <button
                type="button"
                onClick={handleSelectAll}
                className="px-2.5 py-1 text-xs font-medium text-navy-700 hover:bg-slate-100 rounded-md border border-slate-200 transition"
              >
                Select All
              </button>

              <button
                type="button"
                onClick={handleClearAll}
                className="px-2.5 py-1 text-xs font-medium text-navy-700 hover:bg-slate-100 rounded-md border border-slate-200 transition"
              >
                Clear All
              </button>

              <div className="h-4 w-px bg-slate-200 mx-1 hidden sm:block" />

              <button
                type="button"
                onClick={expandAll}
                className="px-2 py-1 text-xs text-slate-500 hover:text-navy-900 transition"
              >
                Expand All
              </button>

              <button
                type="button"
                onClick={collapseAll}
                className="px-2 py-1 text-xs text-slate-500 hover:text-navy-900 transition"
              >
                Collapse All
              </button>

              <div className="h-4 w-px bg-slate-200 mx-1 hidden sm:block" />

              {/* Selected Count Indicator */}
              <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-brand-50 border border-brand-200 text-brand-800 text-xs font-semibold">
                <CheckSquare className="w-3.5 h-3.5 text-brand-600" />
                <span>
                  {selectedCount} Selected ({selectedWorkspacesCount} Workspaces)
                </span>
              </div>
            </div>
          </div>

          {/* Discovery Results Tree */}
          <div className="p-4 max-h-[560px] overflow-y-auto">
            {isDiscovering ? (
              <div className="py-12 text-center space-y-3">
                <RefreshCw className="w-6 h-6 text-brand-600 animate-spin mx-auto" />
                <p className="text-xs text-navy-600 font-medium">
                  Discovering cloud hierarchy, Resource Groups, and Databricks Workspaces...
                </p>
              </div>
            ) : discoveryResponse && discoveryResponse.tree.length > 0 ? (
              <div className="space-y-1">
                {discoveryResponse.tree.map((node) => renderTreeNode(node, 0))}
              </div>
            ) : (
              <div className="py-12 text-center text-slate-400 text-xs">
                No resources discovered for this connection. Click "Rediscover" above.
              </div>
            )}
          </div>

          {/* Card Footer: Metadata and Databricks Apps Guarantee */}
          <div className="p-3 bg-slate-50 border-t border-slate-200 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 text-[11px] text-slate-500">
            <div className="flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
              <span>Strict Read-Only Discovery. Zero automated cloud mutations.</span>
            </div>
            <div>
              Last discovered:{" "}
              {discoveryResponse?.last_discovered_at
                ? new Date(discoveryResponse.last_discovered_at).toLocaleTimeString()
                : "Never"}
            </div>
          </div>
        </div>
      )}

      {/* Recent Ingestion Runs & Configuration Lineage (Phase 2C) */}
      {selectedProvider !== "aws" && ingestionRuns.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
          <div className="p-4 border-b border-slate-200 bg-slate-50/50 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <History className="w-4 h-4 text-brand-600" />
              <h3 className="text-xs font-bold text-navy-900 tracking-wide uppercase">
                Recent Ingestion Runs & Version Lineage
              </h3>
            </div>
            <span className="text-[11px] text-slate-500 font-medium">
              {ingestionRuns.length} Recorded Execution{ingestionRuns.length === 1 ? "" : "s"}
            </span>
          </div>

          <div className="divide-y divide-slate-100 overflow-x-auto">
            {ingestionRuns.map((run) => (
              <div
                key={run.run_id}
                className="p-3 hover:bg-slate-50/70 transition flex items-center justify-between gap-4 text-xs"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <span
                    className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider ${
                      run.status === "completed"
                        ? "bg-emerald-100 text-emerald-800 border border-emerald-200"
                        : run.status === "partial_failure"
                        ? "bg-amber-100 text-amber-800 border border-amber-200"
                        : run.status === "failed"
                        ? "bg-rose-100 text-rose-800 border border-rose-200"
                        : "bg-blue-100 text-blue-800 border border-blue-200 animate-pulse"
                    }`}
                  >
                    {run.status}
                  </span>

                  <div className="flex items-center gap-2">
                    <span className="font-mono text-slate-500 text-[11px]">
                      {run.run_id.slice(0, 8)}
                    </span>
                    <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-semibold bg-brand-50 text-brand-700 border border-brand-200">
                      Scope v{run.configuration_version}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-4 shrink-0">
                  <div className="text-slate-600 text-[11px]">
                    <span className="font-semibold text-navy-900">
                      {run.successful_resources_count} / {run.total_resources_scoped}
                    </span>{" "}
                    Resources Ingested
                  </div>

                  <div className="text-slate-400 text-[11px] flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    <span>{new Date(run.started_at).toLocaleTimeString()}</span>
                  </div>

                  {(run.status === "failed" || run.status === "partial_failure") && (
                    <button
                      type="button"
                      onClick={() => handleRetryIngest(run.run_id)}
                      disabled={isIngesting}
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-white hover:bg-slate-100 text-navy-700 text-[11px] font-medium border border-slate-200 shadow-2xs transition disabled:opacity-50"
                    >
                      <RotateCcw className="w-3 h-3 text-slate-500" />
                      <span>Retry</span>
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

