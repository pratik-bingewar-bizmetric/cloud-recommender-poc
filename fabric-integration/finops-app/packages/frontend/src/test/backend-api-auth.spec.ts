import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { listConnections, setAuthTokenProvider, setStoredEntraToken } from "../lib/api";
import { createEntraTokenService } from "../services/entra-token.service";
import { entraTokenService } from "../services/entra-token.service";

const config = {
  clientId: "22222222-2222-2222-2222-222222222222",
  tenantId: "11111111-1111-1111-1111-111111111111",
  apiScope: "api://backend/access_as_user",
  redirectUri: "https://app.test/redirect.html",
  popupRelayUri: "/popup-relay.html",
};

function stubFetchOk() {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("FastAPI backend calls carry the backend-audience Entra token", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_API_BASE_URL", "http://localhost:8000/api/v1");
    vi.stubEnv("VITE_USE_FABRIC_UDF", "false");
    setStoredEntraToken(null);
    setAuthTokenProvider(null);
  });
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    setAuthTokenProvider(null);
  });

  it("prefers the signed-in user's backend token over the Rayfin session token", async () => {
    vi.spyOn(entraTokenService, "getAccessTokenSilent").mockResolvedValue("entra-backend-token");
    setAuthTokenProvider(async () => "rayfin-session-token");
    const fetchMock = stubFetchOk();

    await listConnections();

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/connections");
    expect(init.headers.Authorization).toBe("Bearer entra-backend-token");
  });

  it("keeps the existing token behaviour when no backend token is available", async () => {
    vi.spyOn(entraTokenService, "getAccessTokenSilent").mockResolvedValue(null);
    setAuthTokenProvider(async () => "rayfin-session-token");
    const fetchMock = stubFetchOk();

    await listConnections();

    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer rayfin-session-token");
  });
});

describe("silent backend token acquisition", () => {
  const pcaWith = (overrides: Record<string, unknown> = {}) => ({
    initialize: vi.fn().mockResolvedValue(undefined),
    getActiveAccount: vi.fn().mockReturnValue({ username: "u" }),
    getAllAccounts: vi.fn().mockReturnValue([]),
    acquireTokenSilent: vi.fn().mockResolvedValue({ accessToken: "silent-token" }),
    acquireTokenPopup: vi.fn(),
    loginPopup: vi.fn(),
    setActiveAccount: vi.fn(),
    clearCache: vi.fn(),
    ...overrides,
  });

  it("returns a token for the backend scope without any interaction", async () => {
    const pca = pcaWith();
    const service = createEntraTokenService(() => config, () => pca as never);
    expect(await service.getAccessTokenSilent()).toBe("silent-token");
    expect(pca.acquireTokenSilent.mock.calls[0][0].scopes).toEqual([config.apiScope]);
    expect(pca.acquireTokenPopup).not.toHaveBeenCalled();
  });

  it("returns null (never a popup) when not configured, signed out or refresh fails", async () => {
    expect(await createEntraTokenService(() => null).getAccessTokenSilent()).toBeNull();

    const noAccount = pcaWith({ getActiveAccount: vi.fn().mockReturnValue(null) });
    expect(await createEntraTokenService(() => config, () => noAccount as never).getAccessTokenSilent()).toBeNull();

    const failing = pcaWith({ acquireTokenSilent: vi.fn().mockRejectedValue(new Error("interaction_required")) });
    expect(await createEntraTokenService(() => config, () => failing as never).getAccessTokenSilent()).toBeNull();
    expect(failing.acquireTokenPopup).not.toHaveBeenCalled();
  });
});
