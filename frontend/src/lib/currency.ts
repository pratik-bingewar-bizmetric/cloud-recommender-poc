/**
 * Bizmetric FinOps Platform - Currency & Exchange Rate Traceability Engine
 * 
 * Supports USD (base/billing), EUR, GBP, AUD, CAD, INR with explicit
 * central-bank referenced exchange rates and source attribution.
 * Part of Milestone 3J.5 / Part E.
 */

export interface CurrencyMeta {
  code: "USD" | "EUR" | "GBP" | "AUD" | "CAD" | "INR";
  name: string;
  symbol: string;
  rateToUsd: number; // 1 USD = X Target Currency
  source: string;
  asOf: string; // ISO date string
  isSourceBillingCurrency: boolean;
  notes: string;
}

export const SUPPORTED_CURRENCIES: CurrencyMeta[] = [
  {
    code: "USD",
    name: "US Dollar",
    symbol: "$",
    rateToUsd: 1.0,
    source: "Databricks & Cloud Provider Billing Primary Rate",
    asOf: "2026-11-08",
    isSourceBillingCurrency: true,
    notes: "Direct native billing currency from Azure Databricks System Tables & Retail API",
  },
  {
    code: "EUR",
    name: "Euro",
    symbol: "€",
    rateToUsd: 0.922,
    source: "European Central Bank (ECB) Reference Rate",
    asOf: "2026-11-07",
    isSourceBillingCurrency: false,
    notes: "Converted from USD billing source via ECB official spot reference",
  },
  {
    code: "GBP",
    name: "British Pound",
    symbol: "£",
    rateToUsd: 0.7895,
    source: "Bank of England (BoE) Daily Spot Rate",
    asOf: "2026-11-07",
    isSourceBillingCurrency: false,
    notes: "Converted from USD billing source via BoE official spot rate",
  },
  {
    code: "AUD",
    name: "Australian Dollar",
    symbol: "A$",
    rateToUsd: 1.523,
    source: "Reserve Bank of Australia (RBA) Reference Rate",
    asOf: "2026-11-07",
    isSourceBillingCurrency: false,
    notes: "Converted from USD billing source via RBA reference rate",
  },
  {
    code: "CAD",
    name: "Canadian Dollar",
    symbol: "C$",
    rateToUsd: 1.358,
    source: "Bank of Canada (BoC) Operational Reference",
    asOf: "2026-11-07",
    isSourceBillingCurrency: false,
    notes: "Converted from USD billing source via BoC daily reference",
  },
  {
    code: "INR",
    name: "Indian Rupee",
    symbol: "₹",
    rateToUsd: 83.45,
    source: "Reserve Bank of India (RBI) Reference Rate",
    asOf: "2026-11-07",
    isSourceBillingCurrency: false,
    notes: "Converted from USD billing source via RBI reference rate",
  },
];

export const CURRENCY_MAP: Record<string, CurrencyMeta> = SUPPORTED_CURRENCIES.reduce(
  (acc, curr) => {
    acc[curr.code] = curr;
    return acc;
  },
  {} as Record<string, CurrencyMeta>
);

export function getCurrencyMeta(code: string): CurrencyMeta {
  return CURRENCY_MAP[code.toUpperCase()] || CURRENCY_MAP["USD"];
}

/**
 * Format an amount in USD into the target display currency with symbol and localized separation.
 */
export function formatCost(
  usdAmount: number,
  currencyCode: string = "USD",
  options: {
    showCode?: boolean;
    forceDecimals?: boolean;
    maximumFractionDigits?: number;
  } = {}
): string {
  if (isNaN(usdAmount) || !isFinite(usdAmount)) return "$0.00";

  const meta = getCurrencyMeta(currencyCode);
  const converted = usdAmount * meta.rateToUsd;

  const { showCode = false, forceDecimals = false, maximumFractionDigits } = options;

  let formattedNum: string;
  if (!forceDecimals && Math.abs(converted) >= 1000) {
    formattedNum = converted.toLocaleString("en-US", {
      minimumFractionDigits: 0,
      maximumFractionDigits: maximumFractionDigits ?? 0,
    });
  } else {
    formattedNum = converted.toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: maximumFractionDigits ?? 2,
    });
  }

  const result = `${meta.symbol}${formattedNum}`;
  return showCode ? `${result} ${meta.code}` : result;
}

/**
 * Generates an audit string detailing the currency conversion trail.
 */
export function getCurrencyTraceability(currencyCode: string): string {
  const meta = getCurrencyMeta(currencyCode);
  if (meta.isSourceBillingCurrency) {
    return `Native Billing Source: All figures sourced directly in ${meta.code} without conversion.`;
  }
  return `Converted to ${meta.code} at 1 USD = ${meta.rateToUsd} (Source: ${meta.source}, as of ${meta.asOf}). Raw billing remains USD.`;
}

