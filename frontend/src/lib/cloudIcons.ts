/**
 * Centralized, typed cloud service icon registry and Mermaid DSL enrichment utilities.
 *
 * Supports authentic official visual identities and architecture icons for:
 * - Microsoft Azure (Provider & Service Icons)
 * - Google Cloud Platform (Provider & Service Icons)
 * - Amazon Web Services (Provider & Service Icons - Deferred integration, full visual support)
 * - Neutral Architectural Fallback
 */

export type CloudProvider = "azure" | "aws" | "gcp" | "neutral" | "multi";

export type ServiceCategory =
  | "compute"
  | "database"
  | "storage"
  | "networking"
  | "security"
  | "monitoring"
  | "ai_ml"
  | "integration"
  | "general";

export interface CloudServiceIcon {
  id: string;
  name: string;
  provider: CloudProvider;
  category: ServiceCategory;
  svg: string;
  dataUri: string;
}

export interface ProviderBrand {
  id: CloudProvider;
  name: string;
  shortName: string;
  badgeBg: string;
  badgeText: string;
  badgeBorder: string;
  svg: string;
  dataUri: string;
}

/**
 * Convert SVG string into UTF-8 safe base64 Data URI.
 */
export function svgToDataUri(svg: string): string {
  const cleaned = svg.trim().replace(/\s+/g, " ");
  if (typeof window !== "undefined" && typeof window.btoa === "function") {
    try {
      const base64 = window.btoa(unescape(encodeURIComponent(cleaned)));
      return `data:image/svg+xml;base64,${base64}`;
    } catch {
      return `data:image/svg+xml;utf8,${encodeURIComponent(cleaned)}`;
    }
  } else if (typeof Buffer !== "undefined") {
    const base64 = Buffer.from(cleaned, "utf8").toString("base64");
    return `data:image/svg+xml;base64,${base64}`;
  }
  return `data:image/svg+xml;utf8,${encodeURIComponent(cleaned)}`;
}

// =============================================================================
// OFFICIAL PROVIDER BRAND ASSETS
// =============================================================================

// Official Microsoft Azure Cloud Identity
export const AZURE_PROVIDER_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="48" height="48">
  <path fill="#0078D4" d="M29.8 4L14.6 22.8H26.3L8 44h15.2l18.4-30.8H29.8z"/>
  <path fill="#50E6FF" opacity="0.9" d="M38.5 13.2H23.2L14.6 22.8h11.7l-9.1 10.6 6 10.6L41.6 18l-3.1-4.8z"/>
  <path fill="#005A9E" d="M14.6 22.8L8 44h15.2l4.8-5.6-13.4-15.6z"/>
</svg>
`;

// Official Google Cloud Platform Identity
export const GCP_PROVIDER_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="48" height="48">
  <path fill="#EA4335" d="M24 16.5c2.3 0 4.4.8 6 2.2l4.5-4.5C31.7 11.6 28 10 24 10c-5.8 0-10.8 3.3-13.3 8.2l5.4 4.2C17.3 18.6 20.4 16.5 24 16.5z"/>
  <path fill="#4285F4" d="M37.5 24c0-.9-.1-1.8-.3-2.6H24v5.4h7.6c-.4 1.9-1.5 3.6-3.1 4.7l4.9 3.8C36.3 32.7 37.5 28.7 37.5 24z"/>
  <path fill="#FBBC04" d="M16.1 22.4l-5.4-4.2C9.4 20.3 8.7 22.1 8.7 24s.7 3.7 2 5.8l5.4-4.2c-.3-.9-.5-1-.5-1.6 0-.6.2-.7.5-1.6z"/>
  <path fill="#34A853" d="M24 38c3.9 0 7.2-1.3 9.6-3.6l-4.9-3.8c-1.3.9-3 1.5-4.7 1.5-3.6 0-6.7-2.1-7.9-5.9l-5.4 4.2C13.2 35.2 18.2 38 24 38z"/>
</svg>
`;

// Official Amazon Web Services Identity
export const AWS_PROVIDER_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="48" height="48">
  <rect width="48" height="48" rx="8" fill="#232F3E"/>
  <path fill="#FFFFFF" d="M11 25.5l3.2-12h3.5l3.2 12h-3l-.7-3h-2.5l-.7 3H11zm4.3-5.2h1.6L16 16.2h-.1l-.6 4.1zm7.5 5.2l2.3-12h2.8l1.6 7.8h.1l1.6-7.8h2.8l2.3 12h-2.7l-1.3-8.2h-.1l-1.6 8.2h-2.1l-1.6-8.2h-.1l-1.3 8.2h-2.8zm15.4-.2c-.8 0-1.5-.2-2.1-.6-.6-.4-1-.9-1.3-1.6l2.3-1c.3.8.9 1.3 1.6 1.3.5 0 .9-.2 1.2-.5.3-.3.4-.6.4-1 0-.4-.1-.7-.4-.9-.3-.2-.7-.4-1.3-.6l-1-.3c-.8-.2-1.5-.6-2-1.1-.5-.5-.8-1.2-.8-2 0-.9.4-1.7 1.1-2.3.7-.6 1.7-.9 2.8-.9 1 0 1.8.3 2.5.8.7.5 1.1 1.2 1.2 2l-2.3.9c-.2-.6-.6-1-1.3-1-.4 0-.8.1-1.1.4-.3.2-.4.5-.4.8 0 .3.1.6.3.8.2.2.6.4 1.1.5l1.1.3c1 .3 1.7.7 2.2 1.2.5.5.7 1.2.7 2 0 1-.4 1.8-1.1 2.4-.6.6-1.6 1-2.8 1z"/>
  <path fill="#FF9900" d="M37 32.5c-4.5 3.3-11 5-17.5 5-8.2 0-14-3-15.5-3.8-.4-.2-.5-.7-.2-1 .2-.3.6-.4 1-.2 1.4.7 7 3.5 14.7 3.5 6 0 12-1.6 16.2-4.6.4-.3.9-.2 1.2.2.3.4.1.9-.1.9z"/>
  <path fill="#FF9900" d="M38.5 30.5c.3.5.7 1.4.6 2.1 0 .3-.3.5-.6.4-.9-.3-2.1-1.2-2.8-2.2-.2-.3 0-.6.3-.6.9 0 2.1.2 2.5.3z"/>
</svg>
`;

export const NEUTRAL_PROVIDER_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="48" height="48">
  <rect x="6" y="6" width="36" height="36" rx="8" fill="#F1F5F9" stroke="#94A3B8" stroke-width="2.5"/>
  <path fill="#64748B" d="M18 16h12v4H18zm0 8h12v4H18zm0 8h8v4H18z"/>
  <circle cx="34" cy="34" r="3" fill="#3B82F6"/>
</svg>
`;

