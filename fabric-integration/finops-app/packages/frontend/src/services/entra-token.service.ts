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

import { getEntraConfig, missingEntraSettings, type EntraConfig } from "@/config/entra";

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
  getAccount(): AccountInfo | null;
  signOut(): Promise<void>;
}

export function buildMsalConfiguration(config: EntraConfig): Configuration {
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
): BackendTokenService {
  let client: PublicClientApplication | null = null;
  let initialized: Promise<PublicClientApplication> | null = null;

  const requireConfig = (): EntraConfig => {
    const config = configProvider();
    if (!config) throw new EntraNotConfiguredError(missingEntraSettings());
    return config;
  };

  const getClient = (): Promise<PublicClientApplication> => {
    if (!initialized) {
      const config = requireConfig();
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
