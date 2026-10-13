/**
 * Diagram export and clipboard utility for Mermaid architecture diagrams.
 *
 * Implements:
 * - Fail-proof, 100% XML-compliant standalone SVG export
 * - Pure SVG vector translation for reliable, error-free Canvas rasterization
 * - High-resolution PNG export (retina scale 2x)
 * - System clipboard image copying via ClipboardItem API
 * - Content and provider-aware filename generation
 */

import {
  CloudProvider,
  PROVIDER_BRANDS,
} from "./cloudIcons";

export interface ExportOptions {
  title?: string;
  provider?: CloudProvider;
  filenamePrefix?: string;
  scale?: number;
  backgroundColor?: string;
  includeBanner?: boolean;
  includeLegend?: boolean;
}

export interface ExportResult {
  success: boolean;
  format: "png" | "svg" | "clipboard";
  filename?: string;
  error?: string;
}

/**
 * Sanitizes and generates a meaningful filename based on diagram title and provider.
 */
export function generateExportFilename(
  title?: string,
  provider?: CloudProvider,
  extension: "png" | "svg" = "png"
): string {
  const cleanTitle = (title || "architecture-topology")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");

  const providerPrefix =
    provider === "azure"
      ? "azure-"
      : provider === "gcp"
      ? "gcp-"
      : provider === "aws"
      ? "aws-"
      : provider === "multi"
      ? "multicloud-"
      : "";

  let base = cleanTitle;
  if (providerPrefix && !cleanTitle.startsWith(providerPrefix)) {
    base = `${providerPrefix}${cleanTitle}`;
  }

  const timestamp = new Date().toISOString().slice(0, 10);
  return `${base}-${timestamp}.${extension}`;
}

/**
 * Sanitizes raw Mermaid SVG string to ensure 100% strict XML compliance.
 * Resolves void HTML tags (<br>, <hr>, <img>) that cause XML parsers to abort in new Image().
 */
export function sanitizeSvgForXmlCompliance(rawSvg: string): string {
  let xml = rawSvg;

  // 1. Close unclosed <br> tags
  xml = xml.replace(/<br(?!\s*\/?>)(\s*[^>]*)>/gi, "<br$1/>");
  xml = xml.replace(/<br\s*>/gi, "<br/>");

  // 2. Close unclosed <hr> tags
  xml = xml.replace(/<hr(?!\s*\/?>)(\s*[^>]*)>/gi, "<hr$1/>");
  xml = xml.replace(/<hr\s*>/gi, "<hr/>");

  // 3. Close unclosed <img> tags
  xml = xml.replace(/<img(?!\s*\/?>)([^>]*?)>/gi, "<img$1/>");

  // 4. Ensure foreignObject divs declare XHTML namespace
  xml = xml.replace(
    /<foreignObject([^>]*)>\s*<div(?!\s+xmlns)/gi,
    '<foreignObject$1><div xmlns="http://www.w3.org/1999/xhtml"'
  );

  // 5. Ensure requiredExtensions on foreignObject for strict SVG validators
  xml = xml.replace(
    /<foreignObject(?![^>]*requiredExtensions)([^>]*)>/gi,
    '<foreignObject requiredExtensions="http://www.w3.org/1999/xhtml"$1>'
  );

  // 6. Ensure image tags have both href and xlink:href
  xml = xml.replace(
    /<image\s+([^>]*?)href="([^"]+)"(?!\s+xlink:href)/gi,
    '<image $1href="$2" xlink:href="$2"'
  );

  // 7. Ensure bare ampersands in text/styles are XML encoded
  xml = xml.replace(/&(?!(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)/g, "&amp;");

  return xml;
}

/**
 * Converts HTML labels inside <foreignObject> into standard pure SVG elements (<g>, <image>, <text>, <tspan>).
 * This completely eliminates browser XML parsing failures and canvas tainting issues when rasterizing.
 */