export const PROVIDER_BRANDS: Record<CloudProvider, ProviderBrand> = {
  azure: {
    id: "azure",
    name: "Microsoft Azure",
    shortName: "Azure",
    badgeBg: "bg-blue-50/90",
    badgeText: "text-blue-700",
    badgeBorder: "border-blue-200",
    svg: AZURE_PROVIDER_SVG,
    dataUri: svgToDataUri(AZURE_PROVIDER_SVG),
  },
  gcp: {
    id: "gcp",
    name: "Google Cloud Platform",
    shortName: "GCP",
    badgeBg: "bg-red-50/90",
    badgeText: "text-red-700",
    badgeBorder: "border-red-200",
    svg: GCP_PROVIDER_SVG,
    dataUri: svgToDataUri(GCP_PROVIDER_SVG),
  },
  aws: {
    id: "aws",
    name: "Amazon Web Services",
    shortName: "AWS",
    badgeBg: "bg-amber-50/90",
    badgeText: "text-amber-800",
    badgeBorder: "border-amber-200",
    svg: AWS_PROVIDER_SVG,
    dataUri: svgToDataUri(AWS_PROVIDER_SVG),
  },
  multi: {
    id: "multi",
    name: "Multi-Cloud Architecture",
    shortName: "Multi-Cloud",
    badgeBg: "bg-indigo-50/90",
    badgeText: "text-indigo-700",
    badgeBorder: "border-indigo-200",
    svg: AZURE_PROVIDER_SVG,
    dataUri: svgToDataUri(AZURE_PROVIDER_SVG),
  },
  neutral: {
    id: "neutral",
    name: "Cloud Architecture",
    shortName: "Cloud",
    badgeBg: "bg-slate-50/90",
    badgeText: "text-slate-700",
    badgeBorder: "border-slate-200",
    svg: NEUTRAL_PROVIDER_SVG,
    dataUri: svgToDataUri(NEUTRAL_PROVIDER_SVG),
  },
};

// =============================================================================
// OFFICIAL AZURE ARCHITECTURE SERVICE ICONS
// =============================================================================

export const AZURE_VM_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <rect x="2" y="3" width="20" height="14" rx="2" fill="#0078D4"/>
  <rect x="4" y="5" width="16" height="10" rx="1" fill="#FFFFFF" opacity="0.95"/>
  <path fill="#0078D4" d="M6 7h4v2H6zm0 3h8v1.5H6zm0 2.5h6v1.5H6z"/>
  <circle cx="16.5" cy="8" r="1.5" fill="#50E6FF"/>
  <path fill="#005A9E" d="M8 18h8v2H8zm-2 2h12v1H6z"/>
</svg>
`;

export const AZURE_CONTAINER_APPS_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <path fill="#0078D4" d="M12 2l8 4.6v9.2L12 20.4 4 15.8V6.6L12 2z"/>
  <path fill="#50E6FF" d="M12 4.3l6 3.5v7l-6 3.4-6-3.4v-7l6-3.5z"/>
  <path fill="#FFFFFF" d="M12 6.5l4 2.3v4.6l-4 2.3-4-2.3V8.8l4-2.3z"/>
  <path fill="#0078D4" d="M12 8.5l2 1.2v2.4l-2 1.2-2-1.2V9.7l2-1.2z"/>
</svg>
`;

export const AZURE_APP_SERVICE_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <rect x="3" y="3" width="18" height="18" rx="3" fill="#0078D4"/>
  <path fill="#FFFFFF" d="M5 6h14v2H5zm0 4h6v2H5zm0 4h8v2H5zm0 4h14v1H5z"/>
  <circle cx="16" cy="13" r="2.5" fill="#50E6FF"/>
  <path fill="#005A9E" d="M15.5 11.5h1v3h-1zM14 13h3v1h-3z"/>
</svg>
`;

export const AZURE_POSTGRESQL_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <ellipse cx="12" cy="6" rx="8" ry="3.2" fill="#0078D4"/>
  <path fill="#005A9E" d="M4 6v5c0 1.8 3.6 3.2 8 3.2s8-1.4 8-3.2V6c0 1.8-3.6 3.2-8 3.2S4 7.8 4 6z"/>
  <path fill="#0078D4" d="M4 11v5c0 1.8 3.6 3.2 8 3.2s8-1.4 8-3.2v-5c0 1.8-3.6 3.2-8 3.2s-8-1.4-8-3.2z"/>
  <circle cx="12" cy="14" r="2.2" fill="#50E6FF"/>
  <path fill="#FFFFFF" d="M11 13h2v2h-2z"/>
</svg>
`;

export const AZURE_STORAGE_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <rect x="3" y="4" width="18" height="4.5" rx="1.5" fill="#0078D4"/>
  <rect x="3" y="9.75" width="18" height="4.5" rx="1.5" fill="#0078D4"/>
  <rect x="3" y="15.5" width="18" height="4.5" rx="1.5" fill="#0078D4"/>
  <circle cx="6.5" cy="6.25" r="1" fill="#50E6FF"/>
  <circle cx="6.5" cy="12" r="1" fill="#50E6FF"/>
  <circle cx="6.5" cy="17.75" r="1" fill="#50E6FF"/>
  <rect x="10" y="5.75" width="9" height="1" rx="0.5" fill="#FFFFFF"/>
  <rect x="10" y="11.5" width="9" height="1" rx="0.5" fill="#FFFFFF"/>
  <rect x="10" y="17.25" width="9" height="1" rx="0.5" fill="#FFFFFF"/>
</svg>
`;

export const AZURE_FRONT_DOOR_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <circle cx="12" cy="12" r="9" fill="#0078D4"/>
  <ellipse cx="12" cy="12" rx="4" ry="8" fill="none" stroke="#FFFFFF" stroke-width="1.2"/>
  <path stroke="#FFFFFF" stroke-width="1.2" d="M3.5 12h17M5.5 7.5h13M5.5 16.5h13"/>
  <circle cx="12" cy="4" r="1.5" fill="#50E6FF"/>
  <circle cx="19" cy="12" r="1.5" fill="#50E6FF"/>
  <circle cx="12" cy="20" r="1.5" fill="#50E6FF"/>
  <circle cx="5" cy="12" r="1.5" fill="#50E6FF"/>
</svg>
`;

