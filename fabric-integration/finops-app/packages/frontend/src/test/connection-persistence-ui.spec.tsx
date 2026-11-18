import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { ApiError } from "../lib/api";
import { describeConnectionError } from "../lib/connectionErrors";
import type { CloudConnection } from "../types";

const TENANT = "11111111-1111-1111-1111-111111111111";
const CLIENT = "22222222-2222-2222-2222-222222222222";
const SUB = "aaaaaaaa-0000-0000-0000-000000000001";
const SECRET = "Sup3r-Secret-Value-For-Tests~abc123";

const api = vi.hoisted(() => ({
  listConnections: vi.fn(),
  createConnection: vi.fn(),
  validateConnection: vi.fn(),
  deleteConnection: vi.fn(),
}));

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, ...api };
});

import { ConnectCloudView } from "../components/ConnectCloudView";

const owned: CloudConnection = {
  id: "conn-1",
  name: "Production",
  provider: "azure",
  scope_id: SUB,
  display_name: "Production",
  tenant_or_org_id: TENANT,
  auth_method: "service_principal",
  status: "connected",
  is_live: true,
  capabilities: [],
  access_limitations: [],
  ownership: "owned",
  integrations: [
    { integration: "resource_manager", state: "connected" },
    { integration: "cost_management", state: "permission_denied", message: "needs Cost Management Reader" },
    { integration: "fabric", state: "not_configured" },
  ],
};

function inputFor(label: string): HTMLInputElement {
  const el = screen.getByText(label, { selector: "label" }).parentElement?.querySelector("input");
  if (!el) throw new Error(`no input for ${label}`);
  return el as HTMLInputElement;
}

async function openNewForm() {
  render(<ConnectCloudView onConnectionSelected={vi.fn()} />);
  const addTabs = await screen.findAllByRole("button", { name: /^Add new connection$/ });
  fireEvent.click(addTabs[0]); // the Azure card is first
}

function fillForm(secret = SECRET) {
  fireEvent.change(inputFor("Connection Name"), { target: { value: "Production" } });
  fireEvent.change(inputFor("Subscription ID"), { target: { value: SUB } });
  fireEvent.change(inputFor("Tenant / Directory ID"), { target: { value: TENANT } });
  fireEvent.change(inputFor("App / Client ID"), { target: { value: CLIENT } });
  fireEvent.change(inputFor("Client Secret"), { target: { value: secret } });
}

describe("Fabric frontend: persistent connection workflow", () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset());
    api.listConnections.mockResolvedValue([]);
    window.localStorage.clear();
    window.sessionStorage.clear();
  });
  afterEach(() => cleanup());

  it("sends the service principal explicitly and clears the secret after a successful save", async () => {
    api.createConnection.mockResolvedValue({ ...owned });
    api.validateConnection.mockResolvedValue({ success: true, status: "connected" });
    await openNewForm();
    fillForm();
    fireEvent.click(screen.getByRole("button", { name: /Test & Connect Azure/ }));

    await waitFor(() => expect(api.createConnection).toHaveBeenCalledTimes(1));
    expect(api.createConnection.mock.calls[0][0]).toMatchObject({
      provider: "azure",
      auth_method: "service_principal",
      scope_id: SUB,
      azure_tenant_id: TENANT,
      azure_client_id: CLIENT,
      azure_client_secret: SECRET,
    });
    await waitFor(() => expect(inputFor("Client Secret").value).toBe(""));
    expect(JSON.stringify({ ...window.localStorage, ...window.sessionStorage })).not.toContain(SECRET);
  });

  it("keeps non-secret fields and shows an authentication error after invalid credentials", async () => {
    api.createConnection.mockRejectedValue(
      new ApiError(400, { error_code: "INVALID_AZURE_CREDENTIALS", message: "The client secret is incorrect." } as never),
    );
    await openNewForm();
    fillForm();
    fireEvent.click(screen.getByRole("button", { name: /Test & Connect Azure/ }));

    const alert = await screen.findByText(/The cloud account credentials were rejected/);
    expect(alert.textContent).toContain("The client secret is incorrect.");
    expect(inputFor("Connection Name").value).toBe("Production");
    expect(inputFor("Tenant / Directory ID").value).toBe(TENANT);
    expect(inputFor("App / Client ID").value).toBe(CLIENT);
    expect(inputFor("Client Secret").value).toBe(""); // secrets are never kept after a failure
  });

  it("shows application authorization failures separately from cloud failures", async () => {
    api.createConnection.mockRejectedValue(
      new ApiError(401, { message: "Authentication is required." } as never),
    );
    await openNewForm();
    fillForm();
    fireEvent.click(screen.getByRole("button", { name: /Test & Connect Azure/ }));
    expect(await screen.findByText(/not signed in to the application/i)).toBeInTheDocument();
  });

  it("explains which required fields are missing without calling the backend", async () => {
    await openNewForm();
    fireEvent.change(inputFor("Connection Name"), { target: { value: "Production" } });
    fireEvent.submit(inputFor("Connection Name").closest("form")!);
    expect(await screen.findByText(/Required to validate the Azure service principal: .*Client secret/)).toBeInTheDocument();
    expect(api.createConnection).not.toHaveBeenCalled();
  });

  it("shows per-integration status for saved connections and deletes them on the server", async () => {
    api.listConnections.mockResolvedValue([owned]);
    api.deleteConnection.mockResolvedValue({ deleted: true, connection_id: "conn-1" });
    render(<ConnectCloudView onConnectionSelected={vi.fn()} />);

    const chips = await screen.findByTestId("integrations-conn-1");
    expect(chips.textContent).toContain("resource manager: connected");
    expect(chips.textContent).toContain("cost management: permission denied"); // never shown as zero cost
    expect(chips.textContent).toContain("fabric: not configured");

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(api.deleteConnection).toHaveBeenCalledWith("conn-1"));
    await waitFor(() => expect(api.listConnections).toHaveBeenCalledTimes(2)); // list refreshed
  });
});

describe("connection error classification (Fabric frontend)", () => {
  it("separates application authentication, cloud authentication and cloud permission problems", () => {
    expect(describeConnectionError({ status: 401, detail: { message: "x" } }).kind).toBe("application_auth");
    expect(describeConnectionError({ status: 403, detail: { message: "x" } }).kind).toBe("application_permission");
    expect(describeConnectionError({ status: 400, detail: { error_code: "INVALID_AZURE_CREDENTIALS", message: "x" } }).kind).toBe("cloud_auth");
    expect(describeConnectionError({ status: 400, detail: { error_code: "SUBSCRIPTION_NOT_ACCESSIBLE", message: "x" } }).kind).toBe("cloud_permission");
    expect(describeConnectionError({ status: 409, detail: { error_code: "DUPLICATE_CONNECTION", message: "x" } }).kind).toBe("conflict");
    expect(describeConnectionError({ status: 503, detail: { error_code: "DATABASE_UNAVAILABLE", message: "x" } }).kind).toBe("service");
  });
});
