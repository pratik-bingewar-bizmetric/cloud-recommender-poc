/**
 * Centralized, Strongly-Typed Microsoft Fabric User Data Functions (UDF) Client.
 *
 * Direct RPC communication with Microsoft Fabric Python UDF backend:
 * POST https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/userDataFunctions/{udfId}/functions/{functionName}/invoke
 *
 * Strict Compliance:
 * 1. Real Data Only - Zero mock / synthetic fallbacks.
 * 2. Authentication: the request carries a DELEGATED Microsoft Entra access token whose audience is
 *    the Power BI / Fabric service (`https://analysis.windows.net/powerbi/api`) with the delegated
 *    `UserDataFunction.Execute.All` / `Item.Execute.All` permissions. It is acquired with MSAL.
 *    The Fabric App (Rayfin) SESSION token and the FastAPI backend-audience token are different
 *    credentials for different services: they are never sent to Fabric (that was the cause of the
 *    HTTP 401 UNAUTHENTICATED this client used to report).
 * 3. Never logs or exposes credentials, tokens, or private keys (only a few non-sensitive claims).
 * 4. Request de-duplication, timeout (AbortController), and typed error handling with diagnostics.
 */

import { getStoredEntraToken } from "@/lib/api";
import { classifyFabricToken, decodeJwtClaims, type TokenDiagnosis } from "@/lib/jwt-claims";
import { missingFabricEntraSettings } from "@/config/entra";
import { entraTokenService } from "@/services/entra-token.service";

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

/** User-facing text while Microsoft Entra authentication for Fabric UDFs is not configured yet. */
export const FABRIC_AUTH_PENDING_MESSAGE =
  "Microsoft Fabric connection authentication is being configured. Connection discovery will become available once Microsoft Entra authentication is enabled.";

/**
 * Entra sign-in for Fabric UDFs is not configured (no client ID). This is an explicit, typed state:
 * it is neither a successful call nor an empty connection list, and no request is sent to Fabric.
 * `message` is the plain user-facing text so any screen that prints `error.message` stays readable.
 */
export class FabricAuthPendingError extends Error {
  readonly status = 401;
  readonly errorCode = "ENTRA_NOT_CONFIGURED";
  readonly detailMessage: string;
  readonly missing: string[];

  constructor(missing: string[]) {
    super(FABRIC_AUTH_PENDING_MESSAGE);
    this.name = "FabricAuthPendingError";
    this.missing = missing;
    this.detailMessage = `Missing build setting(s): ${missing.join(", ")}.`;
  }
}

export function isFabricAuthPendingError(error: unknown): error is FabricAuthPendingError {
  return (
    error instanceof FabricAuthPendingError ||
    (error instanceof Error &&
      (error as { errorCode?: string }).errorCode === "ENTRA_NOT_CONFIGURED")
  );
}

/** Safe, token-free facts about a failed call (shown to users and engineers). */
export interface UdfDiagnostics {
  functionName: string;
  httpStatus: number | null;
  correlationId: string;
  /** Fabric's own request id header (requestid / x-ms-request-id), when returned. */
  fabricRequestId?: string | null;
  /** What the token we sent looked like (no token value). */
  token?: TokenDiagnosis | null;
  /** Sanitised, truncated response body. */
  responseBody?: string | null;
}

export class FabricUdfError extends Error {
  status: number;
  errorCode: string;
  detailMessage: string;
  diagnostics?: UdfDiagnostics;

  constructor(status: number, errorCode: string, detailMessage: string, diagnostics?: UdfDiagnostics) {
    super(`[Fabric UDF Error ${status}] ${errorCode}: ${detailMessage}`);
    this.name = "FabricUdfError";
    this.status = status;
    this.errorCode = errorCode;
    this.detailMessage = detailMessage;
    this.diagnostics = diagnostics;
  }
}

// In-flight request cache for de-duplication of concurrent identical read queries
const inFlightRequests = new Map<string, Promise<unknown>>();

export function resetUdfInFlightCache(): void {
  inFlightRequests.clear();
}

/** Supplies a delegated Entra token for the Fabric audience; `null` means "none available". */
export type FabricUdfTokenProvider = (options: { forceRefresh: boolean }) => Promise<string | null>;

