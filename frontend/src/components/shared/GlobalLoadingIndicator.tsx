"use client";

import React from "react";
import { Loader2, RefreshCw, X, AlertCircle } from "lucide-react";

export interface GlobalLoadingState {
  isLoading: boolean;
  stageMessage?: string;
  progressPct?: number | null; // null = indeterminate
  isError?: boolean;
  errorMessage?: string | null;
  onRetry?: () => void;
  onCancel?: () => void;
}

interface GlobalLoadingIndicatorProps {
  state: GlobalLoadingState;
  className?: string;
}

export const GlobalLoadingIndicator: React.FC<GlobalLoadingIndicatorProps> = ({
  state,
  className = "",
}) => {
  if (!state.isLoading && !state.isError) return null;

  return (
    <div
      className={`w-full bg-navy-950 text-white shadow-md z-40 transition-all duration-200 border-b border-navy-800 ${className}`}
    >
      <div className="w-full px-4 sm:px-6 py-2.5 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          {state.isLoading ? (
            <Loader2 className="w-4 h-4 text-brand-400 animate-spin shrink-0" />
          ) : (
            <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
          )}

          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold truncate text-slate-100">
                {state.isError
                  ? state.errorMessage || "Operation failed"
                  : state.stageMessage || "Processing cloud request..."}
              </span>
              {typeof state.progressPct === "number" && (
                <span className="text-[10px] font-mono font-bold text-brand-400 bg-brand-950/80 px-1.5 py-0.2 rounded border border-brand-800">
                  {Math.round(state.progressPct)}%
                </span>
              )}
            </div>

            {/* Progress Bar */}
            {state.isLoading && (
              <div className="w-48 sm:w-72 bg-navy-800 h-1 rounded-full overflow-hidden mt-1">
                {typeof state.progressPct === "number" ? (
                  <div
                    className="bg-brand-500 h-1 rounded-full transition-all duration-300"
                    style={{ width: `${Math.min(Math.max(state.progressPct, 0), 100)}%` }}
                  />
                ) : (
                  <div className="bg-brand-500 h-1 w-1/3 rounded-full animate-pulse" />
                )}
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {state.isError && state.onRetry && (
            <button
              type="button"
              onClick={state.onRetry}
              className="px-2.5 py-1 rounded bg-brand-600 hover:bg-brand-500 text-white text-[11px] font-semibold flex items-center gap-1.5 transition"
            >
              <RefreshCw className="w-3 h-3" />
              <span>Retry</span>
            </button>
          )}

          {state.onCancel && (
            <button
              type="button"
              onClick={state.onCancel}
              className="p-1 text-slate-400 hover:text-white rounded hover:bg-navy-800 transition"
              title="Dismiss"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

