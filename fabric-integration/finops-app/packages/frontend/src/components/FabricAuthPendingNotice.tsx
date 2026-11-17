import React from "react";
import { Info } from "lucide-react";

import { FABRIC_AUTH_PENDING_MESSAGE } from "@/lib/fabric-udf-status";

interface Props {
  /** Smaller variant used inside list areas. */
  compact?: boolean;
}

/**
 * Shown instead of connection data while Microsoft Entra authentication for Fabric is not
 * configured. It is a status, not data: it is never rendered as an empty connection list.
 */
export const FabricAuthPendingNotice: React.FC<Props> = ({ compact = false }) => (
  <div
    role="status"
    data-testid="fabric-auth-pending"
    className={`rounded-xl border border-amber-200 bg-amber-50 text-amber-900 text-xs flex items-start gap-2.5 ${
      compact ? "p-4" : "mb-8 p-4"
    }`}
  >
    <Info className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
    <div>
      <p className="font-semibold mb-0.5">Authentication pending</p>
      <p>{FABRIC_AUTH_PENDING_MESSAGE}</p>
    </div>
  </div>
);
