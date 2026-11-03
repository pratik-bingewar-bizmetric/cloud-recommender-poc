"use client";

import { CloudProvider } from "@/types";
import { ENABLE_AI_ARCHITECT } from "@/config/features";
import {
  Search,
  Globe,
  Sparkles,
  Calculator,
  AlertTriangle,
  XCircle,
  Loader2,
  Menu,
} from "lucide-react";

interface TopNavProps {
  backendStatus: "checking" | "online" | "offline";
  aiStatus: "standby" | "busy" | "verified" | "error";
  pricingStatus: "standby" | "verified" | "warning";
  monthlyTotal: string | null;
  targetRegion: string;
  onRegionChange: (region: string) => void;
  onOpenMobileMenu: () => void;
  onScrollToCost: () => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  connectedScope?: { provider: CloudProvider; name: string; id: string } | null;
  onSwitchConnection?: () => void;
}

export const TopNav: React.FC<TopNavProps> = ({
  backendStatus,
  aiStatus,
  pricingStatus,
  monthlyTotal,
  targetRegion,
  onRegionChange,
  onOpenMobileMenu,
  onScrollToCost,
  searchQuery,
  onSearchChange,
  connectedScope,
  onSwitchConnection,
}) => {
  const regions = [
    { id: "eastus", label: "East US (eastus)" },
    { id: "westeurope", label: "West Europe (westeurope)" },
    { id: "centralus", label: "Central US (centralus)" },
    { id: "southeastasia", label: "Southeast Asia (southeastasia)" },
    { id: "centralindia", label: "Central India (centralindia)" },
  ];

  return (
    <header className="topbar-surface sticky top-0 z-30 h-14 px-4 sm:px-6 flex items-center justify-between gap-3">
      {/* Left: Mobile Menu & Search Input */}
      <div className="flex items-center gap-3 flex-1 max-w-md">
        <button
          type="button"
          onClick={onOpenMobileMenu}
          className="p-1.5 rounded-lg text-slate-500 hover:text-navy-900 hover:bg-slate-100 sm:hidden transition"
          aria-label="Open mobile navigation menu"
        >
          <Menu className="w-5 h-5" />
        </button>

        <div className="relative w-full">
          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search resources, subscriptions, metrics..."
            className="w-full pl-8 pr-3 py-1.5 text-xs bg-slate-50 hover:bg-slate-100/80 focus:bg-white border border-slate-200 rounded-lg text-navy-900 placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-brand-500 transition"
          />
        </div>
      </div>

      {/* Right: Region Selector, Status Indicators & Live Cost */}
      <div className="flex items-center gap-2 sm:gap-3">
        {/* Connected Cloud Scope Badge */}
        {connectedScope ? (
          <div
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-50 border border-emerald-200 text-xs text-emerald-800"
            title={`Connected Scope: ${connectedScope.name} (${connectedScope.id})`}
          >
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="font-semibold uppercase tracking-wider text-[10px] text-emerald-700">
              {connectedScope.provider}
            </span>
            <span
              className="font-mono text-[11px] font-medium text-slate-700 hidden sm:inline max-w-[160px] truncate"
              title={`${connectedScope.name} (${connectedScope.id})`}
            >
              {connectedScope.name}
            </span>
            {onSwitchConnection && (
              <button
                type="button"
                onClick={onSwitchConnection}
                className="ml-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-white border border-emerald-300 text-emerald-700 hover:bg-emerald-100 transition shadow-2xs"
                title="Switch cloud connection scope"
              >
                Switch
              </button>
            )}
          </div>
        ) : null}

        {/* Region Selector */}
        <div className="flex items-center gap-1.5 px-2 py-1 rounded-lg border border-slate-200 bg-white text-xs">
          <Globe className="w-3.5 h-3.5 text-slate-500 shrink-0" />
          <select
            value={targetRegion}
            onChange={(e) => onRegionChange(e.target.value)}
            aria-label="Cloud Region Selector"
            className="bg-transparent text-navy-800 font-medium text-xs focus:outline-none cursor-pointer pr-1"
          >
            {regions.map((r) => (
              <option key={r.id} value={r.id}>
                {r.label}
              </option>
            ))}
          </select>
        </div>

        {/* Foundry Status Pill (Only if AI Architect is enabled) */}
        {ENABLE_AI_ARCHITECT && (
          <div className="hidden lg:flex items-center">
            {backendStatus === "offline" || aiStatus === "error" ? (
              <span
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-rose-50 text-accent-rose border border-rose-200 text-xs font-medium"
                title="Backend unreachable"
              >
                <XCircle className="w-3 h-3" />
                <span>Foundry Disconnected</span>
              </span>
            ) : aiStatus === "busy" ? (
              <span
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-blue-50 text-brand-700 border border-blue-200 text-xs font-medium"
                title="Inference active"
              >
                <Loader2 className="w-3 h-3 animate-spin text-brand-600" />
                <span>Foundry Active</span>
              </span>
            ) : (
              <span
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-slate-100 text-navy-700 border border-slate-200 text-xs font-medium"
                title="Azure AI Foundry ready"
              >
                <Sparkles className="w-3 h-3 text-brand-600" />
                <span>Foundry Ready</span>
              </span>
            )}
          </div>
        )}

        {/* Pricing Status Pill */}
        <div className="hidden xl:flex items-center">
          {pricingStatus === "warning" ? (
            <span
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-amber-50 text-accent-amber border border-amber-200 text-xs font-medium"
              title="Unverified or fallback prices detected"
            >
              <AlertTriangle className="w-3 h-3" />
              <span>Pricing Notice</span>
            </span>
          ) : (
            <span
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-emerald-50 text-accent-emerald border border-emerald-200 text-xs font-medium"
              title="Azure Retail Prices API verified"
            >
              <Calculator className="w-3 h-3" />
              <span>Retail Prices Verified</span>
            </span>
          )}
        </div>

        {/* Live Monthly Cost Pill */}
        {monthlyTotal && (
          <button
            type="button"
            onClick={onScrollToCost}
            className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-navy-900 hover:bg-navy-800 text-white text-xs font-semibold shadow-2xs transition"
            title="View Deterministic Cost Simulator"
          >
            <span className="text-slate-300 font-normal">Est.</span>
            <span className="font-mono tabular-nums">
              ${parseFloat(monthlyTotal).toLocaleString("en-US", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })}
              /mo
            </span>
          </button>
        )}
      </div>
    </header>
  );
};
