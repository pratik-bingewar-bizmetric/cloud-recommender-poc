/**
 * Centralized, Strongly-Typed Microsoft Fabric User Data Functions (UDF) Client.
 *
 * Direct RPC communication with Microsoft Fabric Python UDF backend:
 * POST https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/userDataFunctions/{udfId}/functions/{functionName}
 *
 * Strict Compliance:
 * 1. Real Data Only - Zero mock / synthetic fallbacks.
 * 2. Entra ID JWT Bearer authentication forwarding.
 * 3. Never logs or exposes credentials, tokens, or private keys.
 * 4. Request de-duplication, timeout (AbortController), and typed error handling.
 */

import { getAuthToken } from "@/lib/api";

// Known Fabric Workspace & UDF Item IDs from deployment metadata
export const DEFAULT_FABRIC_WORKSPACE_ID = "672a6995-4190-4000-befd-5cc6479c3f74";
export const DEFAULT_FABRIC_UDF_ID = "8c5bbc01-c941-4f0e-90d3-7053921c32f8";

export interface UdfResponseEnvelope<T> {
  status: "success" | "error";
  data?: T;
  error_code?: string;
  error_message?: string;
  timestamp?: string;
}

export class FabricUdfError extends Error {
  status: number;
  errorCode: string;
  detailMessage: string;

  constructor(status: number, errorCode: string, detailMessage: string) {
    super(`[Fabric UDF Error ${status}] ${errorCode}: ${detailMessage}`);
    this.name = "FabricUdfError";
    this.status = status;
    this.errorCode = errorCode;
    this.detailMessage = detailMessage;
  }
}

// In-flight request cache for de-duplication of concurrent identical read queries
const inFlightRequests = new Map<string, Promise<unknown>>();

export function resetUdfInFlightCache(): void {
  inFlightRequests.clear();
}

/**
 * Resolve the authoritative base URL for Microsoft Fabric User Data Functions.
 */
export function getFabricUdfBaseUrl(): string {
  // 1. Explicit environment override if provided
  const envUdfUrl = import.meta.env.VITE_FABRIC_UDF_BASE_URL;
  if (envUdfUrl && envUdfUrl.trim() !== "") {
    return envUdfUrl.replace(/\/+$/, "");
  }

  // 2. Production Fabric Apps Public REST endpoint
  const workspaceId =
    import.meta.env.VITE_FABRIC_WORKSPACE_ID || DEFAULT_FABRIC_WORKSPACE_ID;
  const udfId = import.meta.env.VITE_FABRIC_UDF_ID || DEFAULT_FABRIC_UDF_ID;

  return `https://api.fabric.microsoft.com/v1/workspaces/${workspaceId}/userDataFunctions/${udfId}`;
}

export interface UdfClientConfig {
  timeoutMs?: number;
  enableDeduplication?: boolean;
}

const DEFAULT_CONFIG: UdfClientConfig = {
  timeoutMs: 25000,
  enableDeduplication: true,
};

/**
 * Invoke a Microsoft Fabric User Data Function via POST RPC.
 */
