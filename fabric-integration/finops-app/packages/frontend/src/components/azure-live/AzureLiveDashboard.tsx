import { useMemo, useState } from "react";

import type {
  AzureConnectionInfo,
  AzureResource,
  CostSummary,
  DataDomain,
  MetricDefinition,
  MetricSeries,
  OverviewResponse,
} from "@/types/azureLive";
import { DataDomainNotice, StateBadge } from "./DataDomainNotice";

interface Props {
  connection: AzureConnectionInfo;
  subscriptions: OverviewResponse["subscriptions"] | null;
  selectedSubscriptionId: string | null;
  overview: OverviewResponse | null;
  loading: boolean;
  validation: { valid: boolean; checkedAt: string } | null;
  selectedResource: AzureResource | null;
  metricDefinitions: DataDomain<MetricDefinition> | null;
  metricValues: DataDomain<MetricSeries> | null;
  onSelectSubscription: (id: string) => void;
  onRefresh: () => void;
  onSelectResource: (resource: AzureResource | null) => void;
  onLoadMetricValues: (names: string[]) => void;
}

/** Count tile: shows "—" (never 0) when the data could not be read. */
function Tile({ label, domain, value }: { label: string; domain: DataDomain<unknown> | null; value: number | null }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3" data-testid={`tile-${label}`}>
      <div className="text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-bold text-navy-900">{value === null ? "—" : value}</div>
      {domain && <StateBadge state={domain.state} />}
    </div>
  );
}

function money(total: number | null, currency: string | null): string {
  if (total === null) return "—";
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency: currency ?? "USD" }).format(total);
  } catch {
    return `${total.toFixed(2)} ${currency ?? ""}`.trim();
  }
}

