"use client";

import React, { useState, useMemo, useRef, useCallback } from "react";
import {
  TokenTrendPoint,
  TimeWindowPreset,
  MetricInterval,
  TokenDataStatus,
  CloudProvider,
} from "@/types";
import {
  Coins,
  SlidersHorizontal,
  AlertTriangle,
  Terminal,
  Activity,
  Maximize2,
  TrendingUp,
} from "lucide-react";

interface TokenConsumptionChartProps {
  trendPoints: TokenTrendPoint[];
  timeWindow: TimeWindowPreset;
  metricInterval?: MetricInterval;
  dataStatus: TokenDataStatus;
  provider: CloudProvider;
  isLoading?: boolean;
  isMeasuredZero?: boolean;
  onBenchmarkPreviewClick?: () => void;
}

interface NormalizedPoint {
  date: Date;
  timestamp: string;
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
  costUsd: number;
}

export const TokenConsumptionChart: React.FC<TokenConsumptionChartProps> = ({
  trendPoints,
  timeWindow,
  metricInterval = "1h",
  dataStatus,
  provider,
  isLoading = false,
  isMeasuredZero = false,
  onBenchmarkPreviewClick,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [scaleMode, setScaleMode] = useState<"linear" | "log">("linear");

  // 1. Data Normalization: Parse, deduplicate, chronological sort, and reconcile
  const normalizedData = useMemo<NormalizedPoint[]>(() => {
    if (!trendPoints || trendPoints.length === 0) return [];

    // Bucket by ISO hour/period key to aggregate duplicates
    const bucketMap = new Map<string, NormalizedPoint>();

    for (const pt of trendPoints) {
      if (!pt || !pt.timestamp) continue;
      const parsedDate = new Date(pt.timestamp);
      if (isNaN(parsedDate.getTime())) continue;

      const isoKey = parsedDate.toISOString();

      const pTokens = Math.max(0, Number(pt.prompt_tokens) || 0);
      const cTokens = Math.max(0, Number(pt.completion_tokens) || 0);
      let tTokens = Math.max(0, Number(pt.total_tokens) || 0);

      // Reconcile total to prevent double-counting if both input/output and total are provided
      if (tTokens === 0 && (pTokens > 0 || cTokens > 0)) {
        tTokens = pTokens + cTokens;
      } else if (
        pTokens + cTokens > 0 &&
        Math.abs(tTokens - (pTokens + cTokens)) > tTokens * 0.5
      ) {
        // Guard against double count where total = prompt + completion + transaction
        tTokens = pTokens + cTokens;
      }

      const cost = Math.max(0, Number(pt.estimated_cost_usd) || 0);

      if (bucketMap.has(isoKey)) {
        const existing = bucketMap.get(isoKey)!;
        existing.promptTokens += pTokens;
        existing.completionTokens += cTokens;
        existing.totalTokens += tTokens;
        existing.costUsd += cost;
      } else {
        bucketMap.set(isoKey, {
          date: parsedDate,
          timestamp: pt.timestamp,
          promptTokens: pTokens,
          completionTokens: cTokens,
          totalTokens: tTokens,
          costUsd: cost,
        });
      }
    }

    // Sort chronologically ascending
    return Array.from(bucketMap.values()).sort(
      (a, b) => a.date.getTime() - b.date.getTime()
    );
  }, [trendPoints]);

  // 2. Chart Layout Dimensions & Mathematical Scaling
  const width = 660;
  const height = 220;
  const padLeft = 58;
  const padRight = 24;
  const padTop = 18;
  const padBottom = 34;

  const chartW = width - padLeft - padRight;
  const chartH = height - padTop - padBottom;

  const maxVal = useMemo(() => {
    if (normalizedData.length === 0) return 1000;
    const maxToken = Math.max(
      ...normalizedData.map((d) =>
        Math.max(d.totalTokens, d.promptTokens + d.completionTokens)
      ),
      0
    );
    if (maxToken === 0) return 1000;
    // Round up to clean ceiling
    const magnitude = Math.pow(10, Math.floor(Math.log10(maxToken)));
    return Math.ceil(maxToken / magnitude) * magnitude;
  }, [normalizedData]);

  // Detect if there is a dominant spike (> 5x the median non-zero value)
  const hasDominantSpike = useMemo(() => {
    const nonZero = normalizedData
      .map((d) => d.totalTokens)
      .filter((v) => v > 0)
      .sort((a, b) => a - b);
    if (nonZero.length < 3) return false;
    const median = nonZero[Math.floor(nonZero.length / 2)];
    const peak = nonZero[nonZero.length - 1];
    return median > 0 && peak / median > 6;
  }, [normalizedData]);

  // Generate clean horizontal grid values based on scale mode
  const yTicks = useMemo(() => {
    if (scaleMode === "log") {
      const ticks = [0];
      let val = 10;
      while (val <= maxVal) {
        ticks.push(val);
        val *= 10;
      }
      if (ticks[ticks.length - 1] < maxVal) {
        ticks.push(maxVal);
      }
      return ticks.slice(-4);
    }
    return [0, maxVal * 0.33, maxVal * 0.66, maxVal];
  }, [maxVal, scaleMode]);

  const formatTokenNumber = useCallback((val: number): string => {
    if (val >= 1_000_000) return `${(val / 1_000_000).toFixed(1)}M`;
    if (val >= 1_000) return `${Math.round(val / 1_000)}k`;
    return Math.round(val).toString();
  }, []);

  // Format date/time based on window preset
  const formatTickLabel = useCallback(
    (d: Date): string => {
      if (timeWindow === "1h" || timeWindow === "24h") {
        return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      }
      if (timeWindow === "7d") {
        return d.toLocaleDateString([], { weekday: "short", day: "numeric" });
      }
      return d.toLocaleDateString([], { month: "short", day: "numeric" });
    },
    [timeWindow]
  );

  // Responsive, non-overflowing X-axis ticks (5-6 evenly spaced ticks)
  const xTicks = useMemo(() => {
    const len = normalizedData.length;
    if (len === 0) return [];
    if (len <= 6) {
      return normalizedData.map((pt, i) => ({
        x: padLeft + (i / Math.max(1, len - 1)) * chartW,
        label: formatTickLabel(pt.date),
        date: pt.date,
      }));
    }

    const numTicks = 5;
    const step = (len - 1) / (numTicks - 1);
    const ticks: { x: number; label: string; date: Date }[] = [];

    for (let i = 0; i < numTicks; i++) {
      const idx = Math.min(len - 1, Math.round(i * step));
      const pt = normalizedData[idx];
      ticks.push({
        x: padLeft + (idx / (len - 1)) * chartW,
        label: formatTickLabel(pt.date),
        date: pt.date,
      });
    }

    return ticks;
  }, [normalizedData, padLeft, chartW, formatTickLabel]);

  // Dynamic Y-coordinate calculator with optional logarithmic scale
  const getYCoord = useCallback(
    (val: number): number => {
      if (val <= 0 || maxVal <= 0) return padTop + chartH;
      if (scaleMode === "log") {
        const logVal = Math.log10(val + 1);
        const logMax = Math.log10(maxVal + 1);
        const ratio = logMax > 0 ? logVal / logMax : 0;
        return padTop + chartH - ratio * chartH;
      }
      return padTop + chartH - (val / maxVal) * chartH;
    },
    [padTop, chartH, maxVal, scaleMode]
  );

  // SVG coordinate path builders
  const getCoordinates = useCallback(
    (points: NormalizedPoint[], key: "promptTokens" | "completionTokens") => {
      const len = points.length;
      return points.map((p, idx) => {
        const x =
          len <= 1
            ? padLeft + chartW / 2
            : padLeft + (idx / (len - 1)) * chartW;
        const val = p[key];
        const y = getYCoord(val);
        return { x, y, val };
      });
    },
    [padLeft, chartW, getYCoord]
  );

  const promptCoords = useMemo(
    () => getCoordinates(normalizedData, "promptTokens"),
    [normalizedData, getCoordinates]
  );
  const completionCoords = useMemo(
    () => getCoordinates(normalizedData, "completionTokens"),
    [normalizedData, getCoordinates]
  );

  const buildPathString = useCallback(
    (coords: { x: number; y: number }[]): string => {
      if (coords.length === 0) return "";
      return coords.reduce(
        (acc, c, i) => `${acc} ${i === 0 ? "M" : "L"} ${c.x} ${c.y}`,
        ""
      );
    },
    []
  );

  const buildAreaPathString = useCallback(
    (coords: { x: number; y: number }[]): string => {
      if (coords.length === 0) return "";
      const linePath = buildPathString(coords);
      const firstX = coords[0].x;
      const lastX = coords[coords.length - 1].x;
      const bottomY = padTop + chartH;
      return `${linePath} L ${lastX} ${bottomY} L ${firstX} ${bottomY} Z`;
    },
    [buildPathString, padTop, chartH]
  );

  const promptPath = useMemo(
    () => buildPathString(promptCoords),
    [promptCoords, buildPathString]
  );
  const promptAreaPath = useMemo(
    () => buildAreaPathString(promptCoords),
    [promptCoords, buildAreaPathString]
  );
  const completionPath = useMemo(
    () => buildPathString(completionCoords),
    [completionCoords, buildPathString]
  );
  const completionAreaPath = useMemo(
    () => buildAreaPathString(completionCoords),
    [completionCoords, buildAreaPathString]
  );

  // Mouse hover tracker
  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (normalizedData.length === 0) return;
    const svgRect = e.currentTarget.getBoundingClientRect();
    const mouseX = e.clientX - svgRect.left;
    const relX = (mouseX / svgRect.width) * width;

    if (relX < padLeft - 10 || relX > width - padRight + 10) {
      setHoveredIndex(null);
      return;
    }

    const len = normalizedData.length;
    let closestIdx = 0;
    let minDiff = Infinity;

    for (let i = 0; i < len; i++) {
      const ptX =
        len <= 1
          ? padLeft + chartW / 2
          : padLeft + (i / (len - 1)) * chartW;
      const diff = Math.abs(ptX - relX);
      if (diff < minDiff) {
        minDiff = diff;
        closestIdx = i;
      }
    }

    setHoveredIndex(closestIdx);
  };

  const handleMouseLeave = () => {
    setHoveredIndex(null);
  };

  // Keyboard accessibility handler (Arrow keys & Escape)
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (normalizedData.length === 0) return;
    if (e.key === "ArrowRight") {
      e.preventDefault();
      setHoveredIndex((prev) =>
        prev === null ? 0 : Math.min(normalizedData.length - 1, prev + 1)
      );
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      setHoveredIndex((prev) =>
        prev === null
          ? normalizedData.length - 1
          : Math.max(0, prev - 1)
      );
    } else if (e.key === "Escape") {
      setHoveredIndex(null);
    }
  };

  // Hovered item details
  const hoveredPoint =
    hoveredIndex !== null ? normalizedData[hoveredIndex] : null;
  const hoveredPromptCoord =
    hoveredIndex !== null ? promptCoords[hoveredIndex] : null;

  // 3. Render Loading Skeleton
  if (isLoading) {
    return (
      <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-slate-100">
          <div className="space-y-1">
            <div className="h-4 w-44 bg-slate-200 rounded animate-pulse" />
            <div className="h-3 w-64 bg-slate-100 rounded animate-pulse" />
          </div>
          <div className="flex gap-3">
            <div className="h-3 w-16 bg-slate-100 rounded animate-pulse" />
            <div className="h-3 w-16 bg-slate-100 rounded animate-pulse" />
          </div>
        </div>
        <div className="h-52 w-full bg-slate-50 border border-slate-100 rounded-xl flex items-center justify-center animate-pulse">
          <Activity className="w-6 h-6 text-slate-300 animate-spin" />
        </div>
      </div>
    );
  }

  // 4. Render Permission Required Empty State (403)
  if (dataStatus === "unavailable_permission_required") {
    return (
      <div className="bg-white border border-rose-200 rounded-2xl p-6 shadow-xs text-center space-y-3">
        <div className="w-10 h-10 rounded-xl bg-rose-50 border border-rose-200 text-rose-600 flex items-center justify-center mx-auto">
          <AlertTriangle className="w-5 h-5" />
        </div>
        <h4 className="text-sm font-semibold text-navy-950">
          Hourly Telemetry Unavailable &bull; Permission Required (403)
        </h4>
        <p className="text-xs text-slate-500 max-w-md mx-auto leading-relaxed">
          The connected cloud credentials lack permissions to query monitoring
          timeseries metrics. Grant{" "}
          <code className="bg-slate-100 px-1 py-0.5 rounded text-[11px] font-mono">
            Monitoring Reader
          </code>{" "}
          (Azure) or{" "}
          <code className="bg-slate-100 px-1 py-0.5 rounded text-[11px] font-mono">
            roles/monitoring.viewer
          </code>{" "}
          (GCP) to view hourly inference curves.
        </p>
        {onBenchmarkPreviewClick && (
          <button
            type="button"
            onClick={onBenchmarkPreviewClick}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-50 border border-indigo-200 text-indigo-700 text-xs font-semibold hover:bg-indigo-100 transition"
          >
            <SlidersHorizontal className="w-3.5 h-3.5" />
            <span>Preview Reference Benchmark Curve</span>
          </button>
        )}
      </div>
    );
  }

  // 5. Render Instrumentation Required Empty State
  if (dataStatus === "instrumentation_required") {
    return (
      <div className="bg-white border border-dashed border-amber-200 rounded-2xl p-6 shadow-xs text-center space-y-3">
        <div className="w-10 h-10 rounded-xl bg-amber-50 border border-amber-200 text-amber-600 flex items-center justify-center mx-auto">
          <Terminal className="w-5 h-5" />
        </div>
        <h4 className="text-sm font-semibold text-navy-950">
          Hourly Inference Velocity Telemetry Unavailable
        </h4>
        <p className="text-xs text-slate-500 max-w-md mx-auto leading-relaxed">
          {provider === "gcp"
            ? "Vertex AI token logging is not active or export sinks have not routed metrics to Cloud Monitoring."
            : "Azure Monitor Diagnostic Settings are not enabled for the target AI service, or no token metrics have been streamed to Log Analytics."}
        </p>
        {onBenchmarkPreviewClick && (
          <button
            type="button"
            onClick={onBenchmarkPreviewClick}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-50 border border-indigo-200 text-indigo-700 text-xs font-semibold hover:bg-indigo-100 transition"
          >
            <SlidersHorizontal className="w-3.5 h-3.5" />
            <span>Preview Reference Benchmark Curve</span>
          </button>
        )}
      </div>
    );
  }

  // 6. Render Measured Zero State (Provider connected, queried datapoints, but 0 tokens observed)
  if (
    isMeasuredZero ||
    (normalizedData.length > 0 &&
      normalizedData.every((d) => d.totalTokens === 0))
  ) {
    return (
      <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-slate-100">
          <div>
            <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
              Hourly Token Consumption &amp; Inference Velocity
            </h4>
            <p className="text-xs text-slate-500 mt-0.5">
              Empirical observation: exactly 0 inference tokens logged across the
              selected {timeWindow} window ({metricInterval} resolution).
            </p>
          </div>
          <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-100 text-slate-600 border border-slate-200">
            Measured Zero (0 Tokens)
          </span>
        </div>

        <div className="h-52 w-full bg-slate-50/50 border border-slate-100 rounded-xl flex flex-col items-center justify-center p-4 text-center space-y-1">
          <Coins className="w-5 h-5 text-slate-300" />
          <span className="text-xs font-semibold text-navy-900">
            0 Tokens Logged
          </span>
          <p className="text-[11px] text-slate-400 max-w-sm">
            Telemetry endpoints were polled successfully, but no client
            requests triggered prompt or completion execution during this
            period.
          </p>
        </div>
      </div>
    );
  }

  // 7. Render Empty Fallback if no points returned
  if (normalizedData.length === 0) {
    return (
      <div className="bg-white border border-slate-200 rounded-2xl p-6 text-center space-y-3 shadow-xs">
        <div className="w-10 h-10 rounded-xl bg-slate-50 border border-slate-200 text-slate-400 flex items-center justify-center mx-auto">
          <Coins className="w-5 h-5" />
        </div>
        <h4 className="text-sm font-semibold text-navy-950">
          No Hourly Telemetry Points
        </h4>
        <p className="text-xs text-slate-500 max-w-md mx-auto">
          No timeseries intervals were returned for the {timeWindow} preset.
        </p>
      </div>
    );
  }

  // 8. Render Populated, Normalized, Fully Responsive SVG Chart
  return (
    <div
      ref={containerRef}
      className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs space-y-3 relative overflow-hidden"
    >
      {/* Chart Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
        <div>
          <div className="flex items-center gap-2">
            <h4 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
              Token Consumption &amp; Inference Velocity
            </h4>
            {scaleMode === "log" && (
              <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-purple-50 text-purple-700 border border-purple-200">
                Log Scale
              </span>
            )}
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Prompt / input request volume vs. completion tokens across {timeWindow} window ({metricInterval} bucket resolution).
          </p>
        </div>

        {/* Legend & Spike Scale Toggle */}
        <div className="flex flex-wrap items-center gap-4 text-xs font-medium">
          {/* Series Legend */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-xs bg-blue-600 shrink-0" />
              <span className="text-slate-700">Prompt / Input</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-xs bg-purple-600 shrink-0" />
              <span className="text-slate-700">Completion / Output</span>
            </div>
          </div>

          {/* Scale Mode Toggle: Linear vs Logarithmic */}
          <div
            className="flex items-center p-0.5 bg-slate-100 rounded-lg border border-slate-200"
            role="group"
            aria-label="Chart vertical scale"
          >
            <button
              type="button"
              onClick={() => setScaleMode("linear")}
              aria-pressed={scaleMode === "linear"}
              className={`px-2 py-0.5 rounded text-[10px] font-semibold transition ${
                scaleMode === "linear"
                  ? "bg-white text-navy-950 shadow-2xs"
                  : "text-slate-500 hover:text-slate-900"
              }`}
              title="Linear scale — authentic proportional token volume"
            >
              Linear
            </button>
            <button
              type="button"
              onClick={() => setScaleMode("log")}
              aria-pressed={scaleMode === "log"}
              className={`px-2 py-0.5 rounded text-[10px] font-semibold transition flex items-center gap-1 ${
                scaleMode === "log"
                  ? "bg-purple-700 text-white shadow-2xs"
                  : "text-slate-500 hover:text-slate-900"
              }`}
              title="Logarithmic scale — exposes quiet baseline periods when a single peak dominates"
            >
              <Maximize2 className="w-2.5 h-2.5" />
              <span>Log Scale</span>
            </button>
          </div>
        </div>
      </div>

      {/* Dominant Spike Notification Banner */}
      {hasDominantSpike && scaleMode === "linear" && (
        <div className="flex items-center justify-between gap-2 px-3 py-1.5 rounded-lg bg-indigo-50/80 border border-indigo-100 text-indigo-800 text-[11px]">
          <div className="flex items-center gap-1.5">
            <TrendingUp className="w-3.5 h-3.5 text-indigo-600 shrink-0" />
            <span>
              High dynamic range detected: Peak inference spike dwarfs baseline volume.
            </span>
          </div>
          <button
            type="button"
            onClick={() => setScaleMode("log")}
            className="underline font-semibold hover:text-indigo-950 transition text-[11px] shrink-0"
          >
            Enable Log Scale
          </button>
        </div>
      )}

      {/* SVG Canvas Area with Fixed/Responsive Bounds */}
      <div className="relative w-full min-h-[220px] h-[220px] select-none">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full h-full overflow-visible cursor-crosshair focus:outline-hidden focus-visible:ring-2 focus-visible:ring-blue-500 rounded-lg"
          tabIndex={0}
          role="region"
          aria-label="Hourly token consumption and inference velocity time series"
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
          onKeyDown={handleKeyDown}
        >
          <defs>
            {/* Prompt Gradient */}
            <linearGradient id="promptGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#2563eb" stopOpacity="0.18" />
              <stop offset="100%" stopColor="#2563eb" stopOpacity="0.0" />
            </linearGradient>

            {/* Completion Gradient */}
            <linearGradient id="compGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#9333ea" stopOpacity="0.18" />
              <stop offset="100%" stopColor="#9333ea" stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {/* Horizontal Gridlines & Y-Axis Labels */}
          {yTicks.map((tickVal, idx) => {
            const yCoord = getYCoord(tickVal);
            return (
              <g key={idx}>
                <line
                  x1={padLeft}
                  y1={yCoord}
                  x2={width - padRight}
                  y2={yCoord}
                  stroke="#f1f5f9"
                  strokeWidth="1"
                  strokeDasharray={idx === 0 ? "none" : "3 3"}
                />
                <text
                  x={padLeft - 8}
                  y={yCoord + 3}
                  textAnchor="end"
                  className="fill-slate-400 font-mono text-[9px]"
                >
                  {formatTokenNumber(tickVal)}
                </text>
              </g>
            );
          })}

          {/* Shaded Subtle Series Fills */}
          {promptAreaPath && <path d={promptAreaPath} fill="url(#promptGrad)" />}
          {completionAreaPath && (
            <path d={completionAreaPath} fill="url(#compGrad)" />
          )}

          {/* Crisp Series Lines */}
          {promptPath && (
            <path
              d={promptPath}
              fill="none"
              stroke="#2563eb"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )}
          {completionPath && (
            <path
              d={completionPath}
              fill="none"
              stroke="#9333ea"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )}

          {/* Data Points */}
          {promptCoords.map((c, i) => (
            <circle
              key={`p-${i}`}
              cx={c.x}
              cy={c.y}
              r={hoveredIndex === i ? "4.5" : "2"}
              className={`transition-all duration-150 ${
                hoveredIndex === i
                  ? "fill-white stroke-blue-600 stroke-[2.5px]"
                  : "fill-blue-600"
              }`}
            />
          ))}

          {completionCoords.map((c, i) => (
            <circle
              key={`c-${i}`}
              cx={c.x}
              cy={c.y}
              r={hoveredIndex === i ? "4.5" : "2"}
              className={`transition-all duration-150 ${
                hoveredIndex === i
                  ? "fill-white stroke-purple-600 stroke-[2.5px]"
                  : "fill-purple-600"
              }`}
            />
          ))}

          {/* Hover Crosshair Vertical Line */}
          {hoveredPromptCoord && (
            <line
              x1={hoveredPromptCoord.x}
              y1={padTop}
              x2={hoveredPromptCoord.x}
              y2={padTop + chartH}
              stroke="#94a3b8"
              strokeWidth="1"
              strokeDasharray="2 2"
            />
          )}

          {/* Responsive X-Axis Labels (Clamped strictly within card bounds) */}
          {xTicks.map((tick, i) => {
            const clampedX = Math.max(
              padLeft + 14,
              Math.min(width - padRight - 14, tick.x)
            );
            return (
              <text
                key={i}
                x={clampedX}
                y={height - 10}
                textAnchor="middle"
                className="fill-slate-400 font-mono text-[9px]"
              >
                {tick.label}
              </text>
            );
          })}
        </svg>

        {/* Constrained Interactive Hover Tooltip */}
        {hoveredPoint && hoveredPromptCoord && (
          <div
            className="absolute pointer-events-none z-20 bg-slate-900/95 backdrop-blur-xs text-white p-2.5 rounded-xl shadow-xl border border-slate-700/80 text-[11px] space-y-1 transition-all duration-75"
            style={{
              left: `${Math.min(
                Math.max(16, (hoveredPromptCoord.x / width) * 100),
                84
              )}%`,
              top: "10px",
              transform: "translateX(-50%)",
            }}
            role="status"
            aria-live="polite"
          >
            <div className="text-[10px] text-slate-300 font-medium border-b border-slate-800 pb-1 flex items-center justify-between gap-4">
              <span>
                {hoveredPoint.date.toLocaleDateString([], {
                  month: "short",
                  day: "numeric",
                })}{" "}
                {hoveredPoint.date.toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
              <span className="font-mono text-emerald-400 font-semibold">
                ${hoveredPoint.costUsd.toFixed(4)}
              </span>
            </div>

            <div className="space-y-0.5 pt-0.5 font-mono text-[10px]">
              <div className="flex items-center justify-between gap-3 text-blue-300">
                <span>Prompt:</span>
                <span className="font-bold">
                  {hoveredPoint.promptTokens.toLocaleString()}
                </span>
              </div>
              <div className="flex items-center justify-between gap-3 text-purple-300">
                <span>Completion:</span>
                <span className="font-bold">
                  {hoveredPoint.completionTokens.toLocaleString()}
                </span>
              </div>
              <div className="flex items-center justify-between gap-3 text-white pt-1 border-t border-slate-800 font-bold">
                <span>Total:</span>
                <span>{hoveredPoint.totalTokens.toLocaleString()}</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
