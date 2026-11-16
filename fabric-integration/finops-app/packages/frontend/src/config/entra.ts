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

/**
 * Base URL of the FastAPI backend (e.g. https://<app>.azurewebsites.net/api/v1).
 * There is deliberately no fallback to the Fabric UDF or to localhost in production.
 */
export function getBackendBaseUrl(): string | null {
  const url = clean(import.meta.env.VITE_API_BASE_URL);
  if (url) return url.replace(/\/+$/, "");
  return import.meta.env.DEV ? "http://localhost:8000/api/v1" : null;
}
