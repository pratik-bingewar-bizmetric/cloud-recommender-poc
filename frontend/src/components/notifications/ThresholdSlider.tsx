"use client";

import React from "react";
import { Plus, Minus, Target, Gauge } from "lucide-react";
import { ThresholdStatus } from "@/types/notifications";

interface ThresholdSliderProps {
  threshold: number;
  simulatedValue: number;
  thresholdStatus: ThresholdStatus;
  isArmed: boolean;
  onThresholdChange: (val: number) => void;
  onIncrement: () => void;
  onDecrement: () => void;
  onSliderChange: (val: number) => void;
}

export const ThresholdSlider: React.FC<ThresholdSliderProps> = ({
  threshold,
  simulatedValue,
  thresholdStatus,
  isArmed,
  onThresholdChange,
  onIncrement,
  onDecrement,
  onSliderChange,
}) => {
  // Color styling based on threshold status
  const getStatusStyles = () => {
    switch (thresholdStatus) {
      case "EXCEEDED":
        return {
          textColor: "text-rose-600",
          bgColor: "bg-rose-50",
          borderColor: "border-rose-200",
          trackColor: "accent-rose-600",
          badgeBg: "bg-rose-100 text-rose-800 border-rose-300",
          label: "Threshold Exceeded",
        };
      case "AT_THRESHOLD":
        return {
          textColor: "text-amber-600",
          bgColor: "bg-amber-50",
          borderColor: "border-amber-200",
          trackColor: "accent-amber-500",
          badgeBg: "bg-amber-100 text-amber-800 border-amber-300",
          label: "At Threshold",
        };
      case "NORMAL":
      default:
        return {
          textColor: "text-emerald-600",
          bgColor: "bg-emerald-50",
          borderColor: "border-emerald-200",
          trackColor: "accent-emerald-600",
          badgeBg: "bg-emerald-100 text-emerald-800 border-emerald-300",
          label: "Normal Utilization",
        };
    }
  };

  const status = getStatusStyles();

  return (
    <div className="space-y-4">
      {/* 1. Threshold Configuration Input */}
      <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-700">
            <Target className="w-3.5 h-3.5 text-brand-600" />
            <span>Configured Threshold</span>
          </div>
          <span className="text-[11px] font-mono text-slate-500">Range: 0% – 100%</span>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onDecrement}
            disabled={threshold <= 0}
            className="w-8 h-8 flex items-center justify-center rounded-lg border border-slate-200 bg-white hover:bg-slate-100 disabled:opacity-40 text-slate-700 transition"
            aria-label="Decrement threshold"
          >
            <Minus className="w-3.5 h-3.5" />
          </button>

          <div className="relative flex-1">
            <input
              type="number"
              min={0}
              max={100}
              value={threshold}
              onChange={(e) => {
                const v = parseInt(e.target.value, 10);
                onThresholdChange(isNaN(v) ? 0 : v);
              }}
              className="w-full text-center py-1.5 px-3 rounded-lg border border-slate-200 bg-white font-mono text-sm font-bold text-navy-950 focus:outline-none focus:ring-1 focus:ring-brand-500"
              aria-label="Threshold percentage"
            />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 font-mono text-xs text-slate-400">
              %
            </span>
          </div>

          <button
            type="button"
            onClick={onIncrement}
            disabled={threshold >= 100}
            className="w-8 h-8 flex items-center justify-center rounded-lg border border-slate-200 bg-white hover:bg-slate-100 disabled:opacity-40 text-slate-700 transition"
            aria-label="Increment threshold"
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* 2. Interactive Simulation Slider */}
      <div className={`p-4 rounded-xl border ${status.borderColor} ${status.bgColor} space-y-3 transition`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Gauge className={`w-4 h-4 ${status.textColor}`} />
            <span className="text-xs font-bold text-navy-950">Simulated Utilization</span>
          </div>
          <div className="flex items-center gap-2">
            <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${status.badgeBg}`}>
              {status.label}
            </span>
            <span className="text-base font-extrabold font-mono text-navy-950">
              {simulatedValue}%
            </span>
          </div>
        </div>

        {/* Slider Track with Threshold Marker */}
        <div className="relative pt-1 pb-1">
          {/* Visual Track Marker for Threshold */}
          <div
            className="absolute top-0 bottom-0 w-0.5 bg-slate-700 z-10 pointer-events-none"
            style={{ left: `${threshold}%` }}
            title={`Threshold: ${threshold}%`}
          >
            <div className="absolute -top-3.5 -translate-x-1/2 bg-slate-800 text-white text-[9px] font-mono px-1 rounded shadow-xs">
              {threshold}%
            </div>
          </div>

          <input
            type="range"
            min={0}
            max={100}
            step={1}
            value={simulatedValue}
            onChange={(e) => onSliderChange(Number(e.target.value))}
            className={`w-full h-2 rounded-lg cursor-pointer bg-slate-200 ${status.trackColor}`}
            aria-label="Simulated utilization slider"
          />
        </div>

        {/* Helper Footer */}
        <div className="flex items-center justify-between text-[11px] text-slate-500 font-mono">
          <span>0%</span>
          <span className="text-slate-600 font-medium">
            Trigger State:{" "}
            <strong className={isArmed ? "text-emerald-700" : "text-amber-700"}>
              {isArmed ? "Armed" : "Triggered / Disarmed"}
            </strong>
          </span>
          <span>100%</span>
        </div>
      </div>
    </div>
  );
};

