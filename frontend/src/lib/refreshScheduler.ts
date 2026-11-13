/**
 * Refresh scheduling primitives (framework-free so they can be unit tested).
 * - single-flight: a task never overlaps itself
 * - tracks last success / last failure so stale data is never shown as current
 */

export interface RefreshStatus {
  lastSuccessAt: number | null;
  lastAttemptAt: number | null;
  lastError: string | null;
  inFlight: boolean;
  /** Failed since the last success, or no success within `staleAfterMs`. */
  stale: boolean;
}

export interface RefreshController {
  run: () => Promise<boolean>;
  status: () => RefreshStatus;
}

export const createRefreshController = (
  task: () => Promise<void>,
  opts: { staleAfterMs: number; now?: () => number }
): RefreshController => {
  const now = opts.now ?? (() => Date.now());
  let inFlight = false;
  let lastSuccessAt: number | null = null;
  let lastAttemptAt: number | null = null;
  let lastError: string | null = null;

  return {
    /** Returns false when skipped because a refresh is already running or when it failed. */
    run: async () => {
      if (inFlight) return false;
      inFlight = true;
      lastAttemptAt = now();
      try {
        await task();
        lastSuccessAt = now();
        lastError = null;
        return true;
      } catch (err) {
        lastError = err instanceof Error ? err.message : String(err);
        return false;
      } finally {
        inFlight = false;
      }
    },
    status: () => ({
      lastSuccessAt,
      lastAttemptAt,
      lastError,
      inFlight,
      stale: lastError !== null || (lastSuccessAt !== null && now() - lastSuccessAt > opts.staleAfterMs),
    }),
  };
};

/** Format "last updated" text deterministically (UTC). */
export const formatUpdatedAt = (ms: number | string | null | undefined): string => {
  if (ms === null || ms === undefined) return "-";
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toISOString().replace("T", " ").slice(0, 19) + " UTC";
};

export const DEFAULT_OPERATIONAL_REFRESH_MS = 60_000;
export const DEFAULT_METADATA_REFRESH_MS = 300_000;
