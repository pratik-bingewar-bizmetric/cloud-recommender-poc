import type { DataAccessState, DataDomain } from "@/types/azureLive";

const STATE_STYLE: Record<DataAccessState, { label: string; className: string }> = {
  accessible: { label: "Accessible", className: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  permission_denied: { label: "Permission denied", className: "bg-red-50 text-red-700 border-red-200" },
  unavailable: { label: "Unavailable", className: "bg-amber-50 text-amber-800 border-amber-200" },
  empty: { label: "Empty", className: "bg-slate-50 text-slate-700 border-slate-200" },
  error: { label: "Error", className: "bg-red-50 text-red-700 border-red-200" },
};

export function StateBadge({ state }: { state: DataAccessState }) {
  const style = STATE_STYLE[state];
  return (
    <span
      data-testid={`state-${state}`}
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${style.className}`}
    >
      {style.label}
    </span>
  );
}

/** Where a dataset came from: connection, subscription, API and time. */
export function SourceLine({ domain }: { domain: DataDomain<unknown> }) {
  const { source } = domain;
  return (
    <p className="text-[11px] text-slate-500" data-testid="source-line">
      Source: connection <code>{source.connection_id.slice(0, 8)}…</code> (client{" "}
      <code>{source.client_id.slice(0, 8)}…</code>)
      {source.subscription_id && (
        <>
          {" "}
          · subscription <code>{source.subscription_id}</code>
        </>
      )}{" "}
      · {source.api} · {new Date(source.fetched_at).toLocaleTimeString()}
    </p>
  );
}

/** State badge plus a meaningful explanation. Renders nothing extra for healthy data. */
export function DataDomainNotice({
  domain,
  title,
}: {
  domain: DataDomain<unknown> | null;
  title: string;
}) {
  if (!domain) return null;
  const needsExplanation = domain.state !== "accessible";
  return (
    <div className="space-y-1" data-testid={`domain-${domain.domain}`}>
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold text-navy-900">{title}</h3>
        <StateBadge state={domain.state} />
        {domain.truncated && (
          <span className="text-[10px] font-semibold text-amber-700">Showing first results only</span>
        )}
      </div>
      {needsExplanation && domain.message && (
        <p className="text-xs text-slate-700" role="status">
          {domain.message}
          {domain.required_permission && (
            <>
              {" "}
              Required role: <strong>{domain.required_permission}</strong>.
            </>
          )}
          {domain.azure_error_code && <span className="text-slate-500"> (Azure: {domain.azure_error_code})</span>}
        </p>
      )}
      <SourceLine domain={domain} />
    </div>
  );
}
