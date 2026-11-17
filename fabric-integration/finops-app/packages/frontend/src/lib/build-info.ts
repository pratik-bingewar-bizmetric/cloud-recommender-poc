/**
 * Build identity of the running bundle (commit, branch, build time). Contains no secrets.
 * Visible in the browser console / `window.__FINOPS_BUILD__`, in the page's
 * `<meta name="finops-build">` tag and at `/build-info.json`.
 */
export interface BuildInfo {
  commit: string;
  branch: string;
  dirty: boolean;
  builtAt: string;
}

export const BUILD_INFO: BuildInfo =
  typeof __BUILD_INFO__ !== "undefined"
    ? __BUILD_INFO__
    : { commit: "dev", branch: "dev", dirty: false, builtAt: "dev" };

export function buildLabel(info: BuildInfo = BUILD_INFO): string {
  return `${info.commit}${info.dirty ? "+dirty" : ""} (${info.builtAt})`;
}

declare global {
  interface Window {
    __FINOPS_BUILD__?: BuildInfo;
  }
}

if (typeof window !== "undefined") {
  window.__FINOPS_BUILD__ = BUILD_INFO;
  console.info(`[FinOps] frontend build ${buildLabel()}`);
}
