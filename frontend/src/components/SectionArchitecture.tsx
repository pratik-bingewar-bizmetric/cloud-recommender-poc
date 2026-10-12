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
} from "lucide-react";
import { ArchitectureComponent, ServiceCategory } from "@/types";
import { MermaidDiagram } from "./MermaidDiagram";

interface SectionArchitectureProps {
  architectureDescription: string;
  mermaidDiagram: string;
  components: ArchitectureComponent[];
  onComponentsChange: (updated: ArchitectureComponent[]) => void;
}

const CATEGORY_ICONS: Record<ServiceCategory, React.ReactNode> = {
  compute: <Server className="w-4 h-4 text-blue-600" />,
  database: <Database className="w-4 h-4 text-emerald-600" />,
  storage: <HardDrive className="w-4 h-4 text-amber-600" />,
  networking: <Network className="w-4 h-4 text-cyan-600" />,
  security: <Shield className="w-4 h-4 text-rose-600" />,
  monitoring: <Activity className="w-4 h-4 text-indigo-600" />,
  ai_ml: <Cpu className="w-4 h-4 text-purple-600" />,
  integration: <Layers className="w-4 h-4 text-slate-600" />,
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
];

export const SectionArchitecture: React.FC<SectionArchitectureProps> = ({
  architectureDescription,
  mermaidDiagram,
  components,
  onComponentsChange,
}) => {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [showAddModal, setShowAddModal] = useState<boolean>(false);

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

  return (
    <section className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 mb-5 border-b border-slate-100 gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-900 flex items-center">
            <span className="w-6 h-6 rounded-full bg-blue-100 text-blue-700 text-xs font-bold flex items-center justify-center mr-2">
              C
            </span>
            Production Azure Architecture
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            AI-synthesized cloud blueprint. Add, remove, or modify components below to test architectural alternatives.
          </p>
        </div>

        <button
          type="button"
          onClick={() => setShowAddModal(true)}
          className="inline-flex items-center px-3.5 py-1.5 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold shadow-2xs transition"
        >
          <Plus className="w-3.5 h-3.5 mr-1 text-blue-600" />
          Add Service Component
        </button>
      </div>

      {/* Architecture Narrative */}
      {architectureDescription && (
        <div className="mb-6 p-4 bg-slate-50 border border-slate-200 rounded-lg text-xs leading-relaxed text-slate-700">
          <strong className="text-slate-900 font-semibold block mb-1">
            Architecture Blueprint Summary:
          </strong>
          {architectureDescription}
        </div>
      )}

      {/* Mermaid Architecture Diagram */}
      {mermaidDiagram && (
        <div className="mb-6">
          <div className="text-xs font-bold text-slate-700 mb-2 flex items-center">
            <Layers className="w-4 h-4 mr-1 text-blue-600" />
            Topological Architecture Diagram:
          </div>
          <MermaidDiagram chart={mermaidDiagram} />
        </div>
      )}

      {/* Recommended Service Components List */}
      <div>
        <div className="text-xs font-bold text-slate-700 mb-3 flex items-center justify-between">
          <span>Configured Services ({components.length}):</span>
          <span className="text-[11px] text-slate-400 font-normal">
            Click component to view security & reliability details
          </span>
        </div>

        <div className="space-y-3">
          {components.map((comp) => {
            const isExpanded = expandedId === comp.component_id;
            const categoryIcon = CATEGORY_ICONS[comp.category] || <Server className="w-4 h-4 text-slate-500" />;

            return (
              <div
                key={comp.component_id}
                className="border border-slate-200 rounded-lg bg-white hover:border-slate-300 transition overflow-hidden"
              >
                <div className="p-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div
                    className="flex items-start space-x-3 cursor-pointer flex-grow"
                    onClick={() => setExpandedId(isExpanded ? null : comp.component_id)}
                  >
                    <div className="p-2 rounded-lg bg-slate-100 border border-slate-200 mt-0.5">
                      {categoryIcon}
                    </div>
                    <div>
                      <div className="flex items-center space-x-2">
                        <span className="font-bold text-sm text-slate-900">
                          {comp.service_name}
                        </span>
                        <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 bg-slate-100 text-slate-600 rounded border border-slate-200">
                          {comp.category}
                        </span>
                      </div>
                      <div className="text-xs text-slate-500 mt-0.5">
                        <span className="font-medium text-slate-700">{comp.sku_or_tier}</span>
                        {comp.workload_quantity && comp.workload_unit && (
                          <span className="ml-2 text-slate-400">
                            • {comp.workload_quantity} {comp.workload_unit}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Quantity Controls & Cost Display */}
                  <div className="flex items-center justify-between sm:justify-end space-x-4 border-t sm:border-t-0 pt-2 sm:pt-0 border-slate-100">
                    <div className="flex items-center space-x-1.5 bg-slate-100 p-1 rounded-md border border-slate-200">
                      <span className="text-[10px] text-slate-500 px-1 font-medium">Qty:</span>
                      <button
                        type="button"
                        onClick={() => handleQuantityChange(comp.component_id, -1)}
                        className="w-5 h-5 flex items-center justify-center rounded bg-white text-slate-700 hover:bg-slate-200 text-xs font-bold shadow-2xs"
                      >
                        -
                      </button>
                      <span className="text-xs font-mono font-bold px-1.5 text-slate-800">
                        {comp.quantity}
                      </span>
                      <button
                        type="button"
                        onClick={() => handleQuantityChange(comp.component_id, 1)}
                        className="w-5 h-5 flex items-center justify-center rounded bg-white text-slate-700 hover:bg-slate-200 text-xs font-bold shadow-2xs"
                      >
                        +
                      </button>
                    </div>

                    <div className="text-right min-w-[85px]">
                      <div className="text-sm font-bold text-slate-900 font-mono">
                        ${parseFloat(comp.monthly_cost).toFixed(2)}
                      </div>
                      <div className="text-[10px] text-slate-400">per month</div>
                    </div>

                    <button
                      type="button"
                      onClick={() => handleRemoveComponent(comp.component_id)}
                      className="p-1.5 text-slate-400 hover:text-red-600 rounded transition"
                      title="Remove component"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>

                    <button
                      type="button"
                      onClick={() => setExpandedId(isExpanded ? null : comp.component_id)}
                      className="p-1 text-slate-400 hover:text-slate-600"
                    >
                      {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                {/* Expanded Details Drawer */}
                {isExpanded && (
                  <div className="px-4 py-3 bg-slate-50 border-t border-slate-100 text-xs space-y-2 text-slate-700">
                    <div>
                      <strong className="text-slate-900 font-semibold">Architectural Rationale:</strong>{" "}
                      {comp.rationale}
                    </div>
                    {comp.security_considerations && (
                      <div>
                        <strong className="text-slate-900 font-semibold">Security Controls:</strong>{" "}
                        {comp.security_considerations}
                      </div>
                    )}
                    {comp.reliability_considerations && (
                      <div>
                        <strong className="text-slate-900 font-semibold">Reliability & HA:</strong>{" "}
                        {comp.reliability_considerations}
                      </div>
                    )}
                    {comp.scaling_considerations && (
                      <div>
                        <strong className="text-slate-900 font-semibold">Scaling Characteristics:</strong>{" "}
                        {comp.scaling_considerations}
                      </div>
                    )}
                    {comp.pricing_assumptions && (
                      <div className="text-blue-800 bg-blue-50/70 p-2 rounded border border-blue-100">
                        <strong className="font-semibold">Pricing Metric:</strong> {comp.pricing_assumptions}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Add Component Modal / Dropdown */}
      {showAddModal && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl border border-slate-200 max-w-lg w-full p-6">
            <h3 className="text-base font-bold text-slate-900 mb-1">
              Add Azure Service Component
            </h3>
            <p className="text-xs text-slate-500 mb-4">
              Select an official Azure service component to attach to this architecture blueprint:
            </p>

            <div className="space-y-2 max-h-80 overflow-y-auto mb-5">
              {AVAILABLE_CATALOG_SERVICES.map((item) => (
                <div
                  key={item.service_id}
                  onClick={() => handleAddComponent(item)}
                  className="p-3 border border-slate-200 rounded-lg hover:bg-blue-50 hover:border-blue-300 cursor-pointer transition flex items-start justify-between"
                >
                  <div>
                    <div className="font-semibold text-xs text-slate-900">
                      {item.service_name}
                    </div>
                    <div className="text-[11px] text-slate-500 mt-0.5">
                      {item.sku_or_tier} • {item.rationale}
                    </div>
                  </div>
                  <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 bg-slate-100 rounded text-slate-600">
                    {item.category}
                  </span>
                </div>
              ))}
            </div>

            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => setShowAddModal(false)}
                className="px-4 py-2 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition"
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

