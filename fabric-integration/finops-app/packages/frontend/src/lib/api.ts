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

/**
 * Configure an asynchronous or synchronous token provider for Entra ID Bearer token forwarding.
 */
export function setAuthTokenProvider(provider: TokenProvider | null): void {
  currentTokenProvider = provider;
}

/**
 * Resolve the current access token from the active provider or Rayfin localStorage session.
 */
export async function getAuthToken(): Promise<string | null> {
  if (currentTokenProvider) {
    try {
      const token = await currentTokenProvider();
      if (token) return token;
    } catch {
      // Fall through to storage lookup
    }
  }

  if (typeof window !== "undefined" && window.localStorage) {
    try {
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key && (key === "authSession" || key.endsWith("_authSession"))) {
          const raw = localStorage.getItem(key);
          if (raw) {
            const parsed = JSON.parse(raw);
            if (parsed.accessToken && typeof parsed.accessToken === "string") {
              return parsed.accessToken;
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
  const headers = await getHeaders();
  const url = `${API_BASE_URL}/inventory/providers/status`;
  const res = headers ? await fetch(url, { headers }) : await fetch(url);
  return handleResponse<ProviderConnectionStatus[]>(res);
}

export async function listAzureSubscriptions(): Promise<CloudScopeSummary[]> {
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
  const res = await fetch(`${API_BASE_URL}/connections`, {
    method: "GET",
    headers: await getHeaders(),
  });
  return handleResponse<import("@/types").CloudConnection[]>(res);
}

export async function validateConnection(
  payload: import("@/types").ValidateConnectionRequest
): Promise<import("@/types").ConnectionValidationResponse> {
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
  const res = await fetch(`${API_BASE_URL}/connections`, {
    method: "POST",
    headers: await getHeaders(),
    body: JSON.stringify(payload),
  });
  return handleResponse<import("@/types").CloudConnection>(res);
}

// ----------------------------------------------------------------------------
// Token Economics & AI Consumption Telemetry API
// ----------------------------------------------------------------------------

export async function getTokenEconomics(
  payload: MonitoringQueryRequest,
  signal?: AbortSignal
): Promise<import("@/types").TokenEconomicsSummary> {
  const res = await fetch(`${API_BASE_URL}/monitoring/token-economics`, {
    method: "POST",
    headers: await getHeaders(),
    body: JSON.stringify(payload),
    signal,
  });
  return handleResponse<import("@/types").TokenEconomicsSummary>(res);
}