export async function invokeUdfFunction<TResult, TArgs extends Record<string, unknown> = Record<string, unknown>>(
  functionName: string,
  args: TArgs = {} as TArgs,
  config: UdfClientConfig = DEFAULT_CONFIG
): Promise<TResult> {
  const timeoutMs = config.timeoutMs ?? DEFAULT_CONFIG.timeoutMs!;
  const dedupe = config.enableDeduplication ?? DEFAULT_CONFIG.enableDeduplication!;

  // De-duplication key (read operations only)
  const isReadOp = !functionName.startsWith("create_") && !functionName.startsWith("delete_") && functionName !== "record_token_usage";
  const dedupeKey = `${functionName}:${JSON.stringify(args)}`;

  if (dedupe && isReadOp && inFlightRequests.has(dedupeKey)) {
    return inFlightRequests.get(dedupeKey) as Promise<TResult>;
  }

  const executionPromise = (async () => {
    const baseUrl = getFabricUdfBaseUrl();
    const url = `${baseUrl}/functions/${functionName}/invoke`;
    const token = await getAuthToken();
    const correlationId = Math.random().toString(36).substring(2, 10);

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "application/json",
      "X-Correlation-Id": correlationId,
    };

    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    if (import.meta.env.DEV) {
      console.debug(
        `[FabricUDF:${correlationId}] Invoking '${functionName}' (hasToken=${!!token}, url=${url})`
      );
    }

    // Normalize arguments: convert snake_case keys to camelCase for Fabric Python runtime compatibility
    const normalizedArgs: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(args)) {
      if (value !== undefined) {
        const camelKey = key.replace(/_([a-z0-9])/g, (_, letter) => letter.toUpperCase());
        normalizedArgs[camelKey] = value;
      }
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await fetch(url, {
        method: "POST",
        headers,
        body: JSON.stringify(normalizedArgs),
        signal: controller.signal,
      });

      if (!response.ok) {
        let errCode = "HTTP_ERROR";
        let errMsg = `Fabric UDF returned HTTP ${response.status}: ${response.statusText}`;

        try {
          const errBody = await response.json();
          if (errBody.error_code) errCode = errBody.error_code;
          if (errBody.error_message) errMsg = errBody.error_message;
          else if (errBody.message) errMsg = errBody.message;
        } catch {
          // Response body was not JSON
        }

        if (response.status === 401) {
          errCode = "UNAUTHENTICATED";
          errMsg = "Authentication required. Please sign in via Microsoft Entra ID.";
          console.warn(
            `[FabricUDF:${correlationId}] HTTP 401 UNAUTHENTICATED: Fabric UDF rejected request. ` +
            `Token present: ${!!token}. Check Entra ID token audience and permissions.`
          );
        } else if (response.status === 403) {
          errCode = "FORBIDDEN";
          errMsg = "Access denied. Insufficient Entra ID application roles.";
        } else if (response.status === 429) {
          errCode = "RATE_LIMITED";
          errMsg = "Fabric UDF request throttled. Please retry in a few moments.";
        } else if (response.status === 503 || response.status === 502) {
          errCode = "SERVICE_UNAVAILABLE";
          errMsg = "Fabric User Data Function runtime is temporarily unavailable.";
        }

        throw new FabricUdfError(response.status, errCode, errMsg);
      }

      const rawBody = await response.json();
      let envelope: UdfResponseEnvelope<TResult>;
      if (
        rawBody &&
        typeof rawBody === "object" &&
        "output" in rawBody &&
        rawBody.output !== undefined &&
        rawBody.output !== null
      ) {
        envelope = rawBody.output as UdfResponseEnvelope<TResult>;
      } else {
        envelope = rawBody as UdfResponseEnvelope<TResult>;
      }

      if (rawBody && typeof rawBody === "object" && (rawBody as { status?: string }).status === "Failed") {
        const errorDetail = (rawBody as { errors?: Array<{ message?: string; errorCode?: string }> }).errors?.[0]?.message || "Fabric UDF execution failed";
        throw new FabricUdfError(500, "FABRIC_EXECUTION_FAILED", errorDetail);
      }

      if (envelope && typeof envelope === "object" && envelope.status === "error") {
        throw new FabricUdfError(
          400,
          envelope.error_code || "FUNCTION_ERROR",
          envelope.error_message || "Fabric UDF execution reported error."
        );
      }

      if (envelope.data === undefined) {
        // Some operations return top-level json directly
        return envelope as unknown as TResult;
      }

      return envelope.data;
    } catch (err: unknown) {
      if (err instanceof FabricUdfError) {
        throw err;
      }
      if (err instanceof Error && err.name === "AbortError") {
        throw new FabricUdfError(
          504,
          "TIMEOUT",
          `Fabric UDF request to '${functionName}' timed out after ${timeoutMs}ms.`
        );
      }
      throw new FabricUdfError(
        500,
        "CLIENT_NETWORK_ERROR",
        err instanceof Error ? err.message : "Unknown network error communicating with Fabric UDF."
      );
    } finally {
      clearTimeout(timer);
      if (dedupe && isReadOp) {
        inFlightRequests.delete(dedupeKey);
      }
    }
  })();

  if (dedupe && isReadOp) {
    inFlightRequests.set(dedupeKey, executionPromise);
  }

  return executionPromise;
}

// ============================================================================
// Strongly-Typed Implementations of All 10 Fabric UDF Operations
// ============================================================================

export interface DiscoveredCloudResource {
  resource_id: string;
  name: string;
  resource_type: string;
  resource_group?: string | null;
  location: string;
  sku_name?: string | null;
  tags: Record<string, string>;
  power_state?: string | null;
  monthly_cost_usd?: string | number | null;
}

export interface FinOpsWasteCandidate {
  resource_id: string;
  name: string;
  resource_type: string;
  waste_category: "unattached_disk" | "idle_compute" | "unassociated_ip" | "oversized_compute";
  evidence: string;
  current_sku?: string | null;
  recommended_sku?: string | null;
  monthly_cost_leakage_usd: number | string;
  projected_monthly_savings_usd: number | string;
}

export interface FinOpsWasteSummary {
  connection_id: string;
  scan_timestamp: string;
  total_monthly_waste_usd: number | string;
  total_annual_waste_usd: number | string;
  waste_count_by_category: Record<string, number>;
  items: FinOpsWasteCandidate[];
}

export interface MetricPoint {
  timestamp: string;
  average?: number | null;
  maximum?: number | null;
  minimum?: number | null;
}

export interface MetricSeries {
  metric_name: string;
  unit: string;
  points: MetricPoint[];
}

export interface ResourceMetricsResult {
  resource_id: string;
  time_grain: string;
  start_time: string;
  end_time: string;
  series: MetricSeries[];
}

