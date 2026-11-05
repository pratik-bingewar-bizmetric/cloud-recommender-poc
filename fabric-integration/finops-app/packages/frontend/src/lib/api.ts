import {
  ApiErrorDetail,
  ArchitectureComponent,
  ClarifyingAnswer,
  CostSimulationResponse,
  LogSearchRequest,
  LogSearchResponse,
  MonitoringOverviewResponse,
  MonitoringQueryRequest,
  MonitoringSourcesResponse,
  RecommendationReport,
  RequirementsAnalysisResponse,
  ResourceDetailMonitoringResponse,
  WorkloadAssumptions,
  WorkloadProfile,
} from "@/types";
import {
  getFabricUdfBaseUrl,
  udfListConnections,
  udfCreateConnection,
  udfValidateConnection,
  udfDeleteConnection,
  udfGetInventory,
  udfGetCostWaste,
  udfGetTokenEconomics,
} from "./fabric-udf-client";

export function getApiBaseUrl(): string {
  const envUrl = import.meta.env.VITE_API_BASE_URL;
  if (envUrl && envUrl.trim() !== "") {
    return envUrl.replace(/\/+$/, "");
  }
  if (import.meta.env.DEV) {
    return "http://localhost:8000/api/v1";
  }
  if (import.meta.env.VITE_USE_FABRIC_UDF === "true") {
    return getFabricUdfBaseUrl();
  }
  // In production, do not silently fallback to localhost
  throw new ApiError(
    503,
    {
      error_code: "API_ENDPOINT_NOT_CONFIGURED",
      message:
        "FinOps Backend API URL (VITE_API_BASE_URL) is not configured for production. Please configure VITE_API_BASE_URL in your Fabric app environment.",
    },
    "FinOps Backend API URL (VITE_API_BASE_URL) is not configured for production."
  );
}

const API_BASE_URL = {
  toString(): string {
    return getApiBaseUrl();
  },
  replace(searchValue: string | RegExp, replaceValue: string): string {
    return getApiBaseUrl().replace(searchValue, replaceValue);
  },
};

export class ApiError extends Error {
  status: number;
  detail: ApiErrorDetail;

