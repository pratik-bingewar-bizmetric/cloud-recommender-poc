"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  CloudConnection,
  CloudProvider,
  ConnectionValidationResponse,
  CreateConnectionRequest,
} from "@/types";
import { listConnections, validateConnection, createConnection } from "@/lib/api";
import {
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  Loader2,
  ArrowRight,
  RefreshCw,
  Key,
  Lock,
  Server,
  Zap,
} from "lucide-react";

interface ConnectCloudViewProps {
  onConnectionSelected: (
    connection: CloudConnection,
    validation?: ConnectionValidationResponse
  ) => void;
  onContinueToDemo?: () => void;
}

type StepState = "idle" | "connecting" | "validating" | "discovering" | "connected" | "failed";

export const ConnectCloudView: React.FC<ConnectCloudViewProps> = ({
  onConnectionSelected,
  onContinueToDemo,
}) => {
  const [connections, setConnections] = useState<CloudConnection[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // Selected existing connection per provider
  const [selectedAzureId, setSelectedAzureId] = useState<string>("");
  const [selectedGcpId, setSelectedGcpId] = useState<string>("");

  // Tab mode per provider: 'existing' | 'new'
  const [azureTab, setAzureTab] = useState<"existing" | "new">("existing");
  const [gcpTab, setGcpTab] = useState<"existing" | "new">("existing");

  // Validation lifecycle state
  const [activeValidatingProvider, setActiveValidatingProvider] = useState<CloudProvider | null>(
    null
  );
  const [validationStep, setValidationStep] = useState<StepState>("idle");
  const [validationResult, setValidationResult] = useState<ConnectionValidationResponse | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  // Add new Azure Connection form state
  const [newAzName, setNewAzName] = useState<string>("");
  const [newAzSubId, setNewAzSubId] = useState<string>("");
  const [newAzTenantId, setNewAzTenantId] = useState<string>("");
  const [newAzClientId, setNewAzClientId] = useState<string>("");
  const [newAzSecret, setNewAzSecret] = useState<string>("");

  // Add new GCP Connection form state
  const [newGcpName, setNewGcpName] = useState<string>("");
  const [newGcpProjectId, setNewGcpProjectId] = useState<string>("");
  const [newGcpToken, setNewGcpToken] = useState<string>("");

  // Fetch configured connections on mount
  const loadConnections = useCallback(async () => {
    setIsLoading(true);
    setFetchError(null);
    try {
      const data = await listConnections();
      setConnections(data);

      const firstAz = data.find((c) => c.provider === "azure");
      if (firstAz) setSelectedAzureId(firstAz.id);

      const firstGcp = data.find((c) => c.provider === "gcp");
      if (firstGcp) setSelectedGcpId(firstGcp.id);
    } catch (err: unknown) {
      setFetchError(
        err instanceof Error ? err.message : "Failed to load configured cloud connections."
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConnections();
  }, [loadConnections]);

  const azureConnections = connections.filter((c) => c.provider === "azure");
  const gcpConnections = connections.filter((c) => c.provider === "gcp");

  // 1. Existing Connection Flow
  const handleConnectExisting = async (targetConn: CloudConnection) => {
    setActiveValidatingProvider(targetConn.provider);
    setValidationError(null);
    setValidationResult(null);

    // Step 1: Connecting
    setValidationStep("connecting");
    await new Promise((r) => setTimeout(r, 600));

    // Step 2: Validating access
    setValidationStep("validating");
    await new Promise((r) => setTimeout(r, 700));

    // Step 3: Discovering scope
    setValidationStep("discovering");

    try {
      const res = await validateConnection({
        connection_id: targetConn.id,
        provider: targetConn.provider,
        scope_id: targetConn.scope_id,
      });

      if (res.success) {
        setValidationResult(res);
        setValidationStep("connected");
        await new Promise((r) => setTimeout(r, 800));
        onConnectionSelected(targetConn, res);
      } else {
        setValidationStep("failed");
        setValidationError(res.details || "Connection validation failed. Check permissions.");
      }
    } catch (err: unknown) {
      setValidationStep("failed");
      setValidationError(
        err instanceof Error ? err.message : "Validation request failed. Server error."
      );
    }
  };

  // 2. Add New Azure Connection Flow
  const handleCreateAzure = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newAzName || !newAzSubId || !newAzTenantId || !newAzClientId || !newAzSecret) {
      setValidationError("All fields are required to validate Azure Service Principal.");
      return;
    }

    setActiveValidatingProvider("azure");
    setValidationError(null);
    setValidationStep("validating");

    try {
      const req: CreateConnectionRequest = {
        provider: "azure",
        name: newAzName,
        scope_id: newAzSubId,
        azure_tenant_id: newAzTenantId,
        azure_client_id: newAzClientId,
        azure_client_secret: newAzSecret,
      };
      const created = await createConnection(req);

      setValidationStep("discovering");
      const val = await validateConnection({
        connection_id: created.id,
        provider: "azure",
        scope_id: created.scope_id,
      });

      setValidationResult(val);
      setValidationStep("connected");
      await new Promise((r) => setTimeout(r, 800));
      onConnectionSelected(created, val);
    } catch (err: unknown) {
      setValidationStep("failed");
      setValidationError(
        err instanceof Error
          ? err.message
          : "Failed to create and validate Azure connection. Verify credentials."
      );
    }
  };

  // 3. Add New GCP Connection Flow
  const handleCreateGcp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newGcpName || !newGcpProjectId) {
      setValidationError("Connection name and GCP Project ID are required.");
      return;
    }

    setActiveValidatingProvider("gcp");
    setValidationError(null);
    setValidationStep("validating");

    try {
      const req: CreateConnectionRequest = {
        provider: "gcp",
        name: newGcpName,
        scope_id: newGcpProjectId,
        gcp_access_token: newGcpToken || undefined,
      };
      const created = await createConnection(req);

      setValidationStep("discovering");
      const val = await validateConnection({
        connection_id: created.id,
        provider: "gcp",
        scope_id: created.scope_id,
      });

      setValidationResult(val);
      setValidationStep("connected");
      await new Promise((r) => setTimeout(r, 800));
      onConnectionSelected(created, val);
    } catch (err: unknown) {
      setValidationStep("failed");
      setValidationError(
        err instanceof Error
          ? err.message
          : "Failed to validate GCP project. Check IAM roles."
      );
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col justify-between py-10 px-4 sm:px-6 lg:px-8">
      <div className="max-w-5xl mx-auto w-full">
        {/* Top Header & Product Tagline */}
        <div className="text-center max-w-3xl mx-auto mb-10">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-50 border border-blue-200 text-brand-600 text-xs font-semibold uppercase tracking-wider mb-4 shadow-2xs">
            <ShieldCheck className="w-4 h-4 text-brand-600" />
            <span>Connection-First Infrastructure Intelligence</span>
          </div>

          <h1 className="text-3xl sm:text-4xl font-extrabold text-navy-950 tracking-tight font-heading">
            Connect your cloud
          </h1>

          <p className="mt-3 text-sm sm:text-base text-navy-600 font-normal leading-relaxed">
            Understand your infrastructure. Optimize your costs. Engineer what comes next.
          </p>

          {/* Zero-Execution Guardrail Notice */}
          <div className="mt-4 inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-medium">
            <Lock className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
            <span>
              <strong>100% Read-Only Architecture:</strong> This platform performs safe inspection only. It will never create, modify, or mutate customer cloud resources.
            </span>
          </div>
        </div>

        {/* Global Error Banner */}
        {fetchError && (
          <div className="mb-8 p-4 rounded-xl bg-rose-50 border border-rose-200 text-accent-rose text-xs flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{fetchError}</span>
            </div>
            <button
              onClick={loadConnections}
              className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md bg-white border border-rose-200 text-accent-rose font-medium hover:bg-rose-50 transition"
            >
              <RefreshCw className="w-3 h-3" />
              <span>Retry</span>
            </button>
          </div>
        )}

        {/* Validation Progress Overlay / Modal */}
        {activeValidatingProvider && validationStep !== "idle" && (
          <div className="mb-8 p-5 rounded-2xl bg-white border border-slate-200 shadow-sm transition-all">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-brand-50 border border-blue-200 text-brand-600 flex items-center justify-center">
                  <Server className="w-4 h-4" />
                </div>
                <div>
                  <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
                    Connecting to {activeValidatingProvider === "azure" ? "Microsoft Azure" : "Google Cloud"}
                  </h4>
                  <p className="text-xs text-slate-500">
                    Executing live verification probe against cloud resource APIs...
                  </p>
                </div>
              </div>

              {validationStep === "failed" && (
                <button
                  onClick={() => {
                    setValidationStep("idle");
                    setActiveValidatingProvider(null);
                  }}
                  className="text-xs font-medium text-slate-500 hover:text-navy-900"
                >
                  Dismiss
                </button>
              )}
            </div>

            {/* Stepper Status Indicator */}
            <div className="grid grid-cols-4 gap-2 py-3 border-y border-slate-100 my-3 text-xs">
              <div className={`flex items-center gap-1.5 ${validationStep === "connecting" ? "text-brand-600 font-bold" : ["validating", "discovering", "connected"].includes(validationStep) ? "text-emerald-600 font-medium" : "text-slate-400"}`}>
                {validationStep === "connecting" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                <span>1. Connecting</span>
              </div>
              <div className={`flex items-center gap-1.5 ${validationStep === "validating" ? "text-brand-600 font-bold" : ["discovering", "connected"].includes(validationStep) ? "text-emerald-600 font-medium" : "text-slate-400"}`}>
                {validationStep === "validating" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                <span>2. Validating access</span>
              </div>
              <div className={`flex items-center gap-1.5 ${validationStep === "discovering" ? "text-brand-600 font-bold" : validationStep === "connected" ? "text-emerald-600 font-medium" : "text-slate-400"}`}>
                {validationStep === "discovering" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                <span>3. Discovering scope</span>
              </div>
              <div className={`flex items-center gap-1.5 ${validationStep === "connected" ? "text-emerald-600 font-bold" : validationStep === "failed" ? "text-accent-rose font-bold" : "text-slate-400"}`}>
                {validationStep === "connected" ? <CheckCircle2 className="w-3.5 h-3.5" /> : validationStep === "failed" ? <AlertCircle className="w-3.5 h-3.5" /> : <div className="w-3.5 h-3.5 rounded-full border border-slate-300" />}
                <span>4. {validationStep === "failed" ? "Failed" : "Connected"}</span>
              </div>
            </div>

            {validationResult && (
              <div className="p-3 bg-emerald-50/70 border border-emerald-200 rounded-lg text-emerald-900 text-xs flex items-center justify-between">
                <span>{validationResult.details}</span>
                <span className="font-mono text-[11px] text-emerald-700 font-semibold">{validationResult.latency_ms}ms</span>
              </div>
            )}

            {validationError && (
              <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg text-rose-800 text-xs">
                <div className="font-bold mb-1 flex items-center gap-1.5">
                  <AlertCircle className="w-3.5 h-3.5 text-accent-rose" />
                  <span>Validation Error</span>
                </div>
                <p className="leading-relaxed">{validationError}</p>
              </div>
            )}
          </div>
        )}

        {/* 2 Provider Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* ========================================================= */}
          {/* PROVIDER 1: MICROSOFT AZURE                               */}
          {/* ========================================================= */}
          <div className="app-card bg-white border border-slate-200 rounded-2xl p-6 flex flex-col justify-between shadow-2xs hover:shadow-xs transition">
            <div>
              {/* Header */}
              <div className="flex items-center justify-between pb-4 border-b border-slate-100">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-blue-600 text-white flex items-center justify-center font-bold text-sm shadow-2xs">
                    Az
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-navy-950 font-heading">
                      Microsoft Azure
                    </h3>
                    <span className="text-xs text-slate-500">
                      ARM, Azure Monitor, Retail Prices
                    </span>
                  </div>
                </div>

                <span className="px-2.5 py-1 rounded-full text-[11px] font-semibold bg-blue-50 text-brand-600 border border-blue-200">
                  Azure-First
                </span>
              </div>

              {/* Sub-tabs: Use existing connection vs. Add new connection */}
              <div className="flex items-center gap-2 p-1 bg-slate-100 rounded-lg my-4 text-xs">
                <button
                  type="button"
                  onClick={() => setAzureTab("existing")}
                  className={`flex-1 py-1.5 px-3 rounded-md font-medium transition ${
                    azureTab === "existing"
                      ? "bg-white text-navy-900 shadow-2xs font-bold"
                      : "text-slate-600 hover:text-navy-900"
                  }`}
                >
                  Use existing connection ({azureConnections.length})
                </button>
                <button
                  type="button"
                  onClick={() => setAzureTab("new")}
                  className={`flex-1 py-1.5 px-3 rounded-md font-medium transition ${
                    azureTab === "new"
                      ? "bg-white text-navy-900 shadow-2xs font-bold"
                      : "text-slate-600 hover:text-navy-900"
                  }`}
                >
                  Add new connection
                </button>
              </div>

              {/* TAB 1: Existing Connections */}
              {azureTab === "existing" && (
                <div className="space-y-3 min-h-[220px]">
                  {isLoading ? (
                    <div className="p-8 text-center text-slate-400 text-xs">
                      <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2 text-brand-600" />
                      <span>Discovering configured Azure subscriptions...</span>
                    </div>
                  ) : azureConnections.length === 0 ? (
                    <div className="p-6 text-center border border-dashed border-slate-200 rounded-xl text-xs text-slate-500">
                      <p className="font-medium text-navy-800 mb-1">No saved connections yet</p>
                      <p className="mb-3">Configure Service Principal credentials or run &apos;az login&apos;.</p>
                      <button
                        type="button"
                        onClick={() => setAzureTab("new")}
                        className="px-3 py-1.5 rounded-lg bg-brand-600 text-white font-medium hover:bg-brand-700 transition"
                      >
                        Add new connection
                      </button>
                    </div>
                  ) : (
                    azureConnections.map((conn) => {
                      const isSelected = selectedAzureId === conn.id;
                      return (
                        <div
                          key={conn.id}
                          onClick={() => setSelectedAzureId(conn.id)}
                          className={`p-3.5 rounded-xl border text-xs cursor-pointer transition ${
                            isSelected
                              ? "bg-blue-50/50 border-brand-500 shadow-2xs ring-1 ring-brand-500"
                              : "bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50/50"
                          }`}
                        >
                          <div className="flex items-center justify-between mb-1.5">
                            <span className="font-bold text-navy-900 truncate">
                              {conn.name}
                            </span>
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${
                                conn.is_live
                                  ? "bg-emerald-100 text-emerald-800"
                                  : "bg-slate-100 text-slate-600"
                              }`}
                            >
                              {conn.is_live ? "Live ARM Session" : "Reference Fixture"}
                            </span>
                          </div>

                          <div className="text-[11px] text-slate-500 space-y-0.5 font-mono">
                            <p className="truncate">Subscription ID: {conn.scope_id}</p>
                            <p className="text-[10px] text-slate-400">
                              Auth: {conn.auth_method} &bull; Read-Only (Reader)
                            </p>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              )}

              {/* TAB 2: Add New Connection Form */}
              {azureTab === "new" && (
                <form onSubmit={handleCreateAzure} className="space-y-3 text-xs">
                  <div>
                    <label className="block font-semibold text-navy-800 mb-1">
                      Connection Name
                    </label>
                    <input
                      type="text"
                      value={newAzName}
                      onChange={(e) => setNewAzName(e.target.value)}
                      placeholder="e.g. Enterprise Azure Production"
                      className="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-xs focus:ring-1 focus:ring-brand-500 focus:outline-none"
                      required
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="block font-semibold text-navy-800 mb-1">
                        Subscription ID
                      </label>
                      <input
                        type="text"
                        value={newAzSubId}
                        onChange={(e) => setNewAzSubId(e.target.value)}
                        placeholder="xxxxxxxx-xxxx-xxxx-xxxx"
                        className="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-xs font-mono focus:ring-1 focus:ring-brand-500 focus:outline-none"
                        required
                      />
                    </div>
                    <div>
                      <label className="block font-semibold text-navy-800 mb-1">
                        Tenant / Directory ID
                      </label>
                      <input
                        type="text"
                        value={newAzTenantId}
                        onChange={(e) => setNewAzTenantId(e.target.value)}
                        placeholder="xxxxxxxx-xxxx-xxxx-xxxx"
                        className="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-xs font-mono focus:ring-1 focus:ring-brand-500 focus:outline-none"
                        required
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="block font-semibold text-navy-800 mb-1">
                        App / Client ID
                      </label>
                      <input
                        type="text"
                        value={newAzClientId}
                        onChange={(e) => setNewAzClientId(e.target.value)}
                        placeholder="xxxxxxxx-xxxx-xxxx-xxxx"
                        className="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-xs font-mono focus:ring-1 focus:ring-brand-500 focus:outline-none"
                        required
                      />
                    </div>
                    <div>
                      <label className="block font-semibold text-navy-800 mb-1">
                        Client Secret
                      </label>
                      <input
                        type="password"
                        value={newAzSecret}
                        onChange={(e) => setNewAzSecret(e.target.value)}
                        placeholder="••••••••••••••••"
                        className="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-xs font-mono focus:ring-1 focus:ring-brand-500 focus:outline-none"
                        required
                      />
                    </div>
                  </div>

                  <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg text-[11px] text-slate-500 flex items-start gap-1.5">
                    <Key className="w-3.5 h-3.5 text-slate-400 mt-0.5 shrink-0" />
                    <span>
                      Requires read-only roles: <strong>Reader</strong> and <strong>Cost Management Reader</strong>. Credentials never leave your secure session.
                    </span>
                  </div>

                  <button
                    type="submit"
                    disabled={validationStep === "validating" || validationStep === "discovering"}
                    className="w-full py-2 px-4 rounded-lg bg-navy-900 hover:bg-navy-800 text-white font-medium text-xs shadow-2xs transition flex items-center justify-center gap-1.5 disabled:opacity-50"
                  >
                    {validationStep === "validating" ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Zap className="w-4 h-4" />
                    )}
                    <span>Test &amp; Connect Azure</span>
                  </button>
                </form>
              )}
            </div>

            {/* Bottom Actions for Azure */}
            {azureTab === "existing" && (
              <div className="pt-4 border-t border-slate-100 mt-4">
                <button
                  type="button"
                  disabled={!selectedAzureId || validationStep === "connecting" || validationStep === "validating" || validationStep === "discovering"}
                  onClick={() => {
                    const conn = azureConnections.find((c) => c.id === selectedAzureId);
                    if (conn) handleConnectExisting(conn);
                  }}
                  className="w-full py-2.5 px-4 rounded-xl bg-brand-600 hover:bg-brand-700 disabled:bg-slate-200 disabled:text-slate-400 text-white font-bold text-xs shadow-2xs transition flex items-center justify-center gap-2"
                >
                  {validationStep === "connecting" || validationStep === "validating" || validationStep === "discovering" ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Validating Scope...</span>
                    </>
                  ) : (
                    <>
                      <span>Connect Azure Subscription</span>
                      <ArrowRight className="w-4 h-4" />
                    </>
                  )}
                </button>
              </div>
            )}
          </div>

          {/* ========================================================= */}
          {/* PROVIDER 2: GOOGLE CLOUD                                  */}
          {/* ========================================================= */}
          <div className="app-card bg-white border border-slate-200 rounded-2xl p-6 flex flex-col justify-between shadow-2xs hover:shadow-xs transition">
            <div>
              {/* Header */}
              <div className="flex items-center justify-between pb-4 border-b border-slate-100">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-amber-500 text-white flex items-center justify-center font-bold text-sm shadow-2xs">
                    GCP
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-navy-950 font-heading">
                      Google Cloud
                    </h3>
                    <span className="text-xs text-slate-500">
                      Cloud Monitoring, Logging, Billing Catalog
                    </span>
                  </div>
                </div>

                <span className="px-2.5 py-1 rounded-full text-[11px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                  Live Pricing
                </span>
              </div>

              {/* Sub-tabs: Use existing connection vs. Add new connection */}
              <div className="flex items-center gap-2 p-1 bg-slate-100 rounded-lg my-4 text-xs">
                <button
                  type="button"
                  onClick={() => setGcpTab("existing")}
                  className={`flex-1 py-1.5 px-3 rounded-md font-medium transition ${
                    gcpTab === "existing"
                      ? "bg-white text-navy-900 shadow-2xs font-bold"
                      : "text-slate-600 hover:text-navy-900"
                  }`}
                >
                  Use existing connection ({gcpConnections.length})
                </button>
                <button
                  type="button"
                  onClick={() => setGcpTab("new")}
                  className={`flex-1 py-1.5 px-3 rounded-md font-medium transition ${
                    gcpTab === "new"
                      ? "bg-white text-navy-900 shadow-2xs font-bold"
                      : "text-slate-600 hover:text-navy-900"
                  }`}
                >
                  Add new connection
                </button>
              </div>

              {/* TAB 1: Existing Connections */}
              {gcpTab === "existing" && (
                <div className="space-y-3 min-h-[220px]">
                  {isLoading ? (
                    <div className="p-8 text-center text-slate-400 text-xs">
                      <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2 text-amber-600" />
                      <span>Discovering configured Google Cloud scopes...</span>
                    </div>
                  ) : gcpConnections.length === 0 ? (
                    <div className="p-6 text-center border border-dashed border-slate-200 rounded-xl text-xs text-slate-500">
                      <p className="font-medium text-navy-800 mb-1">No saved connections yet</p>
                      <p className="mb-3">Configure a service account key or gcloud ADC.</p>
                      <button
                        type="button"
                        onClick={() => setGcpTab("new")}
                        className="px-3 py-1.5 rounded-lg bg-amber-600 text-white font-medium hover:bg-amber-700 transition"
                      >
                        Add new connection
                      </button>
                    </div>
                  ) : (
                    gcpConnections.map((conn) => {
                      const isSelected = selectedGcpId === conn.id;
                      return (
                        <div
                          key={conn.id}
                          onClick={() => setSelectedGcpId(conn.id)}
                          className={`p-3.5 rounded-xl border text-xs cursor-pointer transition ${
                            isSelected
                              ? "bg-amber-50/50 border-amber-500 shadow-2xs ring-1 ring-amber-500"
                              : "bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50/50"
                          }`}
                        >
                          <div className="flex items-center justify-between mb-1.5">
                            <span className="font-bold text-navy-900 truncate">
                              {conn.name}
                            </span>
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${
                                conn.is_live
                                  ? "bg-emerald-100 text-emerald-800"
                                  : "bg-slate-100 text-slate-600"
                              }`}
                            >
                              {conn.is_live ? "Live IAM Session" : "Reference Benchmark"}
                            </span>
                          </div>

                          <div className="text-[11px] text-slate-500 space-y-0.5 font-mono">
                            <p className="truncate">Project ID: {conn.scope_id}</p>
                            <p className="text-[10px] text-slate-400">
                              Auth: {conn.auth_method} &bull; Read-Only (Viewer)
                            </p>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              )}

              {/* TAB 2: Add New Connection Form */}
              {gcpTab === "new" && (
                <form onSubmit={handleCreateGcp} className="space-y-3 text-xs">
                  <div>
                    <label className="block font-semibold text-navy-800 mb-1">
                      Connection Name
                    </label>
                    <input
                      type="text"
                      value={newGcpName}
                      onChange={(e) => setNewGcpName(e.target.value)}
                      placeholder="e.g. Smart Expense GCP Production"
                      className="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-xs focus:ring-1 focus:ring-amber-500 focus:outline-none"
                      required
                    />
                  </div>

                  <div>
                    <label className="block font-semibold text-navy-800 mb-1">
                      GCP Project ID
                    </label>
                    <input
                      type="text"
                      value={newGcpProjectId}
                      onChange={(e) => setNewGcpProjectId(e.target.value)}
                      placeholder="e.g. my-production-project-1234"
                      className="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-xs font-mono focus:ring-1 focus:ring-amber-500 focus:outline-none"
                      required
                    />
                  </div>

                  <div>
                    <label className="block font-semibold text-navy-800 mb-1">
                      OAuth2 Access Token or Service Account Key (Optional)
                    </label>
                    <textarea
                      rows={3}
                      value={newGcpToken}
                      onChange={(e) => setNewGcpToken(e.target.value)}
                      placeholder="Bearer ya29... or paste service account key content"
                      className="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-xs font-mono focus:ring-1 focus:ring-amber-500 focus:outline-none"
                    />
                  </div>

                  <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg text-[11px] text-slate-500 flex items-start gap-1.5">
                    <Key className="w-3.5 h-3.5 text-slate-400 mt-0.5 shrink-0" />
                    <span>
                      Required IAM roles: <strong>roles/viewer</strong>, <strong>roles/monitoring.viewer</strong>, <strong>roles/logging.viewer</strong>.
                    </span>
                  </div>

                  <button
                    type="submit"
                    disabled={validationStep === "validating" || validationStep === "discovering"}
                    className="w-full py-2 px-4 rounded-lg bg-navy-900 hover:bg-navy-800 text-white font-medium text-xs shadow-2xs transition flex items-center justify-center gap-1.5 disabled:opacity-50"
                  >
                    {validationStep === "validating" ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Zap className="w-4 h-4" />
                    )}
                    <span>Test &amp; Connect Google Cloud</span>
                  </button>
                </form>
              )}
            </div>

            {/* Bottom Actions for GCP */}
            {gcpTab === "existing" && (
              <div className="pt-4 border-t border-slate-100 mt-4">
                <button
                  type="button"
                  disabled={!selectedGcpId || validationStep === "connecting" || validationStep === "validating" || validationStep === "discovering"}
                  onClick={() => {
                    const conn = gcpConnections.find((c) => c.id === selectedGcpId);
                    if (conn) handleConnectExisting(conn);
                  }}
                  className="w-full py-2.5 px-4 rounded-xl bg-amber-600 hover:bg-amber-700 disabled:bg-slate-200 disabled:text-slate-400 text-white font-bold text-xs shadow-2xs transition flex items-center justify-center gap-2"
                >
                  {validationStep === "connecting" || validationStep === "validating" || validationStep === "discovering" ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Validating Scope...</span>
                    </>
                  ) : (
                    <>
                      <span>Connect GCP Project</span>
                      <ArrowRight className="w-4 h-4" />
                    </>
                  )}
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Footer info & demo shortcut */}
        <div className="mt-12 text-center text-xs text-slate-400 flex items-center justify-center gap-4">
          <span>Enterprise Multi-Cloud Architecture POC</span>
          <span>&bull;</span>
          <span>Zero Mutations Enforced</span>
          {onContinueToDemo && (
            <>
              <span>&bull;</span>
              <button
                type="button"
                onClick={onContinueToDemo}
                className="text-brand-600 hover:underline font-medium"
              >
                Skip to Demo Standby Mode &rarr;
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

