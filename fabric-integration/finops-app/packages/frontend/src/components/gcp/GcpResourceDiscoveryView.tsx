import React, { useState, useEffect, useCallback } from "react";
import {
  Server,
  Database,
  HardDrive,
  Cpu,
  RefreshCw,
  Trash2,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Loader2,
  Search,
  Tag,
  ShieldCheck,
  Lightbulb,
} from "lucide-react";
import { getGcpResources, deleteGcpConnection } from "@/lib/api";
import type { GcpConnectionResponse, GcpDiscoveryResponse, GcpResourceItem } from "@/types";

interface GcpResourceDiscoveryViewProps {
  connection: GcpConnectionResponse;
  onDisconnect: () => void;
}

export const GcpResourceDiscoveryView: React.FC<GcpResourceDiscoveryViewProps> = ({
  connection,
  onDisconnect,
}) => {
  const [discovery, setDiscovery] = useState<GcpDiscoveryResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterQuery, setFilterQuery] = useState("");
  const [selectedType, setSelectedType] = useState<string>("ALL");
  const [isDeleting, setIsDeleting] = useState(false);

  const loadResources = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await getGcpResources(connection.id);
      setDiscovery(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to discover GCP resources.");
    } finally {
      setIsLoading(false);
    }
  }, [connection.id]);

  useEffect(() => {
    loadResources();
  }, [loadResources]);

  const handleDelete = async () => {
    if (!window.confirm(`Are you sure you want to disconnect and delete '${connection.name}'?`)) {
      return;
    }
    setIsDeleting(true);
    try {
      await deleteGcpConnection(connection.id);
      onDisconnect();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to delete connection.");
      setIsDeleting(false);
    }
  };

  const allTypes = discovery
    ? Array.from(new Set(discovery.resources.map((r) => r.resource_type)))
    : [];

  const filteredResources = (discovery?.resources || []).filter((r: GcpResourceItem) => {
    const matchesSearch =
      r.resource_name.toLowerCase().includes(filterQuery.toLowerCase()) ||
      r.resource_id.toLowerCase().includes(filterQuery.toLowerCase());
    const matchesType = selectedType === "ALL" || r.resource_type === selectedType;
    return matchesSearch && matchesType;
  });

  return (
    <div className="space-y-6">
      {/* Top Project Banner */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-50 text-brand-700 border border-blue-200">
                <ShieldCheck className="w-3.5 h-3.5 text-brand-600" />
                Google Cloud Platform
              </span>
              <span className="text-xs font-bold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-200">
                {connection.status === "connected" ? "Connected" : "Partially Connected"}
              </span>
            </div>
            <h2 className="text-xl font-bold text-navy-950 mt-2">{connection.name}</h2>
            <div className="text-xs text-slate-500 font-mono mt-0.5">
              Project ID: <strong className="text-navy-900">{connection.project_id}</strong>
              {" • "}Principal: <span className="text-navy-800">{connection.client_email}</span>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              onClick={loadResources}
              disabled={isLoading}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-300 text-xs font-semibold text-navy-700 hover:bg-slate-50 transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
              <span>Refresh</span>
            </button>
            <button
              onClick={handleDelete}
              disabled={isDeleting}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-rose-200 text-xs font-semibold text-rose-700 hover:bg-rose-50 transition-colors disabled:opacity-50"
            >
              <Trash2 className="w-3.5 h-3.5 text-rose-600" />
              <span>Disconnect</span>
            </button>
          </div>
        </div>

        {/* Deferred Billing Notice */}
        <div className="p-3 rounded-xl bg-amber-50/80 border border-amber-200 text-xs text-amber-900 flex items-center justify-between">
          <span>
            <strong>Cloud Billing:</strong> {connection.billing_status} (No live billing account; zero spend or billable charges incurred)
          </span>
          <span className="text-2xs uppercase tracking-wider font-bold text-amber-800 bg-amber-100 px-2 py-0.5 rounded">
            Read-Only Guardrail Active
          </span>
        </div>

        {/* Discovery Notes */}
        {discovery?.discovery_notes && discovery.discovery_notes.length > 0 && (
          <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-700 space-y-1">
            <span className="font-semibold text-navy-900">Discovery Notes:</span>
            <ul className="list-disc list-inside space-y-0.5 text-slate-600">
              {discovery.discovery_notes.map((note, idx) => (
                <li key={idx}>{note}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center gap-2">
          <XCircle className="w-4 h-4 shrink-0 text-rose-600" />
          <span>{error}</span>
        </div>
      )}

      {/* Discovery Content */}
      {isLoading ? (
        <div className="py-16 text-center text-slate-400">
          <Loader2 className="w-8 h-8 animate-spin mx-auto mb-2 text-brand-600" />
          <p className="text-xs font-medium">Discovering Google Cloud Platform resources...</p>
        </div>
      ) : discovery ? (
        <div className="space-y-6">
          {/* Summary Stat Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5">
            <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-2xs">
              <span className="text-xs text-slate-500 font-medium">Discovered Resources</span>
              <div className="text-2xl font-bold text-navy-950 mt-1">
                {discovery.total_resources}
              </div>
            </div>
            <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-2xs">
              <span className="text-xs text-slate-500 font-medium">Monitored Descriptors</span>
              <div className="text-2xl font-bold text-navy-950 mt-1">
                {discovery.monitoring?.metric_descriptors_count || 0}
              </div>
            </div>
            <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-2xs">
              <span className="text-xs text-slate-500 font-medium">Optimization Recs</span>
              <div className="text-2xl font-bold text-navy-950 mt-1">
                {discovery.recommendations.length}
              </div>
            </div>
            <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-2xs">
              <span className="text-xs text-slate-500 font-medium">Service Coverage</span>
              <div className="text-2xl font-bold text-navy-950 mt-1">
                {discovery.services_status.filter((s) => s.status === "SUCCESS").length}/
                {discovery.services_status.length}
              </div>
            </div>
          </div>

          {/* Search & Filters */}
          <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-sm flex flex-col sm:flex-row gap-3 items-center justify-between">
            <div className="relative w-full sm:w-72">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="text"
                value={filterQuery}
                onChange={(e) => setFilterQuery(e.target.value)}
                placeholder="Search resources by name or ID..."
                className="w-full pl-9 pr-3 py-1.5 text-xs rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-500 text-navy-900"
              />
            </div>

            <div className="flex items-center gap-2 w-full sm:w-auto overflow-x-auto pb-1 sm:pb-0">
              <button
                onClick={() => setSelectedType("ALL")}
                className={`px-3 py-1 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors ${
                  selectedType === "ALL"
                    ? "bg-brand-600 text-white"
                    : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                }`}
              >
                All Types ({discovery.total_resources})
              </button>
              {allTypes.map((t) => (
                <button
                  key={t}
                  onClick={() => setSelectedType(t)}
                  className={`px-3 py-1 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors ${
                    selectedType === t
                      ? "bg-brand-600 text-white"
                      : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                  }`}
                >
                  {t.split("/").pop()}
                </button>
              ))}
            </div>
          </div>

          {/* Resource Inventory Table */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="p-4 border-b border-slate-100 flex items-center justify-between">
              <h3 className="text-xs font-bold text-navy-900 uppercase tracking-wider">
                Discovered Resources ({filteredResources.length})
              </h3>
            </div>

            {filteredResources.length === 0 ? (
              <div className="p-12 text-center text-slate-400 text-xs">
                No resources match the selected criteria.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs text-navy-800">
                  <thead className="bg-slate-50 border-b border-slate-100 text-slate-500 font-semibold uppercase text-2xs tracking-wider">
                    <tr>
                      <th className="py-2.5 px-4">Resource Name</th>
                      <th className="py-2.5 px-4">Type</th>
                      <th className="py-2.5 px-4">Location</th>
                      <th className="py-2.5 px-4">State</th>
                      <th className="py-2.5 px-4">Details</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filteredResources.map((res: GcpResourceItem) => (
                      <tr key={res.resource_id} className="hover:bg-slate-50/70 transition-colors">
                        <td className="py-3 px-4">
                          <div className="font-semibold text-navy-950">{res.resource_name}</div>
                          <div className="text-2xs text-slate-400 font-mono truncate max-w-xs">
                            {res.resource_id}
                          </div>
                        </td>
                        <td className="py-3 px-4 font-mono text-2xs text-slate-600">
                          {res.resource_type}
                        </td>
                        <td className="py-3 px-4 text-slate-600">{res.location || "global"}</td>
                        <td className="py-3 px-4">
                          <span className="px-2 py-0.5 rounded text-2xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                            {res.state || "ACTIVE"}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-2xs text-slate-500 font-mono">
                          {JSON.stringify(res.details || {})}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
};

