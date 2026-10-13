import {
  ApiErrorDetail,
  ArchitectureComponent,
  ClarifyingAnswer,
  CostSimulationResponse,
  RecommendationReport,
  RequirementsAnalysisResponse,
  WorkloadAssumptions,
  WorkloadProfile,
} from "@/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

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
  const res = await fetch(`${API_BASE_URL}/architecture/generate`, {
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
  const res = await fetch(`${API_BASE_URL}/pricing/simulate`, {
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
  const res = await fetch(`${API_BASE_URL}/inventory/providers/status`);
  return handleResponse<ProviderConnectionStatus[]>(res);
}

export async function listAzureSubscriptions(): Promise<CloudScopeSummary[]> {
  const res = await fetch(`${API_BASE_URL}/inventory/azure/subscriptions`);
  return handleResponse<CloudScopeSummary[]>(res);
}

export async function analyzeAzureSubscription(payload: {
  scope_id?: string | null;
  resource_group_filter?: string | null;
  workload_assumptions?: WorkloadAssumptions;
  safety_buffer_percentage?: string;
}): Promise<SubscriptionOrProjectAnalysis> {
  const res = await fetch(`${API_BASE_URL}/inventory/azure/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      scope_id: payload.scope_id || null,
      resource_group_filter: payload.resource_group_filter || null,
      workload_assumptions: payload.workload_assumptions,
      safety_buffer_percentage: payload.safety_buffer_percentage || "0.00",
    }),
  });
  return handleResponse<SubscriptionOrProjectAnalysis>(res);
}

export async function listGcpProjects(): Promise<CloudScopeSummary[]> {
  const res = await fetch(`${API_BASE_URL}/inventory/gcp/projects`);
  return handleResponse<CloudScopeSummary[]>(res);
}

export async function analyzeGcpProject(payload: {
  scope_id?: string | null;
  workload_assumptions?: WorkloadAssumptions;
  safety_buffer_percentage?: string;
}): Promise<SubscriptionOrProjectAnalysis> {
  const res = await fetch(`${API_BASE_URL}/inventory/gcp/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      scope_id: payload.scope_id || null,
      workload_assumptions: payload.workload_assumptions,
      safety_buffer_percentage: payload.safety_buffer_percentage || "0.00",
    }),
  });
  return handleResponse<SubscriptionOrProjectAnalysis>(res);
}

export async function compareMultiCloud(
  payload: MultiCloudComparisonRequest
): Promise<MultiCloudComparisonResponse> {
  const res = await fetch(`${API_BASE_URL}/inventory/compare`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleResponse<MultiCloudComparisonResponse>(res);
}

