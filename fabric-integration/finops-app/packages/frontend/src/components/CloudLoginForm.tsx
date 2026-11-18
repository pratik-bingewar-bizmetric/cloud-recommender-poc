import React, { useState } from "react";
import {
  Eye,
  EyeOff,
  ShieldCheck,
  Cloud,
  AlertCircle,
  Loader2,
  KeyRound,
} from "lucide-react";
import { connectServicePrincipal } from "@/lib/api";
import type { ServicePrincipalConnectResponse } from "@/types/auth";

interface CloudLoginFormProps {
  onSuccess: (session: ServicePrincipalConnectResponse) => void;
  canSignIn?: boolean;
  onSignInWithMicrosoft?: () => Promise<void>;
  isSigningIn?: boolean;
  signInError?: Error | null;
  authError?: Error | null;
}

const GUID_REGEX =
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

export const CloudLoginForm: React.FC<CloudLoginFormProps> = ({
  onSuccess,
  canSignIn = false,
  onSignInWithMicrosoft,
  isSigningIn = false,
  signInError = null,
  authError = null,
}) => {
  const [accountName, setAccountName] = useState("Azure Enterprise Production");
  const [subscriptionId, setSubscriptionId] = useState("");
  const [tenantId, setTenantId] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [showSecret, setShowSecret] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [errorDetails, setErrorDetails] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setErrorDetails(null);

    // Validate inputs
    if (!accountName.trim()) {
      setErrorMessage("Please enter an Account Name.");
      return;
    }
    if (!subscriptionId.trim() || !GUID_REGEX.test(subscriptionId.trim())) {
      setErrorMessage("Please enter a valid Azure Subscription ID (GUID format).");
      return;
    }
    if (!tenantId.trim() || !GUID_REGEX.test(tenantId.trim())) {
      setErrorMessage("Please enter a valid Microsoft Entra Tenant ID (GUID format).");
      return;
    }
    if (!clientId.trim() || !GUID_REGEX.test(clientId.trim())) {
      setErrorMessage("Please enter a valid Azure Client ID / Application ID (GUID format).");
      return;
    }
    if (!clientSecret) {
      setErrorMessage("Please enter the Azure Service Principal Client Secret.");
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await connectServicePrincipal({
        account_name: accountName.trim(),
        subscription_id: subscriptionId.trim(),
        tenant_id: tenantId.trim(),
        client_id: clientId.trim(),
        client_secret: clientSecret,
      });

      // Clear password field immediately following Zero-Exposure policy
      setClientSecret("");
      onSuccess(response);
    } catch (err: unknown) {
      // Clear password field on error
      setClientSecret("");
      if (err && typeof err === "object" && "detail" in err) {
        const detail = (err as { detail?: { message?: string; error_code?: string; aadsts?: string } }).detail;
        setErrorMessage(detail?.message || "Failed to authenticate with Azure Service Principal.");
        if (detail?.aadsts) {
          setErrorDetails(`Microsoft Entra Error Code: AADSTS${detail.aadsts} (${detail.error_code || "AUTH_ERROR"})`);
        } else if (detail?.error_code) {
          setErrorDetails(`Error code: ${detail.error_code}`);
        }
      } else if (err instanceof Error) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage("An unexpected error occurred during authentication.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-4">
      <div className="w-full max-w-xl rounded-2xl border border-slate-200 bg-white p-8 shadow-xl">
        {/* Header */}
        <div className="text-center mb-6">
          <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-50 text-blue-600">
            <Cloud className="h-8 w-8 text-blue-600" />
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            Connect to FinOps Platform
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Authenticate directly using an Azure Service Principal with read-only access.
          </p>
        </div>

        {/* Security / Principle Banner */}
        <div className="mb-6 rounded-xl border border-blue-100 bg-blue-50/70 p-3.5 text-xs text-blue-800">
          <div className="flex items-start gap-2.5">
            <ShieldCheck className="h-4 w-4 text-blue-600 mt-0.5 shrink-0" />
            <div className="space-y-1">
              <p className="font-semibold text-blue-900">Zero-Execution & Human Approval Policy</p>
              <p className="text-blue-700 leading-relaxed">
                Credentials require only <strong>Reader</strong> permissions (and optionally{" "}
                <strong>Cost Management Reader</strong> / <strong>Monitoring Reader</strong>). The system never
                executes mutations or writes against your cloud subscription. Secrets are sent directly over HTTPS and
                never persisted.
              </p>
            </div>
          </div>
        </div>

        {/* Error Alert */}
        {errorMessage && (
          <div role="alert" className="mb-6 rounded-xl border border-red-200 bg-red-50 p-4 text-xs text-red-800">
            <div className="flex items-start gap-2.5">
              <AlertCircle className="h-4 w-4 text-red-600 mt-0.5 shrink-0" />
              <div>
                <p className="font-semibold text-red-900">{errorMessage}</p>
                {errorDetails && <p className="mt-1 font-mono text-[11px] text-red-700">{errorDetails}</p>}
              </div>
            </div>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <div>
            <label htmlFor="accountName" className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
              Account / Connection Name
            </label>
            <input
              id="accountName"
              type="text"
              required
              value={accountName}
              onChange={(e) => setAccountName(e.target.value)}
              disabled={isSubmitting}
              placeholder="e.g. Azure Enterprise Production"
              className="w-full rounded-lg border border-slate-300 px-3.5 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 disabled:bg-slate-100 transition"
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label htmlFor="subscriptionId" className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
                Azure Subscription ID
              </label>
              <input
                id="subscriptionId"
                type="text"
                required
                value={subscriptionId}
                onChange={(e) => setSubscriptionId(e.target.value)}
                disabled={isSubmitting}
                placeholder="00000000-0000-0000-0000-000000000000"
                className="w-full font-mono text-xs rounded-lg border border-slate-300 px-3.5 py-2.5 text-slate-900 placeholder-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 disabled:bg-slate-100 transition"
              />
            </div>

            <div>
              <label htmlFor="tenantId" className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
                Azure Tenant ID
              </label>
              <input
                id="tenantId"
                type="text"
                required
                value={tenantId}
                onChange={(e) => setTenantId(e.target.value)}
                disabled={isSubmitting}
                placeholder="00000000-0000-0000-0000-000000000000"
                className="w-full font-mono text-xs rounded-lg border border-slate-300 px-3.5 py-2.5 text-slate-900 placeholder-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 disabled:bg-slate-100 transition"
              />
            </div>
          </div>

          <div>
            <label htmlFor="clientId" className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
              Client ID (Application ID)
            </label>
            <input
              id="clientId"
              type="text"
              required
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              disabled={isSubmitting}
              placeholder="00000000-0000-0000-0000-000000000000"
              className="w-full font-mono text-xs rounded-lg border border-slate-300 px-3.5 py-2.5 text-slate-900 placeholder-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 disabled:bg-slate-100 transition"
            />
          </div>

          <div>
            <label htmlFor="clientSecret" className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
              Client Secret
            </label>
            <div className="relative">
              <input
                id="clientSecret"
                type={showSecret ? "text" : "password"}
                required
                value={clientSecret}
                onChange={(e) => setClientSecret(e.target.value)}
                disabled={isSubmitting}
                autoComplete="off"
                placeholder="Enter client secret value"
                className="w-full rounded-lg border border-slate-300 pl-3.5 pr-10 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 disabled:bg-slate-100 transition"
              />
              <button
                type="button"
                aria-label={showSecret ? "Hide secret" : "Show secret"}
                onClick={() => setShowSecret(!showSecret)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition"
              >
                {showSecret ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            <p className="mt-1 text-[11px] text-slate-400">
              The client secret is never saved to disk or browser storage and is masked by default.
            </p>
          </div>

          <div className="pt-2">
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full inline-flex items-center justify-center gap-2 rounded-xl bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white py-3 px-4 text-sm font-semibold shadow-md transition disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>Validating Credentials & Subscriptions…</span>
                </>
              ) : (
                <>
                  <KeyRound className="h-4 w-4" />
                  <span>Connect & Access FinOps Dashboard</span>
                </>
              )}
            </button>
          </div>
        </form>

        {/* Secondary sign-in option if configured in host */}
        {canSignIn && onSignInWithMicrosoft && (
          <div className="mt-6 pt-4 border-t border-slate-100">
            <button
              type="button"
              onClick={() => void onSignInWithMicrosoft()}
              disabled={isSigningIn}
              className="w-full rounded-xl border border-slate-200 bg-slate-50 py-2.5 px-4 text-xs font-semibold text-slate-700 hover:bg-slate-100 transition"
            >
              {isSigningIn
                ? "Signing in…"
                : authError
                ? "Try Sign in with Microsoft"
                : "Sign in with Microsoft"}
            </button>
            {signInError && (
              <p role="alert" className="mt-2 text-xs text-red-600 text-center">
                {signInError.message}
              </p>
            )}
          </div>
        )}

        {/* Footer info */}
        <div className="mt-6 border-t border-slate-100 pt-4 text-center">
          <p className="text-[11px] text-slate-400">
            FinOps Multi-Cloud Recommender Platform &bull; Read-Only Architecture Discovery
          </p>
        </div>
      </div>
    </div>
  );
};