export function AzureLiveDashboard({
  connection,
  subscriptions,
  selectedSubscriptionId,
  overview,
  loading,
  validation,
  selectedResource,
  metricDefinitions,
  metricValues,
  onSelectSubscription,
  onRefresh,
  onSelectResource,
  onLoadMetricValues,
}: Props) {
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [chosenMetrics, setChosenMetrics] = useState<string[]>([]);

  const visibleResources = useMemo(
    () =>
      (overview?.resources.items ?? [])
        .filter((r) => !typeFilter || r.type.toLowerCase() === typeFilter.toLowerCase())
        .slice(0, 200),
    [overview, typeFilter],
  );
  const costSummary: CostSummary | undefined = overview?.cost.items?.[0];
  const maxType = Math.max(1, ...(overview?.type_breakdown.map((t) => t.count) ?? [1]));

  return (
    <div className="space-y-4" data-testid="azure-live-dashboard">
      {/* Connection */}
      <section className="rounded-xl border border-emerald-200 bg-emerald-50/40 p-4 space-y-2" aria-label="Connection status">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded bg-emerald-600 px-2 py-0.5 text-[10px] font-bold uppercase text-white">Connected</span>
          <span className="text-xs text-navy-900">
            Tenant <code>{connection.tenant_id}</code> · Client <code>{connection.client_id}</code>
          </span>
          <button
            type="button"
            onClick={onRefresh}
            disabled={loading || !selectedSubscriptionId}
            className="ml-auto rounded-md border border-slate-300 bg-white px-3 py-1 text-xs font-semibold text-navy-800 disabled:opacity-50"
          >
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
        <p className="text-xs text-slate-700" data-testid="identity-note">
          All data below is read from the Azure account of this service principal using its own
          credentials. It is not read through a shared server identity or an Azure CLI session.
          Session expires {new Date(connection.expires_at).toLocaleTimeString()}.
        </p>
        {validation && (
          <p className="text-xs" role="status">
            Last validation: <strong>{validation.valid ? "credentials accepted by Azure" : "failed"}</strong> at{" "}
            {new Date(validation.checkedAt).toLocaleTimeString()}
          </p>
        )}
      </section>

      {/* Summary tiles */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile label="Subscriptions" domain={subscriptions} value={subscriptions?.count ?? null} />
        <Tile label="Resource groups" domain={overview?.resource_groups ?? null} value={overview?.resource_groups.count ?? null} />
        <Tile label="Resources" domain={overview?.resources ?? null} value={overview?.resources.count ?? null} />
        <Tile
          label="Resource types"
          domain={overview?.resources ?? null}
          value={overview && overview.resources.items ? overview.type_breakdown.length : null}
        />
      </div>

      {/* Subscriptions */}
      <section className="rounded-xl border border-slate-200 bg-white p-4 space-y-2" aria-label="Subscriptions">
        <DataDomainNotice domain={subscriptions} title="Subscriptions" />
        <ul className="divide-y divide-slate-100">
          {(subscriptions?.items ?? []).map((s) => (
            <li key={s.subscription_id}>
              <button
                type="button"
                onClick={() => onSelectSubscription(s.subscription_id)}
                aria-pressed={s.subscription_id === selectedSubscriptionId}
                className={`flex w-full items-center justify-between px-2 py-1.5 text-left text-xs ${
                  s.subscription_id === selectedSubscriptionId ? "bg-brand-50 font-semibold" : "hover:bg-slate-50"
                }`}
              >
                <span>
                  {s.display_name} <code className="text-slate-500">{s.subscription_id}</code>
                </span>
                <span className="text-slate-500">{s.state}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      {overview && (
        <>
          {/* Cost */}
          <section className="rounded-xl border border-slate-200 bg-white p-4 space-y-2" aria-label="Cost">
            <DataDomainNotice domain={overview.cost} title="Cost (month to date, actual)" />
            {costSummary && (
              <div>
                <div className="text-2xl font-bold text-navy-900" data-testid="cost-total">
                  {money(costSummary.total, costSummary.currency)}
                </div>
                <table className="mt-2 w-full text-xs">
                  <tbody>
                    {costSummary.by_service.slice(0, 10).map((row) => (
                      <tr key={`${row.service}-${row.currency}`} className="border-t border-slate-100">
                        <td className="py-1">{row.service ?? "Unknown"}</td>
                        <td className="py-1 text-right">{money(row.cost, row.currency)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* Resource groups */}
          <section className="rounded-xl border border-slate-200 bg-white p-4 space-y-2" aria-label="Resource groups">
            <DataDomainNotice domain={overview.resource_groups} title="Resource groups" />
            <ul className="grid gap-1 sm:grid-cols-2 text-xs">
              {(overview.resource_groups.items ?? []).map((g) => (
                <li key={g.id} className="rounded border border-slate-100 px-2 py-1">
                  <strong>{g.name}</strong> · {g.location}
                </li>
              ))}
            </ul>
          </section>

          {/* Inventory */}
          <section className="rounded-xl border border-slate-200 bg-white p-4 space-y-3" aria-label="Resource inventory">
            <DataDomainNotice domain={overview.resources} title="Resource inventory" />
            {overview.type_breakdown.length > 0 && (
              <div className="space-y-1" aria-label="Resource type breakdown">
                {overview.type_breakdown.map((t) => (
                  <button
                    key={t.resource_type}
                    type="button"
                    onClick={() => setTypeFilter(typeFilter === t.resource_type ? null : t.resource_type)}
                    className="flex w-full items-center gap-2 text-left text-xs"
                  >
                    <span className="w-64 truncate">{t.resource_type}</span>
                    <span className="h-2 rounded bg-brand-500" style={{ width: `${(t.count / maxType) * 100}%`, minWidth: 4 }} />
                    <span className="font-semibold">{t.count}</span>
                  </button>
                ))}
              </div>
            )}
            {visibleResources.length > 0 && (
              <div className="max-h-80 overflow-auto">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-slate-50 text-left">
                    <tr>
                      <th className="p-1.5">Name</th>
                      <th className="p-1.5">Type</th>
                      <th className="p-1.5">Resource group</th>
                      <th className="p-1.5">Location</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleResources.map((r) => (
                      <tr
                        key={r.id}
                        onClick={() => {
                          setChosenMetrics([]);
                          onSelectResource(r);
                        }}
                        className={`cursor-pointer border-t border-slate-100 hover:bg-slate-50 ${
                          selectedResource?.id === r.id ? "bg-brand-50" : ""
                        }`}
                      >
                        <td className="p-1.5 font-medium">{r.name}</td>
                        <td className="p-1.5">{r.type}</td>
                        <td className="p-1.5">{r.resource_group}</td>
                        <td className="p-1.5">{r.location}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* Monitoring */}
          {selectedResource && (
            <section className="rounded-xl border border-slate-200 bg-white p-4 space-y-2" aria-label="Monitoring metrics">
              <h3 className="text-sm font-semibold text-navy-900">Azure Monitor metrics: {selectedResource.name}</h3>
              <DataDomainNotice domain={metricDefinitions} title="Available metrics" />
              <div className="flex flex-wrap gap-2">
                {(metricDefinitions?.items ?? []).map((m) => (
                  <label key={m.name} className="flex items-center gap-1 text-xs">
                    <input
                      type="checkbox"
                      checked={chosenMetrics.includes(m.name)}
                      onChange={(e) =>
                        setChosenMetrics((prev) => (e.target.checked ? [...prev, m.name] : prev.filter((n) => n !== m.name)))
                      }
                    />
                    {m.display_name ?? m.name} {m.unit && <span className="text-slate-400">({m.unit})</span>}
                  </label>
                ))}
              </div>
              {chosenMetrics.length > 0 && (
                <button
                  type="button"
                  onClick={() => onLoadMetricValues(chosenMetrics.slice(0, 20))}
                  className="rounded-md border border-slate-300 px-3 py-1 text-xs font-semibold text-navy-800"
                >
                  Fetch last 24 hours
                </button>
              )}
              <DataDomainNotice domain={metricValues} title="Metric values" />
              {(metricValues?.items ?? []).map((series) => {
                const values = series.points.map((p) => p.value);
                return (
                  <div key={series.name} className="text-xs">
                    <strong>{series.display_name ?? series.name}</strong> ({series.aggregation}
                    {series.unit ? `, ${series.unit}` : ""}):{" "}
                    {values.length === 0
                      ? "no datapoints reported"
                      : `${values.length} points, min ${Math.min(...values)}, max ${Math.max(...values)}, latest ${values[values.length - 1]}`}
                  </div>
                );
              })}
            </section>
          )}
        </>
      )}
    </div>
  );
}
