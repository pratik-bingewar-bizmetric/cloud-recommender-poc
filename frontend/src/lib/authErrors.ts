/**
 * Human-readable explanations for API authentication / authorization failures.
 *
 * The backend answers 401 when the caller is not authenticated (no or invalid token, or local
 * development authentication is not enabled) and 403 when the caller is authenticated but not
 * allowed (missing scope, unapproved client or missing role). These must never look like a
 * generic failure or a silent no-op in the UI.
 */

const LOCAL_DEV_HINT =
  "For local development, set DEV_AUTH_ENABLED=true (and DEV_AUTH_ROLES=[\"FinOpsAdmin\"] for " +
  "restricted operations such as adding or validating connections) in the .env file the backend " +
  "loads, then restart the backend.";

/** Returns an explanatory message for 401/403, or null for any other status. */
export function describeAuthFailure(status: number, backendMessage?: string): string | null {
  const detail = backendMessage?.trim();
  if (status === 401) {
    const base = "Not authenticated (HTTP 401)";
    const hint = detail && /DEV_AUTH_ENABLED/.test(detail) ? "" : ` ${LOCAL_DEV_HINT}`;
    return `${base}${detail ? `: ${detail}` : "."}${hint}`;
  }
  if (status === 403) {
    return `Not authorized (HTTP 403)${detail ? `: ${detail}` : "."} Your account is signed in but lacks the permission or role this action requires.`;
  }
  return null;
}

export type ConnectionErrorKind =
  | "application_auth" // you are not signed in to the application (401)
  | "application_permission" // signed in, but the application denies the action (403)
  | "cloud_auth" // the cloud account's credentials were rejected
  | "cloud_permission" // credentials fine, the cloud account lacks permissions
  | "validation" // the form input is invalid (400/422)
  | "conflict" // duplicate / limit (409)
  | "service"; // storage/database/provider unavailable (5xx)

export interface ConnectionErrorView {
  kind: ConnectionErrorKind;
  title: string;
  message: string;
  /** Names of form fields the backend reported as missing/invalid (never values). */
  fields: string[];
}

interface ErrorLike {
  status?: number;
  message?: string;
  detail?: Record<string, unknown>;
}

const CLOUD_AUTH_CODES = new Set(["INVALID_AZURE_CREDENTIALS", "STORED_CREDENTIAL_REJECTED", "CREDENTIAL_UNREADABLE"]);
const CLOUD_PERMISSION_CODES = new Set([
  "SUBSCRIPTION_NOT_ACCESSIBLE",
  "WRITE_PERMISSIONS_DETECTED",
  "SUBSCRIPTION_TENANT_MISMATCH",
]);

/**
 * Turns a failed connection request into a precise explanation. Application sign-in problems
 * (401/403 from the FinOps API) are kept apart from problems with the CLOUD account's
 * credentials and permissions, so users know what to fix.
 */
export function describeConnectionError(error: unknown): ConnectionErrorView {
  const err = (error ?? {}) as ErrorLike;
  const status = err.status;
  const code = typeof err.detail?.error_code === "string" ? err.detail.error_code : "";
  const detailMessage = typeof err.detail?.message === "string" ? err.detail.message : err.message ?? "";
  const fields = Array.isArray(err.detail?.fields) ? (err.detail?.fields as unknown[]).map(String) : [];

  if (status === 401) {
    return {
      kind: "application_auth",
      title: "You are not signed in to the application (HTTP 401)",
      message: describeAuthFailure(401, detailMessage) ?? detailMessage,
      fields,
    };
  }
  if (status === 403) {
    return {
      kind: "application_permission",
      title: "The application denied this action (HTTP 403)",
      message: describeAuthFailure(403, detailMessage) ?? detailMessage,
      fields,
    };
  }
  if (CLOUD_AUTH_CODES.has(code)) {
    return { kind: "cloud_auth", title: "The cloud account credentials were rejected", message: detailMessage, fields };
  }
  if (CLOUD_PERMISSION_CODES.has(code)) {
    const role = typeof err.detail?.required_permission === "string" ? ` Required role: ${err.detail.required_permission}.` : "";
    return { kind: "cloud_permission", title: "The cloud account lacks the required permissions", message: detailMessage + role, fields };
  }
  if (status === 409) {
    return { kind: "conflict", title: "This connection conflicts with an existing one", message: detailMessage, fields };
  }
  if (status === 400 || status === 422) {
    return { kind: "validation", title: "Please check the connection details", message: detailMessage, fields };
  }
  return {
    kind: "service",
    title: status === 503 ? "A required service is unavailable (HTTP 503)" : "The connection could not be saved",
    message: detailMessage || "An unexpected error occurred. Nothing was saved.",
    fields,
  };
}
