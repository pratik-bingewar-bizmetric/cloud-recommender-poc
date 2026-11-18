import { useState, type FormEvent } from "react";

import type { AzureCredentials } from "@/types/azureLive";

interface Props {
  busy: boolean;
  connected: boolean;
  onConnect: (credentials: AzureCredentials) => void;
  onValidate: () => void;
  onFetchSubscriptions: () => void;
  onDisconnect: () => void;
}

const GUID = /^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$/;

/**
 * Service principal form. The secret lives in this component's state only (memory); it is never
 * written to browser storage or a URL, and it is cleared from the field once connected.
 */
export function AzureConnectionForm({
  busy,
  connected,
  onConnect,
  onValidate,
  onFetchSubscriptions,
  onDisconnect,
}: Props) {
  const [tenantId, setTenantId] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [subscriptionId, setSubscriptionId] = useState("");
  const [touched, setTouched] = useState(false);

  const problems: string[] = [];
  if (!GUID.test(tenantId.trim())) problems.push("Tenant ID must be a GUID.");
  if (!GUID.test(clientId.trim())) problems.push("Client ID must be a GUID.");
  if (!clientSecret) problems.push("Client secret is required.");
  if (subscriptionId.trim() && !GUID.test(subscriptionId.trim())) {
    problems.push("Subscription ID must be a GUID when provided.");
  }

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setTouched(true);
    if (problems.length > 0) return;
    onConnect({
      tenantId: tenantId.trim(),
      clientId: clientId.trim(),
      clientSecret,
      subscriptionId: subscriptionId.trim() || undefined,
    });
    setClientSecret(""); // the field never keeps the secret after submit
  };

  const field = "w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-brand-500";

  return (
    <form
      onSubmit={submit}
      aria-label="Azure service principal connection"
      className="rounded-xl border border-slate-200 bg-white p-4 space-y-3"
    >
      <div>
        <h2 className="text-sm font-bold text-navy-900">Connect your Azure account</h2>
        <p className="text-xs text-slate-600">
          Enter a service principal with <strong>Reader</strong> (and optionally{" "}
          <strong>Cost Management Reader</strong> / <strong>Monitoring Reader</strong>) on your
          subscription. Data is fetched with <em>your</em> credentials. The secret is sent once over
          HTTPS, is never stored by the backend, and is kept only in this page&apos;s memory.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="space-y-1 text-xs font-medium text-navy-800">
          Tenant ID
          <input
            className={field}
            value={tenantId}
            onChange={(e) => setTenantId(e.target.value)}
            autoComplete="off"
            spellCheck={false}
            disabled={connected}
            placeholder="00000000-0000-0000-0000-000000000000"
          />
        </label>
        <label className="space-y-1 text-xs font-medium text-navy-800">
          Client ID
          <input
            className={field}
            value={clientId}
            onChange={(e) => setClientId(e.target.value)}
            autoComplete="off"
            spellCheck={false}
            disabled={connected}
            placeholder="00000000-0000-0000-0000-000000000000"
          />
        </label>
        <label className="space-y-1 text-xs font-medium text-navy-800">
          Client secret
          <input
            className={field}
            type="password"
            value={clientSecret}
            onChange={(e) => setClientSecret(e.target.value)}
            autoComplete="off"
            spellCheck={false}
            disabled={connected}
            placeholder="••••••••••••"
          />
        </label>
        <label className="space-y-1 text-xs font-medium text-navy-800">
          Subscription ID <span className="text-slate-400">(optional)</span>
          <input
            className={field}
            value={subscriptionId}
            onChange={(e) => setSubscriptionId(e.target.value)}
            autoComplete="off"
            spellCheck={false}
            disabled={connected}
            placeholder="Verify access to a specific subscription"
          />
        </label>
      </div>

      {touched && problems.length > 0 && (
        <ul className="text-xs text-red-700 list-disc pl-4" role="alert">
          {problems.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap gap-2">
        <button
          type="submit"
          disabled={busy || connected}
          className="rounded-md bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
        >
          {busy ? "Connecting…" : "Connect Azure"}
        </button>
        <button
          type="button"
          onClick={onValidate}
          disabled={!connected || busy}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-semibold text-navy-800 disabled:opacity-50"
        >
          Validate Connection
        </button>
        <button
          type="button"
          onClick={onFetchSubscriptions}
          disabled={!connected || busy}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-semibold text-navy-800 disabled:opacity-50"
        >
          Fetch Subscriptions
        </button>
        <button
          type="button"
          onClick={() => {
            onDisconnect();
            setClientSecret("");
          }}
          disabled={!connected}
          className="rounded-md border border-red-200 px-3 py-1.5 text-xs font-semibold text-red-700 disabled:opacity-50"
        >
          Disconnect
        </button>
      </div>
    </form>
  );
}
