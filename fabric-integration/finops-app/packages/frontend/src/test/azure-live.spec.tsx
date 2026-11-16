import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { AzureLiveApiError, createAzureLiveApi, type AzureLiveApi } from "../lib/azureLiveApi";
import { AzureLiveView } from "../components/azure-live/AzureLiveView";
import { buildMsalConfiguration, createEntraTokenService } from "../services/entra-token.service";
import type { BackendTokenService } from "../services/entra-token.service";
import type {
  ConnectResponse,
  DataDomain,
  OverviewResponse,
} from "../types/azureLive";

const TENANT = "11111111-1111-1111-1111-111111111111";
const CLIENT = "22222222-2222-2222-2222-222222222222";
const SECRET = "Sup3r-Secret-Value-For-Tests~abc123";
const SUB = "aaaaaaaa-0000-0000-0000-000000000001";

const source = (api = "GET /x", subscription: string | null = null) => ({
  connection_id: "conn-abcdef123456",
  tenant_id: TENANT,
  client_id: CLIENT,
  subscription_id: subscription,
  api,
  auth_method: "service_principal_client_secret",
  fetched_at: "2026-11-16T10:00:00Z",
});

function domain<T>(name: string, partial: Partial<DataDomain<T>> = {}): DataDomain<T> {
  return {
    domain: name,
    state: "accessible",
    items: [],
    count: 0,
    message: null,
    required_permission: null,
    http_status: 200,
    azure_error_code: null,
    retry_after_seconds: null,
    truncated: false,
    source: source(),
    ...partial,
  };
}

const connection = {
  connection_id: "conn-abcdef123456",
  tenant_id: TENANT,
  client_id: CLIENT,
  auth_method: "service_principal_client_secret",
  identity_source: "user_supplied_service_principal",
  connected_at: "2026-11-16T10:00:00Z",
  expires_at: "2026-11-16T11:00:00Z",
};

const subscriptions = domain("subscriptions", {
  items: [{ subscription_id: SUB, display_name: "Prod", state: "Enabled", tenant_id: TENANT }],
  count: 1,
});

const connectResponse: ConnectResponse = { connection, subscriptions, requested_subscription: null };

function overview(costState: "accessible" | "permission_denied" = "permission_denied"): OverviewResponse {
  return {
    connection,
    subscription_id: SUB,
    subscriptions,
    resource_groups: domain("resource_groups", {
      items: [{ name: "rg-app", id: "/x/rg-app", location: "eastus", provisioning_state: "Succeeded", tags: {} }],
      count: 1,
      source: source("GET /rg", SUB),
    }),
    resources: domain("resources", {
      items: [
        {
          id: "/x/vm1",
          name: "vm1",
          type: "Microsoft.Compute/virtualMachines",
          location: "eastus",
          kind: null,
          sku: null,
          resource_group: "rg-app",
          tags: {},
        },
      ],
      count: 1,
      source: source("GET /resources", SUB),
    }),
    type_breakdown: [{ resource_type: "Microsoft.Compute/virtualMachines", count: 1 }],
    cost:
      costState === "permission_denied"
        ? domain("cost", {
            state: "permission_denied",
            items: null,
            count: null,
            http_status: 403,
            required_permission: "Cost Management Reader",
            message: "The connected service principal is not authorized for this data.",
            source: source("POST cost", SUB),
          })
        : domain("cost", {
            items: [
              { period: "month_to_date", period_start: null, period_end: null, currency: "USD", total: 150.75, by_service: [] },
            ],
            count: 1,
            source: source("POST cost", SUB),
          }),
  };
}

function fakeApi(overrides: Partial<AzureLiveApi> = {}): AzureLiveApi {
  return {
    connect: vi.fn().mockResolvedValue(connectResponse),
    validate: vi.fn().mockResolvedValue({ valid: true, connection, subscriptions }),
    disconnect: vi.fn().mockResolvedValue(undefined),
    subscriptions: vi.fn().mockResolvedValue(subscriptions),
    overview: vi.fn().mockResolvedValue(overview()),
    resources: vi.fn(),
    resourceDetail: vi.fn(),
    metricDefinitions: vi.fn().mockResolvedValue(domain("metric_definitions")),
    metricValues: vi.fn(),
    cost: vi.fn(),
    ...overrides,
  } as AzureLiveApi;
}

