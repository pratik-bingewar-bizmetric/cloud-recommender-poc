import { entraTokenService } from "@/services/entra-token.service";
import type {
  LogoutResponse,
  ServicePrincipalConnectRequest,
  ServicePrincipalConnectResponse,
  SessionInfoResponse,
} from "@/types/auth";
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

export function getApiBaseUrl(): string {
  const envUrl = import.meta.env.VITE_API_BASE_URL;
  if (envUrl && envUrl.trim() !== "") {
    return envUrl.replace(/\/+$/, "");
  }
  if (import.meta.env.DEV) {
    return "http://localhost:8000/api/v1";
  }
  // In production, do not silently fallback to localhost or UDF
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
let activeSessionToken: string | null = null;

const ENTRA_TOKEN_STORAGE_KEY = "fabric_entra_access_token";
const SESSION_TOKEN_STORAGE_KEY = "finops_session_token";

/**
 * Persist or clear the active Service Principal application session token.
 */
export function setSessionToken(token: string | null): void {
  activeSessionToken = token && token.trim() ? token.trim() : null;
  if (typeof window !== "undefined") {
    try {
      if (activeSessionToken) {
        sessionStorage.setItem(SESSION_TOKEN_STORAGE_KEY, activeSessionToken);
      } else {
        sessionStorage.removeItem(SESSION_TOKEN_STORAGE_KEY);
      }
    } catch {
      // Storage access restricted
    }
  }
}

/**
 * Retrieve the active Service Principal application session token from memory or session storage.
 */
export function getSessionToken(): string | null {
  if (activeSessionToken) {
    return activeSessionToken;
  }
  if (typeof window !== "undefined") {
    try {
      const stored = sessionStorage.getItem(SESSION_TOKEN_STORAGE_KEY);
      if (stored && stored.trim()) {
        activeSessionToken = stored.trim();
        return activeSessionToken;
      }
    } catch {
      // Storage access restricted
    }
  }
  return null;
}

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
  const sessionToken = getSessionToken();
  const token = sessionToken ?? (await entraTokenService.getAccessTokenSilent()) ?? (await getAuthToken());
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

async function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  try {
    return init !== undefined ? await fetch(input, init) : await fetch(input);
  } catch (err) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(
      503,
      {
        error_code: "BACKEND_UNAVAILABLE",
        message:
          err instanceof Error
            ? `FinOps backend is unreachable: ${err.message}`
            : "FinOps backend is unreachable.",
      },
      "FinOps backend is unreachable. Please verify network connectivity."
    );
  }
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
      defaultMsg =
        detail.message ||
        "Authentication required. Please sign in via Microsoft Entra ID to access FinOps services.";
    } else if (res.status === 403) {
      defaultMsg =
        detail.message ||
        "Access denied. You do not have the required permissions (e.g. FinOpsAdmin) for this operation.";
    } else if (res.status === 503) {
      if (detail.error_code === "DATABASE_UNAVAILABLE") {
        defaultMsg =
          "The application database is temporarily unavailable or not initialized. Cloud connection persistence is paused until migrations are applied.";
      } else if (detail.error_code === "BACKEND_UNAVAILABLE") {
        defaultMsg = detail.message || "FinOps backend is unreachable. Please verify connectivity.";
      } else {
        defaultMsg = detail.message || "The requested FinOps service is temporarily unavailable.";
      }
    } else if (res.status === 404) {
      defaultMsg = detail.message || "The requested resource was not found.";
    } else if (res.status === 422) {
      defaultMsg = detail.message || "Request validation failed. Please check input parameters.";
    }

    throw new ApiError(res.status, detail, defaultMsg);
  }
  return res.json() as Promise<T>;
}

export async function checkBackendHealth(): Promise<{ status: string }> {
  const rootUrl = API_BASE_URL.replace(/\/api\/v1\/?$/, "");
  const res = await apiFetch(`${rootUrl}/health`);
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
  const headers = await getHeaders();
  const url = `${API_BASE_URL}/inventory/providers/status`;
  const res = await apiFetch(url, headers ? { headers } : undefined);
  return handleResponse<ProviderConnectionStatus[]>(res);
}

