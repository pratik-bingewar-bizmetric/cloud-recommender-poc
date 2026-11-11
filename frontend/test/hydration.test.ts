/**
 * Automated Test Suite: Hydration Safety & Deterministic Date/Time Formatting
 * Verifies Milestone 3J.5 / Part A Remediation.
 */

import assert from "node:assert";
import test from "node:test";
import {
  formatDeterministicTime,
  formatDeterministicDate,
  formatDeterministicDateTime,
  formatDeterministicIso,
} from "../src/lib/dateTimeFormat";

test("Hydration Safety: formatDeterministicTime produces exact 24-hour UTC", () => {
  // Benchmark timestamp matching the reported hydration error (12:41 UTC)
  const iso = "2026-11-08T12:41:00.000Z";
  const result = formatDeterministicTime(iso);
  assert.strictEqual(result, "12:41 UTC", "Must output deterministic 12:41 UTC");
});

test("Hydration Safety: formatDeterministicTime with 12h option produces exact AM/PM format", () => {
  const amIso = "2026-11-08T09:15:00.000Z";
  const pmIso = "2026-11-08T14:30:00.000Z";

  assert.strictEqual(
    formatDeterministicTime(amIso, { hour12: true }),
    "9:15 AM UTC"
  );
  assert.strictEqual(
    formatDeterministicTime(pmIso, { hour12: true }),
    "2:30 PM UTC"
  );
});

test("Hydration Safety: formatDeterministicTime with seconds", () => {
  const iso = "2026-11-08T12:41:35.000Z";
  assert.strictEqual(
    formatDeterministicTime(iso, { showSeconds: true }),
    "12:41:35 UTC"
  );
  assert.strictEqual(
    formatDeterministicTime(iso, { showSeconds: true, hour12: true }),
    "12:41:35 PM UTC"
  );
});

test("Hydration Safety: formatDeterministicDate outputs consistent format", () => {
  const iso = "2026-11-08T12:41:00.000Z";
  assert.strictEqual(formatDeterministicDate(iso), "Nov 8, 2026");
  assert.strictEqual(
    formatDeterministicDate(iso, { fullMonth: true }),
    "November 8, 2026"
  );
  assert.strictEqual(
    formatDeterministicDate(iso, { includeWeekday: true }),
    "Sun, Nov 8, 2026"
  );
});

test("Hydration Safety: formatDeterministicDateTime combines date and time deterministically", () => {
  const iso = "2026-11-08T12:41:00.000Z";
  const dt = formatDeterministicDateTime(iso);
  assert.strictEqual(dt, "Nov 8, 2026 12:41 UTC");
});

test("Hydration Safety: Graceful fallback on null, undefined, or invalid date inputs", () => {
  assert.strictEqual(formatDeterministicTime(null), "—");
  assert.strictEqual(formatDeterministicTime(undefined), "—");
  assert.strictEqual(formatDeterministicTime("invalid-date-string"), "—");

  assert.strictEqual(formatDeterministicDate(null), "—");
  assert.strictEqual(formatDeterministicDate("not-a-date"), "—");

  assert.strictEqual(formatDeterministicDateTime(null), "—");
  assert.strictEqual(formatDeterministicIso(null), "—");
});

