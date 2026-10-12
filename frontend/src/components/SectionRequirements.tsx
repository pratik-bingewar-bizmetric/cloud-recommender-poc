"use client";

import React from "react";
import { Sparkles, HelpCircle, CheckCircle2, AlertCircle, ArrowRight } from "lucide-react";
import { ClarifyingQuestion, WorkloadProfile } from "@/types";

interface SectionRequirementsProps {
  idea: string;
  setIdea: (val: string) => void;
  targetRegion: string;
  setTargetRegion: (val: string) => void;
  customerPreset: number;
  setCustomerPreset: (val: number) => void;
  onAnalyze: () => void;
  isAnalyzing: boolean;
  workloadProfile: WorkloadProfile | null;
  clarifyingQuestions: ClarifyingQuestion[];
  clarifyingAnswers: Record<string, string>;
  onAnswerChange: (questionId: string, answer: string) => void;
  missingRequirements: string[];
  onGenerateArchitecture: () => void;
  isGeneratingArch: boolean;
}

const PRESET_IDEAS = [
  {
    label: "Customer Platform (10,000 Users)",
    preset: 10000,
    text: "I want a customer management platform for 10,000 customers with user authentication, a web frontend, REST APIs, PostgreSQL, document storage, monitoring, high availability, and AI-powered customer support.",
  },
  {
    label: "SME Portal (51 Tenants)",
    preset: 51,
    text: "Build a multi-tenant business portal for 51 client companies. Requires secure REST API backend, relational database with daily backups, file uploads up to 50GB total, and standard Azure monitoring.",
  },
  {
    label: "Pilot API Service (21 Users)",
    preset: 21,
    text: "We need a pilot API service for 21 internal business users with lightweight serverless container hosting, PostgreSQL database, and basic log telemetry on East US.",
  },
];

const REGION_OPTIONS = [
  { id: "eastus", label: "East US (Virginia)" },
  { id: "westus2", label: "West US 2 (Washington)" },
  { id: "westeurope", label: "West Europe (Netherlands)" },
  { id: "northeurope", label: "North Europe (Ireland)" },
  { id: "southeastasia", label: "Southeast Asia (Singapore)" },
];

