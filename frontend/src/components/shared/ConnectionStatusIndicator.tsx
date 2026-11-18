"use client";

import React from "react";
import {
  CheckCircle2,
  RefreshCw,
  XCircle,
  ShieldAlert,
  WifiOff,
  Radio,
} from "lucide-react";

export type ConnectionStatusType =
  | "connected"
  | "connecting"
  | "discovering"
  | "loading"
  | "refreshing"
  | "completed"
  | "failed"
  | "auth_failed"
  | "permission_denied"
  | "connection_error"
  | "unavailable"
  | "ready_to_connect"
  | "connection_lost";

interface ConnectionStatusIndicatorProps {
  status: ConnectionStatusType | string;
  label?: string;
  size?: "sm" | "md";
  showDot?: boolean;
  className?: string;
}

export const ConnectionStatusIndicator: React.FC<ConnectionStatusIndicatorProps> = ({
  status,
  label,
  size = "sm",
  showDot = true,
  className = "",
}) => {
  const normalized = (status || "connected").toLowerCase().replace(/-/g, "_");

  const getStatusConfig = () => {
    switch (normalized) {
      case "connected":
      case "online":
      case "available":
        return {
          bg: "bg-emerald-50",
          text: "text-emerald-700",
          border: "border-emerald-200",
          dot: "bg-emerald-500",
          icon: <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />,
          defaultLabel: "Connected",
        };
      case "connecting":
        return {
          bg: "bg-blue-50",
          text: "text-blue-700",
          border: "border-blue-200",
          dot: "bg-blue-500 animate-ping",
          icon: <RefreshCw className="w-3.5 h-3.5 text-blue-600 animate-spin shrink-0" />,
          defaultLabel: "Connecting...",
        };
      case "discovering":
        return {
          bg: "bg-purple-50",
          text: "text-purple-700",
          border: "border-purple-200",
          dot: "bg-purple-500 animate-pulse",
          icon: <Radio className="w-3.5 h-3.5 text-purple-600 animate-pulse shrink-0" />,
          defaultLabel: "Discovering Scopes",
        };
      case "loading":
        return {
          bg: "bg-sky-50",
          text: "text-sky-700",
          border: "border-sky-200",
          dot: "bg-sky-500 animate-ping",
          icon: <RefreshCw className="w-3.5 h-3.5 text-sky-600 animate-spin shrink-0" />,
          defaultLabel: "Loading Data",
        };
      case "refreshing":
        return {
          bg: "bg-amber-50",
          text: "text-amber-700",
          border: "border-amber-200",
          dot: "bg-amber-500 animate-spin",
          icon: <RefreshCw className="w-3.5 h-3.5 text-amber-600 animate-spin shrink-0" />,
          defaultLabel: "Refreshing",
        };
      case "completed":
        return {
          bg: "bg-emerald-50",
          text: "text-emerald-700",
          border: "border-emerald-200",
          dot: "bg-emerald-500",
          icon: <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />,
          defaultLabel: "Completed",
        };
      case "auth_failed":
      case "authentication_failed":
        return {
          bg: "bg-rose-50",
          text: "text-rose-700",
          border: "border-rose-200",
          dot: "bg-rose-500",
          icon: <XCircle className="w-3.5 h-3.5 text-rose-600 shrink-0" />,
          defaultLabel: "Authentication Failed",
        };
      case "permission_denied":
      case "permission_required":
        return {
          bg: "bg-amber-50",
          text: "text-amber-800",
          border: "border-amber-300",
          dot: "bg-amber-500",
          icon: <ShieldAlert className="w-3.5 h-3.5 text-amber-600 shrink-0" />,
          defaultLabel: "Permission Denied",
        };
      case "connection_error":
      case "unavailable":
      case "ready_to_connect":
        return {
          bg: "bg-slate-100",
          text: "text-slate-700",
          border: "border-slate-300",
          dot: "bg-slate-500",
          icon: <WifiOff className="w-3.5 h-3.5 text-slate-600 shrink-0" />,
          defaultLabel: "Unavailable",
        };
      case "connection_lost":
        return {
          bg: "bg-rose-50",
          text: "text-rose-700",
          border: "border-rose-200",
          dot: "bg-rose-500",
          icon: <WifiOff className="w-3.5 h-3.5 text-rose-600 shrink-0" />,
          defaultLabel: "Connection Lost",
        };
      case "failed":
      case "error":
      default:
        return {
          bg: "bg-rose-50",
          text: "text-rose-700",
          border: "border-rose-200",
          dot: "bg-rose-500",
          icon: <XCircle className="w-3.5 h-3.5 text-rose-600 shrink-0" />,
          defaultLabel: "Failed",
        };
    }
  };

  const config = getStatusConfig();
  const displayLabel = label || config.defaultLabel;

  const sizeClasses =
    size === "sm"
      ? "text-[11px] px-2 py-0.5 gap-1.5"
      : "text-xs px-2.5 py-1 gap-2";

  return (
    <span
      className={`inline-flex items-center font-semibold rounded-full border ${config.bg} ${config.text} ${config.border} ${sizeClasses} ${className}`}
    >
      {showDot && (
        <span className="relative flex h-2 w-2">
          <span className={`rounded-full h-2 w-2 ${config.dot}`} />
        </span>
      )}
      <span>{displayLabel}</span>
    </span>
  );
};