export function convertForeignObjectsToPureSvg(svgElement: Element): void {
  const foreignObjects = Array.from(svgElement.querySelectorAll("foreignObject"));
  for (const fo of foreignObjects) {
    const foW = parseFloat(fo.getAttribute("width") || "0") || 160;
    const foX = parseFloat(fo.getAttribute("x") || "0") || 0;
    const foY = parseFloat(fo.getAttribute("y") || "0") || 0;

    // 1. Extract embedded icon if present
    const img = fo.querySelector("img");
    const imgSrc = img ? img.getAttribute("src") : null;
    const imgW = img ? parseFloat(img.getAttribute("width") || "22") || 22 : 0;
    const imgH = img ? parseFloat(img.getAttribute("height") || "22") || 22 : 0;

    // 2. Extract text lines
    const containerDiv = fo.querySelector("div") || fo;
    const clone = containerDiv.cloneNode(true) as Element;
    clone.querySelectorAll("br").forEach((br) => br.replaceWith("\n"));
    const rawLines = (clone.textContent || "")
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l.length > 0);

    // 3. Create pure SVG group replacement
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.setAttribute("class", "pure-svg-label");

    let currentY = foY + 4;

    // Append SVG <image> for icon
    if (imgSrc) {
      const svgImg = document.createElementNS("http://www.w3.org/2000/svg", "image");
      const iconX = foX + (foW - imgW) / 2;
      svgImg.setAttribute("x", iconX.toString());
      svgImg.setAttribute("y", currentY.toString());
      svgImg.setAttribute("width", imgW.toString());
      svgImg.setAttribute("height", imgH.toString());
      svgImg.setAttribute("href", imgSrc);
      svgImg.setAttributeNS("http://www.w3.org/1999/xlink", "xlink:href", imgSrc);
      g.appendChild(svgImg);
      currentY += imgH + 6;
    }

    // Append SVG <text> and <tspan> lines
    if (rawLines.length > 0) {
      const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
      const centerX = (foX + foW / 2).toString();
      text.setAttribute("x", centerX);
      text.setAttribute("y", currentY.toString());
      text.setAttribute("text-anchor", "middle");
      text.setAttribute(
        "font-family",
        "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
      );
      text.setAttribute("fill", "#0f172a");

      rawLines.forEach((lineText, idx) => {
        const tspan = document.createElementNS("http://www.w3.org/2000/svg", "tspan");
        tspan.setAttribute("x", centerX);
        if (idx === 0) {
          tspan.setAttribute("dy", "11");
          tspan.setAttribute("font-size", "13");
          tspan.setAttribute("font-weight", "600");
          tspan.setAttribute("fill", "#0f172a");
        } else if (lineText.includes("$") || lineText.toLowerCase().includes("/mo")) {
          tspan.setAttribute("dy", "15");
          tspan.setAttribute("font-size", "11.5");
          tspan.setAttribute("font-weight", "700");
          tspan.setAttribute("fill", "#1e293b");
        } else {
          tspan.setAttribute("dy", "14");
          tspan.setAttribute("font-size", "11");
          tspan.setAttribute("font-weight", "400");
          tspan.setAttribute("fill", "#475569");
        }
        tspan.textContent = lineText;
        text.appendChild(tspan);
      });
      g.appendChild(text);
    }

    // Replace the foreignObject with the pure SVG representation
    fo.replaceWith(g);
  }
}

/**
 * Builds a standalone, self-contained SVG representation with embedded
 * branding banner, clean background, and visual legend.
 */
