/**
 * Entra ID configuration for acquiring a BACKEND-audience access token.
 *
 * All values are public identifiers (GUIDs / URIs), never secrets. They are supplied at build time
 * through VITE_* variables; the client secret of the user's Azure service principal is never part
 * of any build variable.
 */

export interface EntraConfig {
  /** Application (client) ID of the SPA app registration (must be in ENTRA_ALLOWED_CLIENT_IDS). */
  clientId: string;
  /** Directory (tenant) ID. */
  tenantId: string;
  /** Delegated scope of the backend API, e.g. api://<backend-app-id>/access_as_user. */
  apiScope: string;
  /** Page that relays the popup response (must be registered as an SPA redirect URI). */
  redirectUri: string;
  /** Top-level popup relay page (required when the app runs inside the Fabric iframe). */
  popupRelayUri: string;
}

function clean(value: string | undefined): string {
  return (value ?? "").trim();
}

/**
 * Delegated Fabric / Power BI scope used to call Fabric User Data Functions (not the backend API).
 * This is the scope in Microsoft's own UDF invocation sample ("Tutorial: invoke user data functions
 * from a Python application"): https://analysis.windows.net/powerbi/api/user_impersonation. The app
 * registration must hold the delegated Power BI Service permission UserDataFunction.Execute.All
 * (or Item.Execute.All). Override with VITE_FABRIC_UDF_SCOPE only if Microsoft documents otherwise.
 */
export const DEFAULT_FABRIC_UDF_SCOPE = "https://analysis.windows.net/powerbi/api/user_impersonation";

export interface FabricEntraConfig {
  clientId: string;
  tenantId: string;
  /** Scope for the Fabric REST / UDF audience (`https://analysis.windows.net/powerbi/api`). */
  fabricUdfScope: string;
  redirectUri: string;
  popupRelayUri: string;
}

/**
 * Entra settings for acquiring the delegated FABRIC token. Independent of the backend API scope:
 * the app registration only needs the Power BI Service delegated permission
 * `UserDataFunction.Execute.All` (or `Item.Execute.All`). Null when client / tenant are missing.
 */
export function getFabricEntraConfig(origin: string = window.location.origin): FabricEntraConfig | null {
  const clientId = clean(import.meta.env.VITE_ENTRA_CLIENT_ID);
  // The Fabric tenant (already part of the deployment settings) is the natural authority.
  const tenantId = clean(import.meta.env.VITE_ENTRA_TENANT_ID) || clean(import.meta.env.VITE_FABRIC_TENANT_ID);
  if (!clientId || !tenantId) return null;
  return {
    clientId,
    tenantId,
    fabricUdfScope: clean(import.meta.env.VITE_FABRIC_UDF_SCOPE) || DEFAULT_FABRIC_UDF_SCOPE,
    redirectUri: `${origin}/redirect.html`,
    popupRelayUri: "/popup-relay.html",
  };
}

/** Non-secret summary of whether the Fabric UDF sign-in is ready to be tested. */
export interface FabricUdfAuthReadiness {
  ready: boolean;
  missing: string[];
  tenantId: string | null;
  scope: string;
  clientIdConfigured: boolean;
}

export function getFabricUdfAuthReadiness(): FabricUdfAuthReadiness {
  const config = getFabricEntraConfig();
  const missing = missingFabricEntraSettings();
  return {
    ready: config !== null,
    missing,
    tenantId: config?.tenantId ?? null,
    scope: config?.fabricUdfScope ?? DEFAULT_FABRIC_UDF_SCOPE,
    clientIdConfigured: !missing.includes("VITE_ENTRA_CLIENT_ID"),
  };
}

/** Returns the Entra configuration, or null when it is incomplete. */
export function getEntraConfig(origin: string = window.location.origin): EntraConfig | null {
  const clientId = clean(import.meta.env.VITE_ENTRA_CLIENT_ID);
  const tenantId = clean(import.meta.env.VITE_ENTRA_TENANT_ID);
  const apiScope = clean(import.meta.env.VITE_ENTRA_API_SCOPE);
  if (!clientId || !tenantId || !apiScope) return null;
  return {
    clientId,
    tenantId,
    apiScope,
    redirectUri: `${origin}/redirect.html`,
    popupRelayUri: "/popup-relay.html",
  };
}

/** Which Entra settings are missing, for an actionable message in the UI. */
export function missingEntraSettings(): string[] {
  const missing: string[] = [];
  if (!clean(import.meta.env.VITE_ENTRA_CLIENT_ID)) missing.push("VITE_ENTRA_CLIENT_ID");
  if (!clean(import.meta.env.VITE_ENTRA_TENANT_ID)) missing.push("VITE_ENTRA_TENANT_ID");
  if (!clean(import.meta.env.VITE_ENTRA_API_SCOPE)) missing.push("VITE_ENTRA_API_SCOPE");
  return missing;
}

/** Missing settings for the Fabric UDF token only (the backend API scope is not needed). */
export function missingFabricEntraSettings(): string[] {
  const missing: string[] = [];
  if (!clean(import.meta.env.VITE_ENTRA_CLIENT_ID)) missing.push("VITE_ENTRA_CLIENT_ID");
  if (!clean(import.meta.env.VITE_ENTRA_TENANT_ID) && !clean(import.meta.env.VITE_FABRIC_TENANT_ID)) {
    missing.push("VITE_ENTRA_TENANT_ID");
  }
  return missing;
}

/**
 * Base URL of the FastAPI backend (e.g. https://<app>.azurewebsites.net/api/v1).
 * There is deliberately no fallback to the Fabric UDF or to localhost in production.
 */
export function getBackendBaseUrl(): string | null {
  const url = clean(import.meta.env.VITE_API_BASE_URL);
  if (url) return url.replace(/\/+$/, "");
  return import.meta.env.DEV ? "http://localhost:8000/api/v1" : null;
}
