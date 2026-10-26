"use client";

import React from "react";
import {
  X,
  ShieldCheck,
  CheckCircle2,
  Calculator,
  Cpu,
} from "lucide-react";

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  backendStatus: "checking" | "online" | "offline";
  targetRegion: string;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  backendStatus,
  targetRegion,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-navy-950/40 backdrop-blur-xs animate-in fade-in duration-150">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-dialog-title"
        className="w-full max-w-xl bg-white rounded-xl border border-slate-200 shadow-modal overflow-hidden text-navy-900"
      >
        {/* Modal Header */}
        <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-blue-50 border border-blue-200 text-brand-600 flex items-center justify-center">
              <ShieldCheck className="w-4 h-4" />
            </div>
            <div>
              <h2 id="settings-dialog-title" className="text-sm font-bold text-navy-900">
                Platform Governance &amp; Integrations
              </h2>
              <p className="text-[11px] text-navy-500">
                Security boundary controls, read-only permissions, and pricing engine status.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-navy-900 hover:bg-slate-100 transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-5 space-y-4 text-xs">
          {/* Zero-Execution Guardrail Status */}
          <div className="p-3.5 rounded-lg bg-emerald-50/70 border border-emerald-200 space-y-1">
            <div className="flex items-center justify-between">
              <span className="font-bold text-navy-900 flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-accent-emerald" />
                Zero-Execution Safety Policy
              </span>
              <span className="font-mono text-[10px] uppercase font-bold text-emerald-800 bg-emerald-200/60 px-2 py-0.5 rounded">
                Active &bull; Enforced
              </span>
            </div>
            <p className="text-navy-700 leading-relaxed text-[11px]">
              This POC is strictly an advisory platform. It cannot execute infrastructure changes, create resources, or mutate cloud subscriptions. All destructive APIs are non-existent.
            </p>
          </div>

          {/* Connected Integrations Grid */}
          <div className="space-y-2.5">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
              Active Cloud Integrations
            </h3>

            {/* Azure Read-Only */}
            <div className="p-3 rounded-lg border border-slate-200 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded bg-blue-50 text-brand-600 flex items-center justify-center font-bold">
                  Az
                </div>
                <div>
                  <span className="font-semibold text-navy-900 block">Microsoft Azure</span>
                  <span className="text-[11px] text-slate-500">Role: Reader, Cost Management Reader</span>
                </div>
              </div>
              <span className="inline-flex items-center gap-1 text-[11px] text-accent-emerald font-semibold">
                <CheckCircle2 className="w-3.5 h-3.5" /> Read-Only
              </span>
            </div>

            {/* Pricing API */}
            <div className="p-3 rounded-lg border border-slate-200 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded bg-amber-50 text-accent-amber flex items-center justify-center font-bold">
                  <Calculator className="w-4 h-4" />
                </div>
                <div>
                  <span className="font-semibold text-navy-900 block">Azure Retail Prices API</span>
                  <span className="text-[11px] text-slate-500">Deterministic Engine &bull; Local SQLite Cache</span>
                </div>
              </div>
              <span className="inline-flex items-center gap-1 text-[11px] text-accent-emerald font-semibold">
                <CheckCircle2 className="w-3.5 h-3.5" /> Verified
              </span>
            </div>

            {/* AI Foundry */}
            <div className="p-3 rounded-lg border border-slate-200 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded bg-purple-50 text-accent-purple flex items-center justify-center font-bold">
                  <Cpu className="w-4 h-4" />
                </div>
                <div>
                  <span className="font-semibold text-navy-900 block">Azure AI Foundry</span>
                  <span className="text-[11px] text-slate-500">Model: gpt-5.4-mini &bull; Structured JSON outputs</span>
                </div>
              </div>
              <span className="inline-flex items-center gap-1 text-[11px] text-brand-600 font-semibold font-mono">
                {backendStatus === "online" ? "Connected" : "Standby"}
              </span>
            </div>

            {/* Google Cloud Platform */}
            <div className="p-3 rounded-lg border border-slate-200 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded bg-red-50 text-rose-600 flex items-center justify-center font-bold">
                  GCP
                </div>
                <div>
                  <span className="font-semibold text-navy-900 block">Google Cloud Platform</span>
                  <span className="text-[11px] text-slate-500">Benchmark Simulation &bull; Live Auth Supported</span>
                </div>
              </div>
              <span className="text-[11px] text-slate-500 font-medium">
                Simulation Fixture
              </span>
            </div>
          </div>

          {/* Scope & Region Configuration */}
          <div className="p-3 bg-slate-50 rounded-lg border border-slate-200 space-y-1 text-[11px] text-slate-600">
            <div className="flex justify-between">
              <span>Default Evaluation Region:</span>
              <span className="font-mono font-semibold text-navy-900">{targetRegion}</span>
            </div>
            <div className="flex justify-between">
              <span>Microsoft Fabric Layer:</span>
              <span className="text-slate-500 italic">Deferred for POC</span>
            </div>
            <div className="flex justify-between">
              <span>AWS Integration:</span>
              <span className="text-slate-500 italic">Deferred for POC</span>
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="px-5 py-3 border-t border-slate-200 bg-slate-50 flex items-center justify-between text-xs">
          <span className="text-slate-500 font-mono text-[11px]">
            Tenant: production-core-tenant
          </span>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-navy-900 hover:bg-navy-800 text-white font-medium transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