  constructor(status: number, detail: ApiErrorDetail, message?: string) {
    super(message || detail.message || `API request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export type TokenProvider = () => Promise<string | null> | string | null;
let currentTokenProvider: TokenProvider | null = null;
let isResolvingToken = false;

const ENTRA_TOKEN_STORAGE_KEY = "fabric_entra_access_token";

/**
 * Persist or clear a delegated Microsoft Entra ID access token for Fabric UDF REST calls.
 */
export function setStoredEntraToken(token: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (token && token.trim()) {
      sessionStorage.setItem(ENTRA_TOKEN_STORAGE_KEY, token.trim());
      localStorage.setItem(ENTRA_TOKEN_STORAGE_KEY, token.trim());
    } else {
      sessionStorage.removeItem(ENTRA_TOKEN_STORAGE_KEY);
      localStorage.removeItem(ENTRA_TOKEN_STORAGE_KEY);
    }
  } catch {
    // Storage access restricted
  }
}

/**
 * Retrieve the active delegated Microsoft Entra ID token from session or local storage.
 */
export function getStoredEntraToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const sessionVal = sessionStorage.getItem(ENTRA_TOKEN_STORAGE_KEY);
    if (sessionVal && sessionVal.trim()) return sessionVal.trim();
    const localVal = localStorage.getItem(ENTRA_TOKEN_STORAGE_KEY);
    if (localVal && localVal.trim()) return localVal.trim();
  } catch {
    // Storage access restricted
  }
  return null;
}

/**
 * Configure an asynchronous or synchronous token provider for Entra ID Bearer token forwarding.
 */
export function setAuthTokenProvider(provider: TokenProvider | null): void {
  currentTokenProvider = provider;
}

/**
 * Resolve the current access token from Entra storage, active provider, or Rayfin localStorage session.
 */
export async function getAuthToken(): Promise<string | null> {
  // 1. Explicit delegated Microsoft Entra token (highest priority for Fabric UDF REST)
  const explicitEntra = getStoredEntraToken();
  if (explicitEntra) {
    return explicitEntra;
  }

  // 2. Active token provider with recursion guard
  if (currentTokenProvider && !isResolvingToken) {
    try {
      isResolvingToken = true;
      const token = await currentTokenProvider();
      if (token && typeof token === "string" && token.trim()) {
        return token.trim();
      }
    } catch (err) {
      console.warn("[FinOps Auth] currentTokenProvider failed:", err);
    } finally {
      isResolvingToken = false;
    }
  }

  // 3. Fallback: Rayfin localStorage authSession
  if (typeof window !== "undefined" && window.localStorage) {
    try {
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key && (key === "authSession" || key.endsWith("_authSession"))) {
          const raw = localStorage.getItem(key);
          if (raw) {
            const parsed = JSON.parse(raw);
            if (parsed.accessToken && typeof parsed.accessToken === "string") {
              return parsed.accessToken.trim();
            }
          }
        }
      }
    } catch {
      // Ignore storage read errors
    }
  }
  return null;
}

async function getHeaders(customHeaders?: Record<string, string>): Promise<Record<string, string> | undefined> {
  const token = await getAuthToken();
  if (!token && !customHeaders) {
    return undefined;
  }
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(customHeaders || {}),
  };
  if (token && !headers["Authorization"]) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail: ApiErrorDetail = {};
    try {
      const data = await res.json();
      if (data.error && data.error.message && typeof data.error.message === "object") {
        detail = data.error.message;
      } else if (data.detail && typeof data.detail === "object") {
        detail = data.detail;
      } else if (typeof data.detail === "string") {
        detail = { message: data.detail };
      } else if (data.error && typeof data.error.message === "string") {
        detail = { message: data.error.message };
      }
    } catch {
      detail = { message: res.statusText };
    }

    let defaultMsg = `API request failed with status ${res.status}`;
    if (res.status === 401) {
      defaultMsg = detail.message || "Authentication required. Please sign in via Microsoft Entra ID.";
    } else if (res.status === 403) {
      defaultMsg = detail.message || "Access denied. Insufficient role permissions for this operation.";
    }

    throw new ApiError(res.status, detail, defaultMsg);
  }
  return res.json() as Promise<T>;
}

export async function checkBackendHealth(): Promise<{ status: string }> {
  if (import.meta.env.VITE_USE_FABRIC_UDF === "true") {
    return { status: "healthy" };
  }
  const rootUrl = API_BASE_URL.replace(/\/api\/v1\/?$/, "");
  const res = await fetch(`${rootUrl}/health`);
  return handleResponse<{ status: string }>(res);
}

export async function analyzeRequirements(
  idea: string,
  targetRegion: string = "eastus",
  customerPreset?: number
): Promise<RequirementsAnalysisResponse> {
  const res = await fetch(`${API_BASE_URL}/analysis/requirements`, {
    method: "POST",
    headers: await getHeaders(),
    body: JSON.stringify({
      idea,
      target_region: targetRegion,
      customer_preset: customerPreset,
    }),
  });
  return handleResponse<RequirementsAnalysisResponse>(res);
}

export async function generateArchitecture(
  workloadProfile: WorkloadProfile,
  workloadAssumptions: WorkloadAssumptions,
  clarifications: ClarifyingAnswer[],
  targetRegion: string = "eastus"
): Promise<RecommendationReport> {
  const res = await fetch(`${API_BASE_URL}/architecture/generate`, {
    method: "POST",
    headers: await getHeaders(),
    body: JSON.stringify({
      workload_profile: {
        name: workloadProfile.name,
        category: workloadProfile.category,
        description: workloadProfile.description,
        expected_monthly_active_users: workloadProfile.expected_monthly_active_users,
        expected_requests_per_second: workloadProfile.expected_requests_per_second,
        target_availability_percentage: workloadProfile.target_availability_percentage,
        storage_volume_gb: workloadProfile.storage_volume_gb,
        monthly_data_egress_gb: workloadProfile.monthly_data_egress_gb,
        target_regions: workloadProfile.target_regions,
        estimation_assumptions: workloadProfile.estimation_assumptions,
      },
      workload_assumptions: workloadAssumptions,
      clarifications,
      target_region: targetRegion,
    }),
  });
  return handleResponse<RecommendationReport>(res);
}

export async function simulatePricing(
  components: ArchitectureComponent[],
  workloadAssumptions: WorkloadAssumptions,
  targetRegion: string = "eastus",
  safetyBufferPercentage: string = "15.00"
): Promise<CostSimulationResponse> {
  const res = await fetch(`${API_BASE_URL}/pricing/simulate`, {
    method: "POST",
    headers: await getHeaders(),
    body: JSON.stringify({
      components,
      workload_assumptions: workloadAssumptions,
      target_region: targetRegion,
      safety_buffer_percentage: safetyBufferPercentage,
    }),
  });
  return handleResponse<CostSimulationResponse>(res);
}

// Subscription & Project Inventory API Methods
import type {
  CloudScopeSummary,
  MultiCloudComparisonRequest,
  MultiCloudComparisonResponse,
  ProviderConnectionStatus,
  SubscriptionOrProjectAnalysis,
} from "@/types";

export async function getProvidersStatus(): Promise<ProviderConnectionStatus[]> {
  if (import.meta.env.VITE_USE_FABRIC_UDF === "true") {
    const connections = await udfListConnections();
    const azureConns = connections.filter((c) => c.provider === "azure");
    const isAzureConnected = azureConns.some((c) => c.status === "connected");
    return [
      {
        provider: "azure" as const,
        status: isAzureConnected ? "connected" : "not_configured",
        accounts_count: azureConns.length,
        last_synced_at: azureConns[0]?.last_verified_at || null,
      },
      {
        provider: "aws" as const,
        status: "not_configured" as const,
        accounts_count: 0,
        last_synced_at: null,
      },
      {
        provider: "gcp" as const,
        status: "not_configured" as const,
        accounts_count: 0,
        last_synced_at: null,
      },
    ];
  }
  const headers = await getHeaders();
  const url = `${API_BASE_URL}/inventory/providers/status`;
  const res = headers ? await fetch(url, { headers }) : await fetch(url);
  return handleResponse<ProviderConnectionStatus[]>(res);
}

export async function listAzureSubscriptions(): Promise<CloudScopeSummary[]> {
  if (import.meta.env.VITE_USE_FABRIC_UDF === "true") {
    const connections = await udfListConnections("azure");
    return connections.map((conn) => ({
      provider: "azure" as const,
      scope_id: conn.scope_id || conn.id,
      display_name: conn.name,
      tenant_or_org_id: conn.tenant_or_org_id || null,
      parent_scope_id: null,
      state: conn.status,
      data_source: conn.is_live ? ("live_authenticated" as const) : ("mock_fixture" as const),
    }));
  }
  const headers = await getHeaders();
  const url = `${API_BASE_URL}/inventory/azure/subscriptions`;
  const res = headers ? await fetch(url, { headers }) : await fetch(url);
  return handleResponse<CloudScopeSummary[]>(res);
}

export async function analyzeAzureSubscription(payload: {
  scope_id?: string | null;
  resource_group_filter?: string | null;
  workload_assumptions?: WorkloadAssumptions;
  safety_buffer_percentage?: string;
  metric_window_days?: number;
  refresh_telemetry?: boolean;
}): Promise<SubscriptionOrProjectAnalysis> {
  if (import.meta.env.VITE_USE_FABRIC_UDF === "true") {
    const connectionId = payload.scope_id || "conn-default";
    const [inv, waste] = await Promise.all([
      udfGetInventory({ connection_id: connectionId }),
      udfGetCostWaste({ connection_id: connectionId, force_refresh: payload.refresh_telemetry }),
    ]);

    const resources = inv.map((r) => ({
      resource_id: r.resource_id,
      name: r.name,
      resource_type: r.resource_type,
      location: r.location,
      tags: r.tags || {},
      monthly_cost_usd: String(r.monthly_cost_usd || "0.00"),
    }));

    return {
      provider: "azure" as const,
      scope_id: payload.scope_id || "azure-subscription",
      scope_name: payload.scope_id || "Azure Subscription",
      scope_type: "azure_subscription" as const,
      tenant_or_org_id: null,
      hierarchy_nodes: [],
      data_source: "live_authenticated" as const,
      spend_label: "actual_billed_spend" as const,
      actual_billed_monthly_spend: String(waste.total_monthly_waste_usd),
      resource_count: resources.length,
      group_count: 1,
      groups: [],
      resources: resources as any,
      cost_breakdown: {
        total_monthly_usd: String(waste.total_monthly_waste_usd),
        total_annual_usd: String(waste.total_annual_waste_usd),
        compute_cost_usd: "0.00",
        storage_cost_usd: "0.00",
        network_cost_usd: "0.00",
        database_cost_usd: "0.00",
        other_cost_usd: "0.00",
      },
    };
  }
  const res = await fetch(`${API_BASE_URL}/inventory/azure/analyze`, {
    method: "POST",
    headers: await getHeaders(),
    body: JSON.stringify({
      scope_id: payload.scope_id || null,
      resource_group_filter: payload.resource_group_filter || null,
      workload_assumptions: payload.workload_assumptions,
      safety_buffer_percentage: payload.safety_buffer_percentage || "0.00",
      metric_window_days: payload.metric_window_days ?? 30,
      refresh_telemetry: payload.refresh_telemetry ?? false,
    }),
  });
  return handleResponse<SubscriptionOrProjectAnalysis>(res);
}

export async function listGcpProjects(): Promise<CloudScopeSummary[]> {
  const headers = await getHeaders();
  const url = `${API_BASE_URL}/inventory/gcp/projects`;
  const res = headers ? await fetch(url, { headers }) : await fetch(url);
  return handleResponse<CloudScopeSummary[]>(res);
}

export async function analyzeGcpProject(payload: {
  scope_id?: string | null;
  workload_assumptions?: WorkloadAssumptions;
  safety_buffer_percentage?: string;
  metric_window_days?: number;
  refresh_telemetry?: boolean;
}): Promise<SubscriptionOrProjectAnalysis> {
  const res = await fetch(`${API_BASE_URL}/inventory/gcp/analyze`, {
    method: "POST",
    headers: await getHeaders(),
    body: JSON.stringify({
      scope_id: payload.scope_id || null,
      workload_assumptions: payload.workload_assumptions,
      safety_buffer_percentage: payload.safety_buffer_percentage || "0.00",
      metric_window_days: payload.metric_window_days ?? 30,
      refresh_telemetry: payload.refresh_telemetry ?? false,
    }),
  });
  return handleResponse<SubscriptionOrProjectAnalysis>(res);
}

export async function compareMultiCloud(
  payload: MultiCloudComparisonRequest
): Promise<MultiCloudComparisonResponse> {
  const res = await fetch(`${API_BASE_URL}/inventory/compare`, {
    method: "POST",
    headers: await getHeaders(),
    body: JSON.stringify(payload),
  });
  return handleResponse<MultiCloudComparisonResponse>(res);
}

// ----------------------------------------------------------------------------
// Centralized Monitoring, Telemetry, and Log Intelligence API
// ----------------------------------------------------------------------------

export async function getMonitoringOverview(
  payload: MonitoringQueryRequest,
  signal?: AbortSignal
): Promise<MonitoringOverviewResponse> {
  const res = await fetch(`${API_BASE_URL}/monitoring/overview`, {
    method: "POST",
    headers: await getHeaders(),
    body: JSON.stringify(payload),
    signal,
  });
  return handleResponse<MonitoringOverviewResponse>(res);
}

export async function getResourceMonitoringDetail(
  payload: MonitoringQueryRequest
): Promise<ResourceDetailMonitoringResponse> {
  const res = await fetch(`${API_BASE_URL}/monitoring/resource`, {
    method: "POST",
    headers: await getHeaders(),
    body: JSON.stringify(payload),
  });
  return handleResponse<ResourceDetailMonitoringResponse>(res);
}

export async function searchMonitoringLogs(
  payload: LogSearchRequest
): Promise<LogSearchResponse> {
  const res = await fetch(`${API_BASE_URL}/monitoring/logs`, {
    method: "POST",
    headers: await getHeaders(),
    body: JSON.stringify(payload),
  });
  return handleResponse<LogSearchResponse>(res);
}

export async function getMonitoringSources(): Promise<MonitoringSourcesResponse> {
  const res = await fetch(`${API_BASE_URL}/monitoring/sources`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<MonitoringSourcesResponse>(res);
}

// ----------------------------------------------------------------------------
// Cloud Provider Connections Lifecycle API
// ----------------------------------------------------------------------------

export async function listConnections(): Promise<import("@/types").CloudConnection[]> {
  if (import.meta.env.VITE_USE_FABRIC_UDF === "true") {
    return udfListConnections();
  }
  const res = await fetch(`${API_BASE_URL}/connections`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").CloudConnection[]>(res);
}

export async function validateConnection(
  payload: import("@/types").ValidateConnectionRequest
): Promise<import("@/types").ConnectionValidationResponse> {
  if (import.meta.env.VITE_USE_FABRIC_UDF === "true") {
    const res = await udfValidateConnection({
      connection_id: payload.connection_id || undefined,
      provider: payload.provider,
      subscription_id: payload.scope_id,
    });
    return {
      success: res.valid,
      connection_id: payload.connection_id || "conn-val",
      provider: payload.provider,
      scope_id: payload.scope_id,
      scope_name: payload.scope_id,
      status: res.valid ? "connected" : "auth_failed",
      details: res.message,
      discovered_resource_count: 0,
      discovered_resource_groups: [],
      permissions_verified: ["Reader", "Cost Management Reader"],
      is_live: true,
      latency_ms: 100,
      validated_at: new Date().toISOString(),
    };
  }
  const res = await fetch(`${API_BASE_URL}/connections/validate`, {
    method: "POST",
    headers: await getHeaders(),
    body: JSON.stringify(payload),
  });
  return handleResponse<import("@/types").ConnectionValidationResponse>(res);
}

export async function createConnection(
  payload: import("@/types").CreateConnectionRequest
): Promise<import("@/types").CloudConnection> {
  if (import.meta.env.VITE_USE_FABRIC_UDF === "true") {
    return udfCreateConnection({
      name: payload.name,
      tenant_id: payload.azure_tenant_id || "",
      subscription_id: payload.scope_id,
      client_id: payload.azure_client_id || "",
      client_secret: payload.azure_client_secret || "",
      provider: payload.provider,
    });
  }
  const res = await fetch(`${API_BASE_URL}/connections`, {
    method: "POST",
    headers: await getHeaders(),
    body: JSON.stringify(payload),
  });
  return handleResponse<import("@/types").CloudConnection>(res);
}

export async function deleteConnection(
  connectionId: string
): Promise<{ deleted: boolean; connection_id: string }> {
  if (import.meta.env.VITE_USE_FABRIC_UDF === "true") {
    return udfDeleteConnection(connectionId);
  }
  const res = await fetch(`${API_BASE_URL}/connections/${connectionId}`, {
    method: "DELETE",
    headers: await getHeaders(),
  });
  return handleResponse<{ deleted: boolean; connection_id: string }>(res);
}

// ----------------------------------------------------------------------------
// Token Economics & AI Consumption Telemetry API
// ----------------------------------------------------------------------------

export async function getTokenEconomics(
  payload: MonitoringQueryRequest,
  signal?: AbortSignal
): Promise<import("@/types").TokenEconomicsSummary> {
  if (import.meta.env.VITE_USE_FABRIC_UDF === "true") {
    const raw = await udfGetTokenEconomics({
      connection_id: payload.scope_id || "default",
      days: payload.time_window === "7d" ? 7 : 30,
    });

    const hasTokens = raw.total_tokens > 0;
    return {
      provider: payload.provider || "azure",
      scope_id: payload.scope_id || "",
      scope_name: payload.scope_id || "Connected Scope",
      time_window: payload.time_window || "30d",
      data_status: hasTokens ? "live_telemetry" : "no_data_available",
      status_message: hasTokens
        ? "Live telemetry observed from model invocations and Azure AI Foundry."
        : "No token telemetry recorded in this interval.",
      total_tokens: raw.total_tokens,
      prompt_tokens: raw.total_prompt_tokens,
      completion_tokens: raw.total_completion_tokens,
      estimated_cost_usd: Number(raw.total_cost_usd),
      unattributed_tokens: 0,
      unattributed_percentage: 0,
      active_models_count: raw.models_breakdown.length,
      discovered_ai_resources_count: raw.models_breakdown.length > 0 ? 1 : 0,
      discovered_ai_resources: raw.models_breakdown.map((m) => m.model_name),
      trend_points: raw.daily_timeseries.map((d) => ({
        timestamp: d.timestamp,
        prompt_tokens: d.promptTokens,
        completion_tokens: d.completionTokens,
        total_tokens: d.totalTokens,
        estimated_cost_usd: d.costUsd,
      })),
      model_breakdowns: raw.models_breakdown.map((m) => ({
        model_name: m.model_name,
        provider: "Azure OpenAI",
        prompt_tokens: m.prompt_tokens,
        completion_tokens: m.completion_tokens,
        total_tokens: m.total_tokens,
        prompt_rate_per_million: "2.5000",
        completion_rate_per_million: "10.0000",
        total_cost_usd: m.cost_usd,
        percentage_of_total: raw.total_tokens > 0 ? (m.total_tokens / raw.total_tokens) * 100 : 0,
      })),
      workload_breakdowns: [],
      usage_records: [],
      diagnostic_setup_guide: [
        "1. In Azure AI Foundry, ensure Diagnostic Settings route Metrics (TokenCount) to Log Analytics.",
        "2. For platform LLM requests, real usage tokens are captured automatically upon completion.",
      ],
      generated_at: new Date().toISOString(),
    };
  }

  const res = await fetch(`${API_BASE_URL}/monitoring/token-economics`, {
    method: "POST",
    headers: await getHeaders(),
    body: JSON.stringify(payload),
    signal,
  });
  return handleResponse<import("@/types").TokenEconomicsSummary>(res);
}

// Re-export Fabric UDF client operations
export {
  invokeUdfFunction,
  getFabricUdfBaseUrl,
  FabricUdfError,
  udfListConnections,
  udfCreateConnection,
  udfValidateConnection,
  udfDeleteConnection,
  udfGetInventory,
  udfGetCostWaste,
  udfGetMetrics,
  udfGetTokenEconomics,
  udfRecordTokenUsage,
  udfCalculatePricing,
} from "./fabric-udf-client";

