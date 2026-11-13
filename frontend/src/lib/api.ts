import { globalLoadingManager } from "./loadingManager";

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

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  (typeof window !== "undefined" ? "/api/v1" : "http://127.0.0.1:8000/api/v1");

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

async function appFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const finish = globalLoadingManager.startRequest();
  try {
    const res = await fetch(input, init);
    if (!res.ok) {
      globalLoadingManager.finishRequest(true, `HTTP ${res.status}`);
    } else {
      finish();
    }
    return res;
  } catch (err) {
    globalLoadingManager.finishRequest(true, err instanceof Error ? err.message : "Request failed");
    throw err;
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
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export async function checkBackendHealth(): Promise<{ status: string }> {
  const rootUrl = API_BASE_URL.replace(/\/api\/v1\/?$/, "");
  const res = await appFetch(`${rootUrl}/health`);
  return handleResponse<{ status: string }>(res);
}

export async function analyzeRequirements(
  idea: string,
  targetRegion: string = "eastus",
  customerPreset?: number
): Promise<RequirementsAnalysisResponse> {
  const res = await appFetch(`${API_BASE_URL}/analysis/requirements`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
  const res = await appFetch(`${API_BASE_URL}/architecture/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
  const res = await appFetch(`${API_BASE_URL}/pricing/simulate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
  const res = await appFetch(`${API_BASE_URL}/inventory/providers/status`);
  return handleResponse<ProviderConnectionStatus[]>(res);
}

export async function listAzureSubscriptions(): Promise<CloudScopeSummary[]> {
  const res = await appFetch(`${API_BASE_URL}/inventory/azure/subscriptions`);
  return handleResponse<CloudScopeSummary[]>(res);
}

export type AzureDiscoveryStatus =
  | "OK"
  | "EMPTY"
  | "UNAUTHENTICATED"
  | "FORBIDDEN"
  | "NOT_FOUND"
  | "ERROR";

export interface AzureDiscoveryMeta {
  subscription_id: string;
  subscription_state: string | null;
  status: AzureDiscoveryStatus;
  status_message: string;
  http_status: number | null;
  page_count: number;
  auth_method: string;
  retrieved_at: string | null;
  last_success_at: string | null;
  stale: boolean;
}

export interface AzureResourceGroupItem {
  id: string;
  name: string;
  subscription_id: string;
  location: string | null;
  provisioning_state: string | null;
  managed_by: string | null;
  tags: Record<string, string>;
}

export interface AzureResourceGroupsResponse extends AzureDiscoveryMeta {
  count: number | null;
  items: AzureResourceGroupItem[];
}

export interface AzureResourceItem {
  id: string;
  name: string;
  type: string;
  subscription_id: string;
  resource_group: string | null;
  location: string | null;
  kind: string | null;
  provisioning_state: string | null;
  tags: Record<string, string>;
}

export interface AzureResourcesResponse extends AzureDiscoveryMeta {
  resource_group: string | null;
  count: number | null;
  items: AzureResourceItem[];
}

/** Real ARM resource groups of a subscription (all pages). Never fabricated: failures carry a status. */
export async function listAzureResourceGroups(subscriptionId: string): Promise<AzureResourceGroupsResponse> {
  const res = await appFetch(
    `${API_BASE_URL}/inventory/azure/subscriptions/${encodeURIComponent(subscriptionId)}/resource-groups`
  );
  return handleResponse<AzureResourceGroupsResponse>(res);
}

/** Real ARM resource inventory of a subscription or one resource group (all pages). */
export async function listAzureResources(
  subscriptionId: string,
  resourceGroup?: string
): Promise<AzureResourcesResponse> {
  const qs = resourceGroup ? `?resource_group=${encodeURIComponent(resourceGroup)}` : "";
  const res = await appFetch(
    `${API_BASE_URL}/inventory/azure/subscriptions/${encodeURIComponent(subscriptionId)}/resources${qs}`
  );
  return handleResponse<AzureResourcesResponse>(res);
}

export async function analyzeAzureSubscription(payload: {
  scope_id?: string | null;
  resource_group_filter?: string | null;
  workload_assumptions?: WorkloadAssumptions;
  safety_buffer_percentage?: string;
  metric_window_days?: number;
  refresh_telemetry?: boolean;
}): Promise<SubscriptionOrProjectAnalysis> {
  const res = await appFetch(`${API_BASE_URL}/inventory/azure/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
  const res = await appFetch(`${API_BASE_URL}/inventory/gcp/projects`);
  return handleResponse<CloudScopeSummary[]>(res);
}

export async function analyzeGcpProject(payload: {
  scope_id?: string | null;
  workload_assumptions?: WorkloadAssumptions;
  safety_buffer_percentage?: string;
  metric_window_days?: number;
  refresh_telemetry?: boolean;
}): Promise<SubscriptionOrProjectAnalysis> {
  const res = await appFetch(`${API_BASE_URL}/inventory/gcp/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
  const res = await appFetch(`${API_BASE_URL}/inventory/compare`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
  const res = await appFetch(`${API_BASE_URL}/monitoring/overview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  return handleResponse<MonitoringOverviewResponse>(res);
}

export async function getResourceMonitoringDetail(
  payload: MonitoringQueryRequest
): Promise<ResourceDetailMonitoringResponse> {
  const res = await appFetch(`${API_BASE_URL}/monitoring/resource`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleResponse<ResourceDetailMonitoringResponse>(res);
}

export async function searchMonitoringLogs(
  payload: LogSearchRequest
): Promise<LogSearchResponse> {
  const res = await appFetch(`${API_BASE_URL}/monitoring/logs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleResponse<LogSearchResponse>(res);
}

export async function getMonitoringSources(): Promise<MonitoringSourcesResponse> {
  const res = await appFetch(`${API_BASE_URL}/monitoring/sources`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<MonitoringSourcesResponse>(res);
}

// ----------------------------------------------------------------------------
// Cloud Provider Connections Lifecycle API
// ----------------------------------------------------------------------------

export async function listConnections(): Promise<import("@/types").CloudConnection[]> {
  const res = await appFetch(`${API_BASE_URL}/connections`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").CloudConnection[]>(res);
}

export async function validateConnection(
  payload: import("@/types").ValidateConnectionRequest
): Promise<import("@/types").ConnectionValidationResponse> {
  const res = await appFetch(`${API_BASE_URL}/connections/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleResponse<import("@/types").ConnectionValidationResponse>(res);
}

export async function createConnection(
  payload: import("@/types").CreateConnectionRequest
): Promise<import("@/types").CloudConnection> {
  const res = await appFetch(`${API_BASE_URL}/connections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
  const res = await appFetch(`${API_BASE_URL}/monitoring/token-economics`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  return handleResponse<import("@/types").TokenEconomicsSummary>(res);
}

// ----------------------------------------------------------------------------
// Resource Configuration & Scope Selection APIs
// ----------------------------------------------------------------------------

export async function discoverScopes(
  connectionId: string,
  provider = "azure"
): Promise<import("@/types").ScopeDiscoveryResponse> {
  const res = await appFetch(
    `${API_BASE_URL}/configuration/scopes/discover?connection_id=${encodeURIComponent(connectionId)}&provider=${encodeURIComponent(provider)}`,
    {
      method: "GET",
      headers: { "Content-Type": "application/json" },
    }
  );
  return handleResponse<import("@/types").ScopeDiscoveryResponse>(res);
}

export async function getConfiguration(
  connectionId: string
): Promise<import("@/types").ResourceConfigurationResponse | null> {
  const res = await appFetch(
    `${API_BASE_URL}/configuration?connection_id=${encodeURIComponent(connectionId)}`,
    {
      method: "GET",
      headers: { "Content-Type": "application/json" },
    }
  );
  if (res.status === 404) return null;
  return handleResponse<import("@/types").ResourceConfigurationResponse>(res);
}

export async function saveConfiguration(
  data: import("@/types").ResourceConfigurationCreate
): Promise<import("@/types").ResourceConfigurationResponse> {
  const res = await appFetch(`${API_BASE_URL}/configuration`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handleResponse<import("@/types").ResourceConfigurationResponse>(res);
}

export async function getConfigurationStatus(
  connectionId: string
): Promise<import("@/types").ConfigurationStatusResponse> {
  const res = await appFetch(
    `${API_BASE_URL}/configuration/status?connection_id=${encodeURIComponent(connectionId)}`,
    {
      method: "GET",
      headers: { "Content-Type": "application/json" },
    }
  );
  return handleResponse<import("@/types").ConfigurationStatusResponse>(res);
}

export async function checkIngestionReadiness(
  connectionId: string
): Promise<import("@/types").IngestionReadinessResponse> {
  const res = await appFetch(
    `${API_BASE_URL}/ingestion/readiness?connection_id=${encodeURIComponent(connectionId)}`,
    {
      method: "GET",
      headers: { "Content-Type": "application/json" },
    }
  );
  return handleResponse<import("@/types").IngestionReadinessResponse>(res);
}

export async function triggerIngestionRun(
  connectionId: string,
  triggeredBy = "operator"
): Promise<import("@/types").IngestionRunResponse> {
  const res = await appFetch(`${API_BASE_URL}/ingestion/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ connection_id: connectionId, triggered_by: triggeredBy }),
  });
  return handleResponse<import("@/types").IngestionRunResponse>(res);
}

export async function listIngestionRuns(
  connectionId: string,
  limit = 10
): Promise<import("@/types").IngestionRunSummaryResponse[]> {
  const res = await appFetch(
    `${API_BASE_URL}/ingestion/runs?connection_id=${encodeURIComponent(connectionId)}&limit=${limit}`,
    {
      method: "GET",
      headers: { "Content-Type": "application/json" },
    }
  );
  return handleResponse<import("@/types").IngestionRunSummaryResponse[]>(res);
}

export async function retryIngestionRun(
  runId: string
): Promise<import("@/types").IngestionRunResponse> {
  const res = await appFetch(`${API_BASE_URL}/ingestion/runs/${encodeURIComponent(runId)}/retry`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").IngestionRunResponse>(res);
}

// ----------------------------------------------------------------------------
// Databricks Multi-Workspace APIs
// ----------------------------------------------------------------------------

export async function listDatabricksConnections(): Promise<import("@/types").DatabricksConnection[]> {
  const res = await appFetch(`${API_BASE_URL}/databricks/connections`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").DatabricksConnection[]>(res);
}

export async function getDatabricksConnection(
  connectionId: string
): Promise<import("@/types").DatabricksConnection> {
  const res = await appFetch(`${API_BASE_URL}/databricks/connections/${encodeURIComponent(connectionId)}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").DatabricksConnection>(res);
}

export async function testDatabricksConnection(
  connectionId: string
): Promise<import("@/types").DatabricksConnectionTestResponse> {
  const res = await appFetch(`${API_BASE_URL}/databricks/connections/${encodeURIComponent(connectionId)}/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").DatabricksConnectionTestResponse>(res);
}

export async function getWorkspaceDiscovery(
  connectionId: string
): Promise<import("@/types").DatabricksWorkspaceDiscovery> {
  const res = await appFetch(`${API_BASE_URL}/databricks/connections/${encodeURIComponent(connectionId)}/discovery`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").DatabricksWorkspaceDiscovery>(res);
}

export async function refreshWorkspaceDiscovery(
  connectionId: string
): Promise<import("@/types").DatabricksWorkspaceDiscovery> {
  const res = await appFetch(
    `${API_BASE_URL}/databricks/connections/${encodeURIComponent(connectionId)}/discovery/refresh`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    }
  );
  return handleResponse<import("@/types").DatabricksWorkspaceDiscovery>(res);
}

export async function getWorkspaceHealth(
  connectionId: string
): Promise<import("@/types").DatabricksConnectionHealth> {
  const res = await appFetch(`${API_BASE_URL}/databricks/connections/${encodeURIComponent(connectionId)}/health`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").DatabricksConnectionHealth>(res);
}

export async function getWorkspaceCategoryResources(
  connectionId: string,
  category: string,
  limit = 50,
  offset = 0,
  forceRefresh = false,
  jobId?: number,
  pageToken?: string
): Promise<import("@/types").DatabricksCategoryPageResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
    force_refresh: String(forceRefresh),
  });
  if (jobId) params.append("job_id", String(jobId));
  if (pageToken) params.append("page_token", pageToken);
  const res = await appFetch(
    `${API_BASE_URL}/databricks/connections/${encodeURIComponent(connectionId)}/categories/${encodeURIComponent(category)}?${params.toString()}`,
    {
      method: "GET",
      headers: { "Content-Type": "application/json" },
    }
  );
  return handleResponse<import("@/types").DatabricksCategoryPageResponse>(res);
}

export async function getWorkspaceUnityCatalog(
  connectionId: string,
  catalogName?: string,
  includePermissions = true,
  forceRefresh = false
): Promise<import("@/types").UnityCatalogMetadataResponse> {
  const params = new URLSearchParams({
    include_permissions: String(includePermissions),
    force_refresh: String(forceRefresh),
  });
  if (catalogName) params.append("catalog_name", catalogName);
  const res = await appFetch(
    `${API_BASE_URL}/databricks/connections/${encodeURIComponent(connectionId)}/unity-catalog?${params.toString()}`,
    {
      method: "GET",
      headers: { "Content-Type": "application/json" },
    }
  );
  return handleResponse<import("@/types").UnityCatalogMetadataResponse>(res);
}

export async function getWorkspaceSystemTables(
  connectionId: string,
  forceRefresh = false
): Promise<import("@/types").SystemTablesMetadataResponse> {
  const params = new URLSearchParams({ force_refresh: String(forceRefresh) });
  const res = await appFetch(
    `${API_BASE_URL}/databricks/connections/${encodeURIComponent(connectionId)}/system-tables?${params.toString()}`,
    {
      method: "GET",
      headers: { "Content-Type": "application/json" },
    }
  );
  return handleResponse<import("@/types").SystemTablesMetadataResponse>(res);
}

export async function getWorkspaceQueryHistory(
  connectionId: string,
  options?: {
    warehouseId?: string;
    status?: string;
    startTimeMs?: number;
    endTimeMs?: number;
    querySource?: string;
    maxResults?: number;
    pageToken?: string;
  }
): Promise<import("@/types").LiveQueryHistoryResponse> {
  const params = new URLSearchParams();
  if (options?.warehouseId) params.append("warehouse_id", options.warehouseId);
  if (options?.status && options.status !== "all") params.append("status", options.status);
  if (options?.startTimeMs !== undefined && options.startTimeMs !== null) {
    params.append("start_time_ms", String(options.startTimeMs));
  }
  if (options?.endTimeMs !== undefined && options.endTimeMs !== null) {
    params.append("end_time_ms", String(options.endTimeMs));
  }
  if (options?.querySource && options.querySource !== "all") {
    params.append("query_source", options.querySource);
  }
  if (options?.maxResults) params.append("max_results", String(options.maxResults));
  if (options?.pageToken) params.append("page_token", options.pageToken);
  const qs = params.toString();
  const res = await appFetch(
    `${API_BASE_URL}/databricks/connections/${encodeURIComponent(connectionId)}/query-history${qs ? `?${qs}` : ""}`,
    {
      method: "GET",
      headers: { "Content-Type": "application/json" },
    }
  );
  return handleResponse<import("@/types").LiveQueryHistoryResponse>(res);
}

// ----------------------------------------------------------------------------
// Milestone 3B/3D: FinOps Command Center 15-Module API Functions
// ----------------------------------------------------------------------------

export async function getFinOpsOverview(
  connectionId = "databricks-azure-dev",
  period = "month",
  environment?: string,
  workspaceId?: string,
  resourceId?: string,
  resourceType?: string
): Promise<import("@/types").ExecutiveOverviewData> {
  const params = new URLSearchParams({ connection_id: connectionId, period });
  if (environment) params.append("environment", environment);
  if (workspaceId) params.append("workspace_id", workspaceId);
  if (resourceId) params.append("resource_id", resourceId);
  if (resourceType) params.append("resource_type", resourceType);
  const res = await appFetch(`${API_BASE_URL}/finops/overview?${params.toString()}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").ExecutiveOverviewData>(res);
}

export async function getFinOpsCostExplorer(
  connectionId = "databricks-azure-dev",
  workspaceId?: string,
  resourceId?: string,
  resourceType?: string
): Promise<import("@/types").CostExplorerData> {
  const params = new URLSearchParams({ connection_id: connectionId });
  if (workspaceId) params.append("workspace_id", workspaceId);
  if (resourceId) params.append("resource_id", resourceId);
  if (resourceType) params.append("resource_type", resourceType);
  const res = await appFetch(`${API_BASE_URL}/finops/cost-explorer?${params.toString()}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").CostExplorerData>(res);
}

export async function getFinOpsQueryHistory(
  connectionId = "databricks-azure-dev",
  workspaceId?: string,
  warehouseId?: string,
  user?: string,
  status?: string,
  limit = 50,
  pageToken?: string | null,
  startTimeMs?: number | null,
  endTimeMs?: number | null
): Promise<import("@/types").QueryHistoryData> {
  const params = new URLSearchParams({ connection_id: connectionId, limit: String(limit) });
  if (pageToken) params.append("page_token", pageToken);
  if (startTimeMs != null) params.append("start_time_ms", String(startTimeMs));
  if (endTimeMs != null) params.append("end_time_ms", String(endTimeMs));
  if (workspaceId) params.append("workspace_id", workspaceId);
  if (warehouseId) params.append("warehouse_id", warehouseId);
  if (user) params.append("user", user);
  if (status) params.append("status", status);
  const res = await appFetch(`${API_BASE_URL}/finops/query-history?${params.toString()}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").QueryHistoryData>(res);
}

export async function getFinOpsSystemTables(
  connectionId = "databricks-azure-dev",
  workspaceId?: string
): Promise<import("@/types").SystemTablesExplorerData> {
  const params = new URLSearchParams({ connection_id: connectionId });
  if (workspaceId) params.append("workspace_id", workspaceId);
  const res = await appFetch(`${API_BASE_URL}/finops/system-tables?${params.toString()}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").SystemTablesExplorerData>(res);
}

export async function getFinOpsCostAllocation(
  connectionId = "databricks-azure-dev",
  workspaceId?: string,
  resourceId?: string,
  resourceType?: string
): Promise<import("@/types").CostAllocationData> {
  const params = new URLSearchParams({ connection_id: connectionId });
  if (workspaceId) params.append("workspace_id", workspaceId);
  if (resourceId) params.append("resource_id", resourceId);
  if (resourceType) params.append("resource_type", resourceType);
  const res = await appFetch(`${API_BASE_URL}/finops/cost-allocation?${params.toString()}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").CostAllocationData>(res);
}

export async function getFinOpsComputeWarehouses(
  connectionId = "databricks-azure-dev",
  workspaceId?: string,
  resourceId?: string,
  resourceType?: string
): Promise<import("@/types").ComputeWarehousesData> {
  const params = new URLSearchParams({ connection_id: connectionId });
  if (workspaceId) params.append("workspace_id", workspaceId);
  if (resourceId) params.append("resource_id", resourceId);
  if (resourceType) params.append("resource_type", resourceType);
  const res = await appFetch(`${API_BASE_URL}/finops/compute-warehouses?${params.toString()}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").ComputeWarehousesData>(res);
}

export async function getFinOpsAiEconomics(
  connectionId = "databricks-azure-dev",
  workspaceId?: string,
  resourceId?: string,
  resourceType?: string
): Promise<import("@/types").AiEconomicsData> {
  const params = new URLSearchParams({ connection_id: connectionId });
  if (workspaceId) params.append("workspace_id", workspaceId);
  if (resourceId) params.append("resource_id", resourceId);
  if (resourceType) params.append("resource_type", resourceType);
  const res = await appFetch(`${API_BASE_URL}/finops/ai-economics?${params.toString()}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").AiEconomicsData>(res);
}

export async function getFinOpsDataStorage(
  connectionId = "databricks-azure-dev",
  workspaceId?: string,
  resourceId?: string,
  resourceType?: string
): Promise<import("@/types").DataStorageData> {
  const params = new URLSearchParams({ connection_id: connectionId });
  if (workspaceId) params.append("workspace_id", workspaceId);
  if (resourceId) params.append("resource_id", resourceId);
  if (resourceType) params.append("resource_type", resourceType);
  const res = await appFetch(`${API_BASE_URL}/finops/data-storage?${params.toString()}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").DataStorageData>(res);
}

export async function getFinOpsNetworkCloud(
  connectionId = "databricks-azure-dev",
  workspaceId?: string,
  resourceId?: string,
  resourceType?: string
): Promise<import("@/types").NetworkCloudData> {
  const params = new URLSearchParams({ connection_id: connectionId });
  if (workspaceId) params.append("workspace_id", workspaceId);
  if (resourceId) params.append("resource_id", resourceId);
  if (resourceType) params.append("resource_type", resourceType);
  const res = await appFetch(`${API_BASE_URL}/finops/network-cloud?${params.toString()}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").NetworkCloudData>(res);
}

export async function getFinOpsOptimizationAdvisor(
  connectionId = "databricks-azure-dev",
  workspaceId?: string,
  resourceId?: string,
  resourceType?: string
): Promise<import("@/types").OptimizationAdvisorData> {
  const params = new URLSearchParams({ connection_id: connectionId });
  if (workspaceId) params.append("workspace_id", workspaceId);
  if (resourceId) params.append("resource_id", resourceId);
  if (resourceType) params.append("resource_type", resourceType);
  const res = await appFetch(`${API_BASE_URL}/finops/optimization-advisor?${params.toString()}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").OptimizationAdvisorData>(res);
}

export async function recordFinOpsRecommendationAction(
  decisionId: string,
  action: string,
  notes?: string
): Promise<import("@/types").FinOpsDecisionItem> {
  const res = await appFetch(`${API_BASE_URL}/finops/optimization-advisor/${encodeURIComponent(decisionId)}/action`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, notes }),
  });
  return handleResponse<import("@/types").FinOpsDecisionItem>(res);
}

export async function getFinOpsForecastBudgets(
  connectionId = "databricks-azure-dev",
  workspaceId?: string,
  resourceId?: string,
  resourceType?: string
): Promise<import("@/types").ForecastBudgetsData> {
  const params = new URLSearchParams({ connection_id: connectionId });
  if (workspaceId) params.append("workspace_id", workspaceId);
  if (resourceId) params.append("resource_id", resourceId);
  if (resourceType) params.append("resource_type", resourceType);
  const res = await appFetch(`${API_BASE_URL}/finops/forecast-budgets?${params.toString()}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").ForecastBudgetsData>(res);
}

export async function simulateFinOpsScenario(
  computeSavePct: number,
  tokenSavePct: number,
  growthPct: number
): Promise<import("@/types").ScenarioSimulationResult> {
  const res = await appFetch(`${API_BASE_URL}/finops/forecast-budgets/simulate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      compute_save_pct: computeSavePct,
      token_save_pct: tokenSavePct,
      growth_pct: growthPct,
    }),
  });
  return handleResponse<import("@/types").ScenarioSimulationResult>(res);
}

export async function getFinOpsAnomalyDetection(
  connectionId = "databricks-azure-dev",
  workspaceId?: string,
  resourceId?: string,
  resourceType?: string
): Promise<import("@/types").AnomalyDetectionData> {
  const params = new URLSearchParams({ connection_id: connectionId });
  if (workspaceId) params.append("workspace_id", workspaceId);
  if (resourceId) params.append("resource_id", resourceId);
  if (resourceType) params.append("resource_type", resourceType);
  const res = await appFetch(`${API_BASE_URL}/finops/anomaly-detection?${params.toString()}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").AnomalyDetectionData>(res);
}

export async function getFinOpsGovernancePolicies(
  connectionId = "databricks-azure-dev",
  workspaceId?: string,
  resourceId?: string,
  resourceType?: string
): Promise<import("@/types").GovernancePoliciesData> {
  const params = new URLSearchParams({ connection_id: connectionId });
  if (workspaceId) params.append("workspace_id", workspaceId);
  if (resourceId) params.append("resource_id", resourceId);
  if (resourceType) params.append("resource_type", resourceType);
  const res = await appFetch(`${API_BASE_URL}/finops/governance-policies?${params.toString()}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").GovernancePoliciesData>(res);
}

export async function getFinOpsShowbackChargeback(
  connectionId = "databricks-azure-dev",
  workspaceId?: string,
  resourceId?: string,
  resourceType?: string
): Promise<import("@/types").ShowbackChargebackData> {
  const params = new URLSearchParams({ connection_id: connectionId });
  if (workspaceId) params.append("workspace_id", workspaceId);
  if (resourceId) params.append("resource_id", resourceId);
  if (resourceType) params.append("resource_type", resourceType);
  const res = await appFetch(`${API_BASE_URL}/finops/showback-chargeback?${params.toString()}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").ShowbackChargebackData>(res);
}

export async function getFinOpsWorkloadEconomics(
  connectionId = "databricks-azure-dev",
  workspaceId?: string,
  resourceId?: string,
  resourceType?: string
): Promise<import("@/types").WorkloadEconomicsData> {
  const params = new URLSearchParams({ connection_id: connectionId });
  if (workspaceId) params.append("workspace_id", workspaceId);
  if (resourceId) params.append("resource_id", resourceId);
  if (resourceType) params.append("resource_type", resourceType);
  const res = await appFetch(`${API_BASE_URL}/finops/workload-economics?${params.toString()}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").WorkloadEconomicsData>(res);
}

export async function getFinOpsReportsAudit(
  connectionId = "databricks-azure-dev",
  workspaceId?: string,
  resourceId?: string,
  resourceType?: string
): Promise<import("@/types").ReportsAuditData> {
  const params = new URLSearchParams({ connection_id: connectionId });
  if (workspaceId) params.append("workspace_id", workspaceId);
  if (resourceId) params.append("resource_id", resourceId);
  if (resourceType) params.append("resource_type", resourceType);
  const res = await appFetch(`${API_BASE_URL}/finops/reports-audit?${params.toString()}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").ReportsAuditData>(res);
}

export async function getFinOpsSettingsIntegrations(
  connectionId = "databricks-azure-dev",
  workspaceId?: string,
  resourceId?: string,
  resourceType?: string
): Promise<import("@/types").SettingsIntegrationsData> {
  const params = new URLSearchParams({ connection_id: connectionId });
  if (workspaceId) params.append("workspace_id", workspaceId);
  if (resourceId) params.append("resource_id", resourceId);
  if (resourceType) params.append("resource_type", resourceType);
  const res = await appFetch(`${API_BASE_URL}/finops/settings-integrations?${params.toString()}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").SettingsIntegrationsData>(res);
}

export async function getFinOpsCanonicalKpi(
  metricId: string,
  connectionId = "databricks-azure-dev",
  workspaceId?: string,
  resourceId?: string,
  resourceType?: string
): Promise<import("@/types").CanonicalKpiResponse> {
  const params = new URLSearchParams({ connection_id: connectionId });
  if (workspaceId) params.append("workspace_id", workspaceId);
  if (resourceId) params.append("resource_id", resourceId);
  if (resourceType) params.append("resource_type", resourceType);
  const res = await appFetch(
    `${API_BASE_URL}/finops/kpis/${encodeURIComponent(metricId)}?${params.toString()}`,
    {
      method: "GET",
      headers: { "Content-Type": "application/json" },
    }
  );
  return handleResponse<import("@/types").CanonicalKpiResponse>(res);
}

// ============================================================================
// Milestone 3H: Live Databricks Financial Ingestion & Reconciliation Client
// ============================================================================

export async function getFinOpsIngestionStatus(
  connectionId = "databricks-azure-dev"
): Promise<import("@/types").BillingIngestionStatusResponse> {
  const params = new URLSearchParams({ connection_id: connectionId });
  const res = await appFetch(`${API_BASE_URL}/finops/ingestion/status?${params.toString()}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").BillingIngestionStatusResponse>(res);
}

export async function getFinOpsIngestionRuns(
  connectionId = "databricks-azure-dev",
  workspaceId?: string,
  limit = 20
): Promise<import("@/types").BillingIngestionRunResponse[]> {
  const params = new URLSearchParams({ connection_id: connectionId, limit: String(limit) });
  if (workspaceId) params.append("workspace_id", workspaceId);
  const res = await appFetch(`${API_BASE_URL}/finops/ingestion/runs?${params.toString()}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").BillingIngestionRunResponse[]>(res);
}

export async function validateFinOpsIngestion(
  workspaceId = "642006393507276",
  warehouseId = "05ed10a52697a344"
): Promise<import("@/types").IngestionValidateResponse> {
  const params = new URLSearchParams({ workspace_id: workspaceId, warehouse_id: warehouseId });
  const res = await appFetch(`${API_BASE_URL}/finops/ingestion/validate?${params.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").IngestionValidateResponse>(res);
}

export async function previewFinOpsIngestion(
  workspaceId = "642006393507276",
  limit = 10
): Promise<import("@/types").IngestionPreviewResponse> {
  const params = new URLSearchParams({ workspace_id: workspaceId, limit: String(limit) });
  const res = await appFetch(`${API_BASE_URL}/finops/ingestion/preview?${params.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").IngestionPreviewResponse>(res);
}

export async function runFinOpsIngestion(
  payload: import("@/types").IngestionRunCreateRequest
): Promise<import("@/types").BillingIngestionRunResponse> {
  const res = await appFetch(`${API_BASE_URL}/finops/ingestion/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleResponse<import("@/types").BillingIngestionRunResponse>(res);
}

export async function getFinOpsBillingSummary(
  connectionId = "databricks-azure-dev",
  workspaceId?: string,
  resourceId?: string
): Promise<import("@/types").BillingSummaryResponse> {
  const params = new URLSearchParams({ connection_id: connectionId });
  if (workspaceId) params.append("workspace_id", workspaceId);
  if (resourceId) params.append("resource_id", resourceId);
  const res = await appFetch(`${API_BASE_URL}/finops/billing/summary?${params.toString()}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").BillingSummaryResponse>(res);
}

export async function getFinOpsBillingUsage(
  connectionId = "databricks-azure-dev",
  workspaceId?: string,
  resourceId?: string,
  recordType?: string,
  limit = 50,
  offset = 0
): Promise<{ total: number; offset: number; limit: number; records: import("@/types").BillingUsageRecord[] }> {
  const params = new URLSearchParams({
    connection_id: connectionId,
    limit: String(limit),
    offset: String(offset),
  });
  if (workspaceId) params.append("workspace_id", workspaceId);
  if (resourceId) params.append("resource_id", resourceId);
  if (recordType) params.append("record_type", recordType);
  const res = await appFetch(`${API_BASE_URL}/finops/billing/usage?${params.toString()}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<{ total: number; offset: number; limit: number; records: import("@/types").BillingUsageRecord[] }>(res);
}

export async function getFinOpsBillingPricing(
  connectionId = "databricks-azure-dev",
  skuName?: string,
  limit = 50
): Promise<{ total: number; records: import("@/types").BillingPriceRecord[] }> {
  const params = new URLSearchParams({ connection_id: connectionId, limit: String(limit) });
  if (skuName) params.append("sku_name", skuName);
  const res = await appFetch(`${API_BASE_URL}/finops/billing/pricing?${params.toString()}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<{ total: number; records: import("@/types").BillingPriceRecord[] }>(res);
}

export async function getFinOpsBillingReconciliation(
  connectionId = "databricks-azure-dev",
  workspaceId?: string
): Promise<import("@/types").BillingReconciliationResponse> {
  const params = new URLSearchParams({ connection_id: connectionId });
  if (workspaceId) params.append("workspace_id", workspaceId);
  const res = await appFetch(`${API_BASE_URL}/finops/billing/reconciliation?${params.toString()}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return handleResponse<import("@/types").BillingReconciliationResponse>(res);
}

export async function getFinOpsAiAnalysis(
  moduleId: string,
  connectionId = "databricks-azure-dev",
  workspaceId = "642006393507276",
  resourceId?: string,
  resourceType?: string
): Promise<import("@/types").FinOpsAiAnalysis> {
  const params = new URLSearchParams({
    connection_id: connectionId,
    workspace_id: workspaceId,
  });
  if (resourceId) params.append("resource_id", resourceId);
  if (resourceType) params.append("resource_type", resourceType);
  const res = await appFetch(
    `${API_BASE_URL}/finops/ai-analysis/${encodeURIComponent(moduleId)}?${params.toString()}`,
    {
      method: "GET",
      headers: { "Content-Type": "application/json" },
    }
  );
  return handleResponse<import("@/types").FinOpsAiAnalysis>(res);
}

export async function updateFinOpsAnomalyStatus(
  anomalyId: string,
  status: string
): Promise<{ anomaly_id: string; status: string; updated_at: string }> {
  const res = await appFetch(
    `${API_BASE_URL}/finops/anomalies/${encodeURIComponent(anomalyId)}/status`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    }
  );
  return handleResponse<{ anomaly_id: string; status: string; updated_at: string }>(res);
}