export interface TokenTelemetrySummaryResult {
  connection_id: string;
  window_days: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  total_cost_usd: number | string;
  token_efficiency_ratio: number;
  models_breakdown: Array<{
    model_name: string;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    cost_usd: number;
    invocations: number;
  }>;
  daily_timeseries: Array<{
    timestamp: string;
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
    costUsd: number;
    requests: number;
  }>;
}

export interface PricingCalculationResult {
  arm_sku_name: string;
  region: string;
  hourly_rate_usd: number;
  monthly_cost_usd: number;
  annual_cost_usd: number;
  currency: string;
  source: string;
}

// 1. list_connections
export async function udfListConnections(providerFilter?: "azure" | "aws" | "gcp"): Promise<import("@/types").CloudConnection[]> {
  return invokeUdfFunction<import("@/types").CloudConnection[]>(
    "list_connections",
    providerFilter ? { provider_filter: providerFilter } : {}
  );
}

// 2. create_connection
export async function udfCreateConnection(params: {
  name: string;
  tenant_id: string;
  subscription_id: string;
  client_id: string;
  client_secret: string;
  provider?: "azure" | "aws" | "gcp";
}): Promise<import("@/types").CloudConnection> {
  return invokeUdfFunction<import("@/types").CloudConnection>("create_connection", {
    name: params.name,
    tenant_id: params.tenant_id,
    subscription_id: params.subscription_id,
    client_id: params.client_id,
    client_secret: params.client_secret,
    provider: params.provider || "azure",
  });
}

// 3. validate_connection
export async function udfValidateConnection(params: {
  connection_id?: string;
  tenant_id?: string;
  subscription_id?: string;
  client_id?: string;
  client_secret?: string;
  provider?: "azure" | "aws" | "gcp";
}): Promise<{ valid: boolean; auth_method: string; message: string }> {
  return invokeUdfFunction<{ valid: boolean; auth_method: string; message: string }>(
    "validate_connection",
    {
      connection_id: params.connection_id,
      tenant_id: params.tenant_id,
      subscription_id: params.subscription_id,
      client_id: params.client_id,
      client_secret: params.client_secret,
      provider: params.provider || "azure",
    }
  );
}

// 4. delete_connection
export async function udfDeleteConnection(connectionId: string): Promise<{ deleted: boolean; connection_id: string }> {
  return invokeUdfFunction<{ deleted: boolean; connection_id: string }>("delete_connection", {
    connection_id: connectionId,
  });
}

// 5. get_inventory
export async function udfGetInventory(params: {
  connection_id: string;
  resource_type_filter?: string | null;
}): Promise<DiscoveredCloudResource[]> {
  return invokeUdfFunction<DiscoveredCloudResource[]>("get_inventory", {
    connection_id: params.connection_id,
    resource_type_filter: params.resource_type_filter || undefined,
  });
}

// 6. get_cost_waste
export async function udfGetCostWaste(params: {
  connection_id: string;
  force_refresh?: boolean;
}): Promise<FinOpsWasteSummary> {
  return invokeUdfFunction<FinOpsWasteSummary>("get_cost_waste", {
    connection_id: params.connection_id,
    force_refresh: params.force_refresh ?? false,
  });
}

// 7. get_metrics
export async function udfGetMetrics(params: {
  connection_id: string;
  resource_id: string;
  metric_names?: string[];
  time_grain?: string;
  days?: number;
}): Promise<ResourceMetricsResult> {
  return invokeUdfFunction<ResourceMetricsResult>("get_metrics", {
    connection_id: params.connection_id,
    resource_id: params.resource_id,
    metric_names: params.metric_names || ["Percentage CPU"],
    time_grain: params.time_grain || "PT1H",
    days: params.days ?? 7,
  });
}

// 8. get_token_economics
export async function udfGetTokenEconomics(params: {
  connection_id: string;
  days?: number;
}): Promise<TokenTelemetrySummaryResult> {
  return invokeUdfFunction<TokenTelemetrySummaryResult>("get_token_economics", {
    connection_id: params.connection_id,
    days: params.days ?? 30,
  });
}

// 9. record_token_usage
export async function udfRecordTokenUsage(params: {
  connection_id: string;
  model_name: string;
  prompt_tokens: number;
  completion_tokens: number;
  deployment_name?: string;
  latency_ms?: number;
}): Promise<import("@/types").TokenUsageRecord> {
  return invokeUdfFunction<import("@/types").TokenUsageRecord>("record_token_usage", {
    connection_id: params.connection_id,
    model_name: params.model_name,
    prompt_tokens: params.prompt_tokens,
    completion_tokens: params.completion_tokens,
    deployment_name: params.deployment_name,
    latency_ms: params.latency_ms,
  });
}

// 10. calculate_pricing
export async function udfCalculatePricing(params: {
  arm_sku_name: string;
  region?: string;
  hours_per_month?: number;
}): Promise<PricingCalculationResult> {
  return invokeUdfFunction<PricingCalculationResult>("calculate_pricing", {
    arm_sku_name: params.arm_sku_name,
    region: params.region || "northcentralus",
    hours_per_month: params.hours_per_month || 730.0,
  });
}