export function buildStandaloneExportSvg(
  sourceSvgMarkup: string,
  options: ExportOptions = {}
): { standaloneSvg: string; width: number; height: number } {
  const {
    title = "Architecture Topology",
    provider = "azure",
    backgroundColor = "#ffffff",
    includeBanner = true,
    includeLegend = true,
  } = options;

  const sanitizedSource = sanitizeSvgForXmlCompliance(sourceSvgMarkup);

  // 1. Extract viewBox or dimensions from the source SVG
  const vbMatch = sanitizedSource.match(/viewBox\s*=\s*["']([^"']+)["']/i);
  let origW = 1000;
  let origH = 650;
  let minX = 0;
  let minY = 0;

  if (vbMatch && vbMatch[1]) {
    const parts = vbMatch[1].trim().split(/[\s,]+/).map(parseFloat);
    if (parts.length === 4) {
      minX = parts[0] || 0;
      minY = parts[1] || 0;
      origW = Math.max(200, parts[2] || 1000);
      origH = Math.max(200, parts[3] || 650);
    }
  } else {
    const wMatch = sanitizedSource.match(/width\s*=\s*["']([0-9.]+)["']/i);
    const hMatch = sanitizedSource.match(/height\s*=\s*["']([0-9.]+)["']/i);
    if (wMatch && wMatch[1]) origW = parseFloat(wMatch[1]) || 1000;
    if (hMatch && hMatch[1]) origH = parseFloat(hMatch[1]) || 650;
  }

  const paddingX = 40;
  const bannerHeight = includeBanner ? 90 : 20;
  const legendHeight = includeLegend ? 70 : 20;

  const totalW = Math.round(origW + paddingX * 2);
  const totalH = Math.round(origH + bannerHeight + legendHeight);

  // 2. Extract inner content of the source SVG
  const innerContent = sanitizedSource
    .replace(/^[\s\S]*?<svg\b[^>]*>/i, "")
    .replace(/<\/svg>[\s\S]*$/i, "");

  // Extract <style> blocks from source to preserve styling
  const styleMatches = sanitizedSource.match(/<style[\s\S]*?<\/style>/gi) || [];
  const inlinedStyles = styleMatches.join("\n");

  const brand = PROVIDER_BRANDS[provider] || PROVIDER_BRANDS.azure;

  // 3. Build Header Banner
  const headerBannerSvg = includeBanner
    ? `
    <!-- Top Branding Banner -->
    <g transform="translate(${paddingX}, 24)">
      <!-- Provider Logo -->
      <image href="${brand.dataUri}" xlink:href="${brand.dataUri}" x="0" y="2" width="36" height="36" />
      
      <!-- Titles -->
      <text x="48" y="20" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="18" font-weight="700" fill="#0f172a">
        ${escapeXml(title)}
      </text>
      <text x="48" y="38" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="11.5" font-weight="500" fill="#64748b">
        FinOps &amp; Infrastructure Intelligence Platform • Production Architecture Blueprint
      </text>

      <!-- Provider Badge Pill -->
      <g transform="translate(${totalW - paddingX * 2 - 120}, 4)">
        <rect width="120" height="26" rx="13" fill="#f1f5f9" stroke="#cbd5e1" stroke-width="1"/>
        <text x="60" y="17" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="11" font-weight="600" fill="#334155" text-anchor="middle">
          ${escapeXml(brand.shortName)} Blueprint
        </text>
      </g>
      
      <!-- Divider Rule -->
      <line x1="0" y1="52" x2="${totalW - paddingX * 2}" y2="52" stroke="#e2e8f0" stroke-width="1.5"/>
    </g>
  `
    : "";

  // 4. Build Bottom Legend
  const legendY = totalH - legendHeight + 8;
  const bottomLegendSvg = includeLegend
    ? `
    <!-- Architecture Component Legend -->
    <g transform="translate(${paddingX}, ${legendY})">
      <line x1="0" y1="0" x2="${totalW - paddingX * 2}" y2="0" stroke="#e2e8f0" stroke-width="1.5"/>
      
      <g transform="translate(0, 16)">
        <text x="0" y="14" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="11" font-weight="700" fill="#1e293b">Legend:</text>
        
        <!-- Compute -->
        <rect x="65" y="4" width="12" height="12" rx="2" fill="#eff6ff" stroke="#3b82f6" stroke-width="1.5"/>
        <text x="83" y="14" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="11" fill="#475569">Compute</text>
        
        <!-- Database -->
        <rect x="155" y="4" width="12" height="12" rx="2" fill="#f0fdf4" stroke="#10b981" stroke-width="1.5"/>
        <text x="173" y="14" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="11" fill="#475569">Database</text>
        
        <!-- Storage -->
        <rect x="250" y="4" width="12" height="12" rx="2" fill="#fffbeb" stroke="#f59e0b" stroke-width="1.5"/>
        <text x="268" y="14" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="11" fill="#475569">Storage</text>
        
        <!-- Network -->
        <rect x="335" y="4" width="12" height="12" rx="2" fill="#f0f9ff" stroke="#0284c7" stroke-width="1.5"/>
        <text x="353" y="14" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="11" fill="#475569">Network</text>
        
        <!-- Security -->
        <rect x="420" y="4" width="12" height="12" rx="2" fill="#fff7ed" stroke="#ea580c" stroke-width="1.5"/>
        <text x="438" y="14" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="11" fill="#475569">Security</text>
        
        <!-- AI/ML -->
        <rect x="505" y="4" width="12" height="12" rx="2" fill="#faf5ff" stroke="#a855f7" stroke-width="1.5"/>
        <text x="523" y="14" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="11" fill="#475569">AI / ML</text>
        
        <!-- Verified Link -->
        <line x1="590" y1="10" x2="615" y2="10" stroke="#475569" stroke-width="2"/>
        <text x="622" y="14" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="11" fill="#475569">Verified Link</text>
        
        <!-- Inferred Link -->
        <line x1="710" y1="10" x2="735" y2="10" stroke="#64748b" stroke-width="1.8" stroke-dasharray="4 3"/>
        <text x="742" y="14" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="11" fill="#475569">Inferred Tier</text>
      </g>
    </g>
  `
    : "";

  const shiftX = paddingX - minX;
  const shiftY = bannerHeight - minY;

  const standaloneSvg = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 ${totalW} ${totalH}" width="${totalW}" height="${totalH}">
  <defs>
    ${inlinedStyles}
    <style>
      <![CDATA[
      text {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      }
      .node rect, .node circle, .node polygon, .node path {
        stroke-width: 1.75px !important;
      }
      .cluster rect {
        rx: 10px !important;
        ry: 10px !important;
        fill: #f8fafc !important;
        stroke: #cbd5e1 !important;
      }
      .cloud-node-icon {
        display: inline-block;
        vertical-align: middle;
      }
      ]]>
    </style>
  </defs>

  <!-- Clean Canvas Background -->
  <rect width="100%" height="100%" fill="${backgroundColor}" />

  ${headerBannerSvg}

  <!-- Diagram Topology Graph -->
  <g transform="translate(${shiftX}, ${shiftY})">
    ${innerContent}
  </g>

  ${bottomLegendSvg}
</svg>`;

  return { standaloneSvg, width: totalW, height: totalH };
}

/**
 * Downloads the diagram as a scalable, self-contained SVG file.
 */
export async function downloadSvg(
  sourceSvgMarkup: string,
  options: ExportOptions = {}
): Promise<ExportResult> {
  try {
    const { standaloneSvg } = buildStandaloneExportSvg(sourceSvgMarkup, options);
    const filename = generateExportFilename(options.title, options.provider, "svg");

    const blob = new Blob([standaloneSvg], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);

    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);

    setTimeout(() => URL.revokeObjectURL(url), 2000);

    return { success: true, format: "svg", filename };
  } catch (err: unknown) {
    const errorMsg = err instanceof Error ? err.message : "SVG generation failed";
    console.error("SVG export error:", err);
    return { success: false, format: "svg", error: errorMsg };
  }
}

/**
 * Robustly renders the standalone SVG onto a high-DPI canvas and returns an image Blob.
 * Performs browser DOM conversion of foreignObjects to pure SVG elements to prevent rasterization errors.
 */
export async function rasterizeSvgToBlob(
  sourceSvgMarkup: string,
  options: ExportOptions = {}
): Promise<{ blob: Blob; width: number; height: number }> {
  const { standaloneSvg, width, height } = buildStandaloneExportSvg(sourceSvgMarkup, options);
  const scale = options.scale || 2; // Retina 2x resolution

  // In browser environments with DOMParser, convert any foreignObjects to pure SVG
  let finalSvgString = standaloneSvg;
  if (typeof window !== "undefined" && typeof DOMParser !== "undefined") {
    try {
      const parser = new DOMParser();
      const doc = parser.parseFromString(standaloneSvg, "image/svg+xml");
      if (!doc.querySelector("parsererror")) {
        convertForeignObjectsToPureSvg(doc.documentElement);
        const serializer = new XMLSerializer();
        finalSvgString = serializer.serializeToString(doc.documentElement);
      }
    } catch (e) {
      console.warn("DOMParser pure SVG conversion warning:", e);
    }
  }

  return new Promise((resolve, reject) => {
    const svgBlob = new Blob([finalSvgString], { type: "image/svg+xml;charset=utf-8" });
    const svgUrl = URL.createObjectURL(svgBlob);
    const img = new Image();
    img.crossOrigin = "anonymous";

    const onImageReady = () => {
      try {
        const canvas = document.createElement("canvas");
        canvas.width = Math.round(width * scale);
        canvas.height = Math.round(height * scale);

        const ctx = canvas.getContext("2d");
        if (!ctx) {
          URL.revokeObjectURL(svgUrl);
          reject(new Error("Unable to create 2D canvas rendering context"));
          return;
        }

        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = "high";
        ctx.scale(scale, scale);

        // Fill solid background
        ctx.fillStyle = options.backgroundColor || "#ffffff";
        ctx.fillRect(0, 0, width, height);

        // Draw image onto canvas
        ctx.drawImage(img, 0, 0, width, height);

        canvas.toBlob(
          (pngBlob) => {
            URL.revokeObjectURL(svgUrl);
            if (!pngBlob || pngBlob.size === 0) {
              reject(new Error("Canvas rasterization returned empty image blob"));
              return;
            }
            resolve({ blob: pngBlob, width: canvas.width, height: canvas.height });
          },
          "image/png",
          1.0
        );
      } catch (e) {
        URL.revokeObjectURL(svgUrl);
        reject(e);
      }
    };

    img.onload = () => {
      if ("decode" in img && typeof img.decode === "function") {
        img
          .decode()
          .then(onImageReady)
          .catch(() => onImageReady());
      } else {
        onImageReady();
      }
    };

    img.onerror = () => {
      URL.revokeObjectURL(svgUrl);
      console.error(
        "SVG rasterization failed. First 500 chars of SVG payload:",
        finalSvgString.slice(0, 500)
      );
      reject(
        new Error(
          `Image element failed to load SVG markup for rasterization (payload size: ${finalSvgString.length} bytes).`
        )
      );
    };

    img.src = svgUrl;
  });
}

/**
 * Downloads the diagram as a high-resolution PNG image.
 */
export async function downloadPng(
  sourceSvgMarkup: string,
  options: ExportOptions = {}
): Promise<ExportResult> {
  try {
    const { blob } = await rasterizeSvgToBlob(sourceSvgMarkup, options);
    const filename = generateExportFilename(options.title, options.provider, "png");
    const url = URL.createObjectURL(blob);

    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);

    setTimeout(() => URL.revokeObjectURL(url), 2000);

    return { success: true, format: "png", filename };
  } catch (err: unknown) {
    const errorMsg = err instanceof Error ? err.message : "PNG generation failed";
    console.error("PNG export error:", err);
    return { success: false, format: "png", error: errorMsg };
  }
}

/**
 * Copies the complete diagram image directly to the system clipboard.
 * Uses browser-native ClipboardItem API with graceful error messaging.
 */
export async function copyDiagramImageToClipboard(
  sourceSvgMarkup: string,
  options: ExportOptions = {}
): Promise<ExportResult> {
  try {
    if (!navigator.clipboard || typeof window.ClipboardItem === "undefined") {
      throw new Error(
        "Direct image clipboard copying is not supported in this browser. Please use 'Download PNG' instead."
      );
    }

    const { blob } = await rasterizeSvgToBlob(sourceSvgMarkup, options);
    const clipboardItem = new ClipboardItem({ "image/png": blob });
    await navigator.clipboard.write([clipboardItem]);

    return { success: true, format: "clipboard" };
  } catch (err: unknown) {
    const errorMsg =
      err instanceof Error ? err.message : "Failed to copy image to clipboard";
    console.warn("Clipboard copy failure:", err);
    return { success: false, format: "clipboard", error: errorMsg };
  }
}

function escapeXml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}
