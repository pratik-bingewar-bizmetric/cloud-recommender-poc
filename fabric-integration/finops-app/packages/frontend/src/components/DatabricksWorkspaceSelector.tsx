"use client";

import React from "react";
import { DatabricksConnection } from "@/types";
import { Server, CheckCircle2, AlertCircle, RefreshCw, ChevronDown } from "lucide-react";

interface DatabricksWorkspaceSelectorProps {
  connections: DatabricksConnection[];
  selectedWorkspaceId: string; // "all" or connection_id
  onSelectWorkspace: (workspaceId: string) => void;
  isLoading?: boolean;
}

export const DatabricksWorkspaceSelector: React.FC<DatabricksWorkspaceSelectorProps> = ({
  connections,
  selectedWorkspaceId,
  onSelectWorkspace,
  isLoading = false,
}) => {
  const selectedConnection = connections.find((c) => c.connection_id === selectedWorkspaceId);

  return (
    <div className="relative inline-block text-left">
      <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 shadow-sm text-xs text-slate-700">
        <Server className="w-3.5 h-3.5 text-indigo-600 shrink-0" />
        <span className="font-medium text-slate-500">Workspace:</span>
        <select
          value={selectedWorkspaceId}
          onChange={(e) => onSelectWorkspace(e.target.value)}
          disabled={isLoading}
          className="bg-transparent font-semibold text-slate-800 focus:outline-none cursor-pointer pr-4"
        >
          <option value="all">All Workspaces ({connections.length})</option>
          {connections.map((conn) => (
            <option key={conn.connection_id} value={conn.connection_id}>
              {conn.workspace_name} [{conn.cloud.toUpperCase()}] ({conn.workspace_id})
            </option>
          ))}
        </select>

        {selectedConnection && (
          <span
            className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${
              selectedConnection.status === "connected"
                ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                : selectedConnection.status === "auth_failed"
                ? "bg-amber-50 text-amber-700 border border-amber-200"
                : "bg-slate-100 text-slate-600"
            }`}
          >
            {selectedConnection.status === "connected" ? (
              <CheckCircle2 className="w-2.5 h-2.5 text-emerald-600" />
            ) : (
              <AlertCircle className="w-2.5 h-2.5 text-amber-600" />
            )}
            {selectedConnection.status}
          </span>
        )}
      </div>
    </div>
  );
};

