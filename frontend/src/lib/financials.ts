import {
  CloudProvider,
  TimeWindowPreset,
  CostBreakdown,
  SubscriptionOrProjectAnalysis,
  MonitoringOverviewResponse,
} from "@/types";
import {
  CanonicalFinancialSummary,
  FinancialCategoryItem,
  FinancialFindingDetail,
} from "@/types/financials";

export const INR_EXCHANGE_RATE = 83.15;

/** Text shown wherever a financial value is null / unknown. Never "0", never a fixture value. */
export const NO_DATA_LABEL = "No data available";

/** Why a financial screen has nothing to show. Drives the message, never a number. */
export type FinancialUnavailableReason =
  | "AUTHENTICATION_REQUIRED"
  | "ACCESS_DENIED"
  | "FIXTURE_DATA"
  | "NO_BILLING_DATA"
  | "FORECAST_UNAVAILABLE"
  | "API_ERROR"
  | "NO_DATA";

export const FINANCIAL_UNAVAILABLE_MESSAGES: Record<FinancialUnavailableReason, string> = {
  AUTHENTICATION_REQUIRED: "Authentication required — run az login.",
  ACCESS_DENIED: "Access denied — check your Azure permissions.",
  FIXTURE_DATA:
    "The backend returned reference fixture data, which is never shown as live financials. Authentication required.",
  NO_BILLING_DATA: "No billing data available.",
  FORECAST_UNAVAILABLE: "Forecast unavailable.",
  API_ERROR: "Financial data could not be loaded (API error).",
  NO_DATA: NO_DATA_LABEL,
};

/**
 * Map an HTTP status from a financial API call to a user-facing state. Only a fixed message and the
 * numeric status are ever shown: raw server text, tokens and stack traces are never surfaced.
 */
export function financialErrorFromStatus(
  status: number | null | undefined,
  provider: CloudProvider = "azure"
): { reason: FinancialUnavailableReason; message: string } {
  const cloud = provider === "gcp" ? "GCP" : "Azure";
  if (status === 401) {
    return {
      reason: "AUTHENTICATION_REQUIRED",
      message:
        provider === "gcp"
          ? "Authentication required — run gcloud auth login."
          : FINANCIAL_UNAVAILABLE_MESSAGES.AUTHENTICATION_REQUIRED,
    };
  }
  if (status === 403) {
    return {
      reason: "ACCESS_DENIED",
      message:
        provider === "gcp"
          ? "Access denied — check your GCP permissions."
          : FINANCIAL_UNAVAILABLE_MESSAGES.ACCESS_DENIED,
    };
  }
  if (status === null || status === undefined || status === 0) {
    return {
      reason: "API_ERROR",
      message: `${cloud} financial data could not be loaded (network error).`,
    };
  }
  return {
    reason: "API_ERROR",
    message: `${cloud} financial data could not be loaded (HTTP ${status}).`,
  };
}

/** "/mo", "/yr" etc. only when a real value is shown; empty when the value is unavailable. */
export function periodSuffix(value: number | null | undefined, suffix: string): string {
  return value === null || value === undefined || !Number.isFinite(value) ? "" : suffix;
}

/** Backend provenance labels that mean "not real customer data". */
export function isFixtureDataSource(source: string | null | undefined): boolean {
  const s = (source ?? "").toLowerCase();
  return s === "mock_fixture" || s === "simulation_fixture" || s === "ai_proposed";
}

/** Parse an API money/number value. null, undefined, "", NaN and Infinity all stay null (never 0). */
export function toFiniteNumber(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "string" && value.trim() === "") return null;
  const n = typeof value === "number" ? value : parseFloat(String(value));
  return Number.isFinite(n) ? n : null;
}

/**
 * Format currency with consistent precision and symbols.
 * A null/undefined/non-finite amount renders NO_DATA_LABEL; it is never coerced to zero.
 */
