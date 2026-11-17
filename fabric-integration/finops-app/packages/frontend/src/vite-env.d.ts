/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** FinOps Backend API base URL (e.g. http://localhost:8000/api/v1). */
  readonly VITE_API_BASE_URL?: string;
  /** Rayfin API base URL (e.g. http://localhost:5168). */
  readonly VITE_RAYFIN_API_URL?: string;
  /** Rayfin publishable key (pk-...). */
  readonly VITE_RAYFIN_PUBLISHABLE_KEY?: string;
  /** Fabric workspace ID — maps to FabricAuthOptions.workspaceId. */
  readonly VITE_FABRIC_WORKSPACE_ID?: string;
  /** Fabric/Rayfin item ID — maps to FabricAuthOptions.projectId. */
  readonly VITE_FABRIC_ITEM_ID?: string;
  /** Fabric portal base URL (e.g. https://app.fabric.microsoft.com/). */
  readonly VITE_FABRIC_PORTAL_URL?: string;
  /** SPA app registration (client) ID used to acquire a backend-audience Entra token. */
  readonly VITE_ENTRA_CLIENT_ID?: string;
  /** Entra directory (tenant) ID. */
  readonly VITE_ENTRA_TENANT_ID?: string;
  /** Backend API scope, e.g. api://<backend-app-id>/access_as_user. */
  readonly VITE_ENTRA_API_SCOPE?: string;
  /** Fabric/Power BI delegated scope for User Data Functions (default: .../powerbi/api/user_impersonation). */
  readonly VITE_FABRIC_UDF_SCOPE?: string;
}

/** Injected at build time by vite.config.ts (see src/lib/build-info.ts). */
declare const __BUILD_INFO__: { commit: string; builtAt: string; branch: string; dirty: boolean };

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
