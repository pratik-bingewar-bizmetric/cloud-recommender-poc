import type {
  FinOpsKpiMetric,
  FinOpsProvenanceMap,
  FinOpsSectionProvenance,
  KpiAvailabilityStatus,
} from "@/types";

/** Statuses whose numeric value is real data (LIVE/CALCULATED) or an explicit projection (ESTIMATED). */
const VALUE_STATUSES: ReadonlySet<KpiAvailabilityStatus> = new Set<KpiAvailabilityStatus>([
  "LIVE",
  "CALCULATED",
  "ESTIMATED",
  "AVAILABLE",
  "BASELINE",
  "PARTIAL",
]);

const STATUS_LABELS: Partial<Record<KpiAvailabilityStatus, string>> = {
  LIVE: "LIVE",
  CALCULATED: "CALCULATED",
  ESTIMATED: "ESTIMATED",
  NO_DATA: "NO DATA",
  UNAVAILABLE: "UNAVAILABLE",
  SOURCE_UNAVAILABLE: "UNAVAILABLE",
  BLOCKED_PENDING_APPROVAL: "BLOCKED",
  STOPPED_WAREHOUSE: "BLOCKED",
  NOT_AUTHORIZED: "PERMISSION REQUIRED",
  PERMISSION_DENIED: "PERMISSION REQUIRED",
  INSUFFICIENT_HISTORY: "INSUFFICIENT HISTORY",
  NOT_ATTRIBUTABLE: "NOT ATTRIBUTABLE",
};

export const statusLabel = (status: KpiAvailabilityStatus | string): string =>
  STATUS_LABELS[status as KpiAvailabilityStatus] ?? String(status).replace(/_/g, " ");

export const statusBadgeClass = (status: KpiAvailabilityStatus | string): string => {
  switch (status) {
    case "LIVE":
      return "bg-emerald-100 text-emerald-800 border border-emerald-300";
    case "CALCULATED":
    case "AVAILABLE":
      return "bg-blue-100 text-blue-800 border border-blue-200";
    case "ESTIMATED":
    case "BASELINE":
      return "bg-purple-100 text-purple-800 border border-purple-200";
    case "BLOCKED_PENDING_APPROVAL":
    case "STOPPED_WAREHOUSE":
    case "NOT_AUTHORIZED":
    case "PERMISSION_DENIED":
      return "bg-amber-100 text-amber-800 border border-amber-300";
    case "INSUFFICIENT_HISTORY":
      return "bg-orange-100 text-orange-800 border border-orange-200";
    case "NO_DATA":
    case "NO_DATA_AVAILABLE":
      return "bg-slate-100 text-slate-600 border border-slate-300";
    default:
      return "bg-slate-100 text-slate-700 border border-slate-200";
  }
};

/** True only when a KPI carries a real numeric value that may be rendered as a figure. */
export const hasRealValue = (metric: FinOpsKpiMetric | null | undefined): boolean =>
  !!metric && metric.value !== null && VALUE_STATUSES.has(metric.status);

/**
 * Display text for a KPI. Never fabricates a number: a missing value renders the backend's
 * provenance text ("Awaiting billing data", "Insufficient history", ...) instead of "$0".
 */
export const kpiDisplay = (
  metric: FinOpsKpiMetric | null | undefined,
  opts: { loading?: boolean; error?: boolean } = {}
): string => {
  if (!metric) return opts.error ? "-" : opts.loading ? "…" : "-";
  // `-` means "could not be established"; the reason is shown in the card tooltip.
  if (metric.value === null) return "-";
  return metric.formatted_value;
};

/** Format a nullable money amount; null means unknown, never zero. */
export const fmtMoney = (value: number | null | undefined, format?: (n: number) => string): string =>
  value === null || value === undefined
    ? "-"
    : format
    ? format(value)
    : `$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;

export const fmtNumber = (value: number | null | undefined, suffix = ""): string =>
  value === null || value === undefined ? "-" : `${value.toLocaleString()}${suffix}`;

/** Sections that are not backed by live or calculated data (banner candidates). */
export const unresolvedSections = (
  provenance: FinOpsProvenanceMap | null | undefined
): Array<[string, FinOpsSectionProvenance]> =>
  Object.entries(provenance ?? {}).filter(
    ([, p]) => p.classification !== "LIVE" && p.classification !== "CALCULATED"
  );

/** Convert a validated YYYY-MM-DD date input to epoch ms (start/end of day, UTC). */
export const dateInputToMs = (value: string, endOfDay = false): number | null => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const ms = Date.parse(`${value}T${endOfDay ? "23:59:59.999" : "00:00:00.000"}Z`);
  return Number.isNaN(ms) ? null : ms;
};