function describeTokenError(error: unknown): FabricUdfError {
  const code = (error as { errorCode?: string } | null)?.errorCode ?? "";
  const name = (error as { name?: string } | null)?.name ?? "";
  const raw = error instanceof Error ? error.message : "Unknown token acquisition error.";
  // MSAL messages never contain the token; strip anything that looks like one anyway.
  const message = sanitize(raw, 240);
  if (
    name === "InteractionRequiredAuthError" ||
    code === "interaction_required" ||
    code === "login_required" ||
    code === "consent_required"
  ) {
    return new FabricUdfError(
      401,
      "INTERACTION_REQUIRED",
      "Sign-in or consent is required to call Fabric User Data Functions. Sign in with Microsoft Entra " +
        "(and approve the Power BI Service delegated permission UserDataFunction.Execute.All / " +
        `Item.Execute.All if prompted). Details: ${message}`
    );
  }
  if (code === "popup_window_error" || code === "empty_window_error" || code === "user_cancelled") {
    return new FabricUdfError(
      401,
      "SIGN_IN_POPUP_BLOCKED",
      `The Microsoft Entra sign-in window could not be completed (${code}). Allow pop-ups for this app and retry.`
    );
  }
  if (code === "invalid_scope" || /AADSTS70011|AADSTS650053|AADSTS65001/.test(raw)) {
    return new FabricUdfError(
      403,
      "CONSENT_OR_SCOPE_MISSING",
      "Microsoft Entra rejected the Fabric scope. The app registration needs the delegated Power BI Service " +
        "permission UserDataFunction.Execute.All (or Item.Execute.All) and user consent. Details: " +
        message
    );
  }
  return new FabricUdfError(401, "TOKEN_ACQUISITION_FAILED", `Could not obtain a Fabric access token: ${message}`);
}

const defaultTokenProvider: FabricUdfTokenProvider = async ({ forceRefresh }) => {
  if (missingFabricEntraSettings().length === 0) {
    try {
      return await entraTokenService.getFabricAccessToken({ forceRefresh });
    } catch (error) {
      throw describeTokenError(error);
    }
  }
  // Without MSAL configuration the only acceptable token is one that was explicitly stored AND
  // really targets the Fabric / Power BI audience. The Rayfin session token is never used.
  const stored = getStoredEntraToken();
  if (stored && classifyFabricToken(decodeJwtClaims(stored)).state === "ok") return stored;
  // Explicit pending state. The Fabric App (Rayfin) session token is deliberately NOT a fallback.
  throw new FabricAuthPendingError(missingFabricEntraSettings());
};

let tokenProvider: FabricUdfTokenProvider = defaultTokenProvider;

/** Override how the Fabric token is acquired (tests; `null` restores the MSAL-based default). */
export function setFabricUdfTokenProvider(provider: FabricUdfTokenProvider | null): void {
  tokenProvider = provider ?? defaultTokenProvider;
}