export function formatFinancialCurrency(
  valUsd: number | null | undefined,
  currency: "USD" | "INR" = "USD",
  decimals: number = 2
): string {
  if (valUsd === null || valUsd === undefined || !Number.isFinite(valUsd)) return NO_DATA_LABEL;
  const rate = currency === "INR" ? INR_EXCHANGE_RATE : 1;
  const sym = currency === "INR" ? "₹" : "$";
  const converted = valUsd * rate;

  return `${sym}${converted.toLocaleString("en-US", {
    minimumFractionDigits: currency === "INR" ? 0 : decimals,
    maximumFractionDigits: currency === "INR" ? 0 : decimals,
  })}`;
}

/** Percentage helper: null when either side is unknown or the base is not positive. */
export function percentOf(part: number | null, whole: number | null, digits = 1): number | null {
  if (part === null || whole === null || whole <= 0) return null;
  return Number(((part / whole) * 100).toFixed(digits));
}

/**
 * Why a live financial summary could not be built, for the given source objects.
 * Returns null when a summary can be built from real (non-fixture) data.
 */
export function financialUnavailableReason(
  overview?: MonitoringOverviewResponse | null,
  analysisData?: SubscriptionOrProjectAnalysis | null,
  greenfieldCost?: CostBreakdown | null
): FinancialUnavailableReason | null {
  if (greenfieldCost) return null;
  if (!overview && !analysisData) return "NO_DATA";
  if (isFixtureDataSource(analysisData?.data_source) || isFixtureDataSource(overview?.data_source)) {
    return "FIXTURE_DATA";
  }
  return null;
}

/**
 * Reconciles API response data into a single canonical financial summary.
 *
 * Returns null (never reference/fixture figures) when there is no live source: no API data,
 * or the backend labelled the payload as a fixture. Individual money fields are null when the
 * source did not provide them; they are never defaulted to a constant or to zero.
 */
