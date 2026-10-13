"use client";

import React, { useState } from "react";
import {
  Zap,
  Shield,
  HardDrive,
  Cpu,
  DollarSign,
  Users,
  Activity,
  ArrowUpRight,
  Sliders,
} from "lucide-react";
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
  const [lastChangedField, setLastChangedField] = useState<string | null>(null);

  const updateField = <K extends keyof WorkloadAssumptions>(
    key: K,
    val: WorkloadAssumptions[K]
  ) => {
    setLastChangedField(String(key));
    onAssumptionsChange({
      ...assumptions,
      [key]: val,
    });
  };

  // Calculated derived metrics (read-only indicators)
  const estDailyRequests =
    assumptions.monthly_active_users * assumptions.requests_per_user_per_day;
  const totalStorageGb = assumptions.db_storage_gb + assumptions.blob_storage_gb;
  const aiTokensMillions = (assumptions.ai_support_monthly_tokens / 1_000_000).toFixed(2);

  return (
    <section
      id="section-sizing"
      className="scroll-mt-28 bg-white rounded-2xl border border-slate-200/90 shadow-card p-5 sm:p-6 lg:p-7 mb-6 transition-shadow"
    >
      {/* Header Row */}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between pb-4 mb-5 border-b border-slate-100 gap-3">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-xl bg-blue-50 border border-blue-200/70 text-blue-700 text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">
            02
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base sm:text-lg font-semibold text-slate-900 tracking-tight">
                Workload Sizing &amp; FinOps Parameters
              </h2>
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 text-[11px] font-medium">
                <Sliders className="w-3 h-3 text-blue-600" />
                Live Recalculation
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Adjust scale, storage, and availability parameters. Modifications immediately recalculate deterministic Azure pricing without calling the LLM.
            </p>
          </div>
        </div>

        {/* Scale Preset Segmented Control */}
        <div
          role="group"
          aria-label="Workload scale presets"
          className="inline-flex items-center bg-slate-100/90 p-1 rounded-xl border border-slate-200/80 self-start lg:self-auto"
        >
          <span className="text-[11px] font-semibold text-slate-500 px-2.5 flex items-center gap-1">
            <Zap className="w-3.5 h-3.5 text-amber-500" />
            <span>Preset:</span>
          </span>
          {[
            { val: 21, label: "21 (Pilot)" },
            { val: 51, label: "51 (SME)" },
            { val: 10000, label: "10k (Scale)" },
          ].map((item) => {
            const active = assumptions.customer_count === item.val;
            return (
              <button
                key={item.val}
                type="button"
                onClick={() => {
                  setLastChangedField("preset");
                  onPresetSelect(item.val);
                }}
                className={`text-xs px-3 py-1.5 rounded-lg font-semibold transition ${
                  active
                    ? "bg-white text-blue-700 shadow-2xs border border-slate-200/90"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                {item.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Derived Telemetry Strip (Distinguishes Calculated Outputs from Editable Inputs) */}
      <div className="mb-5 p-3 rounded-xl bg-slate-50/90 border border-slate-200/80 flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-2 text-slate-600 font-medium">
          <span className="px-2 py-0.5 rounded bg-slate-200/80 text-slate-700 text-[10px] font-mono uppercase font-semibold">
            Calculated Outputs
          </span>
          <span>Real-time derived workload metrics from editable parameters below:</span>
        </div>
        <div className="flex flex-wrap items-center gap-4 font-mono text-xs">
          <div>
            <span className="text-slate-400 mr-1">Est. Daily Requests:</span>
            <span className="font-semibold text-slate-800">
              {estDailyRequests.toLocaleString()} req/day
            </span>
          </div>
          <span className="text-slate-300" aria-hidden="true">
            |
          </span>
          <div>
            <span className="text-slate-400 mr-1">Provisioned Storage:</span>
            <span className="font-semibold text-slate-800">{totalStorageGb} GB</span>
          </div>
          <span className="text-slate-300" aria-hidden="true">
            |
          </span>
          <div>
            <span className="text-slate-400 mr-1">AI Token Volume:</span>
            <span className="font-semibold text-slate-800">{aiTokensMillions}M / mo</span>
          </div>
        </div>
      </div>

      {/* 8-Parameter Sizing Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 mb-5">
        {/* 1. Customer Count */}
        <div
          className={`p-3.5 rounded-xl border transition ${
            lastChangedField === "customer_count"
              ? "bg-blue-50/30 border-blue-300"
              : "bg-slate-50/60 border-slate-200/90 hover:border-slate-300"
          }`}
        >
          <div className="flex items-center justify-between mb-1">
            <label
              htmlFor="input-customer-count"
              className="text-xs font-semibold text-slate-700 flex items-center gap-1.5"
            >
              <Users className="w-3.5 h-3.5 text-blue-600" />
              <span>Customer Count</span>
            </label>
            <span className="text-[10px] font-mono text-slate-400">tenants/users</span>
          </div>
          <div className="relative">
            <input
              id="input-customer-count"
              type="number"
              min={1}
              value={assumptions.customer_count}
              onChange={(e) =>
                updateField("customer_count", Math.max(1, parseInt(e.target.value) || 1))
              }
              className="w-full text-sm font-mono font-semibold px-3 py-2 rounded-lg border border-slate-300 bg-white text-slate-900 focus:border-blue-600"
            />
          </div>
          <p className="text-[11px] text-slate-400 mt-1">
            Drives compute tier &amp; DB sizing thresholds
          </p>
        </div>

        {/* 2. Monthly Active Users (MAU) */}
        <div
          className={`p-3.5 rounded-xl border transition ${
            lastChangedField === "monthly_active_users"
              ? "bg-blue-50/30 border-blue-300"
              : "bg-slate-50/60 border-slate-200/90 hover:border-slate-300"
          }`}
        >
          <div className="flex items-center justify-between mb-1">
            <label
              htmlFor="input-mau"
              className="text-xs font-semibold text-slate-700 flex items-center gap-1.5"
            >
              <Users className="w-3.5 h-3.5 text-indigo-600" />
              <span>Monthly Active Users</span>
            </label>
            <span className="text-[10px] font-mono text-slate-400">MAU</span>
          </div>
          <input
            id="input-mau"
            type="number"
            min={1}
            value={assumptions.monthly_active_users}
            onChange={(e) =>
              updateField("monthly_active_users", Math.max(1, parseInt(e.target.value) || 1))
            }
            className="w-full text-sm font-mono font-semibold px-3 py-2 rounded-lg border border-slate-300 bg-white text-slate-900 focus:border-blue-600"
          />
          <p className="text-[11px] text-slate-400 mt-1">
            Active unique monthly authenticated users
          </p>
        </div>

        {/* 3. Peak Requests / Sec (RPS) */}
        <div
          className={`p-3.5 rounded-xl border transition ${
            lastChangedField === "peak_rps"
              ? "bg-blue-50/30 border-blue-300"
              : "bg-slate-50/60 border-slate-200/90 hover:border-slate-300"
          }`}
        >
          <div className="flex items-center justify-between mb-1">
            <label
              htmlFor="input-peak-rps"
              className="text-xs font-semibold text-slate-700 flex items-center gap-1.5"
            >
              <Activity className="w-3.5 h-3.5 text-blue-600" />
              <span>Peak Throughput</span>
            </label>
            <span className="text-[10px] font-mono text-slate-400">req / sec</span>
          </div>
          <input
            id="input-peak-rps"
            type="number"
            min={0.1}
            step={0.5}
            value={assumptions.peak_rps}
            onChange={(e) =>
              updateField("peak_rps", Math.max(0.1, parseFloat(e.target.value) || 0.1))
            }
            className="w-full text-sm font-mono font-semibold px-3 py-2 rounded-lg border border-slate-300 bg-white text-slate-900 focus:border-blue-600"
          />
          <p className="text-[11px] text-slate-400 mt-1">
            Concurrent peak API &amp; web request rate
          </p>
        </div>

        {/* 4. Requests per User / Day */}
        <div
          className={`p-3.5 rounded-xl border transition ${
            lastChangedField === "requests_per_user_per_day"
              ? "bg-blue-50/30 border-blue-300"
              : "bg-slate-50/60 border-slate-200/90 hover:border-slate-300"
          }`}
        >
          <div className="flex items-center justify-between mb-1">
            <label
              htmlFor="input-req-per-day"
              className="text-xs font-semibold text-slate-700 flex items-center gap-1.5"
            >
              <Activity className="w-3.5 h-3.5 text-indigo-600" />
              <span>Requests / User / Day</span>
            </label>
            <span className="text-[10px] font-mono text-slate-400">req / day</span>
          </div>
          <input
            id="input-req-per-day"
            type="number"
            min={1}
            value={assumptions.requests_per_user_per_day}
            onChange={(e) =>
              updateField(
                "requests_per_user_per_day",
                Math.max(1, parseInt(e.target.value) || 1)
              )
            }
            className="w-full text-sm font-mono font-semibold px-3 py-2 rounded-lg border border-slate-300 bg-white text-slate-900 focus:border-blue-600"
          />
          <p className="text-[11px] text-slate-400 mt-1">
            Average daily interactions per active user
          </p>
        </div>

        {/* 5. PostgreSQL Storage (GB) */}
        <div
          className={`p-3.5 rounded-xl border transition ${
            lastChangedField === "db_storage_gb"
              ? "bg-blue-50/30 border-blue-300"
              : "bg-slate-50/60 border-slate-200/90 hover:border-slate-300"
          }`}
        >
          <div className="flex items-center justify-between mb-1">
            <label
              htmlFor="input-db-storage"
              className="text-xs font-semibold text-slate-700 flex items-center gap-1.5"
            >
              <HardDrive className="w-3.5 h-3.5 text-emerald-600" />
              <span>PostgreSQL Storage</span>
            </label>
            <span className="text-[10px] font-mono text-slate-400">GB</span>
          </div>
          <input
            id="input-db-storage"
            type="number"
            min={5}
            step={5}
            value={assumptions.db_storage_gb}
            onChange={(e) =>
              updateField("db_storage_gb", Math.max(5, parseFloat(e.target.value) || 5))
            }
            className="w-full text-sm font-mono font-semibold px-3 py-2 rounded-lg border border-slate-300 bg-white text-slate-900 focus:border-blue-600"
          />
          <p className="text-[11px] text-slate-400 mt-1">
            Managed Flexible Server SSD disk allocation
          </p>
        </div>

        {/* 6. Blob Storage (GB) */}
        <div
          className={`p-3.5 rounded-xl border transition ${
            lastChangedField === "blob_storage_gb"
              ? "bg-blue-50/30 border-blue-300"
              : "bg-slate-50/60 border-slate-200/90 hover:border-slate-300"
          }`}
        >
          <div className="flex items-center justify-between mb-1">
            <label
              htmlFor="input-blob-storage"
              className="text-xs font-semibold text-slate-700 flex items-center gap-1.5"
            >
              <HardDrive className="w-3.5 h-3.5 text-amber-600" />
              <span>Blob Object Storage</span>
            </label>
            <span className="text-[10px] font-mono text-slate-400">GB</span>
          </div>
          <input
            id="input-blob-storage"
            type="number"
            min={0}
            step={10}
            value={assumptions.blob_storage_gb}
            onChange={(e) =>
              updateField("blob_storage_gb", Math.max(0, parseFloat(e.target.value) || 0))
            }
            className="w-full text-sm font-mono font-semibold px-3 py-2 rounded-lg border border-slate-300 bg-white text-slate-900 focus:border-blue-600"
          />
          <p className="text-[11px] text-slate-400 mt-1">
            Hot LRS unstructured files &amp; documents
          </p>
        </div>

        {/* 7. Monthly Data Egress (GB) */}
        <div
          className={`p-3.5 rounded-xl border transition ${
            lastChangedField === "monthly_egress_gb"
              ? "bg-blue-50/30 border-blue-300"
              : "bg-slate-50/60 border-slate-200/90 hover:border-slate-300"
          }`}
        >
          <div className="flex items-center justify-between mb-1">
            <label
              htmlFor="input-egress"
              className="text-xs font-semibold text-slate-700 flex items-center gap-1.5"
            >
              <ArrowUpRight className="w-3.5 h-3.5 text-cyan-600" />
              <span>Monthly Egress</span>
            </label>
            <span className="text-[10px] font-mono text-slate-400">GB / mo</span>
          </div>
          <input
            id="input-egress"
            type="number"
            min={0}
            step={10}
            value={assumptions.monthly_egress_gb}
            onChange={(e) =>
              updateField("monthly_egress_gb", Math.max(0, parseFloat(e.target.value) || 0))
            }
            className="w-full text-sm font-mono font-semibold px-3 py-2 rounded-lg border border-slate-300 bg-white text-slate-900 focus:border-blue-600"
          />
          <p className="text-[11px] text-slate-400 mt-1">
            Internet outbound data transfer (first 100 GB free)
          </p>
        </div>

        {/* 8. Azure AI Foundry Token Volume */}
        <div
          className={`p-3.5 rounded-xl border transition ${
            lastChangedField === "ai_support_monthly_tokens"
              ? "bg-blue-50/30 border-blue-300"
              : "bg-slate-50/60 border-slate-200/90 hover:border-slate-300"
          }`}
        >
          <div className="flex items-center justify-between mb-1">
            <label
              htmlFor="input-ai-tokens"
              className="text-xs font-semibold text-slate-700 flex items-center gap-1.5"
            >
              <Cpu className="w-3.5 h-3.5 text-purple-600" />
              <span>AI Foundry Tokens</span>
            </label>
            <span className="text-[10px] font-mono text-slate-400">tokens / mo</span>
          </div>
          <input
            id="input-ai-tokens"
            type="number"
            min={0}
            step={500000}
            value={assumptions.ai_support_monthly_tokens}
            onChange={(e) =>
              updateField(
                "ai_support_monthly_tokens",
                Math.max(0, parseInt(e.target.value) || 0)
              )
            }
            className="w-full text-sm font-mono font-semibold px-3 py-2 rounded-lg border border-slate-300 bg-white text-slate-900 focus:border-blue-600"
          />
          <p className="text-[11px] text-slate-400 mt-1">
            Combined prompt &amp; completion token consumption
          </p>
        </div>
      </div>

      {/* Bottom Controls: Zone-Redundant High Availability & FinOps Safety Buffer */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4 border-t border-slate-100">
        {/* Zone-Redundant HA Switch */}
        <div
          className={`flex items-center justify-between p-4 rounded-xl border transition ${
            assumptions.ha_required
              ? "bg-emerald-50/40 border-emerald-200/90"
              : "bg-slate-50/70 border-slate-200/90"
          }`}
        >
          <div className="flex items-start gap-3 pr-3">
            <div
              className={`p-2 rounded-lg border shrink-0 mt-0.5 ${
                assumptions.ha_required
                  ? "bg-emerald-100/80 border-emerald-200 text-emerald-700"
                  : "bg-slate-200/70 border-slate-300 text-slate-500"
              }`}
            >
              <Shield className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-slate-900">
                  Zone-Redundant High Availability (HA)
                </span>
                <span
                  className={`text-[10px] font-mono font-semibold px-1.5 py-0.5 rounded ${
                    assumptions.ha_required
                      ? "bg-emerald-600 text-white"
                      : "bg-slate-200 text-slate-700"
                  }`}
                >
                  {assumptions.ha_required ? "ENABLED (2x DB)" : "SINGLE-AZ"}
                </span>
              </div>
              <p className="text-[11px] text-slate-500 mt-0.5 leading-relaxed">
                {assumptions.ha_required
                  ? "Provisions synchronous standby PostgreSQL replica & multi-zone container instances."
                  : "Single availability zone deployment for non-critical or pilot workloads."}
              </p>
            </div>
          </div>

          <button
            type="button"
            role="switch"
            aria-checked={assumptions.ha_required}
            aria-label="Toggle Zone-Redundant High Availability"
            onClick={() => updateField("ha_required", !assumptions.ha_required)}
            className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out ${
              assumptions.ha_required ? "bg-emerald-600" : "bg-slate-300"
            }`}
          >
            <span
              className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-2xs ring-0 transition duration-200 ease-in-out ${
                assumptions.ha_required ? "translate-x-5" : "translate-x-0"
              }`}
            />
          </button>
        </div>

        {/* FinOps Safety Buffer Slider */}
        <div className="p-4 rounded-xl bg-slate-50/70 border border-slate-200/90 flex flex-col justify-between">
          <div className="flex items-center justify-between mb-2">
            <div>
              <label
                htmlFor="input-safety-buffer"
                className="text-xs font-semibold text-slate-900 flex items-center gap-1.5"
              >
                <DollarSign className="w-3.5 h-3.5 text-blue-600" />
                <span>FinOps Contingency &amp; Burst Buffer</span>
              </label>
              <p className="text-[11px] text-slate-500">
                Accounts for traffic spikes, log ingestion variance, and auxiliary IP/DNS meters.
              </p>
            </div>
            <span className="text-xs font-mono font-bold text-blue-700 bg-blue-50 border border-blue-200 px-2.5 py-1 rounded-lg shrink-0">
              +{parseFloat(safetyBufferPct).toFixed(0)}%
            </span>
          </div>

          <div>
            <input
              id="input-safety-buffer"
              type="range"
              min="0"
              max="40"
              step="5"
              value={safetyBufferPct}
              onChange={(e) => onSafetyBufferChange(e.target.value)}
              className="w-full accent-blue-600 cursor-pointer"
            />
            <div className="flex justify-between text-[10px] font-medium text-slate-400 mt-1">
              <span>0% (Base BOM)</span>
              <span>15% (Recommended FinOps)</span>
              <span>40% (High Volatility)</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
