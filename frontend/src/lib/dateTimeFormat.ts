/**
 * Bizmetric FinOps Platform - Deterministic Date & Time Formatting Utilities
 * 
 * Remediation for Next.js SSR / Client Hydration Mismatches (Milestone 3J.5 / Part A)
 * Eliminates "Text content does not match server-rendered HTML" errors by enforcing
 * strict UTC timezone and deterministic locale-independent string formatting.
 */

const MONTH_NAMES_SHORT = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
];

const MONTH_NAMES_FULL = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"
];

const WEEKDAY_NAMES_SHORT = [
  "Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"
];

/**
 * Format a timestamp into a deterministic time string (e.g., "12:41 UTC" or "12:41:00 UTC")
 * By default outputs 24-hour UTC to ensure exact match between Node.js SSR and client browsers.
 */
export function formatDeterministicTime(
  dateInput: string | number | Date | null | undefined,
  options: {
    hour12?: boolean;
    showSeconds?: boolean;
    includeTz?: boolean;
  } = {}
): string {
  if (!dateInput) return "—";
  const d = typeof dateInput === "object" ? dateInput : new Date(dateInput);
  if (isNaN(d.getTime())) return "—";

  const { hour12 = false, showSeconds = false, includeTz = true } = options;
  const hours24 = d.getUTCHours();
  const mins = String(d.getUTCMinutes()).padStart(2, "0");
  const secs = String(d.getUTCSeconds()).padStart(2, "0");

  let timeStr: string;
  if (hour12) {
    const ampm = hours24 >= 12 ? "PM" : "AM";
    const h12 = hours24 % 12 || 12;
    timeStr = showSeconds ? `${h12}:${mins}:${secs} ${ampm}` : `${h12}:${mins} ${ampm}`;
  } else {
    const h24 = String(hours24).padStart(2, "0");
    timeStr = showSeconds ? `${h24}:${mins}:${secs}` : `${h24}:${mins}`;
  }

  return includeTz ? `${timeStr} UTC` : timeStr;
}

/**
 * Format a timestamp into a deterministic date string (e.g., "Nov 8, 2026")
 */
export function formatDeterministicDate(
  dateInput: string | number | Date | null | undefined,
  options: { fullMonth?: boolean; includeWeekday?: boolean } = {}
): string {
  if (!dateInput) return "—";
  const d = typeof dateInput === "object" ? dateInput : new Date(dateInput);
  if (isNaN(d.getTime())) return "—";

  const { fullMonth = false, includeWeekday = false } = options;
  const monthStr = fullMonth
    ? MONTH_NAMES_FULL[d.getUTCMonth()]
    : MONTH_NAMES_SHORT[d.getUTCMonth()];
  const day = d.getUTCDate();
  const year = d.getUTCFullYear();

  const mainDate = `${monthStr} ${day}, ${year}`;
  if (includeWeekday) {
    const weekday = WEEKDAY_NAMES_SHORT[d.getUTCDay()];
    return `${weekday}, ${mainDate}`;
  }
  return mainDate;
}

/**
 * Format a timestamp into a deterministic date and time string (e.g., "Nov 8, 2026 12:41 UTC")
 */
export function formatDeterministicDateTime(
  dateInput: string | number | Date | null | undefined,
  options: {
    hour12?: boolean;
    showSeconds?: boolean;
    fullMonth?: boolean;
    includeWeekday?: boolean;
  } = {}
): string {
  if (!dateInput) return "—";
  const d = typeof dateInput === "object" ? dateInput : new Date(dateInput);
  if (isNaN(d.getTime())) return "—";

  const dateStr = formatDeterministicDate(d, {
    fullMonth: options.fullMonth,
    includeWeekday: options.includeWeekday,
  });
  const timeStr = formatDeterministicTime(d, {
    hour12: options.hour12 ?? false,
    showSeconds: options.showSeconds ?? false,
    includeTz: true,
  });

  return `${dateStr} ${timeStr}`;
}

/**
 * Format relative duration or ISO string cleanly
 */
export function formatDeterministicIso(dateInput: string | number | Date | null | undefined): string {
  if (!dateInput) return "—";
  const d = typeof dateInput === "object" ? dateInput : new Date(dateInput);
  if (isNaN(d.getTime())) return "—";
  return d.toISOString();
}

