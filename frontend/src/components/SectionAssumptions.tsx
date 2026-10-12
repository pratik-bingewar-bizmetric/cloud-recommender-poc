"use client";

import React from "react";
import { Zap, Shield, HardDrive, Cpu, DollarSign } from "lucide-react";
import { WorkloadAssumptions } from "@/types";

interface SectionAssumptionsProps {
  assumptions: WorkloadAssumptions;
  onAssumptionsChange: (updated: WorkloadAssumptions) => void;
  onPresetSelect: (preset: number) => void;
  safetyBufferPct: string;
  onSafetyBufferChange: (val: string) => void;
}

export const SectionAssumptions: React.FC<SectionAssumptionsProps> = ({
  assumptions,
  onAssumptionsChange,
  onPresetSelect,
  safetyBufferPct,
  onSafetyBufferChange,
}) => {
  const updateField = <K extends keyof WorkloadAssumptions>(
    key: K,
    val: WorkloadAssumptions[K]
  ) => {
    onAssumptionsChange({
      ...assumptions,
      [key]: val,
    });
  };

  return (
    <section className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 mb-5 border-b border-slate-100 gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-900 flex items-center">
            <span className="w-6 h-6 rounded-full bg-blue-100 text-blue-700 text-xs font-bold flex items-center justify-center mr-2">
              B
            </span>
            Workload Sizing & Assumptions Controls
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Tweak traffic, storage, and reliability sliders. Cost simulation recalculates immediately via the deterministic pricing engine.
          </p>
        </div>

        {/* Preset Selector */}
        <div className="flex items-center space-x-1 bg-slate-100 p-1 rounded-lg border border-slate-200">
          <span className="text-[11px] font-semibold text-slate-500 px-2 flex items-center">
            <Zap className="w-3 h-3 mr-1 text-amber-500" />
            Scale Preset:
          </span>
          {[21, 51, 10000].map((presetVal) => (
            <button
              key={presetVal}
              type="button"
              onClick={() => onPresetSelect(presetVal)}
              className={`text-xs px-2.5 py-1 rounded font-semibold transition ${
                assumptions.customer_count === presetVal
                  ? "bg-white text-blue-700 shadow-xs border border-slate-200 font-bold"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              {presetVal === 21 && "21 (Pilot)"}
              {presetVal === 51 && "51 (SME)"}
              {presetVal === 10000 && "10k (Scale)"}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-5">
        {/* Customer Count */}
        <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
          <label className="text-xs font-medium text-slate-600 block mb-1">
            Customer Count
          </label>
          <input
            type="number"
            min={1}
            value={assumptions.customer_count}
            onChange={(e) => updateField("customer_count", Math.max(1, parseInt(e.target.value) || 1))}
            className="w-full text-sm font-semibold p-1.5 rounded border border-slate-300 bg-white"
          />
        </div>

        {/* MAU */}
        <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
          <label className="text-xs font-medium text-slate-600 block mb-1">
            Monthly Active Users (MAU)
          </label>
          <input
            type="number"
            min={1}
            value={assumptions.monthly_active_users}
            onChange={(e) => updateField("monthly_active_users", Math.max(1, parseInt(e.target.value) || 1))}
            className="w-full text-sm font-semibold p-1.5 rounded border border-slate-300 bg-white"
          />
        </div>

        {/* Peak RPS */}
        <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
          <label className="text-xs font-medium text-slate-600 block mb-1">
            Peak Requests / Sec (RPS)
          </label>
          <input
            type="number"
            min={0.1}
            step={0.5}
            value={assumptions.peak_rps}
            onChange={(e) => updateField("peak_rps", Math.max(0.1, parseFloat(e.target.value) || 0.1))}
            className="w-full text-sm font-semibold p-1.5 rounded border border-slate-300 bg-white"
          />
        </div>

        {/* Requests per user / day */}
        <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
          <label className="text-xs font-medium text-slate-600 block mb-1">
            Requests / User / Day
          </label>
          <input
            type="number"
            min={1}
            value={assumptions.requests_per_user_per_day}
            onChange={(e) => updateField("requests_per_user_per_day", Math.max(1, parseInt(e.target.value) || 1))}
            className="w-full text-sm font-semibold p-1.5 rounded border border-slate-300 bg-white"
          />
        </div>

        {/* Relational DB Storage */}
        <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
          <label className="text-xs font-medium text-slate-600 block mb-1 flex items-center">
            <HardDrive className="w-3.5 h-3.5 mr-1 text-slate-500" />
            PostgreSQL Storage (GB)
          </label>
          <input
            type="number"
            min={5}
            step={5}
            value={assumptions.db_storage_gb}
            onChange={(e) => updateField("db_storage_gb", Math.max(5, parseFloat(e.target.value) || 5))}
            className="w-full text-sm font-semibold p-1.5 rounded border border-slate-300 bg-white"
          />
        </div>

        {/* Blob Storage */}
        <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
          <label className="text-xs font-medium text-slate-600 block mb-1 flex items-center">
            <HardDrive className="w-3.5 h-3.5 mr-1 text-slate-500" />
            Blob Storage (GB)
          </label>
          <input
            type="number"
            min={0}
            step={10}
            value={assumptions.blob_storage_gb}
            onChange={(e) => updateField("blob_storage_gb", Math.max(0, parseFloat(e.target.value) || 0))}
            className="w-full text-sm font-semibold p-1.5 rounded border border-slate-300 bg-white"
          />
        </div>

        {/* Monthly Data Egress */}
        <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
          <label className="text-xs font-medium text-slate-600 block mb-1">
            Monthly Egress (GB)
          </label>
          <input
            type="number"
            min={0}
            step={10}
            value={assumptions.monthly_egress_gb}
            onChange={(e) => updateField("monthly_egress_gb", Math.max(0, parseFloat(e.target.value) || 0))}
            className="w-full text-sm font-semibold p-1.5 rounded border border-slate-300 bg-white"
          />
        </div>

        {/* Monthly AI Tokens */}
        <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
          <label className="text-xs font-medium text-slate-600 block mb-1 flex items-center">
            <Cpu className="w-3.5 h-3.5 mr-1 text-purple-600" />
            AI Foundry Tokens / Mo
          </label>
          <input
            type="number"
            min={0}
            step={500000}
            value={assumptions.ai_support_monthly_tokens}
            onChange={(e) => updateField("ai_support_monthly_tokens", Math.max(0, parseInt(e.target.value) || 0))}
            className="w-full text-sm font-semibold p-1.5 rounded border border-slate-300 bg-white"
          />
        </div>
      </div>

      {/* HA Toggle & Safety Buffer Slider */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-3 border-t border-slate-100">
        {/* High Availability Switch */}
        <div className="flex items-center justify-between p-3.5 bg-slate-50 rounded-lg border border-slate-200">
          <div className="flex items-center space-x-2.5">
            <Shield className={`w-5 h-5 ${assumptions.ha_required ? "text-emerald-600" : "text-slate-400"}`} />
            <div>
              <div className="text-xs font-bold text-slate-800">
                Zone-Redundant High Availability
              </div>
              <div className="text-[11px] text-slate-500">
                {assumptions.ha_required
                  ? "Multi-zone compute replicas & database standby enabled (2x DB compute allocation)."
                  : "Single availability zone (lower cost, reduced SLA)."}
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={() => updateField("ha_required", !assumptions.ha_required)}
            className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
              assumptions.ha_required ? "bg-emerald-600" : "bg-slate-300"
            }`}
          >
            <span
              className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                assumptions.ha_required ? "translate-x-5" : "translate-x-0"
              }`}
            />
          </button>
        </div>

        {/* Safety Buffer Percentage Slider */}
        <div className="p-3.5 bg-slate-50 rounded-lg border border-slate-200 flex flex-col justify-center">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs font-bold text-slate-800 flex items-center">
              <DollarSign className="w-3.5 h-3.5 mr-1 text-slate-500" />
              FinOps Safety Buffer
            </span>
            <span className="text-xs font-mono font-bold text-blue-700 bg-blue-100 px-2 py-0.5 rounded">
              +{parseFloat(safetyBufferPct).toFixed(0)}%
            </span>
          </div>
          <input
            type="range"
            min="0"
            max="40"
            step="5"
            value={safetyBufferPct}
            onChange={(e) => onSafetyBufferChange(e.target.value)}
            className="w-full accent-blue-600 cursor-pointer"
          />
          <div className="flex justify-between text-[10px] text-slate-400 mt-1">
            <span>0% (Raw BOM)</span>
            <span>15% (Recommended)</span>
            <span>40% (Peak Volatility)</span>
          </div>
        </div>
      </div>
    </section>
  );
};