const signedIn: BackendTokenService = {
  isConfigured: () => true,
  getAccount: () => ({ homeAccountId: "h", environment: "e", tenantId: TENANT, username: "u@x", localAccountId: "l" }),
  signIn: vi.fn(),
  getAccessToken: vi.fn().mockResolvedValue("backend-token"),
  signOut: vi.fn(),
};

async function fillAndConnect(secret = SECRET) {
  fireEvent.change(screen.getByLabelText(/Tenant ID/i), { target: { value: TENANT } });
  fireEvent.change(screen.getByLabelText(/Client ID/i), { target: { value: CLIENT } });
  fireEvent.change(screen.getByLabelText(/Client secret/i), { target: { value: secret } });
  fireEvent.click(screen.getByRole("button", { name: /Connect Azure/i }));
}

describe("Azure live connection UI", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });
  afterEach(() => cleanup());

  it("never writes the client secret to localStorage or sessionStorage", async () => {
    const local = vi.spyOn(Storage.prototype, "setItem");
    render(<AzureLiveView api={fakeApi()} tokenService={signedIn} />);
    await fillAndConnect();
    await screen.findByTestId("azure-live-dashboard");

    const everythingStored = JSON.stringify([
      ...local.mock.calls,
      { ...window.localStorage },
      { ...window.sessionStorage },
    ]);
    expect(everythingStored).not.toContain(SECRET);
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
    local.mockRestore();
  });

  it("clears the secret field after submit and does not render it anywhere", async () => {
    const { container } = render(<AzureLiveView api={fakeApi()} tokenService={signedIn} />);
    await fillAndConnect();
    await screen.findByTestId("azure-live-dashboard");
    expect((screen.getByLabelText(/Client secret/i) as HTMLInputElement).value).toBe("");
    expect(container.innerHTML).not.toContain(SECRET);
  });

  it("shows the connection, counts, inventory and the identity note", async () => {
    render(<AzureLiveView api={fakeApi()} tokenService={signedIn} />);
    await fillAndConnect();
    const dash = await screen.findByTestId("azure-live-dashboard");
    expect(within(dash).getByText("Connected")).toBeInTheDocument();
    expect(within(screen.getByTestId("tile-Subscriptions")).getByText("1")).toBeInTheDocument();
    expect(within(screen.getByTestId("tile-Resource groups")).getByText("1")).toBeInTheDocument();
    expect(within(screen.getByTestId("tile-Resources")).getByText("1")).toBeInTheDocument();
    expect(screen.getAllByText("Microsoft.Compute/virtualMachines").length).toBeGreaterThan(0);
    expect(screen.getByTestId("identity-note").textContent).toMatch(/not read through a shared server identity/i);
    expect(screen.getAllByTestId("source-line").length).toBeGreaterThan(0);
  });

  it("reports missing Cost Management permission instead of showing zero spend", async () => {
    render(<AzureLiveView api={fakeApi()} tokenService={signedIn} />);
    await fillAndConnect();
    await screen.findByTestId("azure-live-dashboard");
    const cost = screen.getByTestId("domain-cost");
    expect(within(cost).getByTestId("state-permission_denied")).toBeInTheDocument();
    expect(cost.textContent).toContain("Cost Management Reader");
    expect(screen.queryByTestId("cost-total")).toBeNull();
    expect(screen.getByTestId("azure-live-dashboard").textContent).not.toMatch(/\$0(\.00)?/);
  });

  it("shows actual cost when accessible", async () => {
    const api = fakeApi({ overview: vi.fn().mockResolvedValue(overview("accessible")) });
    render(<AzureLiveView api={api} tokenService={signedIn} />);
    await fillAndConnect();
    expect((await screen.findByTestId("cost-total")).textContent).toMatch(/150\.75/);
  });

  it("keeps accessible inventory visible when another domain fails", async () => {
    const api = fakeApi({ overview: vi.fn().mockResolvedValue(overview()) });
    render(<AzureLiveView api={api} tokenService={signedIn} />);
    await fillAndConnect();
    await screen.findByTestId("azure-live-dashboard");
    expect(within(screen.getByTestId("domain-resources")).getByTestId("state-accessible")).toBeInTheDocument();
    expect(screen.getByText("vm1")).toBeInTheDocument();
  });

  it("rejects invalid credentials with the backend's explanation and no dashboard", async () => {
    const api = fakeApi({
      connect: vi
        .fn()
        .mockRejectedValue(new AzureLiveApiError(400, "INVALID_AZURE_CREDENTIALS", "The client secret is incorrect.", { category: "invalid_client_secret" })),
    });
    render(<AzureLiveView api={api} tokenService={signedIn} />);
    await fillAndConnect();
    expect((await screen.findByTestId("connect-error")).textContent).toContain("The client secret is incorrect.");
    expect(screen.queryByTestId("azure-live-dashboard")).toBeNull();
    expect(screen.getByRole("button", { name: /Connect Azure/i })).toBeEnabled();
  });

  it("validates GUIDs client-side and does not call the backend for bad input", async () => {
    const api = fakeApi();
    render(<AzureLiveView api={api} tokenService={signedIn} />);
    fireEvent.change(screen.getByLabelText(/Tenant ID/i), { target: { value: "nope" } });
    fireEvent.click(screen.getByRole("button", { name: /Connect Azure/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Tenant ID must be a GUID/);
    expect(api.connect).not.toHaveBeenCalled();
  });

  it("disconnect forgets the connection and the in-memory secret", async () => {
    const api = fakeApi();
    render(<AzureLiveView api={api} tokenService={signedIn} />);
    await fillAndConnect();
    await screen.findByTestId("azure-live-dashboard");
    fireEvent.click(screen.getByRole("button", { name: /Disconnect/i }));
    await waitFor(() => expect(screen.queryByTestId("azure-live-dashboard")).toBeNull());
    expect(api.disconnect).toHaveBeenCalledWith("conn-abcdef123456");
  });

  it("reconnects once with the in-memory secret when the backend forgot the connection", async () => {
    const gone = new AzureLiveApiError(404, "AZURE_CONNECTION_NOT_FOUND", "expired");
    const overviewFn = vi
      .fn()
      .mockResolvedValueOnce(overview())
      .mockRejectedValueOnce(gone)
      .mockResolvedValueOnce(overview());
    const api = fakeApi({ overview: overviewFn });
    render(<AzureLiveView api={api} tokenService={signedIn} />);
    await fillAndConnect();
    await screen.findByTestId("azure-live-dashboard");
    fireEvent.click(screen.getByRole("button", { name: /^Refresh$/ }));
    await waitFor(() => expect(api.connect).toHaveBeenCalledTimes(2));
    expect((api.connect as ReturnType<typeof vi.fn>).mock.calls[1][0].clientSecret).toBe(SECRET);
  });

  it("asks the user to sign in to the API first when no Entra account exists", () => {
    const token: BackendTokenService = { ...signedIn, getAccount: () => null };
    render(<AzureLiveView api={fakeApi()} tokenService={token} />);
    expect(screen.getByRole("button", { name: /Sign in with Microsoft/i })).toBeInTheDocument();
    expect(screen.queryByLabelText(/Client secret/i)).toBeNull();
  });

  it("explains missing Entra configuration instead of failing silently", () => {
    const token: BackendTokenService = { ...signedIn, isConfigured: () => false, getAccount: () => null };
    render(<AzureLiveView api={fakeApi()} tokenService={token} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/VITE_ENTRA/);
  });
});

