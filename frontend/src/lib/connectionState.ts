import type { DatabricksConnectionHealth } from "@/types";

/** The only workspace connection states the UI may display. */
export type WorkspaceConnectionState =
  | "CONNECTED"
  | "DISCONNECTED"
  | "AUTHENTICATION_REQUIRED"
  | "ACCESS_DENIED"
  | "ERROR"
  | "NOT_CONFIGURED";

export type ConnectionTone = "ok" | "warn" | "bad" | "neutral" | "checking";

export interface ConnectionView {
  /** CHECKING only exists before the first health response arrives. */
  state: WorkspaceConnectionState | "CHECKING";
  label: string;
  tone: ConnectionTone;
  /** Explanation suitable for a tooltip (never contains credentials). */
  reason: string | null;
  /** True when the last refresh failed or the inventory is older than expected. */
  stale: boolean;
  lastSuccessAt: string | null;
  lastAttemptAt: string | null;
  workspaceId: string | null;
  workspaceName: string | null;
  workspaceUrl: string | null;
  environment: string | null;
  authMethod: string | null;
  /** SQL warehouse availability is deliberately separate from workspace connectivity. */
  sqlWarehouse: { id: string | null; name: string | null; state: string | null; available: boolean; message: string } | null;
}

const LABELS: Record<WorkspaceConnectionState | "CHECKING", { label: string; tone: ConnectionTone }> = {
  CONNECTED: { label: "Connected", tone: "ok" },
  DISCONNECTED: { label: "Disconnected", tone: "neutral" },
  AUTHENTICATION_REQUIRED: { label: "Authentication required", tone: "bad" },
  ACCESS_DENIED: { label: "Access denied", tone: "warn" },
  ERROR: { label: "Error", tone: "bad" },
  NOT_CONFIGURED: { label: "Not configured", tone: "neutral" },
  CHECKING: { label: "Checking", tone: "checking" },
};

/** Map the legacy lowercase registry status when an older backend omits `connection_state`. */
const LEGACY: Record<string, WorkspaceConnectionState> = {
  connected: "CONNECTED",
  auth_failed: "AUTHENTICATION_REQUIRED",
  permission_denied: "ACCESS_DENIED",
  connection_error: "ERROR",
  ready_to_connect: "DISCONNECTED",
};

export interface DeriveInput {
  health: DatabricksConnectionHealth | null;
  /** True until the first health response (success or failure) arrived. */
  loading: boolean;
  /** Error of the most recent failed health request, if any. */
  requestError: string | null;
  /** True when the backend registry loaded but lists no Databricks workspace. */
  notConfigured?: boolean;
}

/**
 * Single derivation of the workspace connection state. Every surface (header, sidebar,
 * overview, FinOps modules) must render this value and never compute its own badge.
 * A failed refresh after a successful one keeps the last known state and flags it stale;
 * a stopped SQL warehouse never changes the state.
 */
export const deriveConnectionView = ({
  health,
  loading,
  requestError,
  notConfigured = false,
}: DeriveInput): ConnectionView => {
  const base = {
    stale: false,
    lastSuccessAt: null,
    lastAttemptAt: null,
    workspaceId: null,
    workspaceName: null,
    workspaceUrl: null,
    environment: null,
    authMethod: null,
    sqlWarehouse: null,
  };
  if (!health) {
    if (notConfigured && !requestError) {
      return { ...base, state: "NOT_CONFIGURED", ...LABELS.NOT_CONFIGURED, reason: "No Databricks workspace is configured." };
    }
    if (loading && !requestError) {
      return { ...base, state: "CHECKING", ...LABELS.CHECKING, reason: "Checking the Databricks workspace API…" };
    }
    return {
      ...base,
      state: "ERROR",
      ...LABELS.ERROR,
      reason: requestError || "The backend did not return a connection state.",
    };
  }
  const state: WorkspaceConnectionState =
    (health.connection_state as WorkspaceConnectionState | undefined) ??
    LEGACY[String(health.status)] ??
    "ERROR";
  const stale = Boolean(health.discovery_stale) || Boolean(requestError);
  const wh = health.sql_warehouse;
  return {
    state,
    ...LABELS[state],
    reason: requestError || health.last_error || null,
    stale,
    lastSuccessAt: health.last_discovery_at ?? health.last_connected_at ?? health.last_verified_at ?? null,
    lastAttemptAt: health.last_discovery_attempt_at ?? null,
    workspaceId: health.workspace_id,
    workspaceName: health.workspace_name ?? null,
    workspaceUrl: health.workspace_url ?? null,
    environment: health.environment ?? null,
    authMethod: health.auth_method ?? null,
    sqlWarehouse: wh
      ? {
          id: wh.warehouse_id ?? null,
          name: wh.warehouse_name ?? null,
          state: wh.state ?? null,
          available: wh.sql_available,
          message: wh.message,
        }
      : null,
  };
};

/** Environment label shown in the UI: always the selected workspace's environment. */
export const environmentLabel = (env: string | null | undefined): string => {
  if (!env) return "-";
  const e = env.toLowerCase();
  if (e === "development" || e === "dev") return "Development";
  if (e === "production" || e === "prod") return "Production";
  return env.charAt(0).toUpperCase() + env.slice(1);
};

/** Map a ConnectionView to the legacy indicator's status vocabulary. */
export const toIndicatorStatus = (v: ConnectionView): string => {
  switch (v.state) {
    case "CONNECTED":
      return "connected";
    case "CHECKING":
      return "loading";
    case "AUTHENTICATION_REQUIRED":
      return "auth_failed";
    case "ACCESS_DENIED":
      return "permission_denied";
    case "DISCONNECTED":
    case "NOT_CONFIGURED":
      return "ready_to_connect";
    default:
      return "connection_error";
  }
};

/**
 * Count to display for a discovered resource category. `null` (rendered "-") when the
 * inventory is unknown; a real 0 only when discovery succeeded and returned none.
 */
export const inventoryCount = (
  health: DatabricksConnectionHealth | null | undefined,
  resourceType: string
): number | null => {
  if (!health || !health.resource_counts_by_type) return null;
  if (!health.last_discovery_at && !health.last_verified_at && health.status !== "connected") return null;
  return health.resource_counts_by_type[resourceType] ?? 0;
};
