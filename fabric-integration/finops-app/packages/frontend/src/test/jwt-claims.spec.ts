import { describe, expect, it } from "vitest";
import { classifyFabricToken, decodeJwtClaims } from "../lib/jwt-claims";

const b64 = (o: unknown) => btoa(JSON.stringify(o)).replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_");
const jwt = (claims: Record<string, unknown>) => `${b64({ alg: "none" })}.${b64(claims)}.sig`;
const now = 1_800_000_000;

describe("jwt claims inspection", () => {
  it("returns only the whitelisted claims", () => {
    const claims = decodeJwtClaims(
      jwt({ aud: "a", iss: "i", tid: "t", scp: "s1 s2", roles: ["r"], exp: 1, nbf: 0, upn: "user@x", name: "N", oid: "O" })
    );
    expect(Object.keys(claims ?? {}).sort()).toEqual(["aud", "exp", "iss", "nbf", "roles", "scp", "tid"]);
  });

  it("rejects non-JWT input", () => {
    expect(decodeJwtClaims("not-a-jwt")).toBeNull();
    expect(decodeJwtClaims(null)).toBeNull();
    expect(classifyFabricToken(null).state).toBe("malformed");
  });

  it("accepts the Power BI / Fabric audiences", () => {
    for (const aud of [
      "https://analysis.windows.net/powerbi/api",
      "https://analysis.windows.net/powerbi/api/",
      "00000009-0000-0000-c000-000000000000",
      "https://api.fabric.microsoft.com",
    ]) {
      expect(classifyFabricToken(decodeJwtClaims(jwt({ aud, exp: now + 3600 })), now).state).toBe("ok");
    }
  });

  it("flags the backend API audience and the Rayfin session as the wrong audience", () => {
    expect(classifyFabricToken(decodeJwtClaims(jwt({ aud: "api://backend/access_as_user", exp: now + 60 })), now).state).toBe("wrong_audience");
    expect(classifyFabricToken(decodeJwtClaims(jwt({ exp: now + 60 })), now).state).toBe("wrong_audience");
  });

  it("flags expired and not-yet-valid tokens", () => {
    const aud = "https://analysis.windows.net/powerbi/api";
    expect(classifyFabricToken(decodeJwtClaims(jwt({ aud, exp: now - 3600 })), now).state).toBe("expired");
    expect(classifyFabricToken(decodeJwtClaims(jwt({ aud, exp: now + 3600, nbf: now + 3600 })), now).state).toBe("not_yet_valid");
  });

  it("reports scopes, tenant and expiry for diagnostics", () => {
    const d = classifyFabricToken(
      decodeJwtClaims(jwt({ aud: "https://analysis.windows.net/powerbi/api", tid: "t1", scp: "UserDataFunction.Execute.All Item.Execute.All", exp: now + 60 })),
      now
    );
    expect(d.tenantId).toBe("t1");
    expect(d.scopes).toEqual(["UserDataFunction.Execute.All", "Item.Execute.All"]);
    expect(d.expiresAt).toBe(new Date((now + 60) * 1000).toISOString());
  });
});
