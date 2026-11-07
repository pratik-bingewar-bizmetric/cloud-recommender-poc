"use client";

import React from "react";
import { Clock, Filter, X, BarChart3 } from "lucide-react";
import { QueryHistoryItem } from "@/types";

export interface DurationBucketInfo {
  bucket: string;
  minMs: number;
  maxMs: number;
  count: number;
  percentage: number;
}

interface QueryDurationHistogramProps {
  queries: QueryHistoryItem[];
  selectedBucket: string | null;
  onSelectBucket: (bucket: string | null) => void;
  isLoading?: boolean;
}

const BUCKET_DEFINITIONS: Array<{ bucket: string; minMs: number; maxMs: number }> = [
  { bucket: "< 1s", minMs: 0, maxMs: 1000 },
  { bucket: "1s - 5s", minMs: 1000, maxMs: 5000 },
  { bucket: "5s - 15s", minMs: 5000, maxMs: 15000 },
  { bucket: "15s - 60s", minMs: 15000, maxMs: 60000 },
  { bucket: "1m - 5m", minMs: 60000, maxMs: 300000 },
  { bucket: "> 5m", minMs: 300000, maxMs: Infinity },
];

export const formatDurationMs = (ms: number): string => {
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)} s`;
  const mins = Math.floor(ms / 60000);
  const secs = Math.round((ms % 60000) / 1000);
  return `${mins}m ${secs}s`;
};

export const QueryDurationHistogram: React.FC<QueryDurationHistogramProps> = ({
  queries,
  selectedBucket,
  onSelectBucket,
  isLoading = false,
}) => {
  if (isLoading) {
    return (
      <div className="p-6 rounded-xl border border-slate-200 bg-white space-y-4 animate-pulse">
        <div className="h-4 bg-slate-200 rounded w-1/4" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-16 bg-slate-100 rounded-lg" />
          ))}
        </div>
        <div className="h-40 bg-slate-100 rounded-xl" />
      </div>
    );
  }

  const totalQueries = queries.length;

  // Calculate bucket distributions
  const buckets: DurationBucketInfo[] = BUCKET_DEFINITIONS.map((b) => {
    const matching = queries.filter(
      (q) => q.duration_ms >= b.minMs && (b.maxMs === Infinity ? true : q.duration_ms < b.maxMs)
    );
    const count = matching.length;
    const percentage = totalQueries > 0 ? (count / totalQueries) * 100 : 0;
    return {
      bucket: b.bucket,
      minMs: b.minMs,
      maxMs: b.maxMs,
      count,
      percentage,
    };
  });

  // Calculate summary metrics
  const durations = queries.map((q) => q.duration_ms).sort((a, b) => a - b);
  const avgDuration =
    totalQueries > 0 ? durations.reduce((acc, d) => acc + d, 0) / totalQueries : 0;
  const medianDuration =
    totalQueries > 0
      ? totalQueries % 2 === 1
        ? durations[Math.floor(totalQueries / 2)]
        : (durations[totalQueries / 2 - 1] + durations[totalQueries / 2]) / 2
      : 0;
  const p95Index = Math.min(
    Math.floor(totalQueries * 0.95),
    totalQueries > 0 ? totalQueries - 1 : 0
  );
  const p95Duration = totalQueries > 0 ? durations[p95Index] : 0;
  const maxDuration = totalQueries > 0 ? durations[durations.length - 1] : 0;

  const maxBucketCount = Math.max(...buckets.map((b) => b.count), 1);

  return (
    <div className="p-5 rounded-xl border border-slate-200 bg-white space-y-5 shadow-2xs">
      {/* Header and Filter Badge */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-brand-50 text-brand-600 flex items-center justify-center">
            <BarChart3 className="w-4 h-4" />
          </div>
          <div>
            <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
              Query Execution Duration Histogram
            </h4>
            <p className="text-[11px] text-slate-500">
              Distribution of query runtimes across 6 latency buckets · Click bar to filter
            </p>
          </div>
        </div>

        {selectedBucket && (
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-brand-50 text-brand-700 border border-brand-200">
              <Filter className="w-3 h-3 text-brand-600" />
              <span>Filtered by: {selectedBucket}</span>
              <button
                type="button"
                onClick={() => onSelectBucket(null)}
                className="hover:bg-brand-200/60 rounded p-0.5 ml-1 transition"
                title="Clear bucket filter"
              >
                <X className="w-3 h-3 text-brand-800" />
              </button>
            </span>
            <button
              type="button"
              onClick={() => onSelectBucket(null)}
              className="text-xs font-semibold text-slate-500 hover:text-navy-900 underline"
            >
              Clear Filter
            </button>
          </div>
        )}
      </div>

      {/* Latency Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-3 rounded-lg border border-slate-100 bg-slate-50/70">
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
            Median Duration
          </span>
          <div className="text-base font-extrabold text-navy-900 mt-0.5">
            {formatDurationMs(medianDuration)}
          </div>
          <span className="text-[10px] text-slate-500">P50 runtime</span>
        </div>

        <div className="p-3 rounded-lg border border-slate-100 bg-slate-50/70">
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
            Average Duration
          </span>
          <div className="text-base font-extrabold text-blue-700 mt-0.5">
            {formatDurationMs(avgDuration)}
          </div>
          <span className="text-[10px] text-slate-500">Mean across all queries</span>
        </div>

        <div className="p-3 rounded-lg border border-slate-100 bg-slate-50/70">
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
            P95 Duration
          </span>
          <div className="text-base font-extrabold text-amber-700 mt-0.5">
            {formatDurationMs(p95Duration)}
          </div>
          <span className="text-[10px] text-slate-500">95th percentile SLA</span>
        </div>

        <div className="p-3 rounded-lg border border-slate-100 bg-slate-50/70">
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
            Max Duration
          </span>
          <div className="text-base font-extrabold text-rose-700 mt-0.5">
            {formatDurationMs(maxDuration)}
          </div>
          <span className="text-[10px] text-slate-500">Longest single execution</span>
        </div>
      </div>

      {/* Vertical Histogram Bars */}
      <div className="pt-2">
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
          {buckets.map((b) => {
            const isSelected = selectedBucket === b.bucket;
            const barHeightPct = Math.max((b.count / maxBucketCount) * 100, 6);

            return (
              <button
                key={b.bucket}
                type="button"
                onClick={() => onSelectBucket(isSelected ? null : b.bucket)}
                className={`p-3 rounded-xl border text-left transition flex flex-col justify-between group cursor-pointer ${
                  isSelected
                    ? "border-brand-500 bg-brand-50/60 ring-2 ring-brand-400/30"
                    : "border-slate-200 bg-slate-50/50 hover:border-brand-300 hover:bg-white hover:shadow-sm"
                }`}
              >
                {/* Bucket Label and Count */}
                <div className="flex items-center justify-between w-full mb-2">
                  <span
                    className={`text-xs font-bold truncate ${
                      isSelected ? "text-brand-900" : "text-navy-900 group-hover:text-brand-700"
                    }`}
                  >
                    {b.bucket}
                  </span>
                  <span
                    className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                      isSelected
                        ? "bg-brand-600 text-white"
                        : "bg-slate-200/80 text-slate-700 group-hover:bg-brand-100 group-hover:text-brand-800"
                    }`}
                  >
                    {b.count}
                  </span>
                </div>

                {/* Vertical Bar Visual */}
                <div className="h-28 w-full flex items-end justify-center py-1">
                  <div className="w-10 bg-slate-200/60 rounded-t-md relative flex items-end justify-center h-full overflow-hidden">
                    <div
                      className={`w-full rounded-t-md transition-all duration-300 ${
                        isSelected
                          ? "bg-brand-600"
                          : b.count > 0
                          ? "bg-brand-500 group-hover:bg-brand-600"
                          : "bg-slate-300"
                      }`}
                      style={{ height: `${barHeightPct}%` }}
                    />
                  </div>
                </div>

                {/* Percentage & Range Details */}
                <div className="mt-2 pt-2 border-t border-slate-200/60 w-full text-center">
                  <span className="text-[11px] font-bold text-slate-700 block">
                    {b.percentage.toFixed(1)}%
                  </span>
                  <span className="text-[9px] text-slate-400 block mt-0.5 truncate">
                    {b.count} of {totalQueries}
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {totalQueries === 0 && (
        <div className="p-8 text-center text-slate-400 text-xs">
          <Clock className="w-6 h-6 mx-auto mb-2 text-slate-300" />
          No query executions recorded in current scope or filter window.
        </div>
      )}
    </div>
  );
};

