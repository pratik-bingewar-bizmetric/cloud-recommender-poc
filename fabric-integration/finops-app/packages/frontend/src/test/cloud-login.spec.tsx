import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { CloudLoginForm } from "@/components/CloudLoginForm";
import * as api from "@/lib/api";
import type { ServicePrincipalConnectResponse } from "@/types/auth";

describe("CloudLoginForm Component", () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    vi.restoreAllMocks();
  });

  const validResponse: ServicePrincipalConnectResponse = {
    session_token: "finops_sess_mock_token_12345",
    session_id: "sess-123456",
    account_id: "acc-123456",
    account_name: "Azure Enterprise Production",
    connection_id: "conn-123456",
    tenant_id: "11111111-1111-1111-1111-111111111111",
    subscription_id: "22222222-2222-2222-2222-222222222222",
    subscription_name: "Core Production Subscription",
    roles: ["FinOpsAdmin"],
    permissions: {
      reader: true,
      cost_management_reader: true,
      monitoring_reader: true,
    },
    created_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 28800000).toISOString(),
  };

  it("renders all 5 credentials fields and submit button", () => {
    render(<CloudLoginForm onSuccess={vi.fn()} />);

    expect(screen.getByLabelText(/Account \/ Connection Name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Azure Subscription ID/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Azure Tenant ID/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Client ID/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Client Secret/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Connect & Access FinOps Dashboard/i })
    ).toBeInTheDocument();
  });

  it("toggles client secret visibility via show/hide button", () => {
    render(<CloudLoginForm onSuccess={vi.fn()} />);
    const secretInput = screen.getByLabelText(/Client Secret/i);
    expect(secretInput).toHaveAttribute("type", "password");

    const toggleBtn = screen.getByRole("button", { name: /Show secret/i });
    fireEvent.click(toggleBtn);
    expect(secretInput).toHaveAttribute("type", "text");

    const hideBtn = screen.getByRole("button", { name: /Hide secret/i });
    fireEvent.click(hideBtn);
    expect(secretInput).toHaveAttribute("type", "password");
  });

  it("validates invalid GUIDs before submitting", async () => {
    render(<CloudLoginForm onSuccess={vi.fn()} />);

    fireEvent.change(screen.getByLabelText(/Azure Subscription ID/i), {
      target: { value: "invalid-uuid" },
    });
    fireEvent.change(screen.getByLabelText(/Azure Tenant ID/i), {
      target: { value: "11111111-1111-1111-1111-111111111111" },
    });
    fireEvent.change(screen.getByLabelText(/Client ID/i), {
      target: { value: "22222222-2222-2222-2222-222222222222" },
    });
    fireEvent.change(screen.getByLabelText(/Client Secret/i), {
      target: { value: "secret123" },
    });

    const submitBtn = screen.getByRole("button", { name: /Connect & Access FinOps Dashboard/i });
    fireEvent.click(submitBtn);

    expect(
      await screen.findByText(/Please enter a valid Azure Subscription ID/i)
    ).toBeInTheDocument();
  });

  it("submits valid credentials and triggers onSuccess without storing secrets", async () => {
    const onSuccess = vi.fn();
    const connectSpy = vi
      .spyOn(api, "connectServicePrincipal")
      .mockResolvedValue(validResponse);

    render(<CloudLoginForm onSuccess={onSuccess} />);

    fireEvent.change(screen.getByLabelText(/Azure Subscription ID/i), {
      target: { value: "22222222-2222-2222-2222-222222222222" },
    });
    fireEvent.change(screen.getByLabelText(/Azure Tenant ID/i), {
      target: { value: "11111111-1111-1111-1111-111111111111" },
    });
    fireEvent.change(screen.getByLabelText(/Client ID/i), {
      target: { value: "33333333-3333-3333-3333-333333333333" },
    });
    fireEvent.change(screen.getByLabelText(/Client Secret/i), {
      target: { value: "super-secure-secret-xyz" },
    });

    const submitBtn = screen.getByRole("button", { name: /Connect & Access FinOps Dashboard/i });
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    expect(connectSpy).toHaveBeenCalledWith({
      account_name: "Azure Enterprise Production",
      subscription_id: "22222222-2222-2222-2222-222222222222",
      tenant_id: "11111111-1111-1111-1111-111111111111",
      client_id: "33333333-3333-3333-3333-333333333333",
      client_secret: "super-secure-secret-xyz",
    });

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalledWith(validResponse);
    });

    // Zero-exposure verification
    expect(localStorage.getItem("super-secure-secret-xyz")).toBeNull();
    expect(sessionStorage.getItem("super-secure-secret-xyz")).toBeNull();
  });

  it("displays actionable error banner on authentication failure", async () => {
    vi.spyOn(api, "connectServicePrincipal").mockRejectedValue({
      status: 400,
      detail: {
        error_code: "INVALID_AZURE_CREDENTIALS",
        category: "invalid_client_secret",
        message: "The client secret is incorrect.",
        aadsts: "7000215",
      },
    });

    render(<CloudLoginForm onSuccess={vi.fn()} />);

    fireEvent.change(screen.getByLabelText(/Azure Subscription ID/i), {
      target: { value: "22222222-2222-2222-2222-222222222222" },
    });
    fireEvent.change(screen.getByLabelText(/Azure Tenant ID/i), {
      target: { value: "11111111-1111-1111-1111-111111111111" },
    });
    fireEvent.change(screen.getByLabelText(/Client ID/i), {
      target: { value: "33333333-3333-3333-3333-333333333333" },
    });
    fireEvent.change(screen.getByLabelText(/Client Secret/i), {
      target: { value: "bad-secret" },
    });

    const submitBtn = screen.getByRole("button", { name: /Connect & Access FinOps Dashboard/i });
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    expect(await screen.findByText(/The client secret is incorrect/i)).toBeInTheDocument();
    expect(screen.getByText(/AADSTS7000215/i)).toBeInTheDocument();
  });
});