export const AZURE_APP_GATEWAY_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <rect x="3" y="4" width="18" height="16" rx="2" fill="#0078D4"/>
  <path fill="#50E6FF" d="M5 8h14v2H5zm0 6h14v2H5z"/>
  <path fill="#FFFFFF" d="M8 6l4 4-4 4V6zm8 4l-4 4 4 4v-8z"/>
</svg>
`;

export const AZURE_KEY_VAULT_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <path fill="#0078D4" d="M12 2l7 3.5v5.8c0 4.8-3 9.3-7 10.7-4-1.4-7-5.9-7-10.7V5.5L12 2z"/>
  <circle cx="12" cy="9.5" r="2.5" fill="#F59E0B"/>
  <path fill="#F59E0B" d="M11.3 11.5h1.4v5h-1.4zm0 2.2h2.5v1.2h-2.5zm0 2.2h2v1.2h-2z"/>
</svg>
`;

export const AZURE_AI_FOUNDRY_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <circle cx="12" cy="12" r="9" fill="#0078D4"/>
  <circle cx="12" cy="8" r="2" fill="#50E6FF"/>
  <circle cx="8" cy="14" r="2" fill="#50E6FF"/>
  <circle cx="16" cy="14" r="2" fill="#50E6FF"/>
  <path stroke="#FFFFFF" stroke-width="1.5" d="M12 10l-3 3m3-3l3 3m-6 1h6"/>
  <circle cx="12" cy="12" r="1.2" fill="#FFFFFF"/>
</svg>
`;

export const AZURE_WAF_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <path fill="#EA580C" d="M12 2l7 3.5v5.8c0 4.8-3 9.3-7 10.7-4-1.4-7-5.9-7-10.7V5.5L12 2z"/>
  <path fill="#FFFFFF" d="M7 8h10v2H7zm0 3.5h10V13H7zm0 3.5h10v1.5H7z"/>
  <path fill="#EA580C" d="M11 8h2v2h-2zm-3 3.5h2V13H8zm6 0h2V13h-2zm-3 3.5h2v1.5h-2z"/>
</svg>
`;

export const AZURE_MONITOR_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <rect x="3" y="4" width="18" height="14" rx="2" fill="#0078D4"/>
  <path fill="#FFFFFF" d="M4 18h16v1.5H4z"/>
  <path stroke="#50E6FF" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" fill="none" d="M6 13l3-4 3 5 2.5-3.5L17 12"/>
  <circle cx="17" cy="12" r="1.5" fill="#10B981"/>
</svg>
`;

export const AZURE_VNET_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <rect x="2" y="3" width="7" height="6" rx="1.5" fill="#0078D4"/>
  <rect x="15" y="3" width="7" height="6" rx="1.5" fill="#0078D4"/>
  <rect x="8.5" y="15" width="7" height="6" rx="1.5" fill="#0078D4"/>
  <path stroke="#0078D4" stroke-width="1.5" fill="none" d="M5.5 9v3h13V9M12 12v3"/>
</svg>
`;

// =============================================================================
// OFFICIAL GOOGLE CLOUD ARCHITECTURE SERVICE ICONS
// =============================================================================

export const GCP_CLOUD_RUN_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <path fill="#4285F4" d="M12 2l8 4.6v9.2L12 20.4 4 15.8V6.6L12 2z"/>
  <path fill="#FFFFFF" d="M8 8.5l4-2.3 4 2.3v1.8l-4-2.3-4 2.3V8.5zm0 3.2l4-2.3 4 2.3v1.8l-4-2.3-4 2.3v-1.8zm0 3.3l4-2.3 4 2.3v1.8l-4-2.3-4 2.3V15z"/>
</svg>
`;

export const GCP_CLOUD_SQL_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <ellipse cx="12" cy="6" rx="7.5" ry="3" fill="#4285F4"/>
  <path fill="#34A853" d="M4.5 6v4.5c0 1.6 3.4 3 7.5 3s7.5-1.4 7.5-3V6c0 1.6-3.4 3-7.5 3S4.5 7.6 4.5 6z"/>
  <path fill="#FBBC04" d="M4.5 10.5V15c0 1.6 3.4 3 7.5 3s7.5-1.4 7.5-3v-4.5c0 1.6-3.4 3-7.5 3s-7.5-1.4-7.5-3z"/>
  <path fill="#EA4335" d="M4.5 15v3.5c0 1.6 3.4 3 7.5 3s7.5-1.4 7.5-3V15c0 1.6-3.4 3-7.5 3s-7.5-1.4-7.5-3z"/>
</svg>
`;

export const GCP_CLOUD_STORAGE_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <rect x="3" y="4" width="18" height="5" rx="1.5" fill="#4285F4"/>
  <rect x="3" y="10" width="18" height="5" rx="1.5" fill="#4285F4"/>
  <rect x="3" y="16" width="18" height="5" rx="1.5" fill="#4285F4"/>
  <rect x="6" y="6" width="3" height="1.5" rx="0.75" fill="#EA4335"/>
  <rect x="6" y="12" width="3" height="1.5" rx="0.75" fill="#FBBC04"/>
  <rect x="6" y="18" width="3" height="1.5" rx="0.75" fill="#34A853"/>
  <rect x="11" y="6" width="7" height="1" rx="0.5" fill="#FFFFFF"/>
  <rect x="11" y="12" width="7" height="1" rx="0.5" fill="#FFFFFF"/>
  <rect x="11" y="18" width="7" height="1" rx="0.5" fill="#FFFFFF"/>
</svg>
`;

export const GCP_LOAD_BALANCING_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <circle cx="12" cy="5" r="3" fill="#4285F4"/>
  <circle cx="6" cy="18" r="3" fill="#34A853"/>
  <circle cx="18" cy="18" r="3" fill="#FBBC04"/>
  <path stroke="#4285F4" stroke-width="1.8" d="M12 8v4m-6 3l6-3 6 3"/>
  <circle cx="12" cy="12" r="1.5" fill="#EA4335"/>
</svg>
`;

export const GCP_CLOUD_ARMOR_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <path fill="#4285F4" d="M12 2l7 3.5v5.8c0 4.8-3 9.3-7 10.7-4-1.4-7-5.9-7-10.7V5.5L12 2z"/>
  <path fill="#34A853" d="M12 4.5l5 2.5v4.5c0 3.7-2.3 7.2-5 8.3-2.7-1.1-5-4.6-5-8.3V7l5-2.5z"/>
  <path fill="#FFFFFF" d="M10.5 11.5l1.5 1.5 3-3 1.2 1.2-4.2 4.2-2.7-2.7z"/>