describe("Azure live API client", () => {
  const okResponse = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

  it("sends the secret only in the POST body, with a bearer token and no cookies or caching", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(okResponse(connectResponse, 201));
    const api = createAzureLiveApi({ baseUrl: "https://api.test/api/v1", getToken: async () => "backend-token", fetchImpl });
    await api.connect({ tenantId: ` ${TENANT} `, clientId: CLIENT, clientSecret: SECRET, subscriptionId: "" });

    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe("https://api.test/api/v1/azure/connections");
    expect(url).not.toContain(SECRET);
    expect(init.headers.Authorization).toBe("Bearer backend-token");
    expect(JSON.stringify(init.headers)).not.toContain(SECRET);
    expect(JSON.parse(init.body)).toEqual({ tenant_id: TENANT, client_id: CLIENT, client_secret: SECRET });
    expect(init.credentials).toBe("omit");
    expect(init.cache).toBe("no-store");
  });

  it("never puts identifiers or secrets in later requests and encodes path parts", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(okResponse(overview()));
    const api = createAzureLiveApi({ baseUrl: "https://api.test/api/v1", getToken: async () => "t", fetchImpl });
    await api.overview("a/b", SUB);
    expect(fetchImpl.mock.calls[0][0]).toBe(`https://api.test/api/v1/azure/connections/a%2Fb/subscriptions/${SUB}/overview`);
    expect(fetchImpl.mock.calls[0][1].body).toBeUndefined();
  });

  it("normalizes backend errors, retry-after and the connection-gone signal", async () => {
    const gone = vi.fn().mockResolvedValue(
      okResponse({ error: { code: 404, type: "http_error", message: { error_code: "AZURE_CONNECTION_NOT_FOUND", message: "expired" } } }, 404),
    );
    const api = createAzureLiveApi({ baseUrl: "https://api.test/api/v1", getToken: async () => "t", fetchImpl: gone });
    await expect(api.subscriptions("x")).rejects.toMatchObject({ status: 404, isConnectionGone: true });

    const limited = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: { message: { error_code: "TOO_MANY_ATTEMPTS", message: "slow down" } } }), {
        status: 429,
        headers: { "Retry-After": "12", "Content-Type": "application/json" },
      }),
    );
    const api2 = createAzureLiveApi({ baseUrl: "https://api.test/api/v1", getToken: async () => "t", fetchImpl: limited });
    await expect(api2.validate("x")).rejects.toMatchObject({ code: "TOO_MANY_ATTEMPTS", retryAfterSeconds: 12 });
  });

  it("refuses to run without a configured backend URL (no localhost/UDF fallback)", async () => {
    const api = createAzureLiveApi({ baseUrl: null, getToken: async () => "t", fetchImpl: vi.fn() });
    await expect(api.subscriptions("x")).rejects.toMatchObject({ code: "API_ENDPOINT_NOT_CONFIGURED" });
  });
});

