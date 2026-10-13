"use client";

import React, { useEffect, useRef, useState, useCallback, useMemo } from "react";
import {
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Maximize2,
  Minimize2,
  Code2,
  Layers,
  Focus,
  ArrowLeftRight,
  Copy,
  Check,
  Download,
  FileCode,
  Image as ImageIcon,
  CheckCircle2,
  AlertCircle,
  Loader2,
} from "lucide-react";
import {
  CloudProvider,
  detectDiagramProvider,
  enrichMermaidWithIcons,
  PROVIDER_BRANDS,
} from "@/lib/cloudIcons";
import {
  downloadPng,
  downloadSvg,
  copyDiagramImageToClipboard,
} from "@/lib/diagramExport";

interface MermaidDiagramProps {
  chart: string;
  className?: string;
  title?: string;
  provider?: CloudProvider;
}

interface SvgDimensions {
  width: number;
  height: number;
  viewBox: string;
}

interface ToastState {
  message: string;
  type: "success" | "error" | "info";
}

export const MermaidDiagram: React.FC<MermaidDiagramProps> = ({
  chart,
  className = "",
  title = "Architecture Topology",
  provider,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const [svgContent, setSvgContent] = useState<string>("");
  const [svgDimensions, setSvgDimensions] = useState<SvgDimensions>({
    width: 800,
    height: 500,
    viewBox: "0 0 800 500",
  });
  const [renderError, setRenderError] = useState<string | null>(null);

  // Viewport navigation state
  const [zoom, setZoom] = useState<number>(100);
  const [pan, setPan] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [dragStart, setDragStart] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  // UI state
  const [isExpanded, setIsExpanded] = useState<boolean>(false);
  const [showSource, setShowSource] = useState<boolean>(false);
  const [copiedDsl, setCopiedDsl] = useState<boolean>(false);
  const [orientation, setOrientation] = useState<"default" | "TD" | "LR">("default");

  // Export action states
  const [isExportingPng, setIsExportingPng] = useState<boolean>(false);
  const [isExportingSvg, setIsExportingSvg] = useState<boolean>(false);
  const [isCopyingImage, setIsCopyingImage] = useState<boolean>(false);
  const [toast, setToast] = useState<ToastState | null>(null);

  // Auto-dismiss toast feedback
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 3800);
    return () => clearTimeout(timer);
  }, [toast]);

  // Determine active provider brand
  const activeProvider = useMemo(() => {
    return detectDiagramProvider(chart, title, provider);
  }, [chart, title, provider]);

  const providerBrand = PROVIDER_BRANDS[activeProvider] || PROVIDER_BRANDS.azure;

  // Clean chart with orientation applied (used in DSL drawer & Copy DSL)
  const effectiveChart = useMemo(() => {
    if (!chart || !chart.trim()) return "";
    let formatted = chart.trim();
    if (orientation === "TD") {
      formatted = formatted.replace(/^flowchart\s+[A-Za-z]+/m, "flowchart TD");
      formatted = formatted.replace(/^graph\s+[A-Za-z]+/m, "graph TD");
    } else if (orientation === "LR") {
      formatted = formatted.replace(/^flowchart\s+[A-Za-z]+/m, "flowchart LR");
      formatted = formatted.replace(/^graph\s+[A-Za-z]+/m, "graph LR");
    }
    return formatted;
  }, [chart, orientation]);

  // Enriched chart with official service icons (used for Mermaid rendering)
  const enrichedChart = useMemo(() => {
    if (!effectiveChart) return "";
    return enrichMermaidWithIcons(effectiveChart, activeProvider);
  }, [effectiveChart, activeProvider]);

  // Clean and enhance SVG markup
  const processSvgMarkup = useCallback((rawSvg: string): { svg: string; dims: SvgDimensions } => {
    // 1. Extract viewBox or width/height
    const viewBoxMatch = rawSvg.match(/viewBox\s*=\s*["']([^"']+)["']/i);
    let vbW = 800;
    let vbH = 500;
    let vbStr = "0 0 800 500";

    if (viewBoxMatch && viewBoxMatch[1]) {
      vbStr = viewBoxMatch[1].trim();
      const parts = vbStr.split(/[\s,]+/);
      if (parts.length === 4) {
        vbW = Math.max(100, parseFloat(parts[2]) || 800);
        vbH = Math.max(100, parseFloat(parts[3]) || 500);
      }
    } else {
      const wMatch = rawSvg.match(/width\s*=\s*["']([0-9.]+)["']/i);
      const hMatch = rawSvg.match(/height\s*=\s*["']([0-9.]+)["']/i);
      if (wMatch && wMatch[1]) vbW = parseFloat(wMatch[1]) || 800;
      if (hMatch && hMatch[1]) vbH = parseFloat(hMatch[1]) || 500;
      vbStr = `0 0 ${vbW} ${vbH}`;
    }

    // 2. Strip restrictive max-width styles that shrink the diagram inside its container
    let clean = rawSvg
      .replace(/style\s*=\s*["']max-width:[^"']+["']/gi, 'style="max-width:none;width:100%;height:100%;"')
      .replace(/(<svg\b[^>]*?)\s+width\s*=\s*["'][^"']*["']/i, '$1 width="100%"')
      .replace(/(<svg\b[^>]*?)\s+height\s*=\s*["'][^"']*["']/i, '$1 height="100%"');

    if (!clean.includes("viewBox")) {
      clean = clean.replace(/(<svg\b[^>]*?)(>)/i, `$1 viewBox="${vbStr}"$2`);
    }

    // 3. Inject high-contrast, modern typography & edge styling directly into the SVG
    const svgStyles = `
      <style>
        .node rect, .node circle, .node ellipse, .node polygon, .node path {
          stroke-width: 1.75px !important;
          rx: 8px !important;
          ry: 8px !important;
        }
        .node .label {
          font-family: inherit !important;
          font-size: 13.5px !important;
          font-weight: 500 !important;
          line-height: 1.35 !important;
          color: #0f172a !important;
          text-align: center !important;
        }
        .cluster rect {
          rx: 12px !important;
          ry: 12px !important;
          stroke-width: 1.75px !important;
          fill: #f8fafc !important;
          stroke: #cbd5e1 !important;
        }
        .cluster text {
          font-size: 13px !important;
          font-weight: 700 !important;
          fill: #1e293b !important;
          letter-spacing: -0.01em !important;
        }
        .edgePath path {
          stroke: #475569 !important;
          stroke-width: 2px !important;
        }
        .edgeLabel {
          background-color: #ffffff !important;
          font-size: 11.5px !important;
          font-weight: 600 !important;
          color: #334155 !important;
          padding: 2px 6px !important;
          border-radius: 4px !important;
          border: 1px solid #e2e8f0 !important;
        }
        .marker {
          fill: #475569 !important;
          stroke: #475569 !important;
        }
        .cloud-node-icon {
          display: inline-block !important;
          vertical-align: middle !important;
          margin-bottom: 3px !important;
          pointer-events: none !important;
        }
      </style>
    `;

    if (clean.includes("<style>")) {
      clean = clean.replace("<style>", `<style>${svgStyles}`);
    } else {
      clean = clean.replace(/(<svg\b[^>]*>)/i, `$1${svgStyles}`);
    }

    return {
      svg: clean,
      dims: { width: vbW, height: vbH, viewBox: vbStr },
    };
  }, []);

  // Calculate zoom to fit container viewport
  const calculateFitZoom = useCallback(
    (customWidth?: number, customHeight?: number): { fitZoom: number; panCenter: { x: number; y: number } } => {
      const vp = viewportRef.current;
      const w = customWidth || svgDimensions.width;
      const h = customHeight || svgDimensions.height;

      if (!vp || !w || !h) {
        return { fitZoom: 100, panCenter: { x: 0, y: 0 } };
      }

      const vpW = vp.clientWidth;
      const vpH = vp.clientHeight;

      if (vpW <= 0 || vpH <= 0) {
        return { fitZoom: 100, panCenter: { x: 0, y: 0 } };
      }

      const padX = 40;
      const padY = 40;

      const scaleX = (vpW - padX * 2) / w;
      const scaleY = (vpH - padY * 2) / h;

      let fitScale = Math.min(scaleX, scaleY);

      if (w < 450 && h < 350) {
        fitScale = Math.min(fitScale, 1.25);
      }
      fitScale = Math.max(0.35, Math.min(1.8, fitScale));

      const computedZoom = Math.round(fitScale * 100);
      return { fitZoom: computedZoom, panCenter: { x: 0, y: 0 } };
    },
    [svgDimensions]
  );

  // Zoom to fit action
  const handleZoomToFit = useCallback(() => {
    const { fitZoom, panCenter } = calculateFitZoom();
    setZoom(fitZoom);
    setPan(panCenter);
  }, [calculateFitZoom]);

  // Render Mermaid on chart, enriched markup, or orientation change
  useEffect(() => {
    let isMounted = true;

    async function renderMermaid() {
      if (!enrichedChart || !enrichedChart.trim()) {
        setSvgContent("");
        return;
      }

      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          theme: "base",
          securityLevel: "loose",
          fontFamily:
            "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
          flowchart: {
            htmlLabels: true,
            curve: "basis",
            nodeSpacing: 50,
            rankSpacing: 60,
            padding: 20,
            useMaxWidth: false,
          },
          themeVariables: {
            primaryColor: "#eff6ff",
            primaryTextColor: "#0f172a",
            primaryBorderColor: "#93c5fd",
            lineColor: "#475569",
            secondaryColor: "#f8fafc",
            tertiaryColor: "#f1f5f9",
            fontSize: "14px",
          },
        });

        const id = `mermaid-${Math.random().toString(36).substring(2, 9)}`;
        const { svg: rawSvg } = await mermaid.render(id, enrichedChart);

        if (isMounted) {
          const { svg, dims } = processSvgMarkup(rawSvg);
          setSvgContent(svg);
          setSvgDimensions(dims);
          setRenderError(null);

          // Auto-fit zoom on initial load
          setTimeout(() => {
            if (viewportRef.current) {
              const vpW = viewportRef.current.clientWidth;
              const vpH = viewportRef.current.clientHeight;
              const padX = 40;
              const padY = 40;
              const scaleX = (vpW - padX * 2) / dims.width;
              const scaleY = (vpH - padY * 2) / dims.height;
              let fitScale = Math.min(scaleX, scaleY);
              if (dims.width < 450 && dims.height < 350) {
                fitScale = Math.min(fitScale, 1.25);
              }
              fitScale = Math.max(0.35, Math.min(1.8, fitScale));
              setZoom(Math.round(fitScale * 100));
              setPan({ x: 0, y: 0 });
            }
          }, 60);
        }
      } catch (err: unknown) {
        if (isMounted) {
          console.warn("Mermaid rendering warning:", err);
          setRenderError(
            err instanceof Error ? err.message : "Diagram rendering failed"
          );
        }
      }
    }

    renderMermaid();

    return () => {
      isMounted = false;
    };
  }, [enrichedChart, processSvgMarkup]);

  // Recalculate on container resize
  useEffect(() => {
    if (!viewportRef.current) return;
    const observer = new ResizeObserver(() => {});
    observer.observe(viewportRef.current);
    return () => observer.disconnect();
  }, []);

  // Escape key handler for fullscreen modal
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isExpanded) {
        setIsExpanded(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isExpanded]);

  // Zoom controls
  const handleZoomIn = () => setZoom((z) => Math.min(250, z + 15));
  const handleZoomOut = () => setZoom((z) => Math.max(30, z - 15));
  const handleZoomReset = () => {
    setZoom(100);
    setPan({ x: 0, y: 0 });
  };

  // Wheel zoom handler
  const handleWheel = (e: React.WheelEvent<HTMLDivElement>) => {
    if (e.ctrlKey || e.metaKey || isExpanded) {
      e.preventDefault();
      const delta = e.deltaY > 0 ? -10 : 10;
      setZoom((z) => Math.max(30, Math.min(250, z + delta)));
    }
  };

  // Drag & Pan handlers
  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    setIsDragging(true);
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!isDragging) return;
    setPan({
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y,
    });
  };

  const handleMouseUp = () => setIsDragging(false);

  // Touch drag handlers
  const handleTouchStart = (e: React.TouchEvent<HTMLDivElement>) => {
    if (e.touches.length === 1) {
      const touch = e.touches[0];
      setIsDragging(true);
      setDragStart({ x: touch.clientX - pan.x, y: touch.clientY - pan.y });
    }
  };

  const handleTouchMove = (e: React.TouchEvent<HTMLDivElement>) => {
    if (!isDragging || e.touches.length !== 1) return;
    const touch = e.touches[0];
    setPan({
      x: touch.clientX - dragStart.x,
      y: touch.clientY - dragStart.y,
    });
  };

  const handleTouchEnd = () => setIsDragging(false);

  // Copy DSL source
  const handleCopyDsl = async () => {
    try {
      await navigator.clipboard.writeText(effectiveChart);
      setCopiedDsl(true);
      setTimeout(() => setCopiedDsl(false), 2000);
    } catch (err) {
      console.warn("Copy to clipboard failed:", err);
    }
  };

  // Cycle orientation (Default -> TD -> LR)
  const toggleOrientation = () => {
    setOrientation((curr) => {
      if (curr === "default" || curr === "TD") return "LR";
      return "TD";
    });
  };

  // Download PNG Handler
  const handleDownloadPng = async () => {
    if (!svgContent || isExportingPng) return;
    setIsExportingPng(true);
    try {
      const result = await downloadPng(svgContent, {
        title,
        provider: activeProvider,
      });
      if (result.success) {
        setToast({
          message: `Saved PNG: ${result.filename}`,
          type: "success",
        });
      } else {
        setToast({
          message: result.error || "Failed to download PNG image",
          type: "error",
        });
      }
    } catch (err: unknown) {
      setToast({
        message: err instanceof Error ? err.message : "Failed to download PNG image",
        type: "error",
      });
    } finally {
      setIsExportingPng(false);
    }
  };

  // Download SVG Handler
  const handleDownloadSvg = async () => {
    if (!svgContent || isExportingSvg) return;
    setIsExportingSvg(true);
    try {
      const result = await downloadSvg(svgContent, {
        title,
        provider: activeProvider,
      });
      if (result.success) {
        setToast({
          message: `Saved Vector SVG: ${result.filename}`,
          type: "success",
        });
      } else {
        setToast({
          message: result.error || "Failed to download SVG vector file",
          type: "error",
        });
      }
    } catch (err: unknown) {
      setToast({
        message: err instanceof Error ? err.message : "Failed to download SVG vector file",
        type: "error",
      });
    } finally {
      setIsExportingSvg(false);
    }
  };

  // Copy Image to Clipboard Handler
  const handleCopyImage = async () => {
    if (!svgContent || isCopyingImage) return;
    setIsCopyingImage(true);
    try {
      const result = await copyDiagramImageToClipboard(svgContent, {
        title,
        provider: activeProvider,
      });
      if (result.success) {
        setToast({
          message: "Diagram image copied to clipboard! (Ready to paste into docs/slides)",
          type: "success",
        });
      } else {
        setToast({
          message: result.error || "Image clipboard copy failed. Please use 'Download PNG'.",
          type: "error",
        });
      }
    } catch (err: unknown) {
      setToast({
        message:
          err instanceof Error
            ? err.message
            : "Image clipboard copy failed. Please use 'Download PNG'.",
        type: "error",
      });
    } finally {
      setIsCopyingImage(false);
    }
  };

  if (renderError) {
    return (
      <div
        className={`p-5 bg-slate-50 border border-slate-200 rounded-2xl text-xs font-mono text-slate-700 whitespace-pre overflow-x-auto ${className}`}
      >
        <div className="text-amber-700 font-semibold mb-2 text-xs flex items-center gap-2">
          <span>Architecture Topology (Mermaid Definition):</span>
        </div>
        {chart}
      </div>
    );
  }

  if (!svgContent) {
    return (
      <div
        className={`flex flex-col items-center justify-center p-16 bg-slate-50/70 border border-slate-200/80 rounded-2xl text-slate-400 text-xs animate-pulse ${className}`}
      >
        <Layers className="w-6 h-6 text-slate-300 mb-2 animate-bounce" />
        <span>Rendering architecture graph viewport...</span>
      </div>
    );
  }

  const diagramCanvas = (
    <div
      ref={containerRef}
      className={`rounded-2xl border border-slate-200/90 bg-white shadow-sm overflow-hidden flex flex-col transition-all duration-200 relative ${
        isExpanded
          ? "fixed inset-4 z-50 bg-white shadow-2xl flex flex-col"
          : `${className} min-h-[500px]`
      }`}
    >
      {/* Toast Notification Pill */}
      {toast && (
        <div
          className={`absolute top-14 right-4 z-30 flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs shadow-lg backdrop-blur-md transition-all duration-300 animate-in fade-in slide-in-from-top-2 ${
            toast.type === "success"
              ? "bg-emerald-950/90 text-emerald-200 border border-emerald-700/60"
              : toast.type === "error"
              ? "bg-rose-950/90 text-rose-200 border border-rose-700/60"
              : "bg-slate-900/90 text-slate-200 border border-slate-700/60"
          }`}
        >
          {toast.type === "success" ? (
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          ) : (
            <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
          )}
          <span className="font-medium">{toast.message}</span>
        </div>
      )}

      {/* Top Toolbar */}
      <div className="px-3.5 py-2.5 bg-slate-50/90 border-b border-slate-200/80 flex flex-wrap items-center justify-between gap-2 text-xs select-none">
        {/* Title & Official Provider Branding Badge */}
        <div className="flex items-center gap-2 sm:gap-2.5 min-w-0">
          <div className="flex items-center gap-1.5 shrink-0">
            {/* Official Provider Logo Icon */}
            <span
              className={`p-1 rounded-lg border flex items-center justify-center shrink-0 ${providerBrand.badgeBg} ${providerBrand.badgeBorder}`}
              title={`${providerBrand.name} Visual Identity`}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={providerBrand.dataUri}
                alt={providerBrand.name}
                className="w-4 h-4"
              />
            </span>
            <span
              className={`hidden md:inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold border ${providerBrand.badgeBg} ${providerBrand.badgeText} ${providerBrand.badgeBorder}`}
            >
              {providerBrand.shortName}
            </span>
          </div>

          <div className="truncate">
            <span className="font-bold text-slate-900 text-xs truncate">
              {title}
            </span>
            <span className="hidden lg:inline-block ml-2 text-[11px] text-slate-500 font-normal">
              • Interactive Vector Canvas
            </span>
          </div>
        </div>

        {/* Action Controls Toolbar */}
        <div className="flex items-center gap-1 flex-wrap justify-end">
          {/* Zoom Out */}
          <button
            type="button"
            onClick={handleZoomOut}
            aria-label="Zoom out"
            className="p-1.5 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-200/60 active:scale-95 transition"
            title="Zoom out (-)"
          >
            <ZoomOut className="w-3.5 h-3.5" />
          </button>

          {/* Zoom % Indicator */}
          <button
            type="button"
            onClick={handleZoomReset}
            className="text-[11px] font-mono font-semibold text-slate-700 min-w-[44px] px-1 py-0.5 rounded hover:bg-slate-200/50 text-center transition"
            title="Click to reset to 100%"
          >
            {zoom}%
          </button>

          {/* Zoom In */}
          <button
            type="button"
            onClick={handleZoomIn}
            aria-label="Zoom in"
            className="p-1.5 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-200/60 active:scale-95 transition"
            title="Zoom in (+)"
          >
            <ZoomIn className="w-3.5 h-3.5" />
          </button>

          {/* Zoom to Fit */}
          <button
            type="button"
            onClick={handleZoomToFit}
            aria-label="Zoom to fit"
            className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-medium text-slate-700 hover:text-slate-900 hover:bg-slate-200/60 active:scale-95 transition"
            title="Fit diagram to viewport"
          >
            <Focus className="w-3.5 h-3.5 text-blue-600" />
            <span className="hidden sm:inline">Fit</span>
          </button>

          {/* Reset View */}
          <button
            type="button"
            onClick={handleZoomReset}
            aria-label="Reset zoom and position"
            className="p-1.5 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-200/60 active:scale-95 transition"
            title="Reset position & 100% zoom"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>

          {/* Flow Direction Toggle */}
          <button
            type="button"
            onClick={toggleOrientation}
            className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-medium text-slate-700 hover:text-slate-900 hover:bg-slate-200/60 active:scale-95 transition"
            title={`Toggle layout flow (Currently ${orientation === "LR" ? "Left-to-Right" : "Top-to-Bottom"})`}
          >
            <ArrowLeftRight className="w-3.5 h-3.5 text-slate-600" />
            <span className="hidden md:inline">
              {orientation === "LR" ? "LR" : "TD"}
            </span>
          </button>

          <span className="mx-0.5 text-slate-300" aria-hidden="true">
            |
          </span>

          {/* DOWNLOAD PNG */}
          <button
            type="button"
            onClick={handleDownloadPng}
            disabled={isExportingPng}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-semibold bg-blue-50 text-blue-700 hover:bg-blue-100 hover:text-blue-900 border border-blue-200/80 active:scale-95 transition disabled:opacity-60 disabled:cursor-not-allowed"
            title="Download high-resolution architecture PNG image"
          >
            {isExportingPng ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-600" />
            ) : (
              <Download className="w-3.5 h-3.5 text-blue-600" />
            )}
            <span>PNG</span>
          </button>

          {/* DOWNLOAD SVG */}
          <button
            type="button"
            onClick={handleDownloadSvg}
            disabled={isExportingSvg}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-semibold bg-emerald-50 text-emerald-700 hover:bg-emerald-100 hover:text-emerald-900 border border-emerald-200/80 active:scale-95 transition disabled:opacity-60 disabled:cursor-not-allowed"
            title="Download scalable standalone SVG vector graphic"
          >
            {isExportingSvg ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin text-emerald-600" />
            ) : (
              <FileCode className="w-3.5 h-3.5 text-emerald-600" />
            )}
            <span>SVG</span>
          </button>

          {/* COPY IMAGE TO CLIPBOARD */}
          <button
            type="button"
            onClick={handleCopyImage}
            disabled={isCopyingImage}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-semibold bg-purple-50 text-purple-700 hover:bg-purple-100 hover:text-purple-900 border border-purple-200/80 active:scale-95 transition disabled:opacity-60 disabled:cursor-not-allowed"
            title="Copy architecture image to clipboard (Paste directly into slides, docs, or chat)"
          >
            {isCopyingImage ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin text-purple-600" />
            ) : (
              <ImageIcon className="w-3.5 h-3.5 text-purple-600" />
            )}
            <span className="hidden sm:inline">Copy Image</span>
          </button>

          <span className="mx-0.5 text-slate-300" aria-hidden="true">
            |
          </span>

          {/* DSL Drawer Toggle */}
          <button
            type="button"
            onClick={() => setShowSource((s) => !s)}
            aria-pressed={showSource}
            className={`inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-medium transition ${
              showSource
                ? "bg-slate-200 text-slate-900 border border-slate-300"
                : "text-slate-700 hover:bg-slate-200/60"
            }`}
            title="Toggle Mermaid DSL source"
          >
            <Code2 className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">DSL</span>
          </button>

          {/* Expand / Fullscreen */}
          <button
            type="button"
            onClick={() => setIsExpanded((e) => !e)}
            aria-label={isExpanded ? "Exit full screen" : "Expand diagram full screen"}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-medium bg-slate-100 hover:bg-slate-200 text-slate-700 hover:text-slate-900 active:scale-95 transition"
            title={isExpanded ? "Close expanded view (Esc)" : "Expand full screen"}
          >
            {isExpanded ? (
              <>
                <Minimize2 className="w-3.5 h-3.5" />
                <span>Close</span>
              </>
            ) : (
              <>
                <Maximize2 className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Expand</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Main Graph Viewport */}
      <div
        ref={viewportRef}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        onWheel={handleWheel}
        onDoubleClick={handleZoomToFit}
        className={`relative overflow-hidden bg-slate-50/50 flex items-center justify-center select-none ${
          isDragging ? "cursor-grabbing" : "cursor-grab"
        } ${isExpanded ? "flex-1 min-h-0" : "h-[540px] sm:h-[600px] lg:h-[640px]"}`}
      >
        {/* Subtle viewport grid background */}
        <div
          className="absolute inset-0 pointer-events-none opacity-[0.35]"
          style={{
            backgroundImage:
              "radial-gradient(#94a3b8 0.75px, transparent 0.75px), radial-gradient(#94a3b8 0.75px, #f8fafc 0.75px)",
            backgroundSize: "28px 28px",
            backgroundPosition: "0 0, 14px 14px",
          }}
        />

        {/* Transform container holding the SVG */}
        <div
          style={{
            transform: `translate3d(${pan.x}px, ${pan.y}px, 0) scale(${zoom / 100})`,
            transformOrigin: "center center",
            width: `${svgDimensions.width}px`,
            height: `${svgDimensions.height}px`,
          }}
          className="transition-transform duration-75 relative flex items-center justify-center"
          dangerouslySetInnerHTML={{ __html: svgContent }}
        />

        {/* Viewport Interaction Helper Pill */}
        <div className="absolute bottom-3 right-3 pointer-events-none px-2.5 py-1 rounded-full bg-slate-900/75 backdrop-blur-xs text-[10px] text-slate-200 flex items-center gap-2 shadow-xs">
          <span>Drag to pan • Scroll to zoom • Double-click to fit</span>
        </div>
      </div>

      {/* Raw Mermaid DSL Drawer (shows clean effectiveChart without base64 noise) */}
      {showSource && (
        <div className="bg-slate-900 text-slate-100 text-xs font-mono border-t border-slate-800">
          <div className="px-4 py-2 bg-slate-950 flex items-center justify-between border-b border-slate-800 text-[11px] text-slate-400">
            <span>Mermaid Definition (DSL)</span>
            <button
              type="button"
              onClick={handleCopyDsl}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 transition"
            >
              {copiedDsl ? (
                <>
                  <Check className="w-3 h-3 text-emerald-400" />
                  <span className="text-emerald-400">Copied</span>
                </>
              ) : (
                <>
                  <Copy className="w-3 h-3" />
                  <span>Copy DSL</span>
                </>
              )}
            </button>
          </div>
          <pre className="p-4 max-h-56 overflow-auto whitespace-pre leading-relaxed text-slate-300">
            {effectiveChart}
          </pre>
        </div>
      )}

      {/* Diagram Footer with Legend & Dimensions */}
      <div className="px-4 py-2.5 bg-slate-50 border-t border-slate-200/80 flex flex-wrap items-center justify-between gap-3 text-[11px] text-slate-600">
        <div className="flex flex-wrap items-center gap-3">
          <span className="font-semibold text-slate-800">Legend:</span>
          <span className="inline-flex items-center gap-1.5">
            <span className="w-3 h-3 rounded bg-blue-100 border border-blue-400 inline-block" />
            <span>Compute</span>
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="w-3 h-3 rounded bg-emerald-100 border border-emerald-400 inline-block" />
            <span>Database</span>
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="w-3 h-3 rounded bg-amber-100 border border-amber-400 inline-block" />
            <span>Storage</span>
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="w-3 h-3 rounded bg-sky-100 border border-sky-400 inline-block" />
            <span>Network</span>
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="w-3 h-3 rounded bg-orange-100 border border-orange-400 inline-block" />
            <span>Security</span>
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="w-3 h-3 rounded bg-purple-100 border border-purple-400 inline-block" />
            <span>AI / ML</span>
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="w-4 h-0.5 bg-slate-600 inline-block" />
            <span>Verified Link</span>
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="w-4 h-0.5 border-b border-dashed border-slate-500 inline-block" />
            <span>Inferred Tier</span>
          </span>
        </div>

        <div className="flex items-center gap-2 text-slate-500">
          <span>{svgDimensions.width} × {svgDimensions.height}px native</span>
        </div>
      </div>
    </div>
  );

  return (
    <>
      {isExpanded && (
        <div
          className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-40 transition-opacity"
          onClick={() => setIsExpanded(false)}
          aria-hidden="true"
        />
      )}
      {diagramCanvas}
    </>
  );
};
