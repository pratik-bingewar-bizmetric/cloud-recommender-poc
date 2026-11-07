"use client";

import React from "react";

export const KpiCardSkeleton: React.FC<{ count?: number }> = ({ count = 4 }) => {
  return (
    <div className={`grid grid-cols-2 md:grid-cols-4 lg:grid-cols-${count} gap-3`}>
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="bg-white border border-slate-200 rounded-xl p-3.5 space-y-2 animate-pulse"
        >
          <div className="flex justify-between items-center">
            <div className="h-2.5 bg-slate-200 rounded w-20" />
            <div className="h-4 bg-slate-100 rounded w-12" />
          </div>
          <div className="h-6 bg-slate-200 rounded w-28 mt-2" />
          <div className="h-2 bg-slate-100 rounded w-36 mt-1" />
        </div>
      ))}
    </div>
  );
};

export const ChartSkeleton: React.FC<{ height?: string; title?: string }> = ({
  height = "h-64",
  title = "Loading telemetry visualization...",
}) => {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4 animate-pulse">
      <div className="flex justify-between items-center">
        <div className="space-y-1">
          <div className="h-3.5 bg-slate-200 rounded w-48" />
          <div className="h-2.5 bg-slate-100 rounded w-32" />
        </div>
        <div className="h-6 bg-slate-100 rounded w-24" />
      </div>
      <div className={`w-full ${height} bg-slate-50 rounded-lg flex items-center justify-center border border-dashed border-slate-200`}>
        <span className="text-xs text-slate-400 font-medium">{title}</span>
      </div>
    </div>
  );
};

export const TableSkeleton: React.FC<{ rows?: number; columns?: number }> = ({
  rows = 5,
  columns = 4,
}) => {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3 animate-pulse">
      <div className="flex justify-between items-center pb-2 border-b border-slate-100">
        <div className="h-3.5 bg-slate-200 rounded w-40" />
        <div className="h-6 bg-slate-100 rounded w-28" />
      </div>
      <div className="space-y-2.5 pt-1">
        {Array.from({ length: rows }).map((_, rIdx) => (
          <div key={rIdx} className="grid grid-cols-12 gap-3 py-2 border-b border-slate-100/60 items-center">
            {Array.from({ length: columns }).map((_, cIdx) => (
              <div
                key={cIdx}
                className={`h-3 bg-slate-200 rounded ${
                  cIdx === 0 ? "col-span-4" : cIdx === 1 ? "col-span-3" : "col-span-2"
                }`}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
};

export const DrawerSkeleton: React.FC = () => {
  return (
    <div className="space-y-4 p-5 animate-pulse">
      <div className="space-y-2 pb-3 border-b border-slate-200">
        <div className="h-4 bg-slate-200 rounded w-48" />
        <div className="h-3 bg-slate-100 rounded w-64" />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="h-20 bg-slate-100 rounded-lg" />
        <div className="h-20 bg-slate-100 rounded-lg" />
      </div>
      <div className="h-40 bg-slate-100 rounded-lg" />
      <div className="h-28 bg-slate-100 rounded-lg" />
    </div>
  );
};

