"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  CloudConnection,
  ConnectionValidationResponse,
  CreateConnectionRequest,
} from "@/types";
import { listConnections, validateConnection, createConnection } from "@/lib/api";
import { formatDeterministicTime } from "@/lib/dateTimeFormat";
import {
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  Loader2,
  RefreshCw,
  ArrowLeft,
  Trash2,
  Edit3,
  Plus,
  Check,
  X,
  Server,
  Database,
  Layers,
  Copy,
} from "lucide-react";

interface ConnectCloudViewProps {
  onConnectionSelected: (
    connection: CloudConnection,
    validation?: ConnectionValidationResponse
  ) => void;
  onContinueToDemo?: () => void;
  onCancel?: () => void;
  currentActiveConnectionId?: string;
}

export const ConnectCloudView: React.FC<ConnectCloudViewProps> = ({
  onConnectionSelected,
  onCancel,
  currentActiveConnectionId = "",
}) => {
  const [connections, setConnections] = useState<CloudConnection[]>([]);
  const [activeConnectionId, setActiveConnectionId] = useState<string>(currentActiveConnectionId);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // Top-Level Provider Filter: "all" | "azure" | "gcp"
  const [providerFilter, setProviderFilter] = useState<"all" | "azure" | "gcp">("all");

  // Reconnection / Probe states
  const [activeValidatingConnId, setActiveValidatingConnId] = useState<string | null>(null);
  const [validationStep, setValidationStep] = useState<
    "idle" | "connecting" | "validating" | "discovering" | "connected" | "failed"
  >("idle");
  const [validationResult, setValidationResult] =
    useState<ConnectionValidationResponse | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [actionSuccessMessage, setActionSuccessMessage] = useState<string | null>(null);

  // Modal States
  const [disconnectModalConnection, setDisconnectModalConnection] =
    useState<CloudConnection | null>(null);
  const [editModalConnection, setEditModalConnection] =
    useState<CloudConnection | null>(null);
  const [isAddConnectionOpen, setIsAddConnectionOpen] = useState<boolean>(false);

  // Add Connection Form States
  const [addEcosystem, setAddEcosystem] = useState<"azure" | "gcp">("azure");
  const [newConnName, setNewConnName] = useState<string>("");
  const [newScopeId, setNewScopeId] = useState<string>("");
  const [newTenantId, setNewTenantId] = useState<string>("");
  const [newAuthMethod, setNewAuthMethod] = useState<string>("azure_cli_credentials");
  const [enableDatabricksIntegration, setEnableDatabricksIntegration] = useState<boolean>(true);
  const [enableFabricIntegration, setEnableFabricIntegration] = useState<boolean>(true);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Load existing connections from backend
  const refreshConnections = useCallback(async () => {
    setIsLoading(true);
    setFetchError(null);
    try {
      const serverConns = await listConnections();
      setConnections(serverConns || []);
    } catch (err) {
      // No offline fallback: an unreachable backend is shown as an error, never as seeded accounts.
      setConnections([]);
      setFetchError(
        err instanceof Error ? `Could not load cloud connections: ${err.message}` : "Could not load cloud connections."
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshConnections();
  }, [refreshConnections]);

  useEffect(() => {
    if (currentActiveConnectionId) {
      setActiveConnectionId(currentActiveConnectionId);
    }
  }, [currentActiveConnectionId]);

  // Filter connections strictly by top-level ecosystem: "all" | "azure" | "gcp"
  const filteredConnections = useMemo(() => {
    if (providerFilter === "all") return connections;
    return connections.filter((c) => c.provider === providerFilter);
  }, [connections, providerFilter]);

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  // 1. Select Account Action: validates metadata and routes directly to Configuration
  const handleSelectAccount = async (conn: CloudConnection) => {
    setActiveConnectionId(conn.id);
    setActiveValidatingConnId(conn.id);
    setValidationStep("validating");

    try {
      const res = await validateConnection({
        connection_id: conn.id,
        provider: conn.provider,
        scope_id: conn.scope_id,
      });
      setValidationStep("connected");
      onConnectionSelected(conn, res);
    } catch (err) {
      setValidationStep("failed");
      setValidationError(
        err instanceof Error ? `Validation failed: ${err.message}` : "Validation failed: backend unreachable."
      );
    }
  };

  // 2. Reconnect / Verification Action
  const handleReconnect = async (conn: CloudConnection) => {
    setActiveValidatingConnId(conn.id);
    setValidationError(null);
    setValidationResult(null);

    setValidationStep("validating");

    try {
      const res = await validateConnection({
        connection_id: conn.id,
        provider: conn.provider,
        scope_id: conn.scope_id,
      });
      setValidationResult(res);
      setValidationStep("connected");
      setConnections((prev) =>
        prev.map((item) =>
          item.id === conn.id ? { ...item, status: "connected", last_verified_at: res.validated_at } : item
        )
      );
      setActionSuccessMessage(`Account "${conn.name}" re-verified successfully.`);
      setTimeout(() => setActionSuccessMessage(null), 4000);
    } catch (err) {
      setValidationStep("failed");
      setValidationError(
        err instanceof Error ? `Verification failed: ${err.message}` : "Verification failed: backend unreachable."
      );
    }
  };

  // 3. Disconnect Action
  const confirmDisconnect = () => {
    if (!disconnectModalConnection) return;
    const target = disconnectModalConnection;
    setConnections((prev) => prev.filter((c) => c.id !== target.id));
    if (activeConnectionId === target.id) {
      const remaining = connections.filter((c) => c.id !== target.id);
      if (remaining.length > 0) {
        setActiveConnectionId(remaining[0].id);
      }
    }
    setDisconnectModalConnection(null);
    setActionSuccessMessage(`Cloud connection "${target.name}" deactivated.`);
    setTimeout(() => setActionSuccessMessage(null), 4000);
  };

  // 4. Edit Modal Save
  const handleSaveEdit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!editModalConnection) return;
    setConnections((prev) =>
      prev.map((c) => (c.id === editModalConnection.id ? editModalConnection : c))
    );
    setEditModalConnection(null);
    setActionSuccessMessage("Connection configuration updated successfully.");
    setTimeout(() => setActionSuccessMessage(null), 3000);
  };

  // 5. Add New Connection
  const handleAddNewConnection = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newConnName.trim() || !newScopeId.trim()) return;

    try {
      const req: CreateConnectionRequest = {
        provider: addEcosystem,
        name: newConnName,
        scope_id: newScopeId,
        azure_tenant_id: newTenantId,
      };
      const created = await createConnection(req);
      await refreshConnections();
      if (created?.id) setActiveConnectionId(created.id);
      setIsAddConnectionOpen(false);
      setNewConnName("");
      setNewScopeId("");
      setNewTenantId("");
      setActionSuccessMessage(`Account "${newConnName}" added; its status is whatever the backend verified.`);
      setTimeout(() => setActionSuccessMessage(null), 4000);
    } catch (err) {
      setValidationError(
        err instanceof Error ? `Could not add the connection: ${err.message}` : "Could not add the connection."
      );
    }
  };

  return (
    <div className="space-y-6 pb-16 w-full">
      {/* Top Header Card — Clean Enterprise Branding */}
      <div className="app-card bg-white border border-slate-200 rounded-2xl p-6 shadow-2xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            {onCancel && (
              <button
                type="button"
                onClick={onCancel}
                className="p-2 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-600 hover:text-navy-900 transition shrink-0"
                title="Back to Configuration"
              >
                <ArrowLeft className="w-4 h-4" />
              </button>
            )}
            <div>
              <div className="flex items-center gap-2.5">
                <h1 className="text-xl font-bold text-navy-950 tracking-tight font-heading">
                  Cloud Connection Management
                </h1>
                <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-blue-50 text-brand-700 border border-blue-200">
                  Account-Level Authorization
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-1">
                Connect your cloud account first. Configure your infrastructure scope next. Then analyze your costs and infrastructure from the FinOps Application.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap self-start sm:self-auto">
            {onCancel && (
              <button
                type="button"
                onClick={onCancel}
                className="px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold transition"
              >
                Back to Configuration
              </button>
            )}

            <button
              type="button"
              onClick={() => setIsAddConnectionOpen(true)}
              className="px-3.5 py-1.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white text-xs font-semibold flex items-center gap-1.5 transition shadow-2xs"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Add New Connection</span>
            </button>
          </div>
        </div>

        {/* Global Notifications */}
        {actionSuccessMessage && (
          <div className="p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-xs text-emerald-800 flex items-center gap-2 animate-in fade-in duration-200">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span>{actionSuccessMessage}</span>
          </div>
        )}
        {fetchError && (
          <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-800 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{fetchError}</span>
          </div>
        )}

        {/* Redesigned Provider Filter Tabs — 3 Logical Categories Only */}
        <div className="border-t border-slate-100 pt-3 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 overflow-x-auto pb-1 text-xs">
            {[
              { id: "all" as const, label: "All Connections", count: connections.length },
              {
                id: "azure" as const,
                label: "Microsoft Azure",
                count: connections.filter((c) => c.provider === "azure").length,
              },
              {
                id: "gcp" as const,
                label: "Google Cloud",
                count: connections.filter((c) => c.provider === "gcp").length,
              },
            ].map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setProviderFilter(tab.id)}
                className={`px-3 py-1.5 rounded-lg font-medium whitespace-nowrap transition flex items-center gap-1.5 ${
                  providerFilter === tab.id
                    ? "bg-navy-950 text-white font-semibold shadow-2xs"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-navy-900"
                }`}
              >
                <span>{tab.label}</span>
                <span
                  className={`text-[10px] px-1.5 py-0.2 rounded-full font-bold ${
                    providerFilter === tab.id ? "bg-white/20 text-white" : "bg-slate-200 text-slate-700"
                  }`}
                >
                  {tab.count}
                </span>
              </button>
            ))}
          </div>
          {isLoading && (
            <div className="flex items-center gap-1.5 text-xs text-slate-400 shrink-0">
              <Loader2 className="w-3.5 h-3.5 animate-spin text-brand-600" />
              <span>Syncing...</span>
            </div>
          )}
        </div>
      </div>

      {/* Strictly Read-Only & Zero-Execution Policy Indicator */}
      <div className="p-3.5 bg-emerald-50/80 border border-emerald-200 rounded-xl text-xs text-emerald-900 flex items-center justify-between gap-3 shadow-2xs">
        <div className="flex items-center gap-2.5">
          <ShieldCheck className="w-4 h-4 text-emerald-600 shrink-0" />
          <span>
            <strong>Strictly Read-Only &bull; Zero-Execution Policy:</strong> All cloud accounts operate with strictly read-only authorization (<code className="font-mono bg-white px-1 py-0.5 rounded border border-emerald-300">Reader</code>, <code className="font-mono bg-white px-1 py-0.5 rounded border border-emerald-300">Cost Management Reader</code>). The platform never executes mutations, starts compute, or modifies cloud resources.
          </span>
        </div>
        <span className="text-[10px] font-mono text-emerald-700 shrink-0 font-bold hidden md:inline">
          100% Read-Only Protected
        </span>
      </div>

      {/* Validation / Probe Banner */}
      {activeValidatingConnId && validationStep !== "idle" && (
        <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <Loader2 className="w-4 h-4 animate-spin text-brand-600" />
              <span className="font-bold text-xs text-navy-900">
                Verifying cloud access probe for: {activeValidatingConnId}...
              </span>
            </div>
            {validationStep === "failed" && (
              <button
                type="button"
                onClick={() => {
                  setValidationStep("idle");
                  setActiveValidatingConnId(null);
                }}
                className="text-xs text-slate-500 hover:text-navy-900 font-semibold"
              >
                Dismiss
              </button>
            )}
          </div>

          <div className="grid grid-cols-4 gap-2 text-xs py-2 border-y border-slate-100">
            <div className={`flex items-center gap-1.5 ${validationStep === "connecting" ? "text-brand-600 font-bold" : ["validating", "discovering", "connected"].includes(validationStep) ? "text-emerald-600 font-medium" : "text-slate-400"}`}>
              {validationStep === "connecting" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
              <span>1. Connecting</span>
            </div>
            <div className={`flex items-center gap-1.5 ${validationStep === "validating" ? "text-brand-600 font-bold" : ["discovering", "connected"].includes(validationStep) ? "text-emerald-600 font-medium" : "text-slate-400"}`}>
              {validationStep === "validating" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
              <span>2. Validating credentials</span>
            </div>
            <div className={`flex items-center gap-1.5 ${validationStep === "discovering" ? "text-brand-600 font-bold" : validationStep === "connected" ? "text-emerald-600 font-medium" : "text-slate-400"}`}>
              {validationStep === "discovering" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
              <span>3. Discovering services</span>
            </div>
            <div className={`flex items-center gap-1.5 ${validationStep === "connected" ? "text-emerald-600 font-bold" : validationStep === "failed" ? "text-rose-600 font-bold" : "text-slate-400"}`}>
              {validationStep === "connected" ? <CheckCircle2 className="w-3.5 h-3.5" /> : validationStep === "failed" ? <AlertCircle className="w-3.5 h-3.5" /> : <div className="w-3.5 h-3.5 rounded-full border border-slate-300" />}
              <span>4. {validationStep === "failed" ? "Failed" : "Connected"}</span>
            </div>
          </div>

          {validationResult && (
            <div className="p-2.5 bg-emerald-50 border border-emerald-200 rounded-lg text-emerald-900 text-xs flex items-center justify-between">
              <span>{validationResult.details}</span>
              <span className="font-mono text-[11px] text-emerald-700 font-semibold">{validationResult.latency_ms}ms latency</span>
            </div>
          )}

          {validationError && (
            <div className="p-2.5 bg-rose-50 border border-rose-200 rounded-lg text-rose-800 text-xs flex items-center gap-1.5">
              <AlertCircle className="w-3.5 h-3.5 text-rose-600 shrink-0" />
              <span>{validationError}</span>
            </div>
          )}
        </div>
      )}

      {/* Account Cards Grid — Section 3: Azure Account Cards & Service Integrations */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {filteredConnections.map((conn) => {
          const isActive = conn.id === activeConnectionId;
          const isAzure = conn.provider === "azure";
          const isValidatingThis = activeValidatingConnId === conn.id && validationStep !== "idle";

          return (
            <div
              key={conn.id}
              className={`rounded-2xl border transition bg-white flex flex-col justify-between shadow-xs overflow-hidden ${
                isActive
                  ? "border-blue-500 ring-2 ring-blue-500/20 bg-gradient-to-b from-blue-50/30 to-white"
                  : "border-slate-200 hover:border-slate-300"
              }`}
            >
              {/* Account Card Header */}
              <div className="p-5 pb-4">
                <div className="flex items-start justify-between gap-3 pb-3 border-b border-slate-100">
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-10 h-10 rounded-xl flex items-center justify-center font-bold text-sm shrink-0 shadow-2xs ${
                        isAzure
                          ? "bg-blue-600 text-white"
                          : "bg-amber-600 text-white"
                      }`}
                    >
                      {isAzure ? "Az" : "GCP"}
                    </div>
                    <div>
                      <h3 className="font-bold text-sm text-navy-950 flex items-center gap-2">
                        <span>{conn.name}</span>
                      </h3>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <span className="text-[11px] font-semibold text-slate-500">
                          {isAzure ? "Microsoft Azure" : "Google Cloud"}
                        </span>
                        <span className="text-slate-300">&bull;</span>
                        <span className="text-[11px] font-medium text-slate-400">
                          {conn.auth_method}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-1.5 shrink-0">
                    {isActive ? (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
                        <Check className="w-3 h-3" />
                        <span>Active Account</span>
                      </span>
                    ) : (
                      <span className="px-2.5 py-0.5 rounded-full text-[10px] font-medium bg-slate-100 text-slate-600">
                        Standby
                      </span>
                    )}
                  </div>
                </div>

                {/* Account Identifiers (Subscription ID & Tenant ID) */}
                <div className="mt-3.5 space-y-1.5 text-xs font-mono p-3 rounded-xl bg-slate-50 border border-slate-100 text-[11px]">
                  <div className="flex justify-between items-center">
                    <span className="text-slate-500 font-sans">
                      {isAzure ? "Subscription ID:" : "Project ID:"}
                    </span>
                    <div className="flex items-center gap-1">
                      <span className="font-semibold text-navy-900 truncate max-w-[200px]">
                        {conn.scope_id}
                      </span>
                      <button
                        type="button"
                        onClick={() => copyToClipboard(conn.scope_id, `${conn.id}-scope`)}
                        className="text-slate-400 hover:text-navy-900 p-0.5"
                        title={isAzure ? "Copy Subscription ID" : "Copy Project ID"}
                        aria-label={isAzure ? "Copy Subscription ID" : "Copy Project ID"}
                      >
                        {copiedId === `${conn.id}-scope` ? (
                          <Check className="w-3 h-3 text-emerald-600" />
                        ) : (
                          <Copy className="w-3 h-3" />
                        )}
                      </button>
                    </div>
                  </div>

                  {conn.tenant_or_org_id && (
                    <div className="flex justify-between items-center">
                      <span className="text-slate-500 font-sans">
                        {isAzure ? "Tenant ID:" : "Organization ID:"}
                      </span>
                      <span className="font-semibold text-navy-900 truncate max-w-[200px]">
                        {conn.tenant_or_org_id}
                      </span>
                    </div>
                  )}

                  {conn.last_verified_at && (
                    <div className="flex justify-between items-center">
                      <span className="text-slate-500 font-sans">Last Verified:</span>
                      <span className="text-slate-500">
                        {formatDeterministicTime(conn.last_verified_at, { hour12: false })}
                      </span>
                    </div>
                  )}
                </div>

                {/* Available Service Integrations Group (Section 3 Requirement) */}
                <div className="mt-4 pt-3 border-t border-slate-100">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[11px] font-bold text-slate-700 uppercase tracking-wider">
                      Available Service Integrations
                    </span>
                    <span className="text-[10px] text-slate-400 font-medium">
                      {conn.service_integrations?.length || 3} Services Configured
                    </span>
                  </div>

                  <div className="space-y-2">
                    {conn.service_integrations && conn.service_integrations.length > 0 ? (
                      conn.service_integrations.map((svc, idx) => (
                        <div
                          key={idx}
                          className="p-2.5 rounded-lg bg-white border border-slate-200/90 flex items-center justify-between text-xs hover:border-slate-300 transition"
                        >
                          <div className="flex items-center gap-2.5 min-w-0">
                            <div className="p-1.5 rounded-md bg-slate-50 border border-slate-200 text-slate-600 shrink-0">
                              {svc.service_type === "databricks" ? (
                                <Database className="w-3.5 h-3.5 text-orange-600" />
                              ) : svc.service_type === "fabric" ? (
                                <Layers className="w-3.5 h-3.5 text-teal-600" />
                              ) : (
                                <Server className="w-3.5 h-3.5 text-blue-600" />
                              )}
                            </div>
                            <div className="min-w-0">
                              <span className="font-semibold text-navy-900 block truncate">
                                {svc.display_name}
                              </span>
                              <span className="text-[11px] text-slate-500 block truncate">
                                {svc.details || svc.capabilities.slice(0, 2).join(", ")}
                              </span>
                            </div>
                          </div>

                          <span
                            className={`px-2 py-0.5 rounded-md text-[10px] font-bold uppercase shrink-0 ${
                              svc.status === "connected"
                                ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                                : svc.status === "standby"
                                ? "bg-amber-50 text-amber-700 border border-amber-200"
                                : "bg-slate-100 text-slate-600"
                            }`}
                          >
                            {svc.status === "connected" ? "Connected" : svc.status === "standby" ? "Standby" : "Unlinked"}
                          </span>
                        </div>
                      ))
                    ) : (
                      <div className="text-xs text-slate-500 italic p-2 bg-slate-50 rounded-lg">
                        Standard Resource Manager integration active
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Bottom Actions Row (Section 4: Select Account Navigation) */}
              <div className="p-4 bg-slate-50/80 border-t border-slate-100 flex items-center justify-between gap-3">
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => handleReconnect(conn)}
                    disabled={isValidatingThis}
                    className="p-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 text-slate-600 text-xs font-semibold flex items-center gap-1 transition shadow-2xs"
                    title="Re-verify credentials & refresh scopes"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${isValidatingThis ? "animate-spin text-brand-600" : ""}`} />
                    <span className="hidden sm:inline">Reconnect</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setEditModalConnection(conn)}
                    className="p-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 text-slate-600 text-xs font-semibold flex items-center gap-1 transition shadow-2xs"
                    title="Edit connection settings"
                  >
                    <Edit3 className="w-3.5 h-3.5" />
                    <span className="hidden sm:inline">Edit</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setDisconnectModalConnection(conn)}
                    className="p-1.5 rounded-lg border border-rose-200 bg-white hover:bg-rose-50 text-rose-600 text-xs font-semibold flex items-center gap-1 transition shadow-2xs"
                    title="Remove connection"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>

                <div>
                  <button
                    type="button"
                    onClick={() => handleSelectAccount(conn)}
                    className={`px-4 py-2 rounded-xl font-bold text-xs transition shadow-2xs flex items-center gap-1.5 ${
                      isActive
                        ? "bg-emerald-600 hover:bg-emerald-700 text-white"
                        : "bg-navy-950 hover:bg-navy-900 text-white"
                    }`}
                  >
                    {isActive ? (
                      <>
                        <Check className="w-4 h-4" />
                        <span>Configured Scope &rarr;</span>
                      </>
                    ) : (
                      <>
                        <span>Select Account &rarr;</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* MODAL 1: DISCONNECT CONFIRMATION */}
      {disconnectModalConnection && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/60 backdrop-blur-xs p-4 animate-in fade-in duration-150">
          <div className="bg-white rounded-2xl border border-slate-200 max-w-md w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center gap-3 pb-3 border-b border-slate-100">
              <div className="w-10 h-10 rounded-xl bg-rose-50 text-rose-600 flex items-center justify-center shrink-0">
                <AlertCircle className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-bold text-sm text-navy-950 font-heading">
                  Disconnect Cloud Account
                </h3>
                <p className="text-xs text-slate-500">
                  Confirm deactivating this cloud account from the FinOps Platform
                </p>
              </div>
            </div>

            <div className="space-y-2 text-xs">
              <p className="text-slate-700 leading-relaxed">
                Are you sure you want to disconnect{" "}
                <strong className="text-navy-900">{disconnectModalConnection.name}</strong> (
                <code className="font-mono text-slate-600">{disconnectModalConnection.scope_id}</code>)?
              </p>
              <div className="p-3 bg-slate-50 rounded-lg text-slate-500 text-[11px] space-y-1 border border-slate-100">
                <p>&bull; Active monitoring and live telemetry will be paused for this account.</p>
                <p>&bull; Historical telemetry cache remains securely preserved in offline storage.</p>
                <p>&bull; Zero changes will be made to real cloud infrastructure.</p>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setDisconnectModalConnection(null)}
                className="px-3.5 py-2 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-700 font-semibold text-xs transition"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmDisconnect}
                className="px-4 py-2 rounded-lg bg-rose-600 hover:bg-rose-700 text-white font-bold text-xs transition shadow-2xs"
              >
                Confirm Disconnect
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 2: EDIT CONNECTION SETTINGS */}
      {editModalConnection && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/60 backdrop-blur-xs p-4 animate-in fade-in duration-150">
          <div className="bg-white rounded-2xl border border-slate-200 max-w-lg w-full p-6 shadow-2xl space-y-4">
            <div className="flex justify-between items-center pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <Edit3 className="w-4 h-4 text-brand-600" />
                <h3 className="font-bold text-sm text-navy-950 font-heading">
                  Edit Cloud Account Settings
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setEditModalConnection(null)}
                className="text-slate-400 hover:text-slate-600 p-1"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSaveEdit} className="space-y-3 text-xs">
              <div>
                <label className="block font-semibold text-navy-900 mb-1">
                  Account Display Name
                </label>
                <input
                  type="text"
                  value={editModalConnection.name}
                  onChange={(e) =>
                    setEditModalConnection({
                      ...editModalConnection,
                      name: e.target.value,
                    })
                  }
                  className="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-xs focus:ring-1 focus:ring-brand-500 focus:outline-none"
                  required
                />
              </div>

              <div>
                <label className="block font-semibold text-navy-900 mb-1">
                  Subscription / Scope ID (Read-Only)
                </label>
                <input
                  type="text"
                  value={editModalConnection.scope_id}
                  disabled
                  className="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-xs bg-slate-50 text-slate-500 font-mono"
                />
              </div>

              <div>
                <label className="block font-semibold text-navy-900 mb-1">
                  Tenant / Organization ID
                </label>
                <input
                  type="text"
                  value={editModalConnection.tenant_or_org_id || ""}
                  onChange={(e) =>
                    setEditModalConnection({
                      ...editModalConnection,
                      tenant_or_org_id: e.target.value,
                    })
                  }
                  placeholder="e.g. fe82a67c-faa7-4d9a-bbfa-7d25b7047b41"
                  className="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-xs font-mono focus:ring-1 focus:ring-brand-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block font-semibold text-navy-900 mb-1">
                  Authentication Method
                </label>
                <select
                  value={editModalConnection.auth_method}
                  onChange={(e) =>
                    setEditModalConnection({
                      ...editModalConnection,
                      auth_method: e.target.value,
                    })
                  }
                  className="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-xs bg-white focus:ring-1 focus:ring-brand-500 focus:outline-none"
                >
                  <option value="Azure CLI Credentials">Azure CLI Credentials (Interactive / Dev)</option>
                  <option value="Service Principal (OAuth2)">Service Principal (Read-Only Client Secret)</option>
                  <option value="Managed Identity">Azure Managed Identity (Production App Service)</option>
                  <option value="GCP Service Account">GCP Service Account Key</option>
                </select>
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setEditModalConnection(null)}
                  className="px-3.5 py-2 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-700 font-semibold text-xs transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-bold text-xs transition shadow-2xs"
                >
                  Save Changes
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 3: ADD NEW CONNECTION — Section 8: Ecosystem First Flow */}
      {isAddConnectionOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/60 backdrop-blur-xs p-4 animate-in fade-in duration-150">
          <div className="bg-white rounded-2xl border border-slate-200 max-w-lg w-full p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex justify-between items-center pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <Plus className="w-4 h-4 text-brand-600" />
                <h3 className="font-bold text-sm text-navy-950 font-heading">
                  Add New Cloud Connection
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setIsAddConnectionOpen(false)}
                className="text-slate-400 hover:text-slate-600 p-1"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Ecosystem Selection Step: Microsoft Azure vs Google Cloud */}
            <div>
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">
                1. Select Cloud Ecosystem
              </label>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <button
                  type="button"
                  onClick={() => {
                    setAddEcosystem("azure");
                    setNewAuthMethod("Azure CLI Credentials");
                  }}
                  className={`p-3 rounded-xl border flex items-center gap-3 transition text-left ${
                    addEcosystem === "azure"
                      ? "border-blue-500 bg-blue-50/50 text-blue-900 font-bold ring-2 ring-blue-500/20"
                      : "border-slate-200 hover:border-slate-300 text-slate-700"
                  }`}
                >
                  <div className="w-8 h-8 rounded-lg bg-blue-600 text-white flex items-center justify-center font-bold text-xs shrink-0">
                    Az
                  </div>
                  <div>
                    <div className="font-bold text-xs">Microsoft Azure</div>
                    <div className="text-[10px] text-slate-500">ARM, Databricks, Fabric</div>
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setAddEcosystem("gcp");
                    setNewAuthMethod("GCP Service Account");
                  }}
                  className={`p-3 rounded-xl border flex items-center gap-3 transition text-left ${
                    addEcosystem === "gcp"
                      ? "border-amber-500 bg-amber-50/50 text-amber-900 font-bold ring-2 ring-amber-500/20"
                      : "border-slate-200 hover:border-slate-300 text-slate-700"
                  }`}
                >
                  <div className="w-8 h-8 rounded-lg bg-amber-600 text-white flex items-center justify-center font-bold text-xs shrink-0">
                    GCP
                  </div>
                  <div>
                    <div className="font-bold text-xs">Google Cloud</div>
                    <div className="text-[10px] text-slate-500">Projects, BigQuery, VMs</div>
                  </div>
                </button>
              </div>
            </div>

            <form onSubmit={handleAddNewConnection} className="space-y-3.5 text-xs">
              <div>
                <label className="block font-semibold text-navy-900 mb-1">
                  Account Name
                </label>
                <input
                  type="text"
                  value={newConnName}
                  onChange={(e) => setNewConnName(e.target.value)}
                  placeholder={
                    addEcosystem === "azure"
                      ? "e.g. Azure Enterprise Production Subscription"
                      : "e.g. Smart Expense GCP Production Project"
                  }
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-xs focus:ring-1 focus:ring-brand-500 focus:outline-none"
                  required
                />
              </div>

              <div>
                <label className="block font-semibold text-navy-900 mb-1">
                  {addEcosystem === "azure" ? "Azure Subscription ID" : "GCP Project ID"}
                </label>
                <input
                  type="text"
                  value={newScopeId}
                  onChange={(e) => setNewScopeId(e.target.value)}
                  placeholder={
                    addEcosystem === "azure"
                      ? "Azure subscription ID (GUID)"
                      : "e.g. smart-expense-prod-8812"
                  }
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-xs font-mono focus:ring-1 focus:ring-brand-500 focus:outline-none"
                  required
                />
              </div>

              <div>
                <label className="block font-semibold text-navy-900 mb-1">
                  {addEcosystem === "azure" ? "Azure Tenant ID" : "GCP Organization ID (Optional)"}
                </label>
                <input
                  type="text"
                  value={newTenantId}
                  onChange={(e) => setNewTenantId(e.target.value)}
                  placeholder={
                    addEcosystem === "azure"
                      ? "e.g. fe82a67c-faa7-4d9a-bbfa-7d25b7047b41"
                      : "e.g. organizations/44910293817"
                  }
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-xs font-mono focus:ring-1 focus:ring-brand-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block font-semibold text-navy-900 mb-1">
                  Authentication Method
                </label>
                <select
                  value={newAuthMethod}
                  onChange={(e) => setNewAuthMethod(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-xs bg-white focus:ring-1 focus:ring-brand-500 focus:outline-none font-medium"
                >
                  {addEcosystem === "azure" ? (
                    <>
                      <option value="Azure CLI Credentials">Azure CLI Credentials (Local / Sandbox Session)</option>
                      <option value="Service Principal (OAuth2)">Service Principal (Read-Only Secret)</option>
                      <option value="Managed Identity">Azure Managed Identity (Production App Service)</option>
                    </>
                  ) : (
                    <>
                      <option value="GCP Service Account">GCP Service Account (JSON Key Reader)</option>
                      <option value="gcloud CLI Auth">Google Cloud CLI Auth</option>
                    </>
                  )}
                </select>
              </div>

              {/* Service Integrations Configuration for Azure */}
              {addEcosystem === "azure" && (
                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 space-y-2">
                  <span className="block text-[11px] font-bold text-slate-700 uppercase tracking-wider">
                    Enable Azure Ecosystem Service Integrations
                  </span>
                  <div className="space-y-1.5">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={true}
                        disabled
                        className="rounded text-brand-600 focus:ring-brand-500"
                      />
                      <span className="font-semibold text-slate-800">
                        Azure Resource Manager (Core Inventory &amp; Cost API)
                      </span>
                    </label>

                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={enableDatabricksIntegration}
                        onChange={(e) => setEnableDatabricksIntegration(e.target.checked)}
                        className="rounded text-brand-600 focus:ring-brand-500"
                      />
                      <span className="font-semibold text-slate-800">
                        Azure Databricks Integration (Workspaces &amp; System Tables)
                      </span>
                    </label>

                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={enableFabricIntegration}
                        onChange={(e) => setEnableFabricIntegration(e.target.checked)}
                        className="rounded text-brand-600 focus:ring-brand-500"
                      />
                      <span className="font-semibold text-slate-800">
                        Microsoft Fabric Integration (FinOps Lakehouse &amp; Capacities)
                      </span>
                    </label>
                  </div>
                </div>
              )}

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setIsAddConnectionOpen(false)}
                  className="px-3.5 py-2 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-700 font-semibold text-xs transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-bold text-xs transition shadow-2xs"
                >
                  Validate &amp; Connect Account
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
