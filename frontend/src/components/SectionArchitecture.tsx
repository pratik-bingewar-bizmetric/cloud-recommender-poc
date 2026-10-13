"use client";

import React, { useState } from "react";
import {
  Layers,
  Plus,
  Trash2,
  Server,
  Database,
  HardDrive,
  Cpu,
  Shield,
  Activity,
  Network,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  FileText,
  X,
} from "lucide-react";
import { ArchitectureComponent, ServiceCategory } from "@/types";
import { MermaidDiagram } from "./MermaidDiagram";

interface SectionArchitectureProps {
  architectureDescription: string;
  mermaidDiagram: string;
  components: ArchitectureComponent[];
  onComponentsChange: (updated: ArchitectureComponent[]) => void;
}

const CATEGORY_META: Record<
  ServiceCategory,
  { icon: React.ReactNode; badge: string; label: string }
> = {
  compute: {
    icon: <Server className="w-4 h-4 text-blue-600" />,
    badge: "bg-blue-50 text-blue-700 border-blue-200/80",
    label: "Compute",
  },
  database: {
    icon: <Database className="w-4 h-4 text-emerald-600" />,
    badge: "bg-emerald-50 text-emerald-700 border-emerald-200/80",
    label: "Database",
  },
  storage: {
    icon: <HardDrive className="w-4 h-4 text-amber-600" />,
    badge: "bg-amber-50 text-amber-800 border-amber-200/80",
    label: "Storage",
  },
  networking: {
    icon: <Network className="w-4 h-4 text-cyan-600" />,
    badge: "bg-cyan-50 text-cyan-800 border-cyan-200/80",
    label: "Networking",
  },
  security: {
    icon: <Shield className="w-4 h-4 text-rose-600" />,
    badge: "bg-rose-50 text-rose-700 border-rose-200/80",
    label: "Security",
  },
  monitoring: {
    icon: <Activity className="w-4 h-4 text-indigo-600" />,
    badge: "bg-indigo-50 text-indigo-700 border-indigo-200/80",
    label: "Monitoring",
  },
  ai_ml: {
    icon: <Cpu className="w-4 h-4 text-purple-600" />,
    badge: "bg-purple-50 text-purple-700 border-purple-200/80",
    label: "AI / ML",
  },
  integration: {
    icon: <Layers className="w-4 h-4 text-slate-600" />,
    badge: "bg-slate-100 text-slate-700 border-slate-200/80",
    label: "Integration",
  },
};

const AVAILABLE_CATALOG_SERVICES = [
  {
    service_id: "azure-key-vault",
    service_name: "Azure Key Vault",
    category: "security" as ServiceCategory,
    sku_or_tier: "Standard",
    rationale: "Hardware security modules, secrets management, and TLS certificates.",
  },
  {
    service_id: "azure-monitor",
    service_name: "Azure Monitor / Log Analytics",
    category: "monitoring" as ServiceCategory,
    sku_or_tier: "Pay-As-You-Go",
    rationale: "Centralized application telemetry, container diagnostics, and metrics.",
  },
  {
    service_id: "azure-blob-storage",
    service_name: "Azure Blob Storage",
    category: "storage" as ServiceCategory,
    sku_or_tier: "Hot LRS",
    rationale: "Scalable object storage for customer uploads and document assets.",
  },
  {
    service_id: "azure-container-apps",
    service_name: "Azure Container Apps",
    category: "compute" as ServiceCategory,
    sku_or_tier: "Consumption 0.5 vCPU 1.0 GiB",
    rationale: "Serverless microservice container hosting with built-in KEDA scaling.",
  },
  {
    service_id: "azure-app-service",
    service_name: "Azure App Service (Linux)",
    category: "compute" as ServiceCategory,
    sku_or_tier: "B1 Basic",
    rationale: "Managed web app hosting for frontend web portals and REST APIs.",
  },
  {
    service_id: "azure-openai-foundry",
    service_name: "Azure AI Foundry / OpenAI",
    category: "ai_ml" as ServiceCategory,
    sku_or_tier: "GPT-4o Standard",
    rationale: "Managed LLM endpoint for customer assistant and automated summarization.",
  },
  {
    service_id: "azure-front-door",
    service_name: "Azure Front Door",
    category: "networking" as ServiceCategory,
    sku_or_tier: "Standard",
    rationale: "Global edge load balancing, SSL offload, and CDN acceleration.",
  },
  {
    service_id: "azure-web-application-firewall",
    service_name: "Azure Web Application Firewall (WAF)",
    category: "security" as ServiceCategory,
    sku_or_tier: "Standard Policy",
    rationale: "OWASP core ruleset and custom edge Layer-7 request protection.",
  },
];

