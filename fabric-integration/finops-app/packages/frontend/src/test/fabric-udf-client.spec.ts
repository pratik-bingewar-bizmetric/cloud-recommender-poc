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
} from "../lib/fabric-udf-client";
import { setAuthTokenProvider } from "../lib/api";

describe("Fabric UDF Client (Microsoft Fabric Python RPC Integration)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    resetUdfInFlightCache();
    setAuthTokenProvider(null);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    resetUdfInFlightCache();
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
    it("attaches Entra ID Bearer token when an auth token provider is registered", async () => {
      setAuthTokenProvider(async () => "mock-entra-jwt-token-xyz");

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
      expect(requestInit.headers["Authorization"]).toBe("Bearer mock-entra-jwt-token-xyz");
      expect(requestInit.headers["Content-Type"]).toBe("application/json");
    });

    it("does not attach Authorization header when no auth token provider is active", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          status: "success",
          data: [],
        }),
      });
      globalThis.fetch = mockFetch;

      await udfListConnections();
      const [, requestInit] = mockFetch.mock.calls[0];
      expect(requestInit.headers["Authorization"]).toBeUndefined();
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
        expect(udfErr.detailMessage).toContain("Insufficient Entra ID application roles");
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