describe("Backend token acquisition (MSAL)", () => {
  const config = {
    clientId: CLIENT,
    tenantId: TENANT,
    apiScope: "api://backend/access_as_user",
    redirectUri: "https://app.test/redirect.html",
    popupRelayUri: "/popup-relay.html",
  };

  it("keeps tokens in memory only and targets the backend API scope", () => {
    const msal = buildMsalConfiguration(config);
    expect(msal.cache?.cacheLocation).toBe("memoryStorage");
    expect(msal.auth.authority).toBe(`https://login.microsoftonline.com/${TENANT}`);
  });

  it("requests the backend scope and never reads Rayfin session storage", async () => {
    window.localStorage.setItem("authSession", JSON.stringify({ accessToken: "rayfin-session-token" }));
    const pca = {
      initialize: vi.fn().mockResolvedValue(undefined),
      getActiveAccount: vi.fn().mockReturnValue({ username: "u" }),
      getAllAccounts: vi.fn().mockReturnValue([]),
      acquireTokenSilent: vi.fn().mockResolvedValue({ accessToken: "entra-backend-token" }),
      acquireTokenPopup: vi.fn(),
      loginPopup: vi.fn(),
      setActiveAccount: vi.fn(),
      clearCache: vi.fn(),
    };
    const service = createEntraTokenService(
      () => config,
      () => pca as never,
    );
    const token = await service.getAccessToken();
    expect(token).toBe("entra-backend-token");
    expect(pca.acquireTokenSilent.mock.calls[0][0].scopes).toEqual([config.apiScope]);
    expect(token).not.toContain("rayfin");
    window.localStorage.clear();
  });

  it("reports not configured when settings are missing", () => {
    const service = createEntraTokenService(() => null);
    expect(service.isConfigured()).toBe(false);
    return expect(service.getAccessToken()).rejects.toThrow(/not configured/i);
  });
});