const SERVICE_SKU_OPTIONS: Record<string, string[]> = {
  "azure-front-door": ["Standard", "Premium"],
  "azure-web-application-firewall": [
    "Standard Policy",
    "Premium Policy",
    "Application Gateway WAF v2",
  ],
  "azure-app-service": ["B1 Basic", "P1v3 Premium"],
  "azure-postgres-flexible": ["Burstable B1ms", "General Purpose D2ds_v5"],
};

const CORE_CATEGORIES: ServiceCategory[] = [
  "compute",
  "database",
  "storage",
  "networking",
  "ai_ml",
];

export const SectionArchitecture: React.FC<SectionArchitectureProps> = ({
  architectureDescription,
  mermaidDiagram,
  components,
  onComponentsChange,
}) => {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [showAddModal, setShowAddModal] = useState<boolean>(false);
  const [summaryExpanded, setSummaryExpanded] = useState<boolean>(true);
  const [activeFilter, setActiveFilter] = useState<"all" | "core" | "supporting">("all");

  const handleRemoveComponent = (id: string) => {
    onComponentsChange(components.filter((c) => c.component_id !== id));
  };

  const handleQuantityChange = (id: string, delta: number) => {
    onComponentsChange(
      components.map((c) => {
        if (c.component_id === id) {
          const nextQty = Math.max(1, c.quantity + delta);
          return { ...c, quantity: nextQty };
        }
        return c;
      })
    );
  };

  const handleSkuChange = (id: string, nextSku: string) => {
    onComponentsChange(
      components.map((c) => {
        if (c.component_id === id) {
          return { ...c, sku_or_tier: nextSku };
        }
        return c;
      })
    );
  };

  const handleAddComponent = (template: (typeof AVAILABLE_CATALOG_SERVICES)[0]) => {
    const newComp: ArchitectureComponent = {
      component_id: `comp-${Date.now().toString(36)}`,
      category: template.category,
      service_id: template.service_id,
      service_name: template.service_name,
      sku_or_tier: template.sku_or_tier,
      quantity: 1,
      monthly_cost: "0.00",
      dependencies: [],
      rationale: template.rationale,
      known_risks: [],
    };
    onComponentsChange([...components, newComp]);
    setShowAddModal(false);
  };

  const coreComponents = components.filter((c) => CORE_CATEGORIES.includes(c.category));
  const supportingComponents = components.filter(
    (c) => !CORE_CATEGORIES.includes(c.category)
  );

  const displayedComponents =
    activeFilter === "core"
      ? coreComponents
      : activeFilter === "supporting"
        ? supportingComponents
        : components;

  return (
    <section
      id="section-architecture"
      className="scroll-mt-28 bg-white rounded-2xl border border-slate-200/90 shadow-card p-5 sm:p-6 lg:p-7 mb-6 transition-shadow"
    >
      {/* Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 mb-5 border-b border-slate-100 gap-3">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-xl bg-blue-50 border border-blue-200/70 text-blue-700 text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">
            03
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base sm:text-lg font-semibold text-slate-900 tracking-tight">
                Production Azure Architecture Blueprint
              </h2>
              <span className="inline-flex items-center px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200/70 text-[11px] font-semibold">
                {components.length} Services
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              AI-synthesized topology tailored to your requirements. Add, remove, change SKU tiers, or scale service instances to evaluate alternatives in real time.
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setShowAddModal(true)}
          className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-blue-200 bg-blue-50/70 hover:bg-blue-100/80 text-blue-700 text-xs font-semibold transition self-start sm:self-auto"
        >
          <Plus className="w-4 h-4" />
          <span>Add Azure Service</span>
        </button>
      </div>

      {/* Collapsible Architecture Narrative Panel */}
      {architectureDescription && (
        <div className="mb-6 rounded-xl border border-slate-200/90 bg-slate-50/70 overflow-hidden">
          <button
            type="button"
            onClick={() => setSummaryExpanded((prev) => !prev)}
            aria-expanded={summaryExpanded}
            className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-slate-100/60 transition"
          >
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-900">
              <FileText className="w-4 h-4 text-blue-600 shrink-0" />
              <span>Architecture Blueprint Narrative &amp; Design Decisions</span>
            </div>
            <span className="inline-flex items-center gap-1 text-[11px] text-slate-500 font-medium">
              <span>{summaryExpanded ? "Collapse" : "Expand"}</span>
              {summaryExpanded ? (
                <ChevronUp className="w-3.5 h-3.5" />
              ) : (
                <ChevronDown className="w-3.5 h-3.5" />
              )}
            </span>
          </button>
          {summaryExpanded && (
            <div className="px-4 pb-4 pt-1 text-xs leading-relaxed text-slate-700 border-t border-slate-200/60">
              {architectureDescription}
            </div>
          )}
        </div>
      )}

      {/* Topological Diagram */}
      {mermaidDiagram && (
        <div className="mb-6">
          <MermaidDiagram chart={mermaidDiagram} />
        </div>
      )}

      {/* Component Inventory Header & Layer Filter */}
      <div>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-3.5">
          <div className="flex items-center gap-2">
            <h3 className="text-xs sm:text-sm font-semibold text-slate-900">
              Service Component Inventory
            </h3>
            <span className="text-[11px] text-slate-400">
              • Select any service to inspect security, HA &amp; scaling controls
            </span>
          </div>

          {/* Grouping Filter Tabs (Primary Deployment vs Supporting/Governance) */}
          <div
            role="tablist"
            aria-label="Filter components by architectural layer"
            className="inline-flex items-center bg-slate-100 p-1 rounded-xl border border-slate-200/80 text-xs self-start sm:self-auto"
          >
            <button
              type="button"
              role="tab"
              aria-selected={activeFilter === "all"}
              onClick={() => setActiveFilter("all")}
              className={`px-2.5 py-1 rounded-lg font-medium transition ${
                activeFilter === "all"
                  ? "bg-white text-slate-900 shadow-2xs font-semibold"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              All ({components.length})
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeFilter === "core"}
              onClick={() => setActiveFilter("core")}
              className={`px-2.5 py-1 rounded-lg font-medium transition ${
                activeFilter === "core"
                  ? "bg-white text-blue-700 shadow-2xs font-semibold"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Primary Workload ({coreComponents.length})
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeFilter === "supporting"}
              onClick={() => setActiveFilter("supporting")}
              className={`px-2.5 py-1 rounded-lg font-medium transition ${
                activeFilter === "supporting"
                  ? "bg-white text-indigo-700 shadow-2xs font-semibold"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Security &amp; Ops ({supportingComponents.length})
            </button>
          </div>
        </div>

        {/* Component Cards List */}
        <div className="space-y-2.5">
          {displayedComponents.map((comp) => {
            const isExpanded = expandedId === comp.component_id;
            const meta = CATEGORY_META[comp.category] || {
              icon: <Server className="w-4 h-4 text-slate-500" />,
              badge: "bg-slate-100 text-slate-700 border-slate-200",
              label: comp.category,
            };
            const isUnpriced =
              comp.pricing_status === "unpriced" ||
              comp.missing_price_warning != null;
            const isBundled = comp.pricing_status === "bundled";
            const skuOptions = SERVICE_SKU_OPTIONS[comp.service_id];

            return (
              <div
                key={comp.component_id}
                className={`border rounded-xl transition-all overflow-hidden ${
                  isExpanded
                    ? "border-blue-300 bg-white shadow-card"
                    : "border-slate-200/90 bg-white hover:border-slate-300"
                }`}
              >
                <div className="p-3.5 sm:p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  {/* Left: Service Identity */}
                  <div
                    role="button"
                    tabIndex={0}
                    aria-expanded={isExpanded}
                    onClick={() =>
                      setExpandedId(isExpanded ? null : comp.component_id)
                    }
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setExpandedId(isExpanded ? null : comp.component_id);
                      }
                    }}
                    className="flex items-start gap-3 cursor-pointer flex-grow min-w-0"
                  >
                    <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-200/80 shrink-0 mt-0.5">
                      {meta.icon}
                    </div>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold text-sm text-slate-900">
                          {comp.service_name}
                        </span>
                        <span
                          className={`text-[10px] uppercase font-mono font-semibold px-2 py-0.5 rounded-md border ${meta.badge}`}
                        >
                          {meta.label}
                        </span>
                        {isUnpriced && (
                          <span className="inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-md bg-amber-50 text-amber-800 border border-amber-200">
                            <AlertTriangle className="w-3 h-3 text-amber-600" />
                            Unpriced / Missing Rate
                          </span>
                        )}
                        {isBundled && (
                          <span className="inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-md bg-teal-50 text-teal-800 border border-teal-200">
                            Bundled in Front Door Premium
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-slate-500 mt-0.5 flex flex-wrap items-center gap-x-2">
                        <span className="font-mono font-medium text-slate-700">
                          {comp.sku_or_tier}
                        </span>
                        {comp.workload_quantity && comp.workload_unit && !isUnpriced && (
                          <span className="text-slate-400">
                            • {comp.workload_quantity} {comp.workload_unit}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Right: SKU Selector, Quantity Stepper, Monthly Cost & Actions */}
                  <div className="flex flex-wrap items-center justify-between sm:justify-end gap-2.5 border-t sm:border-t-0 pt-2.5 sm:pt-0 border-slate-100 shrink-0">
                    {/* SKU / Tier Selector (when service supports multiple SKUs) */}
                    {skuOptions && (
                      <select
                        aria-label={`Select SKU tier for ${comp.service_name}`}
                        value={
                          skuOptions.includes(comp.sku_or_tier)
                            ? comp.sku_or_tier
                            : skuOptions[0]
                        }
                        onChange={(e) =>
                          handleSkuChange(comp.component_id, e.target.value)
                        }
                        className="text-xs font-mono font-medium bg-slate-50 border border-slate-200 rounded-lg px-2 py-1.5 text-slate-800 hover:border-blue-300 focus:outline-hidden focus:ring-2 focus:ring-blue-500/20"
                      >
                        {skuOptions.map((skuOpt) => (
                          <option key={skuOpt} value={skuOpt}>
                            {skuOpt}
                          </option>
                        ))}
                      </select>
                    )}

                    {/* Quantity Stepper */}
                    <div className="inline-flex items-center gap-1 bg-slate-100/90 p-1 rounded-lg border border-slate-200/80">
                      <span className="text-[10px] text-slate-500 px-1.5 font-medium">
                        Qty
                      </span>
                      <button
                        type="button"
                        aria-label={`Decrease quantity for ${comp.service_name}`}
                        onClick={() => handleQuantityChange(comp.component_id, -1)}
                        className="w-6 h-6 flex items-center justify-center rounded-md bg-white text-slate-700 hover:bg-slate-200 text-xs font-bold shadow-2xs transition"
                      >
                        -
                      </button>
                      <span className="text-xs font-mono font-bold px-2 text-slate-900 min-w-[24px] text-center">
                        {comp.quantity}
                      </span>
                      <button
                        type="button"
                        aria-label={`Increase quantity for ${comp.service_name}`}
                        onClick={() => handleQuantityChange(comp.component_id, 1)}
                        className="w-6 h-6 flex items-center justify-center rounded-md bg-white text-slate-700 hover:bg-slate-200 text-xs font-bold shadow-2xs transition"
                      >
                        +
                      </button>
                    </div>

                    {/* Monthly Cost */}
                    <div className="text-right min-w-[100px]">
                      {isUnpriced ? (
                        <>
                          <div className="text-xs font-bold text-amber-800 font-mono">
                            Unpriced
                          </div>
                          <div className="text-[10px] text-amber-600">
                            missing verified rate
                          </div>
                        </>
                      ) : isBundled ? (
                        <>
                          <div className="text-sm font-bold text-teal-800 font-mono">
                            $0.00
                          </div>
                          <div className="text-[10px] text-teal-600 font-medium">
                            Bundled (FD Premium)
                          </div>
                        </>
                      ) : (
                        <>
                          <div className="text-sm font-bold text-slate-900 font-mono">
                            ${parseFloat(comp.monthly_cost).toFixed(2)}
                          </div>
                          <div className="text-[10px] text-slate-400">
                            {comp.pricing_status === "provisional"
                              ? "provisional / mo"
                              : "verified / month"}
                          </div>
                        </>
                      )}
                    </div>

                    {/* Remove Button */}
                    <button
                      type="button"
                      onClick={() => handleRemoveComponent(comp.component_id)}
                      aria-label={`Remove ${comp.service_name}`}
                      className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition"
                      title="Remove component"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>

                    {/* Expand Details Toggle */}
                    <button
                      type="button"
                      aria-label={
                        isExpanded ? "Collapse component details" : "Expand component details"
                      }
                      onClick={() =>
                        setExpandedId(isExpanded ? null : comp.component_id)
                      }
                      className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition"
                    >
                      {isExpanded ? (
                        <ChevronUp className="w-4 h-4" />
                      ) : (
                        <ChevronDown className="w-4 h-4" />
                      )}
                    </button>
                  </div>
                </div>

                {/* Expanded Component Details Drawer */}
                {isExpanded && (
                  <div className="px-4 py-3.5 bg-slate-50/80 border-t border-slate-200/70 text-xs space-y-2.5 text-slate-700">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div className="p-3 rounded-lg bg-white border border-slate-200/80">
                        <span className="text-[11px] font-semibold text-slate-900 block mb-0.5">
                          Architectural Rationale
                        </span>
                        <p className="text-slate-600 leading-relaxed">{comp.rationale}</p>
                      </div>

                      {comp.pricing_assumptions && (
                        <div className="p-3 rounded-lg bg-blue-50/50 border border-blue-200/70">
                          <span className="text-[11px] font-semibold text-blue-950 block mb-0.5">
                            Deterministic Pricing Formula
                          </span>
                          <p className="text-blue-900 font-mono text-[11px] leading-relaxed">
                            {comp.pricing_assumptions}
                          </p>
                        </div>
                      )}
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                      {comp.security_considerations && (
                        <div className="p-2.5 rounded-lg bg-white border border-slate-200/80">
                          <span className="text-[11px] font-semibold text-slate-900 block mb-0.5">
                            Security Controls
                          </span>
                          <p className="text-[11px] text-slate-600">
                            {comp.security_considerations}
                          </p>
                        </div>
                      )}
                      {comp.reliability_considerations && (
                        <div className="p-2.5 rounded-lg bg-white border border-slate-200/80">
                          <span className="text-[11px] font-semibold text-slate-900 block mb-0.5">
                            Reliability &amp; HA
                          </span>
                          <p className="text-[11px] text-slate-600">
                            {comp.reliability_considerations}
                          </p>
                        </div>
                      )}
                      {comp.scaling_considerations && (
                        <div className="p-2.5 rounded-lg bg-white border border-slate-200/80">
                          <span className="text-[11px] font-semibold text-slate-900 block mb-0.5">
                            Scaling Behavior
                          </span>
                          <p className="text-[11px] text-slate-600">
                            {comp.scaling_considerations}
                          </p>
                        </div>
                      )}
                    </div>

                    {comp.known_risks && comp.known_risks.length > 0 && (
                      <div className="p-2.5 rounded-lg bg-amber-50/70 border border-amber-200/80 text-[11px] text-amber-900">
                        <span className="font-semibold mr-1.5">Component Risks:</span>
                        {comp.known_risks.join(" • ")}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Add Service Component Modal */}
      {showAddModal && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="add-service-modal-title"
          className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center z-50 p-4"
        >
          <div className="bg-white rounded-2xl shadow-floating border border-slate-200 max-w-lg w-full p-5 sm:p-6">
            <div className="flex items-start justify-between gap-3 mb-3">
              <div>
                <h3
                  id="add-service-modal-title"
                  className="text-base font-semibold text-slate-900"
                >
                  Add Azure Service Component
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Select a supported Azure service to attach to the architecture and trigger immediate cost recalculation.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowAddModal(false)}
                aria-label="Close modal"
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-2 max-h-80 overflow-y-auto mb-5 pr-1">
              {AVAILABLE_CATALOG_SERVICES.map((item) => {
                const meta = CATEGORY_META[item.category];
                return (
                  <button
                    key={item.service_id}
                    type="button"
                    onClick={() => handleAddComponent(item)}
                    className="w-full text-left p-3.5 border border-slate-200 rounded-xl hover:bg-blue-50/60 hover:border-blue-300 transition flex items-start justify-between gap-3"
                  >
                    <div className="flex items-start gap-2.5">
                      <div className="p-2 rounded-lg bg-slate-50 border border-slate-200 shrink-0 mt-0.5">
                        {meta?.icon}
                      </div>
                      <div>
                        <div className="font-semibold text-xs text-slate-900">
                          {item.service_name}
                        </div>
                        <div className="text-[11px] text-slate-500 mt-0.5">
                          <span className="font-mono text-slate-700">{item.sku_or_tier}</span> •{" "}
                          {item.rationale}
                        </div>
                      </div>
                    </div>
                    <span className="text-[10px] uppercase font-mono font-semibold px-2 py-0.5 bg-slate-100 rounded-md text-slate-700 border border-slate-200 shrink-0">
                      {item.category}
                    </span>
                  </button>
                );
              })}
            </div>

            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => setShowAddModal(false)}
                className="px-4 py-2 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-xl transition"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
};
