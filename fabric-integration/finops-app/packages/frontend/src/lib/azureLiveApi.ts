/**
 * Client for the live Azure connection API.
 *
 * - Every request carries a BACKEND-audience Entra access token (see entra-token.service.ts).
 * - The Azure client secret appears ONLY in the body of the connect request over HTTPS. It is
 *   never placed in a URL, header, log line or browser storage, and is not retained by this module.
 * - No fallback to the Fabric UDF, Rayfin session tokens or mock data.
 */

import { getBackendBaseUrl } from "@/config/entra";
import { entraTokenService } from "@/services/entra-token.service";
import type {
  AzureCredentials,
  ConnectResponse,
  DataDomain,
  MetricDefinition,
  MetricSeries,
  OverviewResponse,
  AzureResource,
  ResourceTypeCount,
  ValidateResponse,
  CostSummary,
} from "@/types/azureLive";

export class AzureLiveApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly category?: string;
  readonly retryAfterSeconds?: number;

  constructor(
    status: number,
    code: string,
    message: string,
    extras: { category?: string; retryAfterSeconds?: number } = {},
  ) {
    super(message);
    this.name = "AzureLiveApiError";
    this.status = status;
    this.code = code;
    this.category = extras.category;
    this.retryAfterSeconds = extras.retryAfterSeconds;
  }

  /** The backend no longer knows this connection (expired, restarted or never existed). */
  get isConnectionGone(): boolean {
    return this.status === 404 && this.code === "AZURE_CONNECTION_NOT_FOUND";
  }
}

export interface AzureLiveApiOptions {
  baseUrl?: string | null;
  getToken?: () => Promise<string>;
  fetchImpl?: typeof fetch;
}

interface ErrorEnvelope {
  error?: {
    code?: number;
    message?: unknown;
    type?: string;
    details?: unknown;
  };
}

function toApiError(status: number, body: ErrorEnvelope | null, retryAfter: string | null): AzureLiveApiError {
  const raw = body?.error?.message;
  let code = body?.error?.type ?? "http_error";
  let message = `Request failed (HTTP ${status}).`;
  let category: string | undefined;
  if (raw && typeof raw === "object") {
    const detail = raw as Record<string, unknown>;
    if (typeof detail.error_code === "string") code = detail.error_code;
    if (typeof detail.message === "string") message = detail.message;
    if (typeof detail.category === "string") category = detail.category;
  } else if (typeof raw === "string") {
    message = raw;
  }
  const retry = retryAfter ? Number.parseInt(retryAfter, 10) : NaN;
  return new AzureLiveApiError(status, code, message, {
    category,
    retryAfterSeconds: Number.isFinite(retry) ? retry : undefined,
  });
}

export function createAzureLiveApi(options: AzureLiveApiOptions = {}) {
  const fetchImpl = options.fetchImpl ?? ((...args: Parameters<typeof fetch>) => fetch(...args));
  const getToken = options.getToken ?? (() => entraTokenService.getAccessToken());

  async function call<T>(method: string, path: string, body?: unknown, query?: Record<string, string>): Promise<T> {
    const base = options.baseUrl === undefined ? getBackendBaseUrl() : options.baseUrl;
    if (!base) {
      throw new AzureLiveApiError(
        503,
        "API_ENDPOINT_NOT_CONFIGURED",
        "The backend API URL (VITE_API_BASE_URL) is not configured for this build.",
      );
    }
    const token = await getToken();
    const qs = query ? `?${new URLSearchParams(query).toString()}` : "";
    const response = await fetchImpl(`${base}/azure/connections${path}${qs}`, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/json",
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      // Never let the browser cache or persist Azure data or credentials.
      cache: "no-store",
      credentials: "omit",
    });
    if (response.status === 204) return undefined as T;
    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    if (!response.ok) {
      throw toApiError(response.status, payload as ErrorEnvelope | null, response.headers.get("Retry-After"));
    }
    return payload as T;
  }

  const sub = (connectionId: string, subscriptionId: string) =>
    `/${encodeURIComponent(connectionId)}/subscriptions/${encodeURIComponent(subscriptionId)}`;

  return {
    connect: (credentials: AzureCredentials) =>
      call<ConnectResponse>("POST", "", {
        tenant_id: credentials.tenantId.trim(),
        client_id: credentials.clientId.trim(),
        client_secret: credentials.clientSecret,
        ...(credentials.subscriptionId?.trim() ? { subscription_id: credentials.subscriptionId.trim() } : {}),
      }),
    validate: (connectionId: string) =>
      call<ValidateResponse>("POST", `/${encodeURIComponent(connectionId)}/validate`),
    disconnect: (connectionId: string) => call<void>("DELETE", `/${encodeURIComponent(connectionId)}`),
    subscriptions: (connectionId: string) =>
      call<ConnectResponse["subscriptions"]>("GET", `/${encodeURIComponent(connectionId)}/subscriptions`),
    overview: (connectionId: string, subscriptionId: string) =>
      call<OverviewResponse>("GET", `${sub(connectionId, subscriptionId)}/overview`),
    resources: (connectionId: string, subscriptionId: string, resourceGroup?: string) =>
      call<{ resources: DataDomain<AzureResource>; type_breakdown: ResourceTypeCount[] }>(
        "GET",
        `${sub(connectionId, subscriptionId)}/resources`,
        undefined,
        resourceGroup ? { resource_group: resourceGroup } : undefined,
      ),
    resourceDetail: (connectionId: string, subscriptionId: string, resourceId: string) =>
      call<DataDomain>("GET", `${sub(connectionId, subscriptionId)}/resource`, undefined, {
        resource_id: resourceId,
      }),
    metricDefinitions: (connectionId: string, subscriptionId: string, resourceId: string) =>
      call<DataDomain<MetricDefinition>>("GET", `${sub(connectionId, subscriptionId)}/metrics/definitions`, undefined, {
        resource_id: resourceId,
      }),
    metricValues: (connectionId: string, subscriptionId: string, resourceId: string, metricNames: string[]) =>
      call<{ metrics: DataDomain<MetricSeries> }>("GET", `${sub(connectionId, subscriptionId)}/metrics`, undefined, {
        resource_id: resourceId,
        metric_names: metricNames.join(","),
      }),
    cost: (connectionId: string, subscriptionId: string, period = "month_to_date") =>
      call<DataDomain<CostSummary>>("GET", `${sub(connectionId, subscriptionId)}/cost`, undefined, { period }),
  };
}

export type AzureLiveApi = ReturnType<typeof createAzureLiveApi>;

export const azureLiveApi: AzureLiveApi = createAzureLiveApi();
