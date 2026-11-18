import type { BillingPriceRecord, BillingSummaryResponse, BillingUsageRecord } from "@/types";

/** What a monetary figure represents. Only AZURE_INVOICED may be presented as "billed". */
export type CostBasis = "METERED_USAGE" | "LIST_PRICE_ESTIMATE" | "AZURE_INVOICED";

export interface BillingUsagePage {
  total: number;
  offset: number;
  limit: number;
  records: BillingUsageRecord[];
}

export interface BillingPricePage {
  total: number;
  records: BillingPriceRecord[];
}

/**
 * Accepts both the paginated envelope and the legacy bare list returned by
 * GET /finops/billing/usage, so older and newer backends are both safe to call.
 */
export function normalizeUsagePage(
  payload: unknown,
  offset = 0,
  limit = 50
): BillingUsagePage {
  if (Array.isArray(payload)) {
    const records = payload as BillingUsageRecord[];
    return { total: records.length, offset, limit, records };
  }
  const env = (payload ?? {}) as Partial<BillingUsagePage>;
  const records = Array.isArray(env.records) ? env.records : [];
  return {
    total: typeof env.total === "number" ? env.total : records.length,
    offset: typeof env.offset === "number" ? env.offset : offset,
    limit: typeof env.limit === "number" ? env.limit : limit,
    records,
  };
}

/** Same tolerance for GET /finops/billing/pricing. */
export function normalizePricePage(payload: unknown): BillingPricePage {
  if (Array.isArray(payload)) {
    const records = payload as BillingPriceRecord[];
    return { total: records.length, records };
  }
  const env = (payload ?? {}) as Partial<BillingPricePage>;
  const records = Array.isArray(env.records) ? env.records : [];
  return {
    total: typeof env.total === "number" ? env.total : records.length,
    records,
  };
}

const COST_BASIS_LABELS: Record<CostBasis, string> = {
  METERED_USAGE: "Metered usage (no cost derived)",
  LIST_PRICE_ESTIMATE: "Estimated at list price",
  AZURE_INVOICED: "Billed (Azure)",
};

/** Human label for a cost basis; unknown/missing values never read as "billed". */
export function costBasisLabel(basis: string | null | undefined): string {
  return basis && basis in COST_BASIS_LABELS
    ? COST_BASIS_LABELS[basis as CostBasis]
    : COST_BASIS_LABELS.METERED_USAGE;
}

/** True only for a genuinely invoiced figure. */
export function isInvoicedBasis(basis: string | null | undefined): boolean {
  return basis === "AZURE_INVOICED";
}

/** The currency of the priced billing rows, exactly as reported by the source. */
export interface SourceCurrency {
  /** Set only when exactly one currency is present. */
  code: string | null;
  /** True when several currencies are present: amounts must never be combined. */
  mixed: boolean;
  codes: string[];
}

export function sourceCurrencyOf(
  summary: Pick<BillingSummaryResponse, "currency" | "spend_by_currency"> | null | undefined
): SourceCurrency {
  const codes = (summary?.spend_by_currency ?? [])
    .map((c) => c.currency)
    .filter((c): c is string => typeof c === "string" && c.length > 0);
  if (codes.length > 1) return { code: null, mixed: true, codes };
  const code = summary?.currency ?? codes[0] ?? null;
  return { code, mixed: false, codes: code ? [code] : [] };
}

/**
 * Format an amount in the currency it was billed in. There is NO conversion: USD uses "$",
 * every other currency is followed by its code; an unknown or mixed currency is never guessed.
 */
export function formatSourceMoney(amount: number | null | undefined, currency: SourceCurrency): string {
  if (amount === null || amount === undefined || !Number.isFinite(amount)) return "-";
  if (currency.mixed) return "n/a (mixed currencies)";
  if (!currency.code) return "-";
  const text = amount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return currency.code.toUpperCase() === "USD" ? `$${text}` : `${text} ${currency.code.toUpperCase()}`;
}

/** Currency descriptor for a single, known (or unknown) currency code. */
export function singleCurrency(code: string | null | undefined): SourceCurrency {
  return { code: code || null, mixed: false, codes: code ? [code] : [] };
}

/** Header text naming the currency of a money column. */
export function currencyColumnName(currency: SourceCurrency): string {
  return currency.code ?? (currency.mixed ? "mixed currencies" : "currency unknown");
}

/** Short label stating which currency the figures are in (and that nothing was converted). */
export function sourceCurrencyLabel(currency: SourceCurrency): string {
  if (currency.mixed) return `Currency: mixed (${currency.codes.join(", ")}) - amounts are not combined`;
  if (currency.code) return `Currency: ${currency.code.toUpperCase()} (as billed, no conversion)`;
  return "Currency: not yet known (no priced billing rows)";
}
