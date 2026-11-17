import { InteractionRequiredAuthError } from "@azure/msal-browser";
import { describe, expect, it, vi } from "vitest";

import { DEFAULT_FABRIC_UDF_SCOPE } from "../config/entra";
import { createEntraTokenService } from "../services/entra-token.service";

const fabric = {
  clientId: "client-1",
  tenantId: "tenant-1",
  fabricUdfScope: DEFAULT_FABRIC_UDF_SCOPE,
  redirectUri: "https://app.example/redirect.html",
  popupRelayUri: "/popup-relay.html",
};

const pcaWith = (overrides: Record<string, unknown> = {}) => ({
  initialize: vi.fn().mockResolvedValue(undefined),
  getActiveAccount: vi.fn().mockReturnValue({ username: "u" }),
  getAllAccounts: vi.fn().mockReturnValue([]),
  acquireTokenSilent: vi.fn().mockResolvedValue({ accessToken: "fabric-token" }),
  acquireTokenPopup: vi.fn().mockResolvedValue({ accessToken: "popup-token", account: { username: "u" } }),
  loginPopup: vi.fn(),
  setActiveAccount: vi.fn(),
  clearCache: vi.fn(),
  ...overrides,
});

// The backend API scope is deliberately NOT configured (configProvider -> null).
const build = (pca: ReturnType<typeof pcaWith>) =>
  createEntraTokenService(() => null, () => pca as never, () => fabric);

describe("Fabric-audience token acquisition", () => {
  it("requests the Power BI / Fabric scope, not the backend API scope", async () => {
    const pca = pcaWith();
    expect(await build(pca).getFabricAccessToken()).toBe("fabric-token");
    expect(pca.acquireTokenSilent.mock.calls[0][0].scopes).toEqual([
      "https://analysis.windows.net/powerbi/api/user_impersonation",
    ]);
    expect(pca.acquireTokenPopup).not.toHaveBeenCalled();
  });

  it("works without the backend API scope being configured", async () => {
    await expect(build(pcaWith()).getFabricAccessToken()).resolves.toBe("fabric-token");
  });

  it("forces a refresh only when asked", async () => {
    const pca = pcaWith();
    const service = build(pca);
    await service.getFabricAccessToken();
    await service.getFabricAccessToken({ forceRefresh: true });
    expect(pca.acquireTokenSilent.mock.calls[0][0].forceRefresh).toBe(false);
    expect(pca.acquireTokenSilent.mock.calls[1][0].forceRefresh).toBe(true);
  });

  it("falls back to an interactive popup only when silent acquisition needs interaction", async () => {
    const pca = pcaWith({
      acquireTokenSilent: vi.fn().mockRejectedValue(new InteractionRequiredAuthError("interaction_required", "interaction required")),
    });
    expect(await build(pca).getFabricAccessToken()).toBe("popup-token");
    expect(pca.acquireTokenPopup).toHaveBeenCalledTimes(1);
    expect(pca.acquireTokenPopup.mock.calls[0][0].scopes).toEqual([DEFAULT_FABRIC_UDF_SCOPE]);
  });

  it("does not swallow non-interaction errors into a popup", async () => {
    const pca = pcaWith({ acquireTokenSilent: vi.fn().mockRejectedValue(new Error("network down")) });
    await expect(build(pca).getFabricAccessToken()).rejects.toThrow("network down");
    expect(pca.acquireTokenPopup).not.toHaveBeenCalled();
  });

  it("initialises MSAL once even for concurrent calls", async () => {
    const pca = pcaWith();
    const factory = vi.fn(() => pca as never);
    const service = createEntraTokenService(() => null, factory, () => fabric);
    await Promise.all([service.getFabricAccessToken(), service.getFabricAccessToken()]);
    expect(factory).toHaveBeenCalledTimes(1);
    expect(pca.initialize).toHaveBeenCalledTimes(1);
  });

  it("requires client and tenant ids", async () => {
    const service = createEntraTokenService(() => null, () => pcaWith() as never, () => null);
    await expect(service.getFabricAccessToken()).rejects.toThrow(/not configured/i);
  });

  it("sign-out clears the MSAL cache and the active account", async () => {
    const pca = pcaWith();
    const service = build(pca);
    await service.getFabricAccessToken();
    await service.signOut();
    expect(pca.clearCache).toHaveBeenCalled();
    expect(pca.setActiveAccount).toHaveBeenCalledWith(null);
  });
});

describe("Fabric UDF sign-in readiness (no network, no secrets)", () => {
  it("defaults to the scope in Microsoft's UDF invocation sample", () => {
    expect(DEFAULT_FABRIC_UDF_SCOPE).toBe("https://analysis.windows.net/powerbi/api/user_impersonation");
  });

  it("reports the missing client id and nothing else when only the Fabric tenant is configured", async () => {
    const { vi: viLocal } = await import("vitest");
    viLocal.stubEnv("VITE_FABRIC_TENANT_ID", "tenant-1");
    viLocal.stubEnv("VITE_ENTRA_CLIENT_ID", "");
    viLocal.stubEnv("VITE_ENTRA_TENANT_ID", "");
    const { getFabricUdfAuthReadiness } = await import("../config/entra");
    const r = getFabricUdfAuthReadiness();
    expect(r.ready).toBe(false);
    expect(r.missing).toEqual(["VITE_ENTRA_CLIENT_ID"]);
    expect(r.clientIdConfigured).toBe(false);
    viLocal.stubEnv("VITE_ENTRA_CLIENT_ID", "00000000-0000-0000-0000-000000000001");
    const ready = getFabricUdfAuthReadiness();
    expect(ready.ready).toBe(true);
    expect(ready.tenantId).toBe("tenant-1");
    expect(ready.scope).toBe(DEFAULT_FABRIC_UDF_SCOPE);
    viLocal.unstubAllEnvs();
  });
});
