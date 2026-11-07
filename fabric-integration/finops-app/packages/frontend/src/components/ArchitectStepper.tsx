"use client";

import React from "react";
import { CheckCircle2, CircleDot, ChevronRight } from "lucide-react";

export type ArchitectStep = "requirements" | "sizing" | "blueprint" | "simulator" | "review";

interface ArchitectStepperProps {
  currentStep: ArchitectStep;
  onStepChange: (step: ArchitectStep) => void;
  hasProfile: boolean;
  hasArchitecture: boolean;
  hasCost: boolean;
  hasAssessment: boolean;
}

export const ArchitectStepper: React.FC<ArchitectStepperProps> = ({
  currentStep,
  onStepChange,
  hasProfile,
  hasArchitecture,
  hasCost,
  hasAssessment,
}) => {
  const steps: Array<{
    id: ArchitectStep;
    num: string;
    label: string;
    isCompleted: boolean;
    isAvailable: boolean;
  }> = [
    {
      id: "requirements",
      num: "01",
      label: "Requirements & Idea",
      isCompleted: hasProfile,
      isAvailable: true,
    },
    {
      id: "sizing",
      num: "02",
      label: "Workload Sizing",
      isCompleted: hasProfile,
      isAvailable: true,
    },
    {
      id: "blueprint",
      num: "03",
      label: "Architecture Blueprint",
      isCompleted: hasArchitecture,
      isAvailable: hasArchitecture,
    },
    {
      id: "simulator",
      num: "04",
      label: "Deterministic Cost",
      isCompleted: hasCost,
      isAvailable: hasCost,
    },
    {
      id: "review",
      num: "05",
      label: "Savings & Review",
      isCompleted: hasAssessment,
      isAvailable: hasAssessment,
    },
  ];

  return (
    <div className="app-card p-3 mb-6 bg-white border border-slate-200">
      <nav aria-label="AI Architect 5-Step Workflow" className="flex items-center justify-between gap-2 overflow-x-auto">
        {steps.map((s, idx) => {
          const isActive = currentStep === s.id;

          return (
            <React.Fragment key={s.id}>
              <button
                type="button"
                disabled={!s.isAvailable}
                onClick={() => onStepChange(s.id)}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium whitespace-nowrap transition ${
                  isActive
                    ? "bg-brand-50 text-brand-700 font-semibold border border-brand-200"
                    : s.isCompleted
                      ? "text-navy-800 hover:bg-slate-50"
                      : s.isAvailable
                        ? "text-navy-600 hover:bg-slate-50"
                        : "text-slate-400 cursor-not-allowed opacity-60"
                }`}
              >
                {s.isCompleted ? (
                  <CheckCircle2 className="w-4 h-4 text-accent-emerald shrink-0" />
                ) : isActive ? (
                  <CircleDot className="w-4 h-4 text-brand-600 shrink-0" />
                ) : (
                  <span className="w-4 h-4 rounded-full bg-slate-100 text-slate-500 text-[10px] font-bold flex items-center justify-center shrink-0">
                    {s.num}
                  </span>
                )}
                <span>
                  <strong className="font-mono mr-1">{s.num}.</strong>
                  {s.label}
                </span>
              </button>

              {idx < steps.length - 1 && (
                <ChevronRight className="w-3.5 h-3.5 text-slate-300 shrink-0 hidden sm:block" />
              )}
            </React.Fragment>
          );
        })}
      </nav>
    </div>
  );
};

