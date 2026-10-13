"use client";

import React from "react";
import { AlertTriangle, Key, Terminal, X, ShieldAlert } from "lucide-react";
import { ApiErrorDetail } from "@/types";

interface FoundryConfigAlertProps {
  errorDetail: ApiErrorDetail | null;
  onDismiss?: () => void;
}

export const FoundryConfigAlert: React.FC<FoundryConfigAlertProps> = ({
  errorDetail,
  onDismiss,
}) => {
  if (!errorDetail) return null;

  const isConfigError = errorDetail.error_code === "AZURE_AI_FOUNDRY_NOT_CONFIGURED";
  const missingVars = errorDetail.missing_variables || [
    "AZURE_AI_FOUNDRY_ENDPOINT",
    "AZURE_AI_FOUNDRY_API_KEY",
    "AZURE_AI_FOUNDRY_DEPLOYMENT_NAME",
  ];

  return (
    <div
      role="alert"
      aria-live="assertive"
      className={`mb-6 rounded-xl border p-4 shadow-card transition-all ${
        isConfigError
          ? "border-amber-300/90 bg-amber-50/95 text-slate-900"
          : "border-rose-300/90 bg-rose-50/95 text-slate-900"
      }`}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div
            className={`p-2 rounded-lg shrink-0 mt-0.5 ${
              isConfigError
                ? "bg-amber-100 text-amber-700 border border-amber-200"
                : "bg-rose-100 text-rose-700 border border-rose-200"
            }`}
          >
            {isConfigError ? (
              <AlertTriangle className="h-4 w-4" />
            ) : (
              <ShieldAlert className="h-4 w-4" />
            )}
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3
                className={`text-sm font-semibold ${
                  isConfigError ? "text-amber-950" : "text-rose-950"
                }`}
              >
                {isConfigError
                  ? "Azure AI Foundry Configuration Required (HTTP 503)"
                  : "Azure AI Foundry Service Error"}
              </h3>
              {errorDetail.error_code && (
                <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-white/80 border border-slate-200 text-slate-700">
                  {errorDetail.error_code}
                </span>
              )}
            </div>
            <p
              className={`mt-1 text-xs leading-relaxed ${
                isConfigError ? "text-amber-900/90" : "text-rose-900/90"
              }`}
            >
              {errorDetail.message ||
                "AI Architect requires valid Azure AI Foundry credentials to analyze requirements and synthesize architectures. The platform never substitutes mock LLM output."}
            </p>

            {errorDetail.guidance && (
              <p className="mt-1.5 text-xs font-medium text-slate-700">
                {errorDetail.guidance}
              </p>
            )}

            {isConfigError && (
              <div className="mt-3 pt-3 border-t border-amber-200/80 space-y-2.5">
                <div>
                  <div className="text-xs font-semibold text-amber-950 flex items-center gap-1.5 mb-1.5">
                    <Key className="w-3.5 h-3.5 text-amber-700" />
                    <span>Missing Environment Variables:</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {missingVars.map((v) => (
                      <code
                        key={v}
                        className="px-2 py-0.5 bg-white/90 border border-amber-300 rounded-md text-xs font-mono text-amber-950 font-semibold"
                      >
                        {v}
                      </code>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-amber-950 flex items-center gap-1.5 font-medium mb-1">
                    <Terminal className="w-3.5 h-3.5 text-amber-700" />
                    <span>
                      Configure in <code className="bg-amber-200/70 px-1.5 py-0.5 rounded font-mono">backend/.env</code>:
                    </span>
                  </div>
                  <pre className="bg-slate-900 text-slate-100 p-3 rounded-lg text-xs font-mono overflow-x-auto border border-slate-800">
{`AZURE_AI_FOUNDRY_ENDPOINT=https://<your-resource>.openai.azure.com/openai/v1
AZURE_AI_FOUNDRY_API_KEY=<your-api-key>
AZURE_AI_FOUNDRY_DEPLOYMENT_NAME=gpt-5.4-mini`}
                  </pre>
                </div>
              </div>
            )}
          </div>
        </div>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Dismiss alert"
            className="p-1.5 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-white/60 transition shrink-0"
            title="Dismiss notification"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
};