export const SectionRequirements: React.FC<SectionRequirementsProps> = ({
  idea,
  setIdea,
  targetRegion,
  setTargetRegion,
  customerPreset,
  setCustomerPreset,
  onAnalyze,
  isAnalyzing,
  workloadProfile,
  clarifyingQuestions,
  clarifyingAnswers,
  onAnswerChange,
  missingRequirements,
  onGenerateArchitecture,
  isGeneratingArch,
}) => {
  return (
    <section className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-6">
      <div className="flex items-center justify-between pb-4 mb-5 border-b border-slate-100">
        <div>
          <h2 className="text-lg font-bold text-slate-900 flex items-center">
            <span className="w-6 h-6 rounded-full bg-blue-100 text-blue-700 text-xs font-bold flex items-center justify-center mr-2">
              A
            </span>
            Application Idea & Requirements Ingestion
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Describe your application in plain text. Azure AI Foundry will extract structured requirements and formulate clarifying questions.
          </p>
        </div>
      </div>

      {/* Preset Quick Selectors */}
      <div className="mb-3">
        <label className="text-xs font-semibold text-slate-700 block mb-1.5">
          Or start with a verified workload archetype:
        </label>
        <div className="flex flex-wrap gap-2">
          {PRESET_IDEAS.map((p, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => {
                setIdea(p.text);
                setCustomerPreset(p.preset);
              }}
              className="text-xs px-3 py-1.5 rounded-lg border border-slate-200 bg-slate-50 hover:bg-blue-50 hover:border-blue-300 text-slate-700 hover:text-blue-700 font-medium transition"
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Natural Language Prompt Area */}
      <div className="mb-4">
        <label htmlFor="app-idea-input" className="text-xs font-semibold text-slate-700 block mb-1">
          Workload Description <span className="text-red-500">*</span>
        </label>
        <textarea
          id="app-idea-input"
          rows={4}
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
          placeholder="Describe application tiers, traffic intensity, expected user count, database needs, storage, compliance..."
          className="w-full text-sm p-3 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-slate-800"
        />
      </div>

      {/* Region & Initial Scale Preset Selectors */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">
        <div>
          <label className="text-xs font-semibold text-slate-700 block mb-1">
            Target Cloud Region
          </label>
          <select
            value={targetRegion}
            onChange={(e) => setTargetRegion(e.target.value)}
            className="w-full text-sm p-2.5 rounded-lg border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {REGION_OPTIONS.map((r) => (
              <option key={r.id} value={r.id}>
                {r.label} ({r.id})
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-xs font-semibold text-slate-700 block mb-1">
            Initial Sizing Preset (Customers)
          </label>
          <div className="grid grid-cols-3 gap-2">
            {[21, 51, 10000].map((presetVal) => (
              <button
                key={presetVal}
                type="button"
                onClick={() => setCustomerPreset(presetVal)}
                className={`text-xs py-2 px-2 rounded-lg font-semibold border transition ${
                  customerPreset === presetVal
                    ? "bg-blue-600 text-white border-blue-600 shadow-sm"
                    : "bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100"
                }`}
              >
                {presetVal === 21 && "21 (Pilot)"}
                {presetVal === 51 && "51 (SME)"}
                {presetVal === 10000 && "10,000 (Scale)"}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Analyze Button */}
      <div className="flex justify-end mb-6">
        <button
          type="button"
          onClick={onAnalyze}
          disabled={isAnalyzing || idea.trim().length < 10}
          className={`inline-flex items-center px-5 py-2.5 rounded-lg text-sm font-semibold text-white transition shadow-sm ${
            isAnalyzing || idea.trim().length < 10
              ? "bg-slate-400 cursor-not-allowed"
              : "bg-blue-600 hover:bg-blue-700 active:bg-blue-800"
          }`}
        >
          <Sparkles className="w-4 h-4 mr-2" />
          {isAnalyzing ? "Extracting Requirements..." : "Analyze Requirements"}
        </button>
      </div>

      {/* Structured Requirements Result Card */}
      {workloadProfile && (
        <div className="mt-6 pt-5 border-t border-slate-200">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-bold text-slate-900 flex items-center">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 mr-1.5" />
              Extracted Workload Profile
            </h3>
            <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
              {workloadProfile.category.toUpperCase()}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4 text-xs">
            <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
              <span className="text-slate-500 font-medium">Application Name:</span>
              <div className="font-bold text-slate-800 mt-0.5 text-sm">
                {workloadProfile.name}
              </div>
            </div>
            <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
              <span className="text-slate-500 font-medium">Availability Target:</span>
              <div className="font-bold text-slate-800 mt-0.5 text-sm">
                {workloadProfile.target_availability_percentage}% SLA
              </div>
            </div>
            <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
              <span className="text-slate-500 font-medium">Data Storage & Egress:</span>
              <div className="font-bold text-slate-800 mt-0.5 text-sm">
                {workloadProfile.storage_volume_gb} GB Vol / {workloadProfile.monthly_data_egress_gb} GB Out
              </div>
            </div>
          </div>

          <p className="text-xs text-slate-600 mb-4 bg-slate-50 p-3 rounded-lg border border-slate-200">
            <strong className="text-slate-800 font-semibold">Summary:</strong> {workloadProfile.description}
          </p>

          {/* Missing Requirements Badges */}
          {missingRequirements.length > 0 && (
            <div className="mb-4 p-3 bg-amber-50 rounded-lg border border-amber-200">
              <div className="flex items-center text-xs font-semibold text-amber-800 mb-1">
                <AlertCircle className="w-3.5 h-3.5 mr-1 text-amber-600" />
                Missing Critical Parameters Identified:
              </div>
              <div className="flex flex-wrap gap-1.5">
                {missingRequirements.map((mr, idx) => (
                  <span
                    key={idx}
                    className="text-xs bg-amber-100 text-amber-900 px-2 py-0.5 rounded border border-amber-200 font-mono"
                  >
                    {mr}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Clarifying Questions Loop */}
          {clarifyingQuestions.length > 0 && (
            <div className="mt-4 p-4 bg-blue-50/60 rounded-xl border border-blue-200">
              <div className="flex items-center text-xs font-bold text-blue-900 mb-3">
                <HelpCircle className="w-4 h-4 mr-1.5 text-blue-600" />
                Clarifying Questions Loop (Select or customize to guide architecture synthesis):
              </div>
              <div className="space-y-4">
                {clarifyingQuestions.map((q) => (
                  <div key={q.id} className="p-3.5 bg-white rounded-lg border border-blue-100 shadow-2xs">
                    <div className="flex items-start justify-between">
                      <div className="font-semibold text-xs text-slate-900">
                        {q.question}
                      </div>
                      <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-blue-100 text-blue-800 font-bold ml-2">
                        {q.category}
                      </span>
                    </div>
                    {q.rationale && (
                      <div className="text-[11px] text-slate-500 mt-0.5 italic">
                        {q.rationale}
                      </div>
                    )}
                    {q.impact_on_architecture && (
                      <div className="text-[11px] text-blue-700 mt-1 font-medium">
                        Architecture Impact: {q.impact_on_architecture}
                      </div>
                    )}

                    {/* Radio Options */}
                    <div className="mt-2.5 flex flex-wrap gap-2">
                      {q.options.map((opt, oIdx) => (
                        <button
                          key={oIdx}
                          type="button"
                          onClick={() => onAnswerChange(q.id, opt)}
                          className={`text-xs px-3 py-1.5 rounded-md border font-medium transition ${
                            clarifyingAnswers[q.id] === opt
                              ? "bg-blue-600 text-white border-blue-600 shadow-xs"
                              : "bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100"
                          }`}
                        >
                          {opt}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Trigger Architecture Generation */}
          <div className="mt-5 flex justify-end">
            <button
              type="button"
              onClick={onGenerateArchitecture}
              disabled={isGeneratingArch}
              className={`inline-flex items-center px-6 py-2.5 rounded-lg text-sm font-semibold text-white transition shadow-sm ${
                isGeneratingArch
                  ? "bg-slate-400 cursor-not-allowed"
                  : "bg-emerald-600 hover:bg-emerald-700 active:bg-emerald-800"
              }`}
            >
              <Sparkles className="w-4 h-4 mr-2" />
              {isGeneratingArch ? "Synthesizing Azure Architecture..." : "Generate Production Architecture"}
              <ArrowRight className="w-4 h-4 ml-2" />
            </button>
          </div>
        </div>
      )}
    </section>
  );
};

