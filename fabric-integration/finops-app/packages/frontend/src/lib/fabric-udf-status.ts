/**
 * Whether Fabric User Data Function calls can authenticate in this build. Pure and offline: no
 * request is made. Used by screens to show an explicit "authentication pending" state instead of
 * issuing a doomed call or showing an empty list.
 */

import { missingFabricEntraSettings } from "@/config/entra";
import { getStoredEntraToken } from "@/lib/api";
import { classifyFabricToken, decodeJwtClaims } from "@/lib/jwt-claims";

export { FABRIC_AUTH_PENDING_MESSAGE, isFabricAuthPendingError } from "@/lib/fabric-udf-client";

/** True when this deployment routes data through Fabric UDFs. */
export function usesFabricUdf(): boolean {
  return import.meta.env.VITE_USE_FABRIC_UDF === "true";
}

/**
 * True when the UDF path is in use but no Fabric-audience Entra token can be obtained: the Entra
 * client ID is not configured and no valid Fabric token was supplied explicitly.
 */
export function isFabricUdfAuthPending(): boolean {
  if (!usesFabricUdf()) return false;
  if (missingFabricEntraSettings().length === 0) return false;
  const stored = getStoredEntraToken();
  return !(stored && classifyFabricToken(decodeJwtClaims(stored)).state === "ok");
}