/** Remove anything that looks like a bearer/JWT and truncate. */
export function sanitize(text: string, max = 300): string {
  return text
    .replace(/Bearer\s+[A-Za-z0-9._~+/=-]+/gi, "Bearer [redacted]")
    .replace(/eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*/g, "[jwt-redacted]")
    .slice(0, max);
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

function statusToError(
  status: number,
  body: { error_code?: string; error_message?: string; message?: string; errorCode?: string } | null,
  diagnostics: UdfDiagnostics
): FabricUdfError {
  const serverMessage = body?.error_message ?? body?.message ?? null;
  const serverCode = body?.error_code ?? body?.errorCode ?? null;
  const fn = diagnostics.functionName;
  switch (status) {
    case 401: {
      const diag = diagnostics.token;
      let why = "Fabric rejected the access token.";
      if (!diag) why = "No access token was sent.";
      else if (diag.state === "expired") why = "The access token has expired.";
      else if (diag.state === "wrong_audience")
        why = `The token audience '${diag.audience ?? "unknown"}' is not accepted by the Fabric API (expected the Power BI service, https://analysis.windows.net/powerbi/api).`;
      else if (diag.state === "not_yet_valid") why = "The access token is not valid yet (clock skew).";
      else if (diag.state === "malformed") why = "The access token is not a valid JWT.";
      else
        why =
          "Fabric rejected a token that looks valid; check that the signed-in user's tenant matches the Fabric workspace tenant and that the app registration has the delegated permission UserDataFunction.Execute.All / Item.Execute.All.";
      return new FabricUdfError(
        401,
        "UNAUTHENTICATED",
        `Authentication required. Please sign in via Microsoft Entra ID. ${why}`,
        diagnostics
      );
    }
    case 403:
      return new FabricUdfError(
        403,
        "FORBIDDEN",
        `Access denied: the signed-in user is authenticated but lacks Execute permission on the User Data Function item, or the delegated permission was not granted/consented.${serverMessage ? ` Server: ${sanitize(serverMessage)}` : ""}`,
        diagnostics
      );
    case 404:
      return new FabricUdfError(
        404,
        "NOT_FOUND",
        `Workspace, User Data Function or function '${fn}' was not found. Check VITE_FABRIC_WORKSPACE_ID / VITE_FABRIC_UDF_ID and the function name.`,
        diagnostics
      );
    case 429:
      return new FabricUdfError(
        429,
        "RATE_LIMITED",
        "Fabric UDF request throttled. Please retry in a few moments.",
        diagnostics
      );
    default:
      if (status >= 500) {
        return new FabricUdfError(
          status,
          status === 502 || status === 503 ? "SERVICE_UNAVAILABLE" : "FABRIC_SERVER_ERROR",
          `Fabric or the function '${fn}' failed (HTTP ${status}).${serverMessage ? ` Server: ${sanitize(serverMessage)}` : ""}`,
          diagnostics
        );
      }
      return new FabricUdfError(
        status,
        serverCode ?? "HTTP_ERROR",
        serverMessage ? sanitize(serverMessage) : `Fabric UDF returned HTTP ${status}.`,
        diagnostics
      );
  }
}

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
    const correlationId = Math.random().toString(36).substring(2, 10);

    // Normalize arguments: convert snake_case keys to camelCase for Fabric Python runtime compatibility
    const normalizedArgs: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(args)) {
      if (value !== undefined) {
        const camelKey = key.replace(/_([a-z0-9])/g, (_, letter) => letter.toUpperCase());
        normalizedArgs[camelKey] = value;
      }
    }

    const send = async (forceRefresh: boolean): Promise<Response> => {
      // A missing token is an authentication failure: never send an unauthenticated request and
      // never turn it into an empty success.
      const token = await tokenProvider({ forceRefresh });
      if (!token) {
        throw new FabricUdfError(
          401,
          "UNAUTHENTICATED",
          "Authentication required. Please sign in via Microsoft Entra ID. No Fabric access token is available.",
          { functionName, httpStatus: null, correlationId, token: null }
        );
      }
      lastToken = classifyFabricToken(decodeJwtClaims(token));
      if (import.meta.env.DEV) {
        // Only non-sensitive facts are logged; never the token itself.
        console.debug(
          `[FabricUDF:${correlationId}] Invoking '${functionName}' (token=${lastToken.state}, aud=${lastToken.audience ?? "?"}, url=${url})`
        );
      }
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeoutMs);
      try {
        return await fetch(url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
            "X-Correlation-Id": correlationId,
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify(normalizedArgs),
          signal: controller.signal,
        });
      } finally {
        clearTimeout(timer);
      }
    };

    let lastToken: TokenDiagnosis | null = null;
    try {
      let response = await send(false);

      // Expired / rejected token: renew once (silent where MSAL can) and retry.
      if (response.status === 401) {
        response = await send(true);
      }

      if (!response.ok) {
        let body: { error_code?: string; error_message?: string; message?: string } | null = null;
        let rawText: string | null = null;
        try {
          if (typeof response.text === "function") {
            rawText = await response.text();
            body = rawText ? JSON.parse(rawText) : null;
          } else if (typeof response.json === "function") {
            body = await response.json();
            rawText = body ? JSON.stringify(body) : null;
          }
        } catch {
          // Response body was not JSON
        }
        throw statusToError(response.status, body, {
          functionName,
          httpStatus: response.status,
          correlationId,
          fabricRequestId:
            response.headers?.get?.("requestid") ?? response.headers?.get?.("x-ms-request-id") ?? null,
          token: lastToken,
          responseBody: rawText ? sanitize(rawText) : null,
        });
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
        throw new FabricUdfError(500, "FABRIC_EXECUTION_FAILED", sanitize(errorDetail), {
          functionName,
          httpStatus: 200,
          correlationId,
          token: lastToken,
        });
      }

      if (envelope && typeof envelope === "object" && envelope.status === "error") {
        // A business-level error from the function, distinct from an authentication failure.
        throw new FabricUdfError(
          400,
          envelope.error_code || "FUNCTION_ERROR",
          envelope.error_message || "Fabric UDF execution reported error.",
          { functionName, httpStatus: 200, correlationId, token: lastToken }
        );
      }

      if (envelope.data === undefined) {
        // Some operations return top-level json directly
        return envelope as unknown as TResult;
      }

      return envelope.data;
    } catch (err: unknown) {
      if (err instanceof FabricUdfError || isFabricAuthPendingError(err)) {
        throw err;
      }
      if (err instanceof Error && err.name === "AbortError") {
        throw new FabricUdfError(
          504,
          "TIMEOUT",
          `Fabric UDF request to '${functionName}' timed out after ${timeoutMs}ms.`,
          { functionName, httpStatus: null, correlationId, token: lastToken }
        );
      }
      throw new FabricUdfError(
        500,
        "CLIENT_NETWORK_ERROR",
        err instanceof Error ? sanitize(err.message) : "Unknown network error communicating with Fabric UDF.",
        { functionName, httpStatus: null, correlationId, token: lastToken }
      );
    } finally {
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

