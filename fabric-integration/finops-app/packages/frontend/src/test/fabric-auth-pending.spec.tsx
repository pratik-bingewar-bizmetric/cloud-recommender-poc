import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import React from "react";

import {
  FABRIC_AUTH_PENDING_MESSAGE,
  FabricAuthPendingError,
  invokeUdfFunction,
  resetUdfInFlightCache,
  setFabricUdfTokenProvider,
  udfListConnections,
} from "../lib/fabric-udf-client";
import { isFabricUdfAuthPending } from "../lib/fabric-udf-status";
import { setAuthTokenProvider } from "../lib/api";
import * as api from "../lib/api";
import { ConfigurationView } from "../components/ConfigurationView";
import { ConnectCloudView } from "../components/ConnectCloudView";

const b64 = (o: unknown) => btoa(JSON.stringify(o)).replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_");
const fabricJwt = () =>
  `${b64({ alg: "none" })}.${b64({
    aud: "https://analysis.windows.net/powerbi/api",
    exp: Math.floor(Date.now() / 1000) + 3600,
  })}.sig`;

/** Production-like build: Fabric UDF path on, Fabric tenant known, Entra client ID NOT configured. */
function stubPendingBuild() {
  vi.stubEnv("VITE_USE_FABRIC_UDF", "true");
  vi.stubEnv("VITE_FABRIC_TENANT_ID", "fe82a67c-faa7-4d9a-bbfa-7d25b7047b41");
  vi.stubEnv("VITE_ENTRA_CLIENT_ID", "");
  vi.stubEnv("VITE_ENTRA_TENANT_ID", "");
}

beforeEach(() => {
  vi.restoreAllMocks();
  resetUdfInFlightCache();
  setFabricUdfTokenProvider(null); // the real default provider (MSAL / pending state)
  setAuthTokenProvider(null);
  localStorage.clear();
  sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
});

describe("Fabric UDF authentication pending (no Entra client ID)", () => {
  it("is detected only when the UDF path is used and no Fabric token source exists", () => {
    stubPendingBuild();
    expect(isFabricUdfAuthPending()).toBe(true);

    vi.stubEnv("VITE_ENTRA_CLIENT_ID", "00000000-0000-0000-0000-000000000001");
    expect(isFabricUdfAuthPending()).toBe(false); // ready to use the client ID once it exists

    vi.stubEnv("VITE_ENTRA_CLIENT_ID", "");
    vi.stubEnv("VITE_USE_FABRIC_UDF", "false");
    expect(isFabricUdfAuthPending()).toBe(false); // not on the UDF path at all
  });

  it("a valid explicitly stored Fabric-audience token also counts as configured", () => {
    stubPendingBuild();
    localStorage.setItem("fabric_entra_access_token", fabricJwt());
    expect(isFabricUdfAuthPending()).toBe(false);
  });

  it("UDF calls fail with an explicit pending error, send no request and never use the Rayfin token", async () => {
    stubPendingBuild();
    setAuthTokenProvider(async () => "rayfin-session-token-must-not-be-used");
    const fetchMock = vi.fn();
    globalThis.fetch = fetchMock;

    const error = await udfListConnections().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(FabricAuthPendingError);
    expect((error as FabricAuthPendingError).message).toBe(FABRIC_AUTH_PENDING_MESSAGE);
    expect((error as FabricAuthPendingError).errorCode).toBe("ENTRA_NOT_CONFIGURED");
    expect((error as FabricAuthPendingError).missing).toContain("VITE_ENTRA_CLIENT_ID");
    expect(fetchMock).not.toHaveBeenCalled(); // not an empty success, not a doomed request
    await expect(invokeUdfFunction("get_inventory", {})).rejects.toBeInstanceOf(FabricAuthPendingError);
  });

  it("ConnectCloudView shows the pending state, makes no connection call and does not claim 'no saved connections'", async () => {
    stubPendingBuild();
    const list = vi.spyOn(api, "listConnections");
    render(<ConnectCloudView onConnectionSelected={vi.fn()} />);

    const notices = await screen.findAllByTestId("fabric-auth-pending");
    expect(notices.length).toBeGreaterThan(0);
    expect(screen.getAllByText(FABRIC_AUTH_PENDING_MESSAGE).length).toBeGreaterThan(0);
    expect(screen.queryByText(/No saved connections yet/i)).toBeNull();
    // Connection-dependent actions are disabled while authentication is pending.
    for (const button of screen.getAllByRole("button", { name: /Connect (Azure|Google Cloud)|Connect to/i })) {
      expect(button).toBeDisabled();
    }
    expect(list).not.toHaveBeenCalled();
  });

  it("a configured build with a genuinely empty list shows 'No saved connections yet', not the pending notice", async () => {
    vi.stubEnv("VITE_USE_FABRIC_UDF", "false");
    vi.spyOn(api, "listConnections").mockResolvedValue([]);
    render(<ConnectCloudView onConnectionSelected={vi.fn()} />);
    expect((await screen.findAllByText(/No saved connections yet/i)).length).toBeGreaterThan(0);
    expect(screen.queryByTestId("fabric-auth-pending")).toBeNull();
  });

  it("ConfigurationView stays accessible, explains the pending state and does not invent connections", async () => {
    stubPendingBuild();
    const list = vi.spyOn(api, "listConnections");
    vi.spyOn(api, "getConfiguration").mockRejectedValue(new Error("no config"));
    vi.spyOn(api, "getConfigurationStatus").mockRejectedValue(new Error("no status"));
    vi.spyOn(api, "discoverScopes").mockRejectedValue(new Error("no discovery"));
    vi.spyOn(api, "checkIngestionReadiness").mockRejectedValue(new Error("no readiness"));
    vi.spyOn(api, "listIngestionRuns").mockResolvedValue([]);

    render(<ConfigurationView />);

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /Multi-Cloud Resource Configuration/i })).toBeInTheDocument()
    );
    expect(screen.getByTestId("fabric-auth-pending")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Connections unavailable \(authentication pending\)/i })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Default azure Scope/i })).toBeNull();
    expect(list).not.toHaveBeenCalled();
  });

  it("ConfigurationView shows a real load failure instead of silently showing an empty list", async () => {
    vi.stubEnv("VITE_USE_FABRIC_UDF", "false");
    vi.spyOn(api, "listConnections").mockRejectedValue(new Error("Backend unreachable"));
    vi.spyOn(api, "getConfiguration").mockRejectedValue(new Error("x"));
    vi.spyOn(api, "getConfigurationStatus").mockRejectedValue(new Error("x"));
    vi.spyOn(api, "discoverScopes").mockRejectedValue(new Error("x"));
    vi.spyOn(api, "checkIngestionReadiness").mockRejectedValue(new Error("x"));
    vi.spyOn(api, "listIngestionRuns").mockResolvedValue([]);
    render(<ConfigurationView />);
    expect(await screen.findByText("Backend unreachable")).toBeInTheDocument();
    expect(screen.queryByTestId("fabric-auth-pending")).toBeNull();
  });
});
