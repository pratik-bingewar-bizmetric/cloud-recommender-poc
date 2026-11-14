/**
 * Bizmetric FinOps Platform - Currency display helpers.
 *
 * NO CONVERSION. Amounts are always shown in the currency they were reported in by their
 * source (billing system table, pricing API). This module deliberately contains no exchange
 * rates: a rate that is not retrieved from a live source would be a fabricated number, and
 * combining or converting currencies silently misstates money.
 */

export interface CurrencyMeta {
  code: string;
  name: string;
  symbol: string;
}

/** Symbols for display only. Not a statement that any amount is available in these currencies. */
export const SUPPORTED_CURRENCIES: CurrencyMeta[] = [
  { code: "USD", name: "US Dollar", symbol: "$" },
  { code: "EUR", name: "Euro", symbol: "€" },
  { code: "GBP", name: "British Pound", symbol: "£" },
  { code: "AUD", name: "Australian Dollar", symbol: "A$" },
  { code: "CAD", name: "Canadian Dollar", symbol: "C$" },
  { code: "INR", name: "Indian Rupee", symbol: "₹" },
];

export const CURRENCY_MAP: Record<string, CurrencyMeta> = Object.fromEntries(
  SUPPORTED_CURRENCIES.map((c) => [c.code, c])
);

/** Metadata for a code; an unknown code is shown as its own code, never mapped to USD. */
export function getCurrencyMeta(code: string): CurrencyMeta {
  const upper = code.toUpperCase();
  return CURRENCY_MAP[upper] ?? { code: upper, name: upper, symbol: `${upper} ` };
}

/** Format an amount in ITS OWN currency (no conversion). */
export function formatCost(
  amount: number,
  currencyCode: string,
  options: { maximumFractionDigits?: number } = {}
): string {
  if (!Number.isFinite(amount)) return "-";
  const meta = getCurrencyMeta(currencyCode);
  const digits = options.maximumFractionDigits ?? 2;
  const text = amount.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  return `${meta.symbol}${text}`;
}

/** Audit note: amounts are shown as reported, never converted. */
export function getCurrencyTraceability(currencyCode: string): string {
  return `Shown in ${getCurrencyMeta(currencyCode).code} exactly as reported by the source. No conversion applied.`;
}
