"use client";

import React, { useState } from "react";
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

export const BUCKET_DEFINITIONS: Array<{ bucket: string; displayLabel: string; minMs: number; maxMs: number }> = [
  { bucket: "< 1s", displayLabel: "< 1s", minMs: 0, maxMs: 1000 },
  { bucket: "1s - 5s", displayLabel: "1s – 5s", minMs: 1000, maxMs: 5000 },
  { bucket: "5s - 15s", displayLabel: "5s – 15s", minMs: 5000, maxMs: 15000 },
  { bucket: "15s - 60s", displayLabel: "15s – 60s", minMs: 15000, maxMs: 60000 },
  { bucket: "1m - 5m", displayLabel: "1m – 5m", minMs: 60000, maxMs: 300000 },
  { bucket: "> 5m", displayLabel: "> 5m", minMs: 300000, maxMs: Infinity },
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
  const [hoveredBucket, setHoveredBucket] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div className="p-6 rounded-xl border border-slate-200 bg-white space-y-4 animate-pulse">
        <div className="h-4 bg-slate-200 rounded w-1/4" />
        <div className="h-10 bg-slate-100 rounded-lg" />
        <div className="h-52 bg-slate-100 rounded-xl" />
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

  // Y-axis ticks (4 ticks: 100%, 75%, 50%, 25%)
  const yTicks = [
    maxBucketCount,
    Math.round(maxBucketCount * 0.75),
    Math.round(maxBucketCount * 0.5),
    Math.round(maxBucketCount * 0.25),
  ];

  return (
    <div className="p-5 rounded-xl border border-slate-200 bg-white space-y-4 shadow-2xs">
      {/* Header and Filter Badge */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-brand-50 text-brand-600 flex items-center justify-center shrink-0">
            <BarChart3 className="w-4 h-4" />
          </div>
          <div>
            <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
              Query Execution Duration Distribution
            </h4>
            <p className="text-[11px] text-slate-500">
              Distribution of query runtimes across 6 latency buckets &bull; Click bar to filter
            </p>
          </div>
        </div>

        {selectedBucket && (
          <div className="flex items-center gap-2 self-start sm:self-auto">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-brand-50 text-brand-700 border border-brand-200">
              <Filter className="w-3 h-3 text-brand-600" />
              <span>
                Filtered by:{" "}
                <span className="font-mono">
                  {BUCKET_DEFINITIONS.find((b) => b.bucket === selectedBucket)?.displayLabel || selectedBucket}
                </span>
              </span>
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
              Clear filter
            </button>
          </div>
        )}
      </div>

      {/* Compact Horizontal Inline Summary Stats Row */}
      <div className="flex flex-wrap items-center justify-between gap-2 p-2.5 bg-slate-50 border border-slate-200 rounded-lg text-xs">
        <div className="flex items-center gap-1.5 px-2">
          <span className="text-[10px] uppercase font-bold text-slate-400">Total Queries:</span>
          <span className="font-bold text-navy-900 font-mono tabular-nums">{totalQueries}</span>
        </div>
        <div className="hidden sm:block text-slate-300">&bull;</div>
        <div className="flex items-center gap-1.5 px-2">
          <span className="text-[10px] uppercase font-bold text-slate-400">Median (P50):</span>
          <span className="font-bold text-navy-900 font-mono tabular-nums">{formatDurationMs(medianDuration)}</span>
        </div>
        <div className="hidden sm:block text-slate-300">&bull;</div>
        <div className="flex items-center gap-1.5 px-2">
          <span className="text-[10px] uppercase font-bold text-slate-400">Average:</span>
          <span className="font-bold text-blue-700 font-mono tabular-nums">{formatDurationMs(avgDuration)}</span>
        </div>
        <div className="hidden sm:block text-slate-300">&bull;</div>
        <div className="flex items-center gap-1.5 px-2">
          <span className="text-[10px] uppercase font-bold text-slate-400">P95 SLA:</span>
          <span className="font-bold text-amber-700 font-mono tabular-nums">{formatDurationMs(p95Duration)}</span>
        </div>
        <div className="hidden sm:block text-slate-300">&bull;</div>
        <div className="flex items-center gap-1.5 px-2">
          <span className="text-[10px] uppercase font-bold text-slate-400">Max Duration:</span>
          <span className="font-bold text-rose-700 font-mono tabular-nums">{formatDurationMs(maxDuration)}</span>
        </div>
      </div>

      {/* Unified Vertical Bar Chart Container */}
      <div className="relative pt-6 pb-2">
        {/* Background Y-Axis Reference Grid Lines */}
        <div className="absolute inset-x-8 top-6 bottom-10 flex flex-col justify-between pointer-events-none">
          {yTicks.map((tick, idx) => (
            <div key={idx} className="w-full flex items-center gap-2 border-b border-dashed border-slate-100">
              <span className="text-[9px] font-mono text-slate-300 tabular-nums w-5 text-right -ml-7 select-none">
                {tick}
              </span>
            </div>
          ))}
          <div className="w-full border-b border-slate-200" />
        </div>

        {/* 6 Vertical Bars */}
        <div className="relative h-48 flex items-end justify-between gap-2 sm:gap-4 px-8 pb-8">
          {buckets.map((b) => {
            const isSelected = selectedBucket === b.bucket;
            const isHovered = hoveredBucket === b.bucket;
            const barHeightPct = totalQueries > 0 && b.count > 0
              ? Math.max(Math.round((b.count / maxBucketCount) * 100), 8)
              : 2;

            const def = BUCKET_DEFINITIONS.find((defItem) => defItem.bucket === b.bucket);
            const label = def?.displayLabel || b.bucket;

            return (
              <div
                key={b.bucket}
                className="flex-1 flex flex-col items-center justify-end h-full relative group cursor-pointer"
                onClick={() => onSelectBucket(isSelected ? null : b.bucket)}
                onMouseEnter={() => setHoveredBucket(b.bucket)}
                onMouseLeave={() => setHoveredBucket(null)}
              >
                {/* Tooltip on Hover */}
                {isHovered && (
                  <div className="absolute -top-14 z-30 px-2.5 py-1.5 bg-navy-950 text-white text-[11px] rounded-lg shadow-xl pointer-events-none whitespace-nowrap animate-in fade-in zoom-in-95 duration-150">
                    <div className="font-bold font-mono">{label}</div>
                    <div className="text-slate-300 text-[10px]">
                      <span className="font-semibold text-white">{b.count}</span> queries ({b.percentage.toFixed(1)}%)
                    </div>
                    {/* Tooltip Arrow */}
                    <div className="w-2 h-2 bg-navy-950 rotate-45 absolute -bottom-1 left-1/2 -translate-x-1/2" />
                  </div>
                )}

                {/* Numeric Count Label Directly Above Bar */}
                <span
                  className={`text-xs font-mono font-bold mb-1 transition-all tabular-nums ${
                    isSelected
                      ? "text-brand-700 font-extrabold text-sm"
                      : isHovered
                      ? "text-navy-900 font-bold"
                      : b.count > 0
                      ? "text-slate-600"
                      : "text-slate-300"
                  }`}
                >
                  {b.count}
                </span>

                {/* Vertical Bar Rising from Common Baseline */}
                <div className="w-full max-w-[64px] flex items-end justify-center h-full">
                  <div
                    style={{ height: `${barHeightPct}%` }}
                    className={`w-full rounded-t-md transition-all duration-300 shadow-2xs ${
                      isSelected
                        ? "bg-gradient-to-t from-brand-700 to-brand-500 ring-2 ring-brand-500 ring-offset-2 shadow-md"
                        : isHovered
                        ? "bg-gradient-to-t from-brand-600 to-brand-400 opacity-95"
                        : b.count > 0
                        ? "bg-gradient-to-t from-brand-600/90 to-brand-500/80"
                        : "bg-slate-200"
                    }`}
                  />
                </div>

                {/* X-Axis Bucket Label Below Baseline */}
                <div className="absolute -bottom-6 w-full text-center">
                  <span
                    className={`text-[11px] font-mono transition-colors block truncate ${
                      isSelected
                        ? "font-bold text-brand-700"
                        : isHovered
                        ? "font-semibold text-navy-950"
                        : "text-slate-500"
                    }`}
                  >
                    {label}
                  </span>
                  <span className="text-[9px] text-slate-400 font-mono block">
                    {b.percentage.toFixed(0)}%
                  </span>
                </div>
              </div>
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
