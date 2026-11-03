import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import {
  getApiBaseUrl,
  ApiError,
  checkBackendHealth,
  analyzeRequirements,
  generateArchitecture,
  simulatePricing,
  getProvidersStatus,
  listAzureSubscriptions,
  analyzeAzureSubscription,
  listGcpProjects,
  analyzeGcpProject,
  compareMultiCloud,
  getMonitoringOverview,
  getResourceMonitoringDetail,
  searchMonitoringLogs,
  getMonitoringSources,
  listConnections,
  validateConnection,
  createConnection,
  getTokenEconomics,
  setAuthTokenProvider,
  getAuthToken,
} from "../lib/api";
import { FinancialKpiDrawer } from "../components/FinancialKpiDrawer";
import { SectionCostSimulator } from "../components/SectionCostSimulator";
import { getAzureReferenceFinancials } from "../lib/financials";
import type {
  ArchitectureComponent,
  CostBreakdown,
  PricingReference,
  WorkloadAssumptions,
  WorkloadProfile,
} from "../types";

describe("FinOps API Client and Production Readiness", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  describe("getApiBaseUrl configuration", () => {
    it("returns configured VITE_API_BASE_URL without trailing slashes", () => {
      vi.stubEnv("VITE_API_BASE_URL", "https://api.finops.fabric.ms/api/v1///");
      expect(getApiBaseUrl()).toBe("https://api.finops.fabric.ms/api/v1");
    });

    it("falls back to local development URL in DEV mode when VITE_API_BASE_URL is empty", () => {
      vi.stubEnv("VITE_API_BASE_URL", "");
      // In Vite test environment, import.meta.env.DEV is boolean
      if (import.meta.env.DEV) {
        expect(getApiBaseUrl()).toBe("http://localhost:8000/api/v1");
      }
    });

    it("throws ApiError with 503 and API_ENDPOINT_NOT_CONFIGURED in simulated production", () => {
      vi.stubEnv("VITE_API_BASE_URL", "");
      // Simulate production by temporarily overriding import.meta.env.DEV
      const envObj = import.meta.env as unknown as { DEV: boolean };
      const originalDev = envObj.DEV;
      try {
        envObj.DEV = false;
        expect(() => getApiBaseUrl()).toThrowError(ApiError);
        try {
          getApiBaseUrl();
        } catch (err) {
          const apiErr = err as ApiError;
          expect(apiErr.status).toBe(503);
          expect(apiErr.detail.error_code).toBe("API_ENDPOINT_NOT_CONFIGURED");
        }
      } finally {
        envObj.DEV = originalDev;
      }
    });
  });

  describe("ApiError class", () => {
    it("initializes with status, detail, error_code, and custom message", () => {
      const err = new ApiError(
        422,
        {
          error_code: "VALIDATION_FAILED",
          message: "Field customer_count is required",
        },
        "Validation Error"
      );
      expect(err.name).toBe("ApiError");
      expect(err.status).toBe(422);
      expect(err.detail.error_code).toBe("VALIDATION_FAILED");
      expect(err.message).toBe("Validation Error");
    });
  });

  describe("API Client functions and error handling", () => {
    beforeEach(() => {
      vi.stubEnv("VITE_API_BASE_URL", "http://localhost:8000/api/v1");
    });

    it("checkBackendHealth performs GET on /health", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: "ok" }),
      });
      globalThis.fetch = mockFetch;

      const result = await checkBackendHealth();
      expect(result.status).toBe("ok");
      expect(mockFetch).toHaveBeenCalledWith("http://localhost:8000/health");
    });

    it("propagates structured FastAPI 422 error on validation failure", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({
          detail: [
            { loc: ["body", "idea"], msg: "Field required", type: "missing" },
          ],
        }),
      });
      globalThis.fetch = mockFetch;

      await expect(analyzeRequirements("")).rejects.toThrowError(ApiError);
    });

    it("attaches Authorization Bearer token when token provider is registered", async () => {
      setAuthTokenProvider(() => "test-jwt-bearer-token-12345");
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [],
      });
      globalThis.fetch = mockFetch;

      await listConnections();
      expect(mockFetch).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/connections",
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: "Bearer test-jwt-bearer-token-12345",
          }),
        })
      );
      setAuthTokenProvider(null);
    });

    it("resolves token from localStorage session fallback", async () => {
      setAuthTokenProvider(null);
      localStorage.setItem("authSession", JSON.stringify({ accessToken: "stored-session-token-xyz" }));
      const token = await getAuthToken();
      expect(token).toBe("stored-session-token-xyz");
      localStorage.removeItem("authSession");
    });

    it("handles 401 Unauthorized with descriptive authentication message", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({
          error: {
            message: {
              error_code: "TOKEN_EXPIRED",
              message: "The Entra ID authentication token has expired.",
            },
          },
        }),
      });
      globalThis.fetch = mockFetch;

      try {
        await listConnections();
        expect.unreachable("Should have thrown ApiError");
      } catch (err) {
        const apiErr = err as ApiError;
        expect(apiErr.status).toBe(401);
        expect(apiErr.detail.error_code).toBe("TOKEN_EXPIRED");
        expect(apiErr.message).toContain("expired");
      }
    });

    it("handles 403 Forbidden with access denied message", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
        json: async () => ({
          detail: {
            error_code: "INSUFFICIENT_PERMISSIONS",
            message: "User requires one of roles: ['Admin']",
          },
        }),
      });
      globalThis.fetch = mockFetch;

      try {
        await listConnections();
        expect.unreachable("Should have thrown ApiError");
      } catch (err) {
        const apiErr = err as ApiError;
        expect(apiErr.status).toBe(403);
        expect(apiErr.detail.error_code).toBe("INSUFFICIENT_PERMISSIONS");
      }
    });

    it("analyzeRequirements POSTs to /analysis/requirements", async () => {
      const mockResponse = {
        workload_profile: { name: "Test App" },
        clarifying_questions: [],
        workload_assumptions: {},
        missing_critical_requirements: [],
        ai_provider_used: "azure_ai_foundry",
        status: "ready_for_architecture",
      };
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => mockResponse,
      });
      globalThis.fetch = mockFetch;

      const res = await analyzeRequirements("Smart expense app", "eastus", 500);
      expect(mockFetch).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/analysis/requirements",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            idea: "Smart expense app",
            target_region: "eastus",
            customer_preset: 500,
          }),
        })
      );
      expect(res.ai_provider_used).toBe("azure_ai_foundry");
    });

    it("generateArchitecture POSTs to /architecture/generate", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ id: "rec-1", provider: "azure" }),
      });
      globalThis.fetch = mockFetch;

      const profile = {
        name: "Test App",
        category: "web_api",
        description: "Test description",
        target_regions: ["eastus"],
      } as unknown as WorkloadProfile;

      const assumptions = {
        customer_count: 500,
      } as unknown as WorkloadAssumptions;

      const res = await generateArchitecture(profile, assumptions, [], "eastus");
      expect(mockFetch).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/architecture/generate",
        expect.anything()
      );
      expect(res.provider).toBe("azure");
    });

    it("simulatePricing POSTs to /pricing/simulate", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          cost_breakdown: { total_monthly: "150.00" },
        }),
      });
      globalThis.fetch = mockFetch;

      const res = await simulatePricing([], {} as WorkloadAssumptions, "eastus", "15.00");
      expect(mockFetch).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/pricing/simulate",
        expect.anything()
      );
      expect(res.cost_breakdown.total_monthly).toBe("150.00");
    });

    it("getProvidersStatus GETs /inventory/providers/status", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [
          { provider: "azure", is_authenticated: true },
          { provider: "gcp", is_authenticated: true },
        ],
      });
      globalThis.fetch = mockFetch;

      const statuses = await getProvidersStatus();
      expect(statuses.length).toBe(2);
      expect(mockFetch).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/inventory/providers/status"
      );
    });

    it("listAzureSubscriptions and analyzeAzureSubscription make expected calls", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [],
      });
      globalThis.fetch = mockFetch;

      await listAzureSubscriptions();
      expect(mockFetch).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/inventory/azure/subscriptions"
      );

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ scope_id: "sub-123" }),
      });

      await analyzeAzureSubscription({ scope_id: "sub-123" });
      expect(mockFetch).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/inventory/azure/analyze",
        expect.objectContaining({ method: "POST" })
      );
    });

    it("listGcpProjects and analyzeGcpProject make expected calls", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [],
      });
      globalThis.fetch = mockFetch;

      await listGcpProjects();
      expect(mockFetch).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/inventory/gcp/projects"
      );

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ scope_id: "proj-123" }),
      });

      await analyzeGcpProject({ scope_id: "proj-123" });
      expect(mockFetch).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/inventory/gcp/analyze",
        expect.objectContaining({ method: "POST" })
      );
    });

    it("compareMultiCloud POSTs to /inventory/compare", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          azure_total_monthly: "100.00",
          gcp_total_monthly: "120.00",
          monthly_delta_gcp_minus_azure: "20.00",
        }),
      });
      globalThis.fetch = mockFetch;

      const res = await compareMultiCloud({
        workload_profile: {
          name: "Test",
          description: "Desc",
          category: "web_app",
          target_traffic_rps: 10,
          monthly_active_users: 500,
          primary_region: "eastus",
        },
        workload_assumptions: { customer_count: 500 } as WorkloadAssumptions,
        azure_region: "eastus",
        gcp_region: "us-central1",
      });
      expect(res.monthly_delta_gcp_minus_azure).toBe("20.00");
    });

    it("monitoring and telemetry endpoints make expected requests", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: "ok" }),
      });
      globalThis.fetch = mockFetch;

      await getMonitoringOverview({ provider: "azure", scope_id: "sub-1" });
      expect(mockFetch).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/monitoring/overview",
        expect.anything()
      );

      await getResourceMonitoringDetail({ provider: "azure", scope_id: "sub-1", resource_id: "r-1" });
      expect(mockFetch).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/monitoring/resource",
        expect.anything()
      );

      await searchMonitoringLogs({ provider: "azure", scope_id: "sub-1" });
      expect(mockFetch).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/monitoring/logs",
        expect.anything()
      );

      await getMonitoringSources();
      expect(mockFetch).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/monitoring/sources",
        expect.anything()
      );

      await getTokenEconomics({ provider: "azure", scope_id: "sub-1" });
      expect(mockFetch).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/monitoring/token-economics",
        expect.anything()
      );
    });

    it("connections lifecycle endpoints make expected requests", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [],
      });
      globalThis.fetch = mockFetch;

      await listConnections();
      expect(mockFetch).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/connections",
        expect.anything()
      );

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ is_valid: true }),
      });
      await validateConnection({ provider: "azure", scope_id: "sub-1" });
      expect(mockFetch).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/connections/validate",
        expect.anything()
      );

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ id: "conn-1" }),
      });
      await createConnection({
        name: "My Connection",
        provider: "azure",
        scope_id: "sub-1",
      });
      expect(mockFetch).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/connections",
        expect.anything()
      );
    });
  });

  describe("FinOps UI Component Rendering", () => {
    const referenceFinancials = getAzureReferenceFinancials("30d", "USD");

    it("renders FinancialKpiDrawer when open and respects ESC key", () => {
      const handleClose = vi.fn();
      const { rerender } = render(
        <FinancialKpiDrawer
          isOpen={true}
          onClose={handleClose}
          kpiType="spend"
          financials={referenceFinancials}
        />
      );

      expect(screen.getByText("Estimated Monthly Spend Breakdown")).toBeInTheDocument();
      expect(screen.getAllByText("$225.11").length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText(/Spend Invariant/i)).toBeInTheDocument();

      // Fire ESC key
      fireEvent.keyDown(window, { key: "Escape", code: "Escape" });
      expect(handleClose).toHaveBeenCalledTimes(1);

      // Does not render when isOpen is false
      rerender(
        <FinancialKpiDrawer
          isOpen={false}
          onClose={handleClose}
          kpiType="spend"
          financials={referenceFinancials}
        />
      );
      expect(screen.queryByText("Estimated Monthly Spend Breakdown")).not.toBeInTheDocument();
    });

    it("renders SectionCostSimulator with complete estimate and verified subtotal", () => {
      const mockCostBreakdown: CostBreakdown = {
        compute: "91.25",
        database: "73.00",
        storage: "32.21",
        ai: "25.00",
        networking: "3.65",
        other: "0.00",
        subtotal: "225.11",
        verified_subtotal: "225.11",
        safety_buffer_amount: "33.77",
        total_monthly: "258.88",
        total_five_month: "1294.40",
        total_annual: "3106.56",
        is_complete: true,
        estimate_status: "complete",
        unpriced_component_count: 0,
      };

      const mockComponents: ArchitectureComponent[] = [
        {
          component_id: "c1",
          service_name: "App Service Plan",
          service_id: "azure-app-service",
          category: "compute",
          sku_or_tier: "B2 Basic",
          quantity: 1,
          pricing_status: "verified",
          monthly_cost: "91.25",
          dependencies: [],
          rationale: "Hosts application backend",
          known_risks: [],
        },
      ];

      const mockProvenance: PricingReference[] = [
        {
          provider: "azure",
          service_id: "azure-app-service",
          meter_or_sku_id: "meter-1",
          rate: "0.075",
          unit_description: "1 Hour",
          retrieval_timestamp: new Date().toISOString(),
          provenance_source: "official_retail_prices_api",
          meter_name: "B2 Basic",
          pricing_tier_or_notes: "Verified Retail Rate",
        },
      ];

      render(
        <SectionCostSimulator
          costBreakdown={mockCostBreakdown}
          components={mockComponents}
          pricingProvenance={mockProvenance}
          unverifiedWarnings={[]}
          isSimulating={false}
        />
      );

      expect(screen.getByText("Deterministic FinOps Cost Simulator")).toBeInTheDocument();
      expect(screen.getByText("All Meters Verified")).toBeInTheDocument();
      expect(screen.getAllByText("$258.88").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("$1,294.40").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("$3,106.56").length).toBeGreaterThanOrEqual(1);
    });

    it("renders warning banner when cost estimate is incomplete with unpriced components", () => {
      const incompleteCostBreakdown: CostBreakdown = {
        compute: "50.00",
        database: "0.00",
        storage: "0.00",
        ai: "0.00",
        networking: "0.00",
        other: "0.00",
        subtotal: "50.00",
        verified_subtotal: "50.00",
        safety_buffer_amount: "7.50",
        total_monthly: "57.50",
        total_five_month: "287.50",
        total_annual: "690.00",
        is_complete: false,
        estimate_status: "incomplete",
        unpriced_component_count: 1,
        unpriced_service_ids: ["azure-custom-hardware"],
      };

      render(
        <SectionCostSimulator
          costBreakdown={incompleteCostBreakdown}
          components={[]}
          pricingProvenance={[]}
          unverifiedWarnings={["Missing retail price for azure-custom-hardware"]}
          isSimulating={false}
        />
      );

      expect(screen.getByText(/Incomplete Cost Estimate — 1 Component\(s\) Unpriced/i)).toBeInTheDocument();
      expect(screen.getByText("Missing retail price for azure-custom-hardware")).toBeInTheDocument();
    });
  });
});
