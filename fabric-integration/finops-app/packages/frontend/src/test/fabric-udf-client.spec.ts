import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import {
  getFabricUdfBaseUrl,
  invokeUdfFunction,
  FabricUdfError,
  DEFAULT_FABRIC_WORKSPACE_ID,
  DEFAULT_FABRIC_UDF_ID,
  udfListConnections,
  udfCreateConnection,
  udfValidateConnection,
  udfDeleteConnection,
  udfGetInventory,
  udfGetCostWaste,
  udfGetMetrics,
  udfGetTokenEconomics,
  udfRecordTokenUsage,
  udfCalculatePricing,
  resetUdfInFlightCache,
  setFabricUdfTokenProvider,
  sanitize,
} from "../lib/fabric-udf-client";
import { setAuthTokenProvider } from "../lib/api";

function jwt(claims: Record<string, unknown>): string {
  const enc = (o: unknown) => btoa(JSON.stringify(o)).replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_");
  return `${enc({ alg: "none", typ: "JWT" })}.${enc(claims)}.sig-not-checked`;
}
const NOW = () => Math.floor(Date.now() / 1000);
const FABRIC_TOKEN = jwt({
  aud: "https://analysis.windows.net/powerbi/api",
  iss: "https://sts.windows.net/tenant-1/",
  tid: "tenant-1",
  scp: "UserDataFunction.Execute.All Item.Execute.All",
  exp: NOW() + 3600,
  nbf: NOW() - 60,
});

