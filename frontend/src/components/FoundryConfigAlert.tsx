"use client";

import React from "react";
import { AlertTriangle, Key, Terminal, X } from "lucide-react";
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
    <div className="mb-6 rounded-lg border border-amber-300 bg-amber-50 p-4 text-slate-800 shadow-sm">
      <div className="flex items-start justify-between">
        <div className="flex items-start space-x-3">
          <AlertTriangle className="h-5 w-5 text-amber-600 mt-0.5 flex-shrink-0" />
          <div>
            <h3 className="text-sm font-semibold text-amber-900">
              {isConfigError
                ? "Azure AI Foundry Not Configured (HTTP 503)"
                : "AI Service Connection Issue"}
            </h3>
            <p className="mt-1 text-xs text-amber-800 leading-relaxed">
              {errorDetail.message ||
                "Phase A requires explicit Azure AI Foundry credentials to generate architectures and extract requirements. The system strictly refuses to hallucinate or silently substitute mock LLMs."}
            </p>

            {isConfigError && (
              <div className="mt-3">
                <div className="text-xs font-semibold text-amber-900 flex items-center mb-1">
                  <Key className="w-3.5 h-3.5 mr-1" />
                  Missing Required Environment Variables:
                </div>
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {missingVars.map((v) => (
                    <code
                      key={v}
                      className="px-2 py-0.5 bg-amber-200/70 border border-amber-300 rounded text-xs font-mono text-amber-950 font-bold"
                    >
                      {v}
                    </code>
                  ))}
                </div>
                <div className="text-xs text-amber-900 flex items-center mt-2 font-medium">
                  <Terminal className="w-3.5 h-3.5 mr-1" />
                  To configure, add the following to your <code className="mx-1 bg-amber-200 px-1 rounded">backend/.env</code> file:
                </div>
                <pre className="mt-1 bg-slate-900 text-amber-300 p-2.5 rounded-md text-xs font-mono overflow-x-auto">
{`AZURE_AI_FOUNDRY_ENDPOINT=https://<your-hub>.services.ai.azure.com/models
AZURE_AI_FOUNDRY_API_KEY=<your-api-key>
AZURE_AI_FOUNDRY_DEPLOYMENT_NAME=gpt-4o`}
                </pre>
              </div>
            )}
          </div>
        </div>
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="text-amber-500 hover:text-amber-700 transition p-1"
            title="Dismiss notification"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
};