</svg>
`;

export const GCP_VERTEX_AI_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <circle cx="12" cy="12" r="9" fill="#4285F4"/>
  <path fill="#EA4335" d="M12 4a8 8 0 0 1 8 8h-4a4 4 0 0 0-4-4V4z"/>
  <path fill="#FBBC04" d="M20 12a8 8 0 0 1-8 8v-4a4 4 0 0 0 4-4h4z"/>
  <path fill="#34A853" d="M12 20a8 8 0 0 1-8-8h4a4 4 0 0 0 4 4v4z"/>
  <circle cx="12" cy="12" r="2.5" fill="#FFFFFF"/>
</svg>
`;

export const GCP_SECRET_MANAGER_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <rect x="5" y="10" width="14" height="11" rx="2" fill="#4285F4"/>
  <path fill="none" stroke="#FBBC04" stroke-width="2.2" stroke-linecap="round" d="M8 10V6.5a4 4 0 0 1 8 0V10"/>
  <circle cx="12" cy="15" r="1.5" fill="#FFFFFF"/>
  <path fill="#FFFFFF" d="M11.5 15.5h1v3h-1z"/>
</svg>
`;

export const GCP_CLOUD_MONITORING_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <rect x="3" y="4" width="18" height="14" rx="2" fill="#4285F4"/>
  <path fill="#34A853" d="M4 18h16v1.5H4z"/>
  <path stroke="#FFFFFF" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" fill="none" d="M5.5 13l3.5-5 3 4 2.5-3 4 4"/>
  <circle cx="18.5" cy="13" r="1.5" fill="#FBBC04"/>
</svg>
`;

export const GCP_COMPUTE_ENGINE_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <rect x="4" y="4" width="16" height="16" rx="2" fill="#4285F4"/>
  <rect x="7" y="7" width="10" height="10" rx="1" fill="#FFFFFF"/>
  <circle cx="10" cy="10" r="1.5" fill="#EA4335"/>
  <circle cx="14" cy="10" r="1.5" fill="#FBBC04"/>
  <circle cx="10" cy="14" r="1.5" fill="#34A853"/>
  <circle cx="14" cy="14" r="1.5" fill="#4285F4"/>
  <path fill="#4285F4" d="M2 9h2v2H2zm0 4h2v2H2zm18-4h2v2h-2zm0 4h2v2h-2zM9 2h2v2H9zm4 0h2v2h-2zm-4 18h2v2H9zm4 0h2v2h-2z"/>
</svg>
`;

// =============================================================================
// OFFICIAL AWS ARCHITECTURE SERVICE ICONS
// =============================================================================

export const AWS_EC2_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <rect x="3" y="3" width="18" height="18" rx="3" fill="#FF9900"/>
  <rect x="6" y="6" width="12" height="12" rx="1" fill="#232F3E"/>
  <path fill="#FF9900" d="M8 8h3v1.5H8zm0 3h5v1.5H8zm0 3h8v1.5H8z"/>
  <circle cx="15.5" cy="8.5" r="1.5" fill="#FF9900"/>
</svg>
`;

export const AWS_ECS_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <rect x="3" y="3" width="8" height="8" rx="1.5" fill="#FF9900"/>
  <rect x="13" y="3" width="8" height="8" rx="1.5" fill="#FF9900"/>
  <rect x="3" y="13" width="8" height="8" rx="1.5" fill="#FF9900"/>
  <rect x="13" y="13" width="8" height="8" rx="1.5" fill="#232F3E"/>
  <circle cx="17" cy="17" r="2" fill="#FF9900"/>
</svg>
`;

export const AWS_LAMBDA_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <rect x="3" y="3" width="18" height="18" rx="3" fill="#FF9900"/>
  <path fill="#FFFFFF" d="M8 6h3l3.5 8.5L16 6h2l-2.8 7.5L18 18h-3l-2.2-5.5L10 18H8l3.8-9.5L8 6z"/>
</svg>
`;

export const AWS_RDS_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <ellipse cx="12" cy="6" rx="8" ry="3" fill="#3B48CC"/>
  <path fill="#2E27AD" d="M4 6v5c0 1.6 3.6 3 8 3s8-1.4 8-3V6c0 1.6-3.6 3-8 3S4 7.6 4 6z"/>
  <path fill="#3B48CC" d="M4 11v5c0 1.6 3.6 3 8 3s8-1.4 8-3v-5c0 1.6-3.6 3-8 3s-8-1.4-8-3z"/>
  <circle cx="12" cy="14" r="2" fill="#50E6FF"/>
</svg>
`;

export const AWS_S3_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <path fill="#7AA116" d="M4 5h16l-2 14H6L4 5z"/>
  <ellipse cx="12" cy="5" rx="8" ry="2" fill="#95C623"/>
  <path fill="#54700F" d="M6 9h12v2H6zm1 4h10v2H7zm2 4h6v1.5H9z"/>
</svg>
`;

export const AWS_CLOUDFRONT_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <circle cx="12" cy="12" r="9" fill="#8C4FFF"/>
  <circle cx="12" cy="6" r="1.5" fill="#FFFFFF"/>
  <circle cx="17.5" cy="15" r="1.5" fill="#FFFFFF"/>
  <circle cx="6.5" cy="15" r="1.5" fill="#FFFFFF"/>
  <path stroke="#FFFFFF" stroke-width="1.4" fill="none" d="M12 7.5v4.5l3.5 2M12 12l-3.5 2"/>
</svg>
`;

export const AWS_ELB_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <rect x="3" y="3" width="18" height="18" rx="3" fill="#8C4FFF"/>
  <circle cx="7" cy="8" r="2" fill="#FFFFFF"/>
  <circle cx="7" cy="16" r="2" fill="#FFFFFF"/>
  <circle cx="17" cy="12" r="2.5" fill="#FFFFFF"/>
  <path stroke="#FFFFFF" stroke-width="1.5" d="M9 8l5 3m-5 5l5-3"/>
</svg>
`;

export const AWS_WAF_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <path fill="#DD344C" d="M12 2l7 3.5v5.8c0 4.8-3 9.3-7 10.7-4-1.4-7-5.9-7-10.7V5.5L12 2z"/>
  <path fill="#FFFFFF" d="M7 8h10v2H7zm0 3.5h10V13H7zm0 3.5h10v1.5H7z"/>
  <path fill="#DD344C" d="M11 8h2v2h-2zm-3 3.5h2V13H8zm6 0h2V13h-2zm-3 3.5h2v1.5h-2z"/>