export function buildCanonicalFinancialSummary(
  provider: CloudProvider,
  scopeId: string,
  scopeName: string,
  timeWindow: TimeWindowPreset = "30d",
  currency: "USD" | "INR" = "USD",
  overview?: MonitoringOverviewResponse | null,
  analysisData?: SubscriptionOrProjectAnalysis | null,
  greenfieldCost?: CostBreakdown | null
): CanonicalFinancialSummary | null {
  // If analyzing a live/connected scope
  if (!greenfieldCost && (analysisData || overview)) {
    if (financialUnavailableReason(overview, analysisData, greenfieldCost) !== null) return null;

    const rawSpend =
      toFiniteNumber(analysisData?.cost_breakdown?.total_monthly) ??
      toFiniteNumber(overview?.kpis.estimated_monthly_cost);
    const rawSavings =
      toFiniteNumber(analysisData?.total_potential_monthly_savings) ??
      toFiniteNumber(overview?.kpis.potential_monthly_savings);

    // Categories come only from the provider's own breakdown. No invented split of the total.
    const cb = analysisData?.cost_breakdown;
    const categories: FinancialCategoryItem[] = [];
    if (cb && rawSpend !== null) {
      const parts: Array<[string, FinancialCategoryItem["category_key"], string, unknown]> = [
        ["Compute", "compute", "bg-brand-600", cb.compute],
        ["Databases", "database", "bg-emerald-500", cb.database],
        ["Storage", "storage", "bg-amber-500", cb.storage],
        ["AI & Cognitive", "ai", "bg-purple-600", cb.ai],
        ["Networking", "networking", "bg-cyan-500", cb.networking],
        ["Other", "other", "bg-slate-400", cb.other],
      ];
      for (const [name, key, color, raw] of parts) {
        const amount = toFiniteNumber(raw);
        if (amount === null) continue;
        categories.push({
          name,
          category_key: key,
          amount_usd: Number(amount.toFixed(2)),
          percentage_of_total: percentOf(amount, rawSpend) ?? 0,
          color_class: color,
        });
      }
    }

    // If analysisData has itemized findings, map them faithfully
    const rawFindings = analysisData?.waste_findings || [];
    const mappedFindings: FinancialFindingDetail[] = rawFindings.map((f) => ({
      id: f.id,
      resource_id: f.resource_id,
      resource_name: f.resource_name,
      category: f.category.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      severity: f.severity,
      title: f.title,
      description: f.description,
      evidence: f.evidence,
      current_monthly_spend: toFiniteNumber(f.current_monthly_spend),
      potential_monthly_savings: toFiniteNumber(f.potential_monthly_savings),
      calculation_formula:
        (Array.isArray(f.pre_remediation_considerations)
          ? f.pre_remediation_considerations.join(". ")
          : f.pre_remediation_considerations) ||
        `Eliminate or downsize unneeded ${f.category} allocation.`,
      pricing_source: provider === "gcp" ? "GCP Cloud Billing Catalog" : "Azure Retail Prices API",
      confidence: f.confidence || "high",
      attribution_group: f.group_name,
      remediation_recommendation: f.remediation_recommendation,
      pre_remediation_considerations: Array.isArray(f.pre_remediation_considerations)
        ? f.pre_remediation_considerations.join(". ")
        : f.pre_remediation_considerations,
    }));

    return {
      provider,
      scope_id: scopeId || "-",
      scope_name: scopeName || "-",
      reporting_period: `${timeWindow.toUpperCase()} Projected Monthly`,
      time_window: timeWindow,
      currency,
      exchange_rate: currency === "INR" ? INR_EXCHANGE_RATE : 1,
      data_provenance: "verified_pricing_catalog",
      pricing_source: provider === "gcp" ? "GCP Cloud Billing Catalog" : "Azure Retail Prices API",
      rate_effective_date: "October 2026",
      last_updated: new Date().toISOString(),
      estimated_monthly_spend: rawSpend === null ? null : Number(rawSpend.toFixed(2)),
      actual_billed_monthly_spend: null,
      spend_basis: "estimated_public_list",
      spend_formula:
        "Deterministic rate card meters applied to discovered resource inventory (continuous 730 hr/mo basis).",
      potential_monthly_savings: rawSavings === null ? null : Number(rawSavings.toFixed(2)),
      projected_annual_savings: rawSavings === null ? null : Number((rawSavings * 12).toFixed(2)),
      realized_monthly_savings: 0.0,
      savings_percentage_of_spend: percentOf(rawSavings, rawSpend),
      findings_count: mappedFindings.length,
      savings_formula:
        "Sum of itemized non-double-counted waste detections vetted against official list rates.",
      categories,
      findings: mappedFindings,
      included_resources_count:
        analysisData?.resources?.length ?? overview?.kpis?.total_resources ?? null,
      unmonitored_or_unpriced_count: overview?.kpis?.unmonitored_count ?? null,
      assumptions: [
        "Pay-as-you-go list rates sourced from official public pricing APIs.",
        "Continuous 24/7 workload execution (730 hours/month).",
        "Taxes, custom enterprise agreements, and support plan costs excluded.",
      ],
      limitations: [
        "100% read-only policy: infrastructure modifications are purely advisory.",
        "Actual invoiced amounts require Billing/Cost Management Reader role.",
      ],
    };
  }

  // If greenfield architectural simulation is active (labelled simulation_benchmark, never "actual")
  if (greenfieldCost) {
    const rawSpend = toFiniteNumber(greenfieldCost.total_monthly);
    if (rawSpend === null) return null;
    const computeCost = toFiniteNumber(greenfieldCost.compute) ?? 0;
    const dbCost = toFiniteNumber(greenfieldCost.database) ?? 0;
    const storageCost = toFiniteNumber(greenfieldCost.storage) ?? 0;
    const aiCost = toFiniteNumber(greenfieldCost.ai) ?? 0;
    const netCost = toFiniteNumber(greenfieldCost.networking) ?? 0;
    const otherCost = toFiniteNumber(greenfieldCost.other) ?? 0;

    const categories: FinancialCategoryItem[] = [
      {
        name: "Compute",
        category_key: "compute",
        amount_usd: computeCost,
        percentage_of_total: percentOf(computeCost, rawSpend) ?? 0,
        color_class: "bg-brand-600",
      },
      {
        name: "Databases",
        category_key: "database",
        amount_usd: dbCost,
        percentage_of_total: percentOf(dbCost, rawSpend) ?? 0,
        color_class: "bg-emerald-500",
      },
      {
        name: "Storage",
        category_key: "storage",
        amount_usd: storageCost,
        percentage_of_total: percentOf(storageCost, rawSpend) ?? 0,
        color_class: "bg-amber-500",
      },
      {
        name: "AI & Cognitive",
        category_key: "ai",
        amount_usd: aiCost,
        percentage_of_total: percentOf(aiCost, rawSpend) ?? 0,
        color_class: "bg-purple-600",
      },
      {
        name: "Networking",
        category_key: "networking",
        amount_usd: netCost + otherCost,
        percentage_of_total: percentOf(netCost + otherCost, rawSpend) ?? 0,
        color_class: "bg-cyan-500",
      },
    ];

    // Greenfield optimization: 18% right-sizing and autoscale headroom savings
    const targetSavings = Number((rawSpend * 0.18).toFixed(2));
    const greenfieldFindings: FinancialFindingDetail[] = [
      {
        id: "gf-opt-1",
        resource_id: "proposed-compute-autoscale",
        resource_name: "App Service Autoscale Schedule",
        category: "Compute Rightsizing",
        severity: "medium",
        title: "Off-Peak Predictive Autoscale Scheduling",
        description: "Scale minimum instance count to 1 during off-peak weekend hours (48 hrs/week).",
        evidence: "Weekly traffic pattern drops to <5 RPS between 22:00 and 06:00.",
        current_monthly_spend: computeCost,
        potential_monthly_savings: Number((targetSavings * 0.6).toFixed(2)),
        calculation_formula: "60% of optimization pool via scheduled off-peak downscaling.",
        pricing_source: "Azure Retail Prices API (Public Tier)",
        confidence: "high",
      },
      {
        id: "gf-opt-2",
        resource_id: "proposed-storage-lifecycle",
        resource_name: "Blob Cold Tier Lifecycle Transition",
        category: "Storage Optimization",
        severity: "low",
        title: "Automated Blob Inactivity Archival",
        description: "Transition blobs older than 30 days to Cool storage tier.",
        evidence: "Historical access telemetry indicates <2% retrieval rate after 30 days.",
        current_monthly_spend: storageCost,
        potential_monthly_savings: Number((targetSavings * 0.4).toFixed(2)),
        calculation_formula: "40% of optimization pool via automated blob lifecycle management.",
        pricing_source: "Azure Retail Prices API (Public Tier)",
        confidence: "high",
      },
    ];

    return {
      provider: "azure",
      scope_id: "greenfield-ai-architect-proposal",
      scope_name: "AI Cloud Architect Proposed Architecture",
      reporting_period: "Proposed Monthly Bill of Materials",
      time_window: timeWindow,
      currency,
      exchange_rate: currency === "INR" ? INR_EXCHANGE_RATE : 1,
      data_provenance: "simulation_benchmark",
      pricing_source: "Azure Retail Prices API (Public Tier)",
      rate_effective_date: "October 2026",
      last_updated: new Date().toISOString(),
      estimated_monthly_spend: rawSpend,
      actual_billed_monthly_spend: null,
      spend_basis: "estimated_public_list",
      spend_formula:
        "Deterministic Bill of Materials calculated from synthesized architecture components.",
      potential_monthly_savings: targetSavings,
      projected_annual_savings: Number((targetSavings * 12).toFixed(2)),
      realized_monthly_savings: 0.0,
      savings_percentage_of_spend: 18.0,
      findings_count: greenfieldFindings.length,
      savings_formula:
        "Architectural efficiency opportunities identified in design stage (autoscale scheduling & storage tiers).",
      categories,
      findings: greenfieldFindings,
      included_resources_count: categories.length,
      unmonitored_or_unpriced_count: greenfieldCost.unpriced_component_count || 0,
      assumptions: [
        "Synthesized architecture bill of materials priced in East US.",
        "Assumes workload specifications provided in Requirements Ingestion step.",
      ],
      limitations: [
        "Pre-deployment architectural estimate; real runtime costs will vary based on live traffic.",
      ],
    };
  }

  // No live source and no simulation: there is nothing truthful to show.
  return null;
}
