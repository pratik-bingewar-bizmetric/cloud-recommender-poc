/**
 * Safe inspection of an access token's non-sensitive claims.
 *
 * Only `aud`, `iss`, `tid`, `scp`, `roles`, `exp` and `nbf` are read. The token is NOT validated
 * here (signature checking is the service's job) and neither the token nor any other claim
 * (name, upn, oid, ...) is ever returned or logged. Used to explain WHY Fabric rejected a call.
 */

export interface SafeClaims {
  aud?: string;
  iss?: string;
  tid?: string;
  scp?: string;
  roles?: string[];
  exp?: number;
  nbf?: number;
}

export type TokenState = "ok" | "malformed" | "expired" | "not_yet_valid" | "wrong_audience";

export interface TokenDiagnosis {
  state: TokenState;
  audience: string | null;
  issuer: string | null;
  tenantId: string | null;
  scopes: string[];
  roles: string[];
  expiresAt: string | null;
}

/** Audiences the Fabric REST API / User Data Functions accept for a delegated user token. */
export const FABRIC_ACCEPTED_AUDIENCES: readonly string[] = [
  "https://analysis.windows.net/powerbi/api",
  "00000009-0000-0000-c000-000000000000", // Power BI Service application id
  "https://api.fabric.microsoft.com",
];

function base64UrlDecode(segment: string): string {
  const padded = segment.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(segment.length / 4) * 4, "=");
  const binary = atob(padded);
  const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

/** Decode the whitelisted claims of a JWT; null when it is not a JWT. */
export function decodeJwtClaims(token: string | null | undefined): SafeClaims | null {
  if (!token) return null;
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  try {
    const raw = JSON.parse(base64UrlDecode(parts[1])) as Record<string, unknown>;
    const aud = Array.isArray(raw.aud) ? String(raw.aud[0] ?? "") : raw.aud;
    return {
      aud: typeof aud === "string" ? aud : undefined,
      iss: typeof raw.iss === "string" ? raw.iss : undefined,
      tid: typeof raw.tid === "string" ? raw.tid : undefined,
      scp: typeof raw.scp === "string" ? raw.scp : undefined,
      roles: Array.isArray(raw.roles) ? raw.roles.map(String) : undefined,
      exp: typeof raw.exp === "number" ? raw.exp : undefined,
      nbf: typeof raw.nbf === "number" ? raw.nbf : undefined,
    };
  } catch {
    return null;
  }
}

/** Is the token plausibly acceptable to the Fabric API (audience, time window)? */
export function classifyFabricToken(
  claims: SafeClaims | null,
  nowSeconds: number = Math.floor(Date.now() / 1000),
  skewSeconds = 120
): TokenDiagnosis {
  if (!claims) {
    return { state: "malformed", audience: null, issuer: null, tenantId: null, scopes: [], roles: [], expiresAt: null };
  }
  const audience = claims.aud ?? null;
  const base = {
    audience,
    issuer: claims.iss ?? null,
    tenantId: claims.tid ?? null,
    scopes: claims.scp ? claims.scp.split(" ").filter(Boolean) : [],
    roles: claims.roles ?? [],
    expiresAt: claims.exp ? new Date(claims.exp * 1000).toISOString() : null,
  };
  const normalized = audience ? audience.replace(/\/+$/, "").toLowerCase() : null;
  if (!normalized || !FABRIC_ACCEPTED_AUDIENCES.some((a) => a.toLowerCase() === normalized)) {
    return { state: "wrong_audience", ...base };
  }
  if (claims.exp !== undefined && claims.exp < nowSeconds - skewSeconds) return { state: "expired", ...base };
  if (claims.nbf !== undefined && claims.nbf > nowSeconds + skewSeconds) return { state: "not_yet_valid", ...base };
  return { state: "ok", ...base };
}