</svg>
`;

export const AWS_KMS_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <path fill="#DD344C" d="M12 2l7 3.5v5.8c0 4.8-3 9.3-7 10.7-4-1.4-7-5.9-7-10.7V5.5L12 2z"/>
  <circle cx="12" cy="9.5" r="2.5" fill="#FF9900"/>
  <path fill="#FF9900" d="M11.3 11.5h1.4v5h-1.4zm0 2.2h2.5v1.2h-2.5zm0 2.2h2v1.2h-2z"/>
</svg>
`;

export const AWS_CLOUDWATCH_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <rect x="3" y="4" width="18" height="14" rx="2" fill="#E7157B"/>
  <path fill="#FFFFFF" d="M4 18h16v1.5H4z"/>
  <path stroke="#FFFFFF" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" fill="none" d="M6 13l3-4 3 5 2.5-3.5L17 12"/>
  <circle cx="17" cy="12" r="1.5" fill="#FF9900"/>
</svg>
`;

export const AWS_VPC_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <rect x="3" y="3" width="18" height="18" rx="3" fill="#8C4FFF"/>
  <rect x="6" y="6" width="5" height="5" rx="1" fill="#FFFFFF"/>
  <rect x="13" y="6" width="5" height="5" rx="1" fill="#FFFFFF"/>
  <rect x="9.5" y="13" width="5" height="5" rx="1" fill="#FFFFFF"/>
  <path stroke="#FFFFFF" stroke-width="1.2" d="M8.5 11v2h7v-2M12 13v2"/>
</svg>
`;

// =============================================================================
// NEUTRAL ARCHITECTURAL FALLBACK ICON
// =============================================================================

export const NEUTRAL_FALLBACK_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <rect x="3" y="3" width="18" height="18" rx="3" fill="#64748B"/>
  <rect x="6" y="6" width="12" height="12" rx="1.5" fill="#F8FAFC"/>
  <circle cx="9" cy="9" r="1.5" fill="#3B82F6"/>
  <circle cx="15" cy="9" r="1.5" fill="#10B981"/>
  <circle cx="9" cy="15" r="1.5" fill="#F59E0B"/>
  <circle cx="15" cy="15" r="1.5" fill="#8B5CF6"/>
