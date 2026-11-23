import React, { useState } from "react";
import {
  Upload,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Loader2,
  ShieldCheck,
  Server,
  Database,
  HardDrive,
  Cpu,
  Activity,
  Lightbulb,
  FileCode,
  Key,
  Check,
  Clock,
} from "lucide-react";
import { testGcpConnection, createGcpConnection } from "@/lib/api";
import type {
  GcpConnectionResponse,
  GcpServiceStatus,
  GcpTestConnectionResponse,
} from "@/types";

interface GcpServiceAccountFormProps {
  onSuccess: (conn: GcpConnectionResponse) => void;
  onCancel?: () => void;
}

export const GcpServiceAccountForm: React.FC<GcpServiceAccountFormProps> = ({
  onSuccess,
  onCancel,
}) => {
  const [connectionName, setConnectionName] = useState("GCP Production");
  const [projectId, setProjectId] = useState("");
  const [jsonContent, setJsonContent] = useState("");
  const [clientEmail, setClientEmail] = useState("");
  const [privateKeyId, setPrivateKeyId] = useState("");

  const [isTesting, setIsTesting] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [testResult, setTestResult] = useState<GcpTestConnectionResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleJsonChange = (raw: string) => {
    setJsonContent(raw);
    setErrorMessage(null);
    setTestResult(null);

    try {
      if (raw.trim()) {
        const parsed = JSON.parse(raw.trim());
        if (parsed.project_id && !projectId) {
          setProjectId(parsed.project_id);
        }
        if (parsed.client_email) {
          setClientEmail(parsed.client_email);
        }
        if (parsed.private_key_id) {
          setPrivateKeyId(parsed.private_key_id);
        }
      } else {
        setClientEmail("");
        setPrivateKeyId("");
      }
    } catch {
      // Ignored while typing
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result as string;
      if (content) {
        handleJsonChange(content);
      }
    };
    reader.readAsText(file);
  };

  const handleTestConnection = async () => {
    setErrorMessage(null);
    if (!projectId.trim()) {
      setErrorMessage("GCP Project ID is required.");
      return;
    }
    if (!jsonContent.trim()) {
      setErrorMessage("Service Account JSON is required.");
      return;
    }

    setIsTesting(true);
    try {
      const result = await testGcpConnection({
        connection_name: connectionName.trim(),
        project_id: projectId.trim(),
        service_account_json: jsonContent.trim(),
      });
      setTestResult(result);
      if (result.client_email) setClientEmail(result.client_email);
      if (result.private_key_id) setPrivateKeyId(result.private_key_id);
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : typeof err === "object" && err && "detail" in err
          ? JSON.stringify((err as { detail: unknown }).detail)
          : "Failed to test GCP connection.";
      setErrorMessage(msg);
    } finally {
      setIsTesting(false);
    }
  };

  const handleSaveConnection = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    if (!projectId.trim() || !jsonContent.trim() || !connectionName.trim()) {
      setErrorMessage("Please complete all required fields.");
      return;
    }

    setIsSaving(true);
    try {
      const created = await createGcpConnection({
        name: connectionName.trim(),
        project_id: projectId.trim(),
        service_account_json: jsonContent.trim(),
      });
      // Zero secrets policy: clear key from memory
      setJsonContent("");
      onSuccess(created);
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : typeof err === "object" && err && "detail" in err
          ? JSON.stringify((err as { detail: unknown }).detail)
          : "Failed to save GCP connection.";
      setErrorMessage(msg);
    } finally {
      setIsSaving(false);
    }
  };

  const getServiceIcon = (service: string) => {
    switch (service) {
      case "cloud_resource_manager":
      case "service_usage":
        return <Server className="w-4 h-4" />;
      case "cloud_asset_inventory":
        return <HardDrive className="w-4 h-4" />;
      case "cloud_storage":
        return <HardDrive className="w-4 h-4" />;
      case "cloud_sql":
        return <Database className="w-4 h-4" />;
      case "compute_engine":
        return <Cpu className="w-4 h-4" />;
      case "cloud_monitoring":
        return <Activity className="w-4 h-4" />;
      case "cloud_recommender":
        return <Lightbulb className="w-4 h-4" />;
      default:
        return <FileCode className="w-4 h-4" />;
    }
  };

  const renderStatusBadge = (status: GcpServiceStatus["status"]) => {
    switch (status) {
      case "SUCCESS":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-2xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle2 className="w-3 h-3 text-emerald-600" />
            Connected
          </span>
        );
      case "API_DISABLED":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-2xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            <AlertTriangle className="w-3 h-3 text-amber-600" />
            API Disabled
          </span>
        );
      case "DEFERRED":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-2xs font-semibold bg-sky-50 text-sky-700 border border-sky-200">
            <Clock className="w-3 h-3 text-sky-600" />
            Deferred (Billing Disabled)
          </span>
        );
      case "PERMISSION_DENIED":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-2xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            <XCircle className="w-3 h-3 text-rose-600" />
            Permission Denied
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-2xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
            {status}
          </span>
        );
    }
  };

  return (
    <form
      onSubmit={handleSaveConnection}
      className="bg-white rounded-2xl border border-slate-200 p-6 space-y-6 shadow-sm"
      aria-label="GCP Service Account Connection Form"
    >
      <div className="flex items-start justify-between border-b border-slate-100 pb-4">
        <div>
          <h2 className="text-base font-bold text-navy-950 flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-brand-600" />
            Connect Google Cloud Platform (GCP)
          </h2>
          <p className="text-xs text-navy-600 mt-1">
            Authenticate using a read-only Google Service Account JSON key. Credentials are validated,
            encrypted at rest using AES-256-GCM, and strictly never exposed in public logs.
          </p>
        </div>
      </div>

      {errorMessage && (
        <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center gap-2.5">
          <XCircle className="w-4 h-4 shrink-0 text-rose-600" />
          <span>{errorMessage}</span>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-xs font-semibold text-navy-800 mb-1">
            Connection Name
          </label>
          <input
            type="text"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-xs text-navy-900 focus:outline-none focus:ring-2 focus:ring-brand-500"
            value={connectionName}
            onChange={(e) => setConnectionName(e.target.value)}
            placeholder="e.g. GCP Pricing & Analytics Dev"
            required
          />
        </div>

        <div>
          <label className="block text-xs font-semibold text-navy-800 mb-1">
            GCP Project ID
          </label>
          <input
            type="text"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-xs text-navy-900 focus:outline-none focus:ring-2 focus:ring-brand-500"
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            placeholder="e.g. cloud-recommender-pricing-dev"
            required
          />
        </div>
      </div>

      {/* Service Account JSON Upload & Input */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-xs font-semibold text-navy-800">
            Service Account Key JSON
          </label>
          <label className="inline-flex items-center gap-1.5 text-xs text-brand-600 hover:text-brand-700 cursor-pointer font-medium">
            <Upload className="w-3.5 h-3.5" />
            <span>Upload JSON File</span>
            <input
              type="file"
              accept=".json,application/json"
              className="hidden"
              onChange={handleFileUpload}
            />
          </label>
        </div>

        <textarea
          className="w-full rounded-lg border border-slate-300 p-3 text-xs font-mono text-navy-900 focus:outline-none focus:ring-2 focus:ring-brand-500 h-28 resize-none"
          placeholder='{"type": "service_account", "project_id": "...", "private_key_id": "...", "private_key": "-----BEGIN PRIVATE KEY-----...", "client_email": "..."}'
          value={jsonContent}
          onChange={(e) => handleJsonChange(e.target.value)}
          spellCheck={false}
          required
        />
      </div>

      {/* Extracted Non-Secret Metadata Card */}
      {clientEmail && (
        <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 text-xs space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="text-slate-500 flex items-center gap-1.5 font-medium">
              <Key className="w-3.5 h-3.5 text-slate-400" />
              Authenticated Principal:
            </span>
            <span className="font-mono text-navy-900 font-semibold">{clientEmail}</span>
          </div>
          {privateKeyId && (
            <div className="flex items-center justify-between">
              <span className="text-slate-500 font-medium">Private Key ID:</span>
              <span className="font-mono text-slate-700">{privateKeyId}</span>
            </div>
          )}
        </div>
      )}

      {/* Per-Service Connectivity Results */}
      {testResult && (
        <div className="space-y-3 pt-2 border-t border-slate-100">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
              GCP API Connectivity Matrix
            </h3>
            <span
              className={`text-xs font-bold px-2.5 py-1 rounded-full ${
                testResult.overall_status === "Connected"
                  ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                  : testResult.overall_status === "Partially Connected"
                  ? "bg-amber-50 text-amber-700 border border-amber-200"
                  : "bg-rose-50 text-rose-700 border border-rose-200"
              }`}
            >
              {testResult.overall_status}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            {testResult.services.map((svc) => (
              <div
                key={svc.service}
                className="p-2.5 rounded-lg border border-slate-200 bg-white flex items-center justify-between text-xs"
              >
                <div className="flex items-center gap-2">
                  <div className="text-slate-500">{getServiceIcon(svc.service)}</div>
                  <div>
                    <div className="font-medium text-navy-900">{svc.service_name}</div>
                    {svc.message && (
                      <div className="text-2xs text-slate-500 line-clamp-1">{svc.message}</div>
                    )}
                  </div>
                </div>
                <div>{renderStatusBadge(svc.status)}</div>
              </div>
            ))}
          </div>

          <div className="p-2.5 rounded-lg bg-blue-50/70 border border-blue-200 text-2xs text-blue-900 flex items-center justify-between">
            <span>
              <strong>Billing Integration:</strong> {testResult.billing_status} (Zero billable
              actions initiated)
            </span>
          </div>
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-100">
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 rounded-lg text-xs font-semibold text-slate-700 hover:bg-slate-100 transition-colors"
          >
            Cancel
          </button>
        )}

        <button
          type="button"
          onClick={handleTestConnection}
          disabled={isTesting || isSaving || !projectId || !jsonContent}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold border border-brand-600 text-brand-600 hover:bg-brand-50 transition-colors disabled:opacity-50"
        >
          {isTesting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Activity className="w-3.5 h-3.5" />}
          <span>Test Connection</span>
        </button>

        <button
          type="submit"
          disabled={isSaving || isTesting || !projectId || !jsonContent}
          className="inline-flex items-center gap-2 px-5 py-2 rounded-lg text-xs font-semibold bg-brand-600 text-white hover:bg-brand-700 transition-colors shadow-2xs disabled:opacity-50"
        >
          {isSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
          <span>Save Connection</span>
        </button>
      </div>
    </form>
  );
};

