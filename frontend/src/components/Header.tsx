"use client";

import React from "react";
import { Cloud, ShieldCheck, Calculator, Sparkles } from "lucide-react";

export const Header: React.FC = () => {
  return (
    <header className="border-b border-slate-200 bg-white sticky top-0 z-50 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3.5 flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div className="flex items-center space-x-3">
          <div className="bg-blue-600 text-white p-2 rounded-lg shadow-sm">
            <Cloud className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-xl font-bold text-slate-900 tracking-tight">
                Cloud Recommender
              </h1>
              <span className="bg-blue-100 text-blue-800 text-xs font-semibold px-2 py-0.5 rounded-full border border-blue-200">
                Phase A POC
              </span>
            </div>
            <p className="text-xs text-slate-500 font-medium">
              AI Cloud Architect & Deterministic Cost Simulator
            </p>
          </div>
        </div>

        {/* Operational Guardrails Pill Badges */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="inline-flex items-center px-2.5 py-1 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200 font-medium">
            <ShieldCheck className="w-3.5 h-3.5 mr-1 text-emerald-600" />
            Advisory Only (Zero-Execution)
          </span>
          <span className="inline-flex items-center px-2.5 py-1 rounded-md bg-purple-50 text-purple-700 border border-purple-200 font-medium">
            <Sparkles className="w-3.5 h-3.5 mr-1 text-purple-600" />
            Azure AI Foundry
          </span>
          <span className="inline-flex items-center px-2.5 py-1 rounded-md bg-blue-50 text-blue-700 border border-blue-200 font-medium">
            <Calculator className="w-3.5 h-3.5 mr-1 text-blue-600" />
            Azure Retail Prices API
          </span>
        </div>
      </div>
    </header>
  );
};