export async function listAzureSubscriptions(): Promise<CloudScopeSummary[]> {
  const headers = await getHeaders();
  const url = `${API_BASE_URL}/inventory/azure/subscriptions`;
  const res = await apiFetch(url, headers ? { headers } : undefined);
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
  const res = await apiFetch(`${API_BASE_URL}/inventory/azure/analyze`, {
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
  const res = await apiFetch(`${API_BASE_URL}/connections`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").CloudConnection[]>(res);
}

export async function validateConnection(
  payload: import("@/types").ValidateConnectionRequest
): Promise<import("@/types").ConnectionValidationResponse> {
  const res = await apiFetch(`${API_BASE_URL}/connections/validate`, {
    method: "POST",
    headers: await getHeaders(),
    body: JSON.stringify(payload),
  });
  return handleResponse<import("@/types").ConnectionValidationResponse>(res);
}

export async function createConnection(
  payload: import("@/types").CreateConnectionRequest
): Promise<import("@/types").CloudConnection> {
  const res = await apiFetch(`${API_BASE_URL}/connections`, {
    method: "POST",
    headers: await getHeaders(),
    body: JSON.stringify(payload),
  });
  return handleResponse<import("@/types").CloudConnection>(res);
}

export async function deleteConnection(
  connectionId: string
): Promise<{ deleted: boolean; connection_id: string }> {
  const res = await apiFetch(`${API_BASE_URL}/connections/${encodeURIComponent(connectionId)}`, {
    method: "DELETE",
    headers: await getHeaders(),
  });
  if (res.status === 204) return { deleted: true, connection_id: connectionId };
  return handleResponse<{ deleted: boolean; connection_id: string }>(res);
}

// ----------------------------------------------------------------------------
// Token Economics & AI Consumption Telemetry API
// ----------------------------------------------------------------------------

export async function getTokenEconomics(
  payload: MonitoringQueryRequest,
  signal?: AbortSignal
): Promise<import("@/types").TokenEconomicsSummary> {
  const res = await apiFetch(`${API_BASE_URL}/monitoring/token-economics`, {
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



// ----------------------------------------------------------------------------
// Multi-Cloud Resource Configuration & Scope Selection Client
// ----------------------------------------------------------------------------

export async function discoverScopes(
  connectionId: string,
  provider: string = "azure"
): Promise<import("@/types").ScopeDiscoveryResponse> {
  const params = new URLSearchParams({ connection_id: connectionId, provider });
  const res = await fetch(`${API_BASE_URL}/configuration/scopes/discover?${params.toString()}`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").ScopeDiscoveryResponse>(res);
}

export async function getConfiguration(
  connectionId: string
): Promise<import("@/types").ResourceConfigurationResponse> {
  const res = await fetch(`${API_BASE_URL}/configuration/${encodeURIComponent(connectionId)}`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").ResourceConfigurationResponse>(res);
}

export async function saveConfiguration(
  payload: import("@/types").ResourceConfigurationCreate
): Promise<import("@/types").ResourceConfigurationResponse> {
  const res = await fetch(`${API_BASE_URL}/configuration`, {
    method: "POST",
    headers: await getHeaders(),
    body: JSON.stringify(payload),
  });
  return handleResponse<import("@/types").ResourceConfigurationResponse>(res);
}

export async function getEffectiveSelection(
  connectionId: string
): Promise<import("@/types").EffectiveSelectionResponse> {
  const res = await fetch(`${API_BASE_URL}/configuration/${encodeURIComponent(connectionId)}/selected`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").EffectiveSelectionResponse>(res);
}

export async function getSelectedWorkspaces(
  connectionId: string
): Promise<Array<Record<string, unknown>>> {
  const res = await fetch(`${API_BASE_URL}/configuration/${encodeURIComponent(connectionId)}/workspaces`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<Array<Record<string, unknown>>>(res);
}

export async function getConfigurationStatus(
  connectionId: string
): Promise<import("@/types").ConfigurationStatusResponse> {
  const res = await fetch(`${API_BASE_URL}/configuration/${encodeURIComponent(connectionId)}/status`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").ConfigurationStatusResponse>(res);
}

// ---------------------------------------------------------------------------
// Scope-Aware Ingestion API Functions (Phase 2C)
// ---------------------------------------------------------------------------

export async function checkIngestionReadiness(
  connectionId: string
): Promise<import("@/types").IngestionReadinessResponse> {
  const res = await fetch(`${API_BASE_URL}/ingestion/${encodeURIComponent(connectionId)}/readiness`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").IngestionReadinessResponse>(res);
}

export async function triggerIngestionRun(
  connectionId: string,
  forceResync: boolean = false
): Promise<import("@/types").IngestionRunResponse> {
  const res = await fetch(`${API_BASE_URL}/ingestion/${encodeURIComponent(connectionId)}/runs`, {
    method: "POST",
    headers: await getHeaders(),
    body: JSON.stringify({ force_resync: forceResync, triggered_by: "user" }),
  });
  return handleResponse<import("@/types").IngestionRunResponse>(res);
}

export async function listIngestionRuns(
  connectionId: string,
  limit: number = 20
): Promise<import("@/types").IngestionRunSummaryResponse[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  const res = await fetch(`${API_BASE_URL}/ingestion/${encodeURIComponent(connectionId)}/runs?${params.toString()}`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").IngestionRunSummaryResponse[]>(res);
}

export async function getIngestionRun(
  runId: string
): Promise<import("@/types").IngestionRunResponse> {
  const res = await fetch(`${API_BASE_URL}/ingestion/runs/${encodeURIComponent(runId)}`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").IngestionRunResponse>(res);
}

export async function retryIngestionRun(
  runId: string
): Promise<import("@/types").IngestionRunResponse> {
  const res = await fetch(`${API_BASE_URL}/ingestion/runs/${encodeURIComponent(runId)}/retry`, {
    method: "POST",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").IngestionRunResponse>(res);
}

// ---------------------------------------------------------------------------
// Milestone 6 Phase 3: Databricks Multi-Workspace API Methods
// ---------------------------------------------------------------------------

export async function listDatabricksConnections(): Promise<import("@/types").DatabricksConnection[]> {
  const res = await apiFetch(`${API_BASE_URL}/databricks/connections`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").DatabricksConnection[]>(res);
}

export async function getDatabricksConnection(
  connectionId: string
): Promise<import("@/types").DatabricksConnection> {
  const res = await apiFetch(`${API_BASE_URL}/databricks/connections/${encodeURIComponent(connectionId)}`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").DatabricksConnection>(res);
}

export async function testDatabricksConnection(
  connectionId: string
): Promise<import("@/types").DatabricksConnectionTestResponse> {
  const res = await apiFetch(`${API_BASE_URL}/databricks/connections/${encodeURIComponent(connectionId)}/test`, {
    method: "POST",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").DatabricksConnectionTestResponse>(res);
}

export async function getWorkspaceDiscovery(
  connectionId: string
): Promise<import("@/types").DatabricksWorkspaceDiscovery> {
  const res = await apiFetch(`${API_BASE_URL}/databricks/connections/${encodeURIComponent(connectionId)}/discovery`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").DatabricksWorkspaceDiscovery>(res);
}

export async function refreshWorkspaceDiscovery(
  connectionId: string
): Promise<import("@/types").DatabricksWorkspaceDiscovery> {
  const res = await apiFetch(`${API_BASE_URL}/databricks/connections/${encodeURIComponent(connectionId)}/discovery/refresh`, {
    method: "POST",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").DatabricksWorkspaceDiscovery>(res);
}

export async function getWorkspaceHealth(
  connectionId: string
): Promise<import("@/types").DatabricksConnectionHealth> {
  const res = await apiFetch(`${API_BASE_URL}/databricks/connections/${encodeURIComponent(connectionId)}/health`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").DatabricksConnectionHealth>(res);
}

// -------------------------------------------------------------
// Milestone 3B: FinOps Command Center 15-Module API Functions
// -------------------------------------------------------------

export async function getFinOpsOverview(
  connectionId = "databricks-azure-dev",
  period = "month",
  environment?: string
): Promise<import("@/types").ExecutiveOverviewData> {
  const params = new URLSearchParams({ connection_id: connectionId, period });
  if (environment) params.append("environment", environment);
  const res = await apiFetch(`${API_BASE_URL}/finops/overview?${params.toString()}`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").ExecutiveOverviewData>(res);
}

export async function getFinOpsCostExplorer(
  connectionId = "databricks-azure-dev"
): Promise<import("@/types").CostExplorerData> {
  const res = await apiFetch(`${API_BASE_URL}/finops/cost-explorer?connection_id=${encodeURIComponent(connectionId)}`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").CostExplorerData>(res);
}

export async function getFinOpsCostAllocation(
  connectionId = "databricks-azure-dev"
): Promise<import("@/types").CostAllocationData> {
  const res = await apiFetch(`${API_BASE_URL}/finops/cost-allocation?connection_id=${encodeURIComponent(connectionId)}`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").CostAllocationData>(res);
}

export async function getFinOpsComputeWarehouses(
  connectionId = "databricks-azure-dev"
): Promise<import("@/types").ComputeWarehousesData> {
  const res = await apiFetch(`${API_BASE_URL}/finops/compute-warehouses?connection_id=${encodeURIComponent(connectionId)}`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").ComputeWarehousesData>(res);
}

export async function getFinOpsAiEconomics(
  connectionId = "databricks-azure-dev"
): Promise<import("@/types").AiEconomicsData> {
  const res = await apiFetch(`${API_BASE_URL}/finops/ai-economics?connection_id=${encodeURIComponent(connectionId)}`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").AiEconomicsData>(res);
}

export async function getFinOpsDataStorage(
  connectionId = "databricks-azure-dev"
): Promise<import("@/types").DataStorageData> {
  const res = await apiFetch(`${API_BASE_URL}/finops/data-storage?connection_id=${encodeURIComponent(connectionId)}`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").DataStorageData>(res);
}

export async function getFinOpsNetworkCloud(
  connectionId = "databricks-azure-dev"
): Promise<import("@/types").NetworkCloudData> {
  const res = await apiFetch(`${API_BASE_URL}/finops/network-cloud?connection_id=${encodeURIComponent(connectionId)}`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").NetworkCloudData>(res);
}

export async function getFinOpsOptimizationAdvisor(
  connectionId = "databricks-azure-dev"
): Promise<import("@/types").OptimizationAdvisorData> {
  const res = await apiFetch(`${API_BASE_URL}/finops/optimization-advisor?connection_id=${encodeURIComponent(connectionId)}`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").OptimizationAdvisorData>(res);
}

export async function recordFinOpsRecommendationAction(
  decisionId: string,
  action: string,
  notes?: string
): Promise<import("@/types").FinOpsDecisionItem> {
  const res = await apiFetch(`${API_BASE_URL}/finops/optimization-advisor/${encodeURIComponent(decisionId)}/action`, {
    method: "POST",
    headers: await getHeaders(),
    body: JSON.stringify({ action, notes }),
  });
  return handleResponse<import("@/types").FinOpsDecisionItem>(res);
}

export async function getFinOpsForecastBudgets(
  connectionId = "databricks-azure-dev"
): Promise<import("@/types").ForecastBudgetsData> {
  const res = await apiFetch(`${API_BASE_URL}/finops/forecast-budgets?connection_id=${encodeURIComponent(connectionId)}`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").ForecastBudgetsData>(res);
}

export async function simulateFinOpsScenario(
  computeSavePct: number,
  tokenSavePct: number,
  growthPct: number
): Promise<import("@/types").ScenarioSimulationResult> {
  const res = await apiFetch(`${API_BASE_URL}/finops/forecast-budgets/simulate`, {
    method: "POST",
    headers: await getHeaders(),
    body: JSON.stringify({
      compute_save_pct: computeSavePct,
      token_save_pct: tokenSavePct,
      growth_pct: growthPct,
    }),
  });
  return handleResponse<import("@/types").ScenarioSimulationResult>(res);
}

export async function getFinOpsAnomalyDetection(
  connectionId = "databricks-azure-dev"
): Promise<import("@/types").AnomalyDetectionData> {
  const res = await apiFetch(`${API_BASE_URL}/finops/anomaly-detection?connection_id=${encodeURIComponent(connectionId)}`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").AnomalyDetectionData>(res);
}

export async function getFinOpsGovernancePolicies(
  connectionId = "databricks-azure-dev"
): Promise<import("@/types").GovernancePoliciesData> {
  const res = await apiFetch(`${API_BASE_URL}/finops/governance-policies?connection_id=${encodeURIComponent(connectionId)}`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").GovernancePoliciesData>(res);
}

export async function getFinOpsShowbackChargeback(
  connectionId = "databricks-azure-dev"
): Promise<import("@/types").ShowbackChargebackData> {
  const res = await apiFetch(`${API_BASE_URL}/finops/showback-chargeback?connection_id=${encodeURIComponent(connectionId)}`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").ShowbackChargebackData>(res);
}

export async function getFinOpsWorkloadEconomics(
  connectionId = "databricks-azure-dev"
): Promise<import("@/types").WorkloadEconomicsData> {
  const res = await apiFetch(`${API_BASE_URL}/finops/workload-economics?connection_id=${encodeURIComponent(connectionId)}`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").WorkloadEconomicsData>(res);
}

export async function getFinOpsReportsAudit(
  connectionId = "databricks-azure-dev"
): Promise<import("@/types").ReportsAuditData> {
  const res = await apiFetch(`${API_BASE_URL}/finops/reports-audit?connection_id=${encodeURIComponent(connectionId)}`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").ReportsAuditData>(res);
}

export async function getFinOpsSettingsIntegrations(
  connectionId = "databricks-azure-dev"
): Promise<import("@/types").SettingsIntegrationsData> {
  const res = await apiFetch(`${API_BASE_URL}/finops/settings-integrations?connection_id=${encodeURIComponent(connectionId)}`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").SettingsIntegrationsData>(res);
}

export async function approveAndRunDatabricksIngestion(
  request: import("@/types").ApproveAndRunIngestionRequest = {}
): Promise<import("@/types").ApproveAndRunIngestionResponse> {
  const res = await apiFetch(`${API_BASE_URL}/finops/ingestion/approve-and-run`, {
    method: "POST",
    headers: await getHeaders(),
    body: JSON.stringify(request),
  });
  return handleResponse<import("@/types").ApproveAndRunIngestionResponse>(res);
}

export async function connectServicePrincipal(
  request: ServicePrincipalConnectRequest
): Promise<ServicePrincipalConnectResponse> {
  const response = await apiFetch(`${API_BASE_URL}/auth/connect`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    const detail =
      errorData.error?.message ||
      errorData.detail || {
        error_code: "AUTH_FAILED",
        message: `Authentication failed with status ${response.status}`,
      };
    throw new ApiError(response.status, detail, detail.message);
  }

  const data: ServicePrincipalConnectResponse = await response.json();
  setSessionToken(data.session_token);
  return data;
}

export async function getSessionInfo(): Promise<SessionInfoResponse> {
  const res = await apiFetch(`${API_BASE_URL}/auth/session`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<SessionInfoResponse>(res);
}

export async function logoutSession(): Promise<LogoutResponse> {
  try {
    const res = await apiFetch(`${API_BASE_URL}/auth/logout`, {
      method: "POST",
      headers: await getHeaders(),
    });
    const data = await res.json().catch(() => ({
      status: "logged_out",
      message: "Application session terminated successfully.",
    }));
    return data;
  } finally {
    setSessionToken(null);
  }
}

// ----------------------------------------------------------------------------
// Dedicated GCP Service Account & Resource Discovery Endpoints
// ----------------------------------------------------------------------------

export async function testGcpConnection(
  payload: import("@/types").GcpTestConnectionRequest
): Promise<import("@/types").GcpTestConnectionResponse> {
  const res = await apiFetch(`${API_BASE_URL}/gcp/connections/test`, {
    method: "POST",
    headers: await getHeaders(),
    body: JSON.stringify(payload),
  });
  return handleResponse<import("@/types").GcpTestConnectionResponse>(res);
}

export async function createGcpConnection(
  payload: import("@/types").GcpCreateConnectionRequest
): Promise<import("@/types").GcpConnectionResponse> {
  const res = await apiFetch(`${API_BASE_URL}/gcp/connections`, {
    method: "POST",
    headers: await getHeaders(),
    body: JSON.stringify(payload),
  });
  return handleResponse<import("@/types").GcpConnectionResponse>(res);
}

export async function listGcpConnections(): Promise<import("@/types").GcpConnectionResponse[]> {
  const res = await apiFetch(`${API_BASE_URL}/gcp/connections`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").GcpConnectionResponse[]>(res);
}

export async function getGcpConnection(
  connectionId: string
): Promise<import("@/types").GcpConnectionResponse> {
  const res = await apiFetch(
    `${API_BASE_URL}/gcp/connections/${encodeURIComponent(connectionId)}`,
    {
      method: "GET",
      headers: await getHeaders(),
    }
  );
  return handleResponse<import("@/types").GcpConnectionResponse>(res);
}

export async function deleteGcpConnection(connectionId: string): Promise<void> {
  const res = await apiFetch(
    `${API_BASE_URL}/gcp/connections/${encodeURIComponent(connectionId)}`,
    {
      method: "DELETE",
      headers: await getHeaders(),
    }
  );
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new ApiError(res.status, errorData);
  }
}

export async function getGcpResources(
  connectionId: string
): Promise<import("@/types").GcpDiscoveryResponse> {
  const res = await apiFetch(
    `${API_BASE_URL}/gcp/resources?connection_id=${encodeURIComponent(connectionId)}`,
    {
      method: "GET",
      headers: await getHeaders(),
    }
  );
  return handleResponse<import("@/types").GcpDiscoveryResponse>(res);
}

export async function getGcpServicesStatus(
  connectionId: string
): Promise<import("@/types").GcpServiceStatus[]> {
  const res = await apiFetch(
    `${API_BASE_URL}/gcp/services/status?connection_id=${encodeURIComponent(connectionId)}`,
    {
      method: "GET",
      headers: await getHeaders(),
    }
  );
  return handleResponse<import("@/types").GcpServiceStatus[]>(res);
}