</svg>
`;

// =============================================================================
// ICON REGISTRY
// =============================================================================

export const CLOUD_ICON_REGISTRY: Record<string, CloudServiceIcon> = {
  // Azure Services
  "azure-virtual-machines": {
    id: "azure-virtual-machines",
    name: "Azure Virtual Machines",
    provider: "azure",
    category: "compute",
    svg: AZURE_VM_SVG,
    dataUri: svgToDataUri(AZURE_VM_SVG),
  },
  "azure-container-apps": {
    id: "azure-container-apps",
    name: "Azure Container Apps",
    provider: "azure",
    category: "compute",
    svg: AZURE_CONTAINER_APPS_SVG,
    dataUri: svgToDataUri(AZURE_CONTAINER_APPS_SVG),
  },
  "azure-app-service": {
    id: "azure-app-service",
    name: "Azure App Service",
    provider: "azure",
    category: "compute",
    svg: AZURE_APP_SERVICE_SVG,
    dataUri: svgToDataUri(AZURE_APP_SERVICE_SVG),
  },
  "azure-postgresql": {
    id: "azure-postgresql",
    name: "Azure Database for PostgreSQL",
    provider: "azure",
    category: "database",
    svg: AZURE_POSTGRESQL_SVG,
    dataUri: svgToDataUri(AZURE_POSTGRESQL_SVG),
  },
  "azure-storage": {
    id: "azure-storage",
    name: "Azure Blob Storage",
    provider: "azure",
    category: "storage",
    svg: AZURE_STORAGE_SVG,
    dataUri: svgToDataUri(AZURE_STORAGE_SVG),
  },
  "azure-front-door": {
    id: "azure-front-door",
    name: "Azure Front Door",
    provider: "azure",
    category: "networking",
    svg: AZURE_FRONT_DOOR_SVG,
    dataUri: svgToDataUri(AZURE_FRONT_DOOR_SVG),
  },
  "azure-application-gateway": {
    id: "azure-application-gateway",
    name: "Azure Application Gateway",
    provider: "azure",
    category: "networking",
    svg: AZURE_APP_GATEWAY_SVG,
    dataUri: svgToDataUri(AZURE_APP_GATEWAY_SVG),
  },
  "azure-key-vault": {
    id: "azure-key-vault",
    name: "Azure Key Vault",
    provider: "azure",
    category: "security",
    svg: AZURE_KEY_VAULT_SVG,
    dataUri: svgToDataUri(AZURE_KEY_VAULT_SVG),
  },
  "azure-ai-foundry": {
    id: "azure-ai-foundry",
    name: "Azure AI Foundry / OpenAI",
    provider: "azure",
    category: "ai_ml",
    svg: AZURE_AI_FOUNDRY_SVG,
    dataUri: svgToDataUri(AZURE_AI_FOUNDRY_SVG),
  },
  "azure-waf": {
    id: "azure-waf",
    name: "Azure WAF Policy",
    provider: "azure",
    category: "security",
    svg: AZURE_WAF_SVG,
    dataUri: svgToDataUri(AZURE_WAF_SVG),
  },
  "azure-monitor": {
    id: "azure-monitor",
    name: "Azure Monitor",
    provider: "azure",
    category: "monitoring",
    svg: AZURE_MONITOR_SVG,
    dataUri: svgToDataUri(AZURE_MONITOR_SVG),
  },
  "azure-virtual-network": {
    id: "azure-virtual-network",
    name: "Azure Virtual Network",
    provider: "azure",
    category: "networking",
    svg: AZURE_VNET_SVG,
    dataUri: svgToDataUri(AZURE_VNET_SVG),
  },

  // GCP Services
  "gcp-cloud-run": {
    id: "gcp-cloud-run",
    name: "Google Cloud Run",
    provider: "gcp",
    category: "compute",
    svg: GCP_CLOUD_RUN_SVG,
    dataUri: svgToDataUri(GCP_CLOUD_RUN_SVG),
  },
  "gcp-cloud-sql": {
    id: "gcp-cloud-sql",
    name: "Cloud SQL for PostgreSQL",
    provider: "gcp",
    category: "database",
    svg: GCP_CLOUD_SQL_SVG,
    dataUri: svgToDataUri(GCP_CLOUD_SQL_SVG),
  },
  "gcp-cloud-storage": {
    id: "gcp-cloud-storage",
    name: "Google Cloud Storage",
    provider: "gcp",
    category: "storage",
    svg: GCP_CLOUD_STORAGE_SVG,
    dataUri: svgToDataUri(GCP_CLOUD_STORAGE_SVG),
  },
  "gcp-cloud-cdn": {
    id: "gcp-cloud-cdn",
    name: "Cloud CDN & Load Balancing",
    provider: "gcp",
    category: "networking",
    svg: GCP_LOAD_BALANCING_SVG,
    dataUri: svgToDataUri(GCP_LOAD_BALANCING_SVG),
  },
  "gcp-cloud-armor": {
    id: "gcp-cloud-armor",
    name: "Cloud Armor WAF",
    provider: "gcp",
    category: "security",
    svg: GCP_CLOUD_ARMOR_SVG,
    dataUri: svgToDataUri(GCP_CLOUD_ARMOR_SVG),
  },
  "gcp-vertex-ai": {
    id: "gcp-vertex-ai",
    name: "Vertex AI (Gemini)",
    provider: "gcp",
    category: "ai_ml",
    svg: GCP_VERTEX_AI_SVG,
    dataUri: svgToDataUri(GCP_VERTEX_AI_SVG),
  },
  "gcp-secret-manager": {
    id: "gcp-secret-manager",
    name: "Secret Manager",
    provider: "gcp",
    category: "security",
    svg: GCP_SECRET_MANAGER_SVG,
    dataUri: svgToDataUri(GCP_SECRET_MANAGER_SVG),
  },
  "gcp-cloud-monitoring": {
    id: "gcp-cloud-monitoring",
    name: "Cloud Monitoring",
    provider: "gcp",
    category: "monitoring",
    svg: GCP_CLOUD_MONITORING_SVG,
    dataUri: svgToDataUri(GCP_CLOUD_MONITORING_SVG),
  },
  "gcp-compute-engine": {
    id: "gcp-compute-engine",
    name: "Compute Engine",
    provider: "gcp",
    category: "compute",
    svg: GCP_COMPUTE_ENGINE_SVG,
    dataUri: svgToDataUri(GCP_COMPUTE_ENGINE_SVG),
  },

  // AWS Services
  "aws-ec2": {
    id: "aws-ec2",
    name: "Amazon EC2",
    provider: "aws",
    category: "compute",
    svg: AWS_EC2_SVG,
    dataUri: svgToDataUri(AWS_EC2_SVG),
  },
  "aws-ecs": {
    id: "aws-ecs",
    name: "Amazon ECS",
    provider: "aws",
    category: "compute",
    svg: AWS_ECS_SVG,
    dataUri: svgToDataUri(AWS_ECS_SVG),
  },
  "aws-lambda": {
    id: "aws-lambda",
    name: "AWS Lambda",
    provider: "aws",
    category: "compute",
    svg: AWS_LAMBDA_SVG,
    dataUri: svgToDataUri(AWS_LAMBDA_SVG),
  },
  "aws-rds": {
    id: "aws-rds",
    name: "Amazon RDS",
    provider: "aws",
    category: "database",
    svg: AWS_RDS_SVG,
    dataUri: svgToDataUri(AWS_RDS_SVG),
  },
  "aws-s3": {
    id: "aws-s3",
    name: "Amazon S3",
    provider: "aws",
    category: "storage",
    svg: AWS_S3_SVG,
    dataUri: svgToDataUri(AWS_S3_SVG),
  },
  "aws-cloudfront": {
    id: "aws-cloudfront",
    name: "Amazon CloudFront",
    provider: "aws",
    category: "networking",
    svg: AWS_CLOUDFRONT_SVG,
    dataUri: svgToDataUri(AWS_CLOUDFRONT_SVG),
  },
  "aws-elb": {
    id: "aws-elb",
    name: "Elastic Load Balancing",
    provider: "aws",
    category: "networking",
    svg: AWS_ELB_SVG,
    dataUri: svgToDataUri(AWS_ELB_SVG),
  },
  "aws-waf": {
    id: "aws-waf",
    name: "AWS WAF",
    provider: "aws",
    category: "security",
    svg: AWS_WAF_SVG,
    dataUri: svgToDataUri(AWS_WAF_SVG),
  },
  "aws-kms": {
    id: "aws-kms",
    name: "AWS Key Management Service",
    provider: "aws",
    category: "security",
    svg: AWS_KMS_SVG,
    dataUri: svgToDataUri(AWS_KMS_SVG),
  },
  "aws-cloudwatch": {
    id: "aws-cloudwatch",
    name: "Amazon CloudWatch",
    provider: "aws",
    category: "monitoring",
    svg: AWS_CLOUDWATCH_SVG,
    dataUri: svgToDataUri(AWS_CLOUDWATCH_SVG),
  },
  "aws-vpc": {
    id: "aws-vpc",
    name: "Amazon VPC",
    provider: "aws",
    category: "networking",
    svg: AWS_VPC_SVG,
    dataUri: svgToDataUri(AWS_VPC_SVG),
  },

  // Fallback
  "neutral-fallback": {
    id: "neutral-fallback",
    name: "Architecture Component",
    provider: "neutral",
    category: "general",
    svg: NEUTRAL_FALLBACK_SVG,
    dataUri: svgToDataUri(NEUTRAL_FALLBACK_SVG),
  },
};

export const NEUTRAL_FALLBACK_ICON = CLOUD_ICON_REGISTRY["neutral-fallback"];

// =============================================================================
// RESOURCE MAPPING ENGINE
// =============================================================================

export function getServiceIcon(
  rawIdentifier: string,
  providerHint?: CloudProvider
): CloudServiceIcon {
  if (!rawIdentifier || !rawIdentifier.trim()) {
    return NEUTRAL_FALLBACK_ICON;
  }

  const s = rawIdentifier.trim().toLowerCase();

  // 1. Direct registry ID match
  if (CLOUD_ICON_REGISTRY[s]) {
    return CLOUD_ICON_REGISTRY[s];
  }

  // 2. AWS Matchers
  if (providerHint === "aws" || (!providerHint && (s.includes("aws") || s.includes("amazon")))) {
    if (s.includes("ec2") || s.includes("virtual-machine") || s.includes("instance")) {
      return CLOUD_ICON_REGISTRY["aws-ec2"];
    }
    if (s.includes("ecs") || s.includes("fargate") || s.includes("container")) {
      return CLOUD_ICON_REGISTRY["aws-ecs"];
    }
    if (s.includes("lambda") || s.includes("serverless")) {
      return CLOUD_ICON_REGISTRY["aws-lambda"];
    }
    if (s.includes("rds") || s.includes("postgres") || s.includes("aurora") || s.includes("database")) {
      return CLOUD_ICON_REGISTRY["aws-rds"];
    }
    if (s.includes("s3") || s.includes("bucket") || s.includes("storage")) {
      return CLOUD_ICON_REGISTRY["aws-s3"];
    }
    if (s.includes("cloudfront") || s.includes("cdn")) {
      return CLOUD_ICON_REGISTRY["aws-cloudfront"];
    }
    if (s.includes("elb") || s.includes("alb") || s.includes("load balancing")) {
      return CLOUD_ICON_REGISTRY["aws-elb"];
    }
    if (s.includes("waf") || s.includes("shield")) {
      return CLOUD_ICON_REGISTRY["aws-waf"];
    }
    if (s.includes("kms") || s.includes("key") || s.includes("secret")) {
      return CLOUD_ICON_REGISTRY["aws-kms"];
    }
    if (s.includes("cloudwatch") || s.includes("monitoring") || s.includes("telemetry")) {
      return CLOUD_ICON_REGISTRY["aws-cloudwatch"];
    }
    if (s.includes("vpc") || s.includes("subnet") || s.includes("network")) {
      return CLOUD_ICON_REGISTRY["aws-vpc"];
    }
  }

  // 3. Azure Explicit Matchers
  if (providerHint === "azure" || (!providerHint && (s.includes("azure") || s.startsWith("microsoft.")))) {
    if (s.includes("virtual-machine") || s.includes("virtualmachine") || s.includes("vm") || s.includes("compute/virtual")) {
      return CLOUD_ICON_REGISTRY["azure-virtual-machines"];
    }
    if (s.includes("container-app") || s.includes("container app") || s.includes("app/container")) {
      return CLOUD_ICON_REGISTRY["azure-container-apps"];
    }
    if (s.includes("app-service") || s.includes("web app") || s.includes("appservice") || s.includes("web/sites")) {
      return CLOUD_ICON_REGISTRY["azure-app-service"];
    }
    if (s.includes("postgres") || s.includes("psql") || s.includes("dbforpostgresql")) {
      return CLOUD_ICON_REGISTRY["azure-postgresql"];
    }
    if (s.includes("blob") || s.includes("storageaccount") || s.includes("storage-account") || s.includes("storage/storage")) {
      return CLOUD_ICON_REGISTRY["azure-storage"];
    }
    if (s.includes("front door") || s.includes("front-door") || s.includes("frontdoor") || s.includes("cdn/profiles")) {
      return CLOUD_ICON_REGISTRY["azure-front-door"];
    }
    if (s.includes("application gateway") || s.includes("app gateway") || s.includes("applicationgateway")) {
      return CLOUD_ICON_REGISTRY["azure-application-gateway"];
    }
    if (s.includes("key vault") || s.includes("key-vault") || s.includes("keyvault")) {
      return CLOUD_ICON_REGISTRY["azure-key-vault"];
    }
    if (s.includes("ai foundry") || s.includes("ai-foundry") || s.includes("openai") || s.includes("cognitive")) {
      return CLOUD_ICON_REGISTRY["azure-ai-foundry"];
    }
    if (s.includes("waf") || s.includes("firewall") || s.includes("web application firewall")) {
      return CLOUD_ICON_REGISTRY["azure-waf"];
    }
    if (s.includes("monitor") || s.includes("log-analytics") || s.includes("insights") || s.includes("operationalinsights")) {
      return CLOUD_ICON_REGISTRY["azure-monitor"];
    }
    if (s.includes("vnet") || s.includes("virtual network") || s.includes("virtualnetwork") || s.includes("subnet")) {
      return CLOUD_ICON_REGISTRY["azure-virtual-network"];
    }
  }

  // 4. GCP Explicit Matchers
  if (providerHint === "gcp" || (!providerHint && (s.includes("gcp") || s.includes("google") || s.includes(".googleapis.com")))) {
    if (s.includes("run") || s.includes("cloud-run") || s.includes("run.googleapis.com")) {
      return CLOUD_ICON_REGISTRY["gcp-cloud-run"];
    }
    if (s.includes("sql") || s.includes("cloud-sql") || s.includes("sqladmin.googleapis.com")) {
      return CLOUD_ICON_REGISTRY["gcp-cloud-sql"];
    }
    if (s.includes("storage") || s.includes("gcs") || s.includes("bucket") || s.includes("storage.googleapis.com")) {
      return CLOUD_ICON_REGISTRY["gcp-cloud-storage"];
    }
    if (s.includes("cdn") || s.includes("load balancing") || s.includes("load-balancing") || s.includes("glb") || s.includes("forwardingrule")) {
      return CLOUD_ICON_REGISTRY["gcp-cloud-cdn"];
    }
    if (s.includes("armor") || s.includes("cloud-armor") || s.includes("securitypolicy")) {
      return CLOUD_ICON_REGISTRY["gcp-cloud-armor"];
    }
    if (s.includes("vertex") || s.includes("gemini") || s.includes("vertex-ai") || s.includes("aiplatform.googleapis.com")) {
      return CLOUD_ICON_REGISTRY["gcp-vertex-ai"];
    }
    if (s.includes("secret") || s.includes("secret-manager") || s.includes("secretmanager.googleapis.com")) {
      return CLOUD_ICON_REGISTRY["gcp-secret-manager"];
    }
    if (s.includes("monitoring") || s.includes("cloud-monitoring") || s.includes("monitoring.googleapis.com")) {
      return CLOUD_ICON_REGISTRY["gcp-cloud-monitoring"];
    }
    if (s.includes("compute") || s.includes("instance") || s.includes("compute.googleapis.com")) {
      return CLOUD_ICON_REGISTRY["gcp-compute-engine"];
    }
  }

  // 5. Generic Keyword Heuristic
  if (s.includes("postgres") || s.includes("database") || s.includes("db")) {
    return providerHint === "gcp"
      ? CLOUD_ICON_REGISTRY["gcp-cloud-sql"]
      : providerHint === "aws"
      ? CLOUD_ICON_REGISTRY["aws-rds"]
      : CLOUD_ICON_REGISTRY["azure-postgresql"];
  }
  if (s.includes("container") || s.includes("docker")) {
    return providerHint === "gcp"
      ? CLOUD_ICON_REGISTRY["gcp-cloud-run"]
      : providerHint === "aws"
      ? CLOUD_ICON_REGISTRY["aws-ecs"]
      : CLOUD_ICON_REGISTRY["azure-container-apps"];
  }
  if (s.includes("storage") || s.includes("blob") || s.includes("bucket")) {
    return providerHint === "gcp"
      ? CLOUD_ICON_REGISTRY["gcp-cloud-storage"]
      : providerHint === "aws"
      ? CLOUD_ICON_REGISTRY["aws-s3"]
      : CLOUD_ICON_REGISTRY["azure-storage"];
  }
  if (s.includes("secret") || s.includes("key") || s.includes("vault")) {
    return providerHint === "gcp"
      ? CLOUD_ICON_REGISTRY["gcp-secret-manager"]
      : providerHint === "aws"
      ? CLOUD_ICON_REGISTRY["aws-kms"]
      : CLOUD_ICON_REGISTRY["azure-key-vault"];
  }
  if (s.includes("waf") || s.includes("armor") || s.includes("shield")) {
    return providerHint === "gcp"
      ? CLOUD_ICON_REGISTRY["gcp-cloud-armor"]
      : providerHint === "aws"
      ? CLOUD_ICON_REGISTRY["aws-waf"]
      : CLOUD_ICON_REGISTRY["azure-waf"];
  }
  if (s.includes("ai") || s.includes("openai") || s.includes("vertex") || s.includes("gemini")) {
    return providerHint === "gcp"
      ? CLOUD_ICON_REGISTRY["gcp-vertex-ai"]
      : CLOUD_ICON_REGISTRY["azure-ai-foundry"];
  }
  if (s.includes("gateway") || s.includes("router") || s.includes("cdn") || s.includes("load balancer")) {
    return providerHint === "gcp"
      ? CLOUD_ICON_REGISTRY["gcp-cloud-cdn"]
      : providerHint === "aws"
      ? CLOUD_ICON_REGISTRY["aws-elb"]
      : CLOUD_ICON_REGISTRY["azure-front-door"];
  }
  if (s.includes("monitor") || s.includes("telemetry") || s.includes("metrics")) {
    return providerHint === "gcp"
      ? CLOUD_ICON_REGISTRY["gcp-cloud-monitoring"]
      : providerHint === "aws"
      ? CLOUD_ICON_REGISTRY["aws-cloudwatch"]
      : CLOUD_ICON_REGISTRY["azure-monitor"];
  }

  return NEUTRAL_FALLBACK_ICON;
}

export function detectDiagramProvider(
  chartDsl: string,
  title?: string,
  explicitProvider?: CloudProvider
): CloudProvider {
  if (explicitProvider && explicitProvider !== "neutral") {
    return explicitProvider;
  }

  const combined = `${title || ""} ${chartDsl || ""}`.toLowerCase();

  const hasAzure =
    combined.includes("azure") ||
    combined.includes("microsoft") ||
    combined.includes("subgraph azure") ||
    combined.includes("subgraph sub");

  const hasGcp =
    combined.includes("gcp") ||
    combined.includes("google") ||
    combined.includes("subgraph gcp") ||
    combined.includes("subgraph org");

  const hasAws =
    combined.includes("aws") ||
    combined.includes("amazon") ||
    combined.includes("subgraph aws");

  if ((hasAzure && hasGcp) || (hasAzure && hasAws) || (hasGcp && hasAws)) {
    return "multi";
  }
  if (hasAzure) return "azure";
  if (hasGcp) return "gcp";
  if (hasAws) return "aws";

  return "neutral";
}

/**
 * Prepares an enriched Mermaid chart with official service icons embedded in node labels,
 * and official provider icons embedded into architecture boundaries.
 */
export function enrichMermaidWithIcons(
  chart: string,
  providerHint?: CloudProvider
): string {
  if (!chart || !chart.trim()) return "";

  const provider = detectDiagramProvider(chart, undefined, providerHint);
  const lines = chart.split("\n");
  const enrichedLines: string[] = [];

  // Match node definitions: nodeId["label"] or nodeId[("label")]
  const nodeDefRegex = /^(\s*)([A-Za-z0-9_]+)(\[\(?["']?)([\s\S]+?)(["']?\)?\])(:::[\w-]+)?$/;
  // Match subgraph declarations: subgraph Id["Title"] or subgraph Id[Title]
  const subgraphRegex = /^(\s*subgraph\s+([A-Za-z0-9_]+)\[["']?)([\s\S]+?)(["']?\]\s*)$/;

  for (const line of lines) {
    // 1. Check subgraph boundary matching provider
    const subMatch = line.match(subgraphRegex);
    if (subMatch) {
      const [, prefix, subId, subTitle, suffix] = subMatch;
      const lowerId = subId.toLowerCase();
      const lowerTitle = subTitle.toLowerCase();

      // Check if this subgraph is the root provider boundary
      if (
        !subTitle.includes("<img") &&
        (lowerId === "azure" ||
          lowerId === "gcp" ||
          lowerId === "aws" ||
          lowerId === "sub" ||
          lowerId === "org" ||
          lowerTitle.includes("azure") ||
          lowerTitle.includes("gcp") ||
          lowerTitle.includes("amazon") ||
          lowerTitle.includes("subscription:"))
      ) {
        const subProvider: CloudProvider =
          lowerId.includes("gcp") || lowerTitle.includes("gcp")
            ? "gcp"
            : lowerId.includes("aws") || lowerTitle.includes("aws")
            ? "aws"
            : "azure";
        const subBrand = PROVIDER_BRANDS[subProvider];
        const brandIconHtml = `<img src='${subBrand.dataUri}' class='cloud-provider-subgraph-icon' width='18' height='18' style='display:inline-block;vertical-align:middle;margin-right:6px;pointer-events:none;' />`;
        enrichedLines.push(`${prefix}${brandIconHtml} ${subTitle}${suffix}`);
        continue;
      }
    }

    // 2. Check standard node definitions
    const match = line.match(nodeDefRegex);
    if (!match) {
      enrichedLines.push(line);
      continue;
    }

    const [, indent, nodeId, openBracket, rawContent, closeBracket, classDef] = match;

    if (rawContent.includes("<img") || rawContent.includes("data:image")) {
      enrichedLines.push(line);
      continue;
    }

    const icon = getServiceIcon(`${nodeId} ${rawContent}`, provider);
    const iconHtml = `<img src='${icon.dataUri}' class='cloud-node-icon' width='22' height='22' style='display:inline-block;vertical-align:middle;margin-bottom:3px;pointer-events:none;' /><br/>`;
    const enrichedContent = `${iconHtml}${rawContent}`;

    const rebuilt = `${indent}${nodeId}${openBracket}${enrichedContent}${closeBracket}${classDef || ""}`;
    enrichedLines.push(rebuilt);
  }

  return enrichedLines.join("\n");
}
