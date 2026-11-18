/**
 * Backend-audience Entra token acquisition (MSAL).
 *
 * The FastAPI backend validates an Entra ID access token whose audience is the backend API, whose
 * client (`azp`) is this SPA and whose scope is the API scope. A Rayfin/Fabric session token is a
 * different credential for a different service: it is NEVER read, forwarded or accepted here.
 *
 * Tokens are cached in memory only (MSAL `memoryStorage`): nothing is written to localStorage or
 * sessionStorage, and a page reload simply re-acquires a token silently or via popup.
 */

import {
  InteractionRequiredAuthError,
  PublicClientApplication,
  type AccountInfo,
  type Configuration,
} from "@azure/msal-browser";

import {
  getEntraConfig,
  getFabricEntraConfig,
  missingEntraSettings,
  missingFabricEntraSettings,
  type EntraConfig,
  type FabricEntraConfig,
} from "@/config/entra";

export class EntraNotConfiguredError extends Error {
  readonly missing: string[];
  constructor(missing: string[]) {
    super(`Entra sign-in is not configured (missing ${missing.join(", ")}).`);
    this.name = "EntraNotConfiguredError";
    this.missing = missing;
  }
}

export interface BackendTokenService {
  isConfigured(): boolean;
  /** Interactive sign-in (popup). Must be called from a user gesture. */
  signIn(): Promise<AccountInfo>;
  /** A fresh backend-audience access token (silent when possible, popup otherwise). */
  getAccessToken(): Promise<string>;
  /**
   * Backend-audience token WITHOUT any user interaction: null when Entra is not configured, nobody
   * is signed in to the backend API, or a silent refresh is not possible. Never opens a popup.
   */
  getAccessTokenSilent(): Promise<string | null>;
  getAccount(): AccountInfo | null;
  signOut(): Promise<void>;
  /**
   * Delegated Entra token for the FABRIC audience (Power BI service), used for Fabric User Data
   * Functions. Silent first (optionally forcing a refresh), interactive popup only when required.
   * It is a different token from the backend-audience one and never shared with it.
   */
  getFabricAccessToken(options?: { forceRefresh?: boolean }): Promise<string>;
}

export function buildMsalConfiguration(
  config: Pick<EntraConfig, "clientId" | "tenantId" | "redirectUri" | "popupRelayUri">
): Configuration {
  return {
    auth: {
      clientId: config.clientId,
      authority: `https://login.microsoftonline.com/${config.tenantId}`,
      redirectUri: config.redirectUri,
      popupRelayUri: config.popupRelayUri,
      postLogoutRedirectUri: config.redirectUri,
    },
    cache: {
      // In-memory only: no tokens in browser storage.
      cacheLocation: "memoryStorage",
    },
  };
}

export function createEntraTokenService(
  configProvider: () => EntraConfig | null = () => getEntraConfig(),
  clientFactory: (cfg: Configuration) => PublicClientApplication = (cfg) =>
    new PublicClientApplication(cfg),
  fabricConfigProvider: () => FabricEntraConfig | null = () => getFabricEntraConfig(),
): BackendTokenService {
  let client: PublicClientApplication | null = null;
  let initialized: Promise<PublicClientApplication> | null = null;

  const requireConfig = (): EntraConfig => {
    const config = configProvider();
    if (!config) throw new EntraNotConfiguredError(missingEntraSettings());
    return config;
  };

  // One MSAL instance serves both tokens (no duplicate initialisation). The Fabric token only
  // needs client + tenant, so it works even when the backend API scope is not configured.
  const getClient = (): Promise<PublicClientApplication> => {
    if (!initialized) {
      const config = configProvider() ?? fabricConfigProvider();
      if (!config) throw new EntraNotConfiguredError(missingEntraSettings());
      client = clientFactory(buildMsalConfiguration(config));
      initialized = client.initialize().then(() => client as PublicClientApplication);
    }
    return initialized;
  };

  const activeAccount = (pca: PublicClientApplication): AccountInfo | null =>
    pca.getActiveAccount() ?? pca.getAllAccounts()[0] ?? null;

  return {
    isConfigured: () => configProvider() !== null,

    async signIn() {
      const config = requireConfig();
      const pca = await getClient();
      const result = await pca.loginPopup({ scopes: [config.apiScope] });
      pca.setActiveAccount(result.account);
      return result.account;
    },

    async getAccessToken() {
      const config = requireConfig();
      const pca = await getClient();
      const account = activeAccount(pca);
      const request = { scopes: [config.apiScope] };
      try {
        if (!account) throw new InteractionRequiredAuthError("no_account", "No signed-in account");
        const result = await pca.acquireTokenSilent({ ...request, account });
        return result.accessToken;
      } catch (error) {
        if (!(error instanceof InteractionRequiredAuthError)) throw error;
        const result = await pca.acquireTokenPopup(request);
        pca.setActiveAccount(result.account);
        return result.accessToken;
      }
    },

    async getAccessTokenSilent() {
      const config = configProvider();
      if (!config) return null;
      try {
        const pca = await getClient();
        const account = activeAccount(pca);
        if (!account) return null;
        const result = await pca.acquireTokenSilent({ scopes: [config.apiScope], account });
        return result.accessToken;
      } catch {
        return null; // caller falls back to its existing behaviour; the backend answers 401
      }
    },

    async getFabricAccessToken(options = {}) {
      const fabric = fabricConfigProvider();
      if (!fabric) throw new EntraNotConfiguredError(missingFabricEntraSettings());
      const pca = await getClient();
      const account = activeAccount(pca);
      const request = { scopes: [fabric.fabricUdfScope] };
      try {
        if (!account) throw new InteractionRequiredAuthError("no_account", "No signed-in account");
        const result = await pca.acquireTokenSilent({
          ...request,
          account,
          forceRefresh: options.forceRefresh ?? false,
        });
        return result.accessToken;
      } catch (error) {
        if (!(error instanceof InteractionRequiredAuthError)) throw error;
        const result = await pca.acquireTokenPopup(request);
        pca.setActiveAccount(result.account);
        return result.accessToken;
      }
    },

    getAccount() {
      return client ? activeAccount(client) : null;
    },

    async signOut() {
      if (!client) return;
      const account = activeAccount(client);
      await client.clearCache();
      if (account) client.setActiveAccount(null);
    },
  };
}

/** Application-wide singleton. */
export const entraTokenService: BackendTokenService = createEntraTokenService();
