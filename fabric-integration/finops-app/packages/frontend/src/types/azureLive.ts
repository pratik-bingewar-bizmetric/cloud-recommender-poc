/**
 * Types for the live Azure connection (user-supplied service principal).
 * Mirrors backend/src/cloud_recommender/schemas/azure_live.py.
 */

export type DataAccessState =
  | "accessible"
  | "permission_denied"
  | "unavailable"
  | "empty"
  | "error";

export interface AzureConnectionInfo {
  connection_id: string;
  tenant_id: string;
  client_id: string;
  auth_method: string;
  identity_source: string;
  connected_at: string;
  expires_at: string;
}

export interface DataSource {
  connection_id: string;
  tenant_id: string;
  client_id: string;
  subscription_id: string | null;
  api: string;
  auth_method: string;
  fetched_at: string;
}

export interface DataDomain<T = Record<string, unknown>> {
  domain: string;
  state: DataAccessState;
  items: T[] | null;
  count: number | null;
  message: string | null;
  required_permission: string | null;
  http_status: number | null;
  azure_error_code: string | null;
  retry_after_seconds: number | null;
  truncated: boolean;
  source: DataSource;
}

export interface AzureSubscription {
  subscription_id: string;
  display_name: string;
  state: string;
  tenant_id: string | null;
}

export interface AzureResourceGroup {
  name: string;
  id: string;
  location: string;
  provisioning_state: string | null;
  tags: Record<string, string>;
}

export interface AzureResource {
  id: string;
  name: string;
  type: string;
  location: string | null;
  kind: string | null;
  sku: string | null;
  resource_group: string | null;
  tags: Record<string, string>;
}

export interface ResourceTypeCount {
  resource_type: string;
  count: number;
}

export interface MetricDefinition {
  name: string;
  display_name: string | null;
  unit: string | null;
  primary_aggregation: string | null;
  supported_aggregations: string[];
  dimensions: string[];
  time_grains: string[];
}

export interface MetricSeries {
  name: string;
  display_name: string | null;
  unit: string | null;
  aggregation: string;
  points: { timestamp: string; value: number }[];
}

export interface CostSummary {
  period: string;
  period_start: string | null;
  period_end: string | null;
  currency: string | null;
  total: number | null;
  by_service: { service: string | null; cost: number; currency: string | null }[];
}

export interface ConnectResponse {
  connection: AzureConnectionInfo;
  subscriptions: DataDomain<AzureSubscription>;
  requested_subscription: DataDomain<AzureSubscription> | null;
}

export interface ValidateResponse {
  valid: boolean;
  connection: AzureConnectionInfo;
  subscriptions: DataDomain<AzureSubscription>;
}

export interface OverviewResponse {
  connection: AzureConnectionInfo;
  subscription_id: string;
  subscriptions: DataDomain<AzureSubscription>;
  resource_groups: DataDomain<AzureResourceGroup>;
  resources: DataDomain<AzureResource>;
  type_breakdown: ResourceTypeCount[];
  cost: DataDomain<CostSummary>;
}

/** Credentials typed by the user. Held in memory only; never persisted or put in a URL. */
export interface AzureCredentials {
  tenantId: string;
  clientId: string;
  clientSecret: string;
  subscriptionId?: string;
}