describe("Fabric UDF Client (Microsoft Fabric Python RPC Integration)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    resetUdfInFlightCache();
    setAuthTokenProvider(null);
    setFabricUdfTokenProvider(async () => FABRIC_TOKEN);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    resetUdfInFlightCache();
    setFabricUdfTokenProvider(null);
  });

  describe("UDF Base URL Resolution", () => {
    it("resolves default Fabric workspace and UDF item IDs in production", () => {
      const url = getFabricUdfBaseUrl();
      expect(url).toBe(
        `https://api.fabric.microsoft.com/v1/workspaces/${DEFAULT_FABRIC_WORKSPACE_ID}/userDataFunctions/${DEFAULT_FABRIC_UDF_ID}`
      );
    });

    it("respects custom workspace and UDF item ID overrides", () => {
      vi.stubEnv("VITE_FABRIC_WORKSPACE_ID", "custom-ws-123");
      vi.stubEnv("VITE_FABRIC_UDF_ID", "custom-udf-456");
      const url = getFabricUdfBaseUrl();
      expect(url).toBe(
        "https://api.fabric.microsoft.com/v1/workspaces/custom-ws-123/userDataFunctions/custom-udf-456"
      );
    });

    it("respects explicit VITE_FABRIC_UDF_BASE_URL override and strips trailing slashes", () => {
      vi.stubEnv("VITE_FABRIC_UDF_BASE_URL", "https://finops-udf.fabricapps.net/api/v1///");
      const url = getFabricUdfBaseUrl();
      expect(url).toBe("https://finops-udf.fabricapps.net/api/v1");
    });
  });

  describe("Authentication & Header Forwarding", () => {
    it("attaches the delegated Fabric-audience Entra token as the Bearer token", async () => {

      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          status: "success",
          data: [{ id: "conn-1", name: "Production Azure" }],
        }),
      });
      globalThis.fetch = mockFetch;

      const result = await udfListConnections();
      expect(result).toHaveLength(1);

      expect(mockFetch).toHaveBeenCalledTimes(1);
      const [, requestInit] = mockFetch.mock.calls[0];
      expect(requestInit.headers["Authorization"]).toBe(`Bearer ${FABRIC_TOKEN}`);
      expect(requestInit.headers["Content-Type"]).toBe("application/json");
    });

    it("never sends an unauthenticated request: no token is a 401, not an empty success", async () => {
      setFabricUdfTokenProvider(async () => null);
      const mockFetch = vi.fn();
      globalThis.fetch = mockFetch;

      await expect(udfListConnections()).rejects.toMatchObject({ status: 401, errorCode: "UNAUTHENTICATED" });
      expect(mockFetch).not.toHaveBeenCalled();
    });

    it("never forwards the Fabric App (Rayfin) session token to Fabric", async () => {
      // This is the regression behind the HTTP 401: the Rayfin session token was sent to Fabric.
      setAuthTokenProvider(async () => "rayfin-session-token-must-not-be-used");
      localStorage.setItem("authSession", JSON.stringify({ accessToken: "rayfin-local-session-token" }));
      const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: "success", data: [] }) });
      globalThis.fetch = mockFetch;
      await udfListConnections();
      const auth = mockFetch.mock.calls[0][1].headers["Authorization"] as string;
      expect(auth).toBe(`Bearer ${FABRIC_TOKEN}`);
      expect(auth).not.toContain("rayfin");
      localStorage.removeItem("authSession");
    });

    it("surfaces token acquisition failures instead of calling Fabric", async () => {
      const failure = Object.assign(new Error("interaction needed"), {
        name: "InteractionRequiredAuthError",
        errorCode: "interaction_required",
      });
      setFabricUdfTokenProvider(async () => {
        throw failure;
      });
      const mockFetch = vi.fn();
      globalThis.fetch = mockFetch;
      await expect(udfListConnections()).rejects.toBeDefined();
      expect(mockFetch).not.toHaveBeenCalled();
    });

    it("on HTTP 401 renews the token once (forceRefresh) and retries", async () => {
      const calls: boolean[] = [];
      setFabricUdfTokenProvider(async ({ forceRefresh }) => {
        calls.push(forceRefresh);
        return FABRIC_TOKEN;
      });
      const mockFetch = vi
        .fn()
        .mockResolvedValueOnce({ ok: false, status: 401, json: async () => ({}) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ status: "success", data: [{ id: "c1" }] }) });
      globalThis.fetch = mockFetch;
      const result = await udfListConnections();
      expect(result).toHaveLength(1);
      expect(calls).toEqual([false, true]);
      expect(mockFetch).toHaveBeenCalledTimes(2);
    });

    it("a persistent 401 is reported with token diagnostics (no token value) and a correlation id", async () => {
      const wrongAud = jwt({ aud: "api://backend-app", tid: "t", scp: "access_as_user", exp: NOW() + 3600 });
      setFabricUdfTokenProvider(async () => wrongAud);
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({}),
        headers: new Headers({ requestid: "fabric-req-123" }),
      });
      try {
        await udfListConnections();
        throw new Error("should have thrown");
      } catch (err) {
        const e = err as FabricUdfError;
        expect(e.status).toBe(401);
        expect(e.detailMessage).toContain("api://backend-app");
        expect(e.detailMessage).toContain("not accepted");
        expect(e.diagnostics?.functionName).toBe("list_connections");
        expect(e.diagnostics?.correlationId).toBeTruthy();
        expect(e.diagnostics?.fabricRequestId).toBe("fabric-req-123");
        expect(e.diagnostics?.token?.state).toBe("wrong_audience");
        expect(JSON.stringify(e.diagnostics)).not.toContain(wrongAud);
        expect(e.message).not.toContain(wrongAud);
      }
    });

    it("maps 404 to a not-found error naming the identifiers to check", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({ ok: false, status: 404, json: async () => ({}) });
      await expect(udfListConnections()).rejects.toMatchObject({ status: 404, errorCode: "NOT_FOUND" });
    });

    it("maps 5xx to a server error and sanitises the response body", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        text: async () => JSON.stringify({ message: "boom Bearer abc.def.ghi" }),
        headers: new Headers(),
      });
      try {
        await udfListConnections();
        throw new Error("should have thrown");
      } catch (err) {
        const e = err as FabricUdfError;
        expect(e.errorCode).toBe("FABRIC_SERVER_ERROR");
        expect(e.detailMessage).not.toContain("abc.def.ghi");
        expect(e.diagnostics?.responseBody).not.toContain("abc.def.ghi");
      }
    });

    it("keeps business errors from the function distinct from authentication failures", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: "error", error_code: "BAD_INPUT", error_message: "nope" }),
      });
      await expect(udfListConnections()).rejects.toMatchObject({ status: 400, errorCode: "BAD_INPUT" });
    });

    it("sanitize() strips bearer tokens and JWTs", () => {
      expect(sanitize("x Bearer abc.def.ghi y")).toBe("x Bearer [redacted] y");
      expect(sanitize(`tok ${FABRIC_TOKEN}`)).toContain("[jwt-redacted]");
    });
  });

  describe("Error Classification and Safe Zero-Leakage Handling", () => {
    it("throws FabricUdfError with code UNAUTHENTICATED on HTTP 401", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        statusText: "Unauthorized",
        json: async () => ({ error_code: "UNAUTHENTICATED", error_message: "Token expired" }),
      });

      await expect(udfListConnections()).rejects.toThrow(FabricUdfError);
      try {
        await udfListConnections();
      } catch (err) {
        const udfErr = err as FabricUdfError;
        expect(udfErr.status).toBe(401);
        expect(udfErr.errorCode).toBe("UNAUTHENTICATED");
        expect(udfErr.detailMessage).toContain("Microsoft Entra ID");
      }
    });

    it("throws FabricUdfError with code FORBIDDEN on HTTP 403", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
        statusText: "Forbidden",
        json: async () => ({ error_code: "FORBIDDEN", error_message: "Insufficient permissions" }),
      });

      try {
        await udfListConnections();
      } catch (err) {
        const udfErr = err as FabricUdfError;
        expect(udfErr.status).toBe(403);
        expect(udfErr.errorCode).toBe("FORBIDDEN");
        expect(udfErr.detailMessage).toContain("lacks Execute permission");
      }
    });

    it("throws FabricUdfError with code RATE_LIMITED on HTTP 429", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 429,
        statusText: "Too Many Requests",
        json: async () => ({}),
      });

      try {
        await udfListConnections();
      } catch (err) {
        const udfErr = err as FabricUdfError;
        expect(udfErr.status).toBe(429);
        expect(udfErr.errorCode).toBe("RATE_LIMITED");
      }
    });

    it("throws FabricUdfError with code SERVICE_UNAVAILABLE on HTTP 503", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        statusText: "Service Unavailable",
        json: async () => ({}),
      });

      try {
        await udfListConnections();
      } catch (err) {
        const udfErr = err as FabricUdfError;
        expect(udfErr.status).toBe(503);
        expect(udfErr.errorCode).toBe("SERVICE_UNAVAILABLE");
      }
    });

    it("handles UdfResponseEnvelope with status error and propagates error code", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          status: "error",
          error_code: "CONNECTION_NOT_FOUND",
          error_message: "The requested connection conn-999 was not found.",
        }),
      });

      try {
        await udfGetInventory({ connection_id: "conn-999" });
      } catch (err) {
        const udfErr = err as FabricUdfError;
        expect(udfErr.status).toBe(400);
        expect(udfErr.errorCode).toBe("CONNECTION_NOT_FOUND");
        expect(udfErr.detailMessage).toBe("The requested connection conn-999 was not found.");
      }
    });

    it("throws FabricUdfError with TIMEOUT when request exceeds configured timeout", async () => {
      globalThis.fetch = vi.fn().mockImplementation((_url, init) => {
        return new Promise((_, reject) => {
          init.signal.addEventListener("abort", () => {
            const err = new Error("The user aborted a request.");
            err.name = "AbortError";
            reject(err);
          });
        });
      });

      await expect(
        invokeUdfFunction("get_cost_waste", { connection_id: "conn-1" }, { timeoutMs: 50 })
      ).rejects.toThrow(FabricUdfError);
    });
  });

  describe("Request De-duplication", () => {
    it("de-duplicates simultaneous identical read queries to a single fetch", async () => {
      let resolvePromise: (value: unknown) => void;
      const delayedResponse = new Promise((resolve) => {
        resolvePromise = resolve;
      });

      const mockFetch = vi.fn().mockReturnValue(
        delayedResponse.then(() => ({
          ok: true,
          json: async () => ({
            status: "success",
            data: [{ id: "c1", name: "Dedupe Azure" }],
          }),
        }))
      );
      globalThis.fetch = mockFetch;

      const p1 = udfListConnections("azure");
      const p2 = udfListConnections("azure");

      await Promise.resolve();
      await Promise.resolve();

      expect(mockFetch).toHaveBeenCalledTimes(1);

      resolvePromise!(true);
      const [res1, res2] = await Promise.all([p1, p2]);

      expect(res1).toEqual(res2);
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });
  });

  describe("10 RPC Operation Contracts", () => {
    it("1. udfListConnections routes to list_connections", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: "success", data: [] }),
      });
      globalThis.fetch = mockFetch;

      await udfListConnections("azure");
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/functions/list_connections"),
        expect.objectContaining({
          body: JSON.stringify({ providerFilter: "azure" }),
        })
      );
    });

    it("2. udfCreateConnection routes to create_connection", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          status: "success",
          data: { id: "conn-new", name: "New Corp Azure" },
        }),
      });
      globalThis.fetch = mockFetch;

      await udfCreateConnection({
        name: "New Corp Azure",
        tenant_id: "t-1",
        subscription_id: "s-1",
        client_id: "c-1",
        client_secret: "sec-1",
      });

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/functions/create_connection"),
        expect.objectContaining({
          body: JSON.stringify({
            name: "New Corp Azure",
            tenantId: "t-1",
            subscriptionId: "s-1",
            clientId: "c-1",
            clientSecret: "sec-1",
            provider: "azure",
          }),
        })
      );
    });

    it("3. udfValidateConnection routes to validate_connection", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          status: "success",
          data: { valid: true, auth_method: "service_principal", message: "OK" },
        }),
      });
      globalThis.fetch = mockFetch;

      const res = await udfValidateConnection({ connection_id: "conn-1" });
      expect(res.valid).toBe(true);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/functions/validate_connection"),
        expect.anything()
      );
    });

    it("4. udfDeleteConnection routes to delete_connection", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          status: "success",
          data: { deleted: true, connection_id: "conn-to-delete" },
        }),
      });
      globalThis.fetch = mockFetch;

      const res = await udfDeleteConnection("conn-to-delete");
      expect(res.deleted).toBe(true);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/functions/delete_connection"),
        expect.objectContaining({
          body: JSON.stringify({ connectionId: "conn-to-delete" }),
        })
      );
    });

    it("5. udfGetInventory routes to get_inventory", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          status: "success",
          data: [
            {
              resource_id: "/sub/1/vm/test",
              name: "vm-test",
              resource_type: "Microsoft.Compute/virtualMachines",
              location: "eastus",
              tags: {},
            },
          ],
        }),
      });
      globalThis.fetch = mockFetch;

      const res = await udfGetInventory({
        connection_id: "conn-1",
        resource_type_filter: "virtualMachines",
      });
      expect(res).toHaveLength(1);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/functions/get_inventory"),
        expect.objectContaining({
          body: JSON.stringify({
            connectionId: "conn-1",
            resourceTypeFilter: "virtualMachines",
          }),
        })
      );
    });

    it("6. udfGetCostWaste routes to get_cost_waste", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          status: "success",
          data: {
            connection_id: "conn-1",
            scan_timestamp: "2026-11-04T00:00:00Z",
            total_monthly_waste_usd: "128.50",
            total_annual_waste_usd: "1542.00",
            waste_count_by_category: { unattached_disk: 1 },
            items: [],
          },
        }),
      });
      globalThis.fetch = mockFetch;

      const res = await udfGetCostWaste({ connection_id: "conn-1", force_refresh: true });
      expect(res.total_monthly_waste_usd).toBe("128.50");
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/functions/get_cost_waste"),
        expect.objectContaining({
          body: JSON.stringify({ connectionId: "conn-1", forceRefresh: true }),
        })
      );
    });

    it("7. udfGetMetrics routes to get_metrics", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          status: "success",
          data: {
            resource_id: "/sub/1/vm/test",
            time_grain: "PT1H",
            start_time: "2026-11-01T00:00:00Z",
            end_time: "2026-11-04T00:00:00Z",
            series: [{ metric_name: "Percentage CPU", unit: "Percent", points: [] }],
          },
        }),
      });
      globalThis.fetch = mockFetch;

      const res = await udfGetMetrics({
        connection_id: "conn-1",
        resource_id: "/sub/1/vm/test",
        metric_names: ["Percentage CPU"],
        days: 7,
      });
      expect(res.series).toHaveLength(1);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/functions/get_metrics"),
        expect.anything()
      );
    });

    it("8. udfGetTokenEconomics routes to get_token_economics", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          status: "success",
          data: {
            connection_id: "conn-1",
            window_days: 30,
            total_prompt_tokens: 500000,
            total_completion_tokens: 150000,
            total_tokens: 650000,
            total_cost_usd: "2.7500",
            token_efficiency_ratio: 0.3,
            models_breakdown: [],
            daily_timeseries: [],
          },
        }),
      });
      globalThis.fetch = mockFetch;

      const res = await udfGetTokenEconomics({ connection_id: "conn-1", days: 30 });
      expect(res.total_tokens).toBe(650000);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/functions/get_token_economics"),
        expect.objectContaining({
          body: JSON.stringify({ connectionId: "conn-1", days: 30 }),
        })
      );
    });

    it("9. udfRecordTokenUsage routes to record_token_usage", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          status: "success",
          data: {
            record_id: "rec-1",
            model_name: "gpt-4o",
            total_tokens: 1500,
            estimated_cost_usd: 0.0125,
          },
        }),
      });
      globalThis.fetch = mockFetch;

      const res = await udfRecordTokenUsage({
        connection_id: "conn-1",
        model_name: "gpt-4o",
        prompt_tokens: 1000,
        completion_tokens: 500,
        deployment_name: "chat-prod",
        latency_ms: 320,
      });
      expect(res.total_tokens).toBe(1500);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/functions/record_token_usage"),
        expect.objectContaining({
          body: JSON.stringify({
            connectionId: "conn-1",
            modelName: "gpt-4o",
            promptTokens: 1000,
            completionTokens: 500,
            deploymentName: "chat-prod",
            latencyMs: 320,
          }),
        })
      );
    });

    it("10. udfCalculatePricing routes to calculate_pricing", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          status: "success",
          data: {
            arm_sku_name: "Standard_D2s_v5",
            region: "northcentralus",
            hourly_rate_usd: 0.096,
            monthly_cost_usd: 70.08,
            annual_cost_usd: 840.96,
            currency: "USD",
            source: "Azure Retail Prices API",
          },
        }),
      });
      globalThis.fetch = mockFetch;

      const res = await udfCalculatePricing({
        arm_sku_name: "Standard_D2s_v5",
        region: "northcentralus",
      });
      expect(res.monthly_cost_usd).toBe(70.08);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/functions/calculate_pricing"),
        expect.objectContaining({
          body: JSON.stringify({
            armSkuName: "Standard_D2s_v5",
            region: "northcentralus",
            hoursPerMonth: 730,
          }),
        })
      );
    });
  });
});

