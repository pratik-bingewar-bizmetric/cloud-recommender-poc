"use client";

import React, { useEffect, useRef, useState, useCallback } from "react";
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
} from "lucide-react";

interface MermaidDiagramProps {
  chart: string;
  className?: string;
  title?: string;
}

interface SvgDimensions {
  width: number;
  height: number;
  viewBox: string;
}

export const MermaidDiagram: React.FC<MermaidDiagramProps> = ({
  chart,
  className = "",
  title = "Architecture Topology",
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

  // Determine active chart DSL with orientation toggle applied
  const effectiveChart = React.useMemo(() => {
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

      // Comfortable padding around graph
      const padX = 40;
      const padY = 40;

      const scaleX = (vpW - padX * 2) / w;
      const scaleY = (vpH - padY * 2) / h;

      // Fit preserving aspect ratio
      let fitScale = Math.min(scaleX, scaleY);

      // Intelligent bounds:
      // Small diagrams (< 450px): limit scaling to max 1.30 to prevent oversized typography
      // Large diagrams (> 1200px): allow scaling down to fit viewport (min 0.35)
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

  // Render Mermaid on chart or orientation change
  useEffect(() => {
    let isMounted = true;

    async function renderMermaid() {
      if (!effectiveChart || !effectiveChart.trim()) {
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
            useMaxWidth: false, // Prevents artificial max-width clamp
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
        const { svg: rawSvg } = await mermaid.render(id, effectiveChart);

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
  }, [effectiveChart, processSvgMarkup]);

  // Recalculate on container resize
  useEffect(() => {
    if (!viewportRef.current) return;
    const observer = new ResizeObserver(() => {
      // Keep pan centered if at fit scale
    });
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
    if (e.button !== 0) return; // Left click only
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
      className={`rounded-2xl border border-slate-200/90 bg-white shadow-sm overflow-hidden flex flex-col transition-all duration-200 ${
        isExpanded
          ? "fixed inset-4 z-50 bg-white shadow-2xl flex flex-col"
          : `${className} min-h-[500px]`
      }`}
    >
      {/* Top Toolbar */}
      <div className="px-4 py-2.5 bg-slate-50/80 border-b border-slate-200/80 flex flex-wrap items-center justify-between gap-2 text-xs select-none">
        <div className="flex items-center gap-2.5">
          <span className="p-1.5 rounded-lg bg-blue-100/70 text-blue-700">
            <Layers className="w-4 h-4" />
          </span>
          <div>
            <span className="font-bold text-slate-900 text-xs">
              {title}
            </span>
            <span className="hidden sm:inline-block ml-2 text-[11px] text-slate-500 font-normal">
              • Interactive Vector Canvas
            </span>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-1">
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
            className="text-[11px] font-mono font-semibold text-slate-700 min-w-[48px] px-1 py-0.5 rounded hover:bg-slate-200/50 text-center transition"
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
            <span className="hidden md:inline">Fit</span>
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

          <span className="mx-1 text-slate-300" aria-hidden="true">
            |
          </span>

          {/* Layout Flow Orientation Toggle */}
          <button
            type="button"
            onClick={toggleOrientation}
            className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-medium text-slate-700 hover:text-slate-900 hover:bg-slate-200/60 active:scale-95 transition"
            title={`Toggle layout flow (Currently ${orientation === "LR" ? "Left-to-Right" : "Top-to-Bottom"})`}
          >
            <ArrowLeftRight className="w-3.5 h-3.5 text-slate-600" />
            <span className="hidden md:inline">
              {orientation === "LR" ? "LR Flow" : "TD Flow"}
            </span>
          </button>

          {/* DSL Drawer Toggle */}
          <button
            type="button"
            onClick={() => setShowSource((s) => !s)}
            aria-pressed={showSource}
            className={`inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-medium transition ${
              showSource
                ? "bg-blue-100 text-blue-800 border border-blue-300"
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
        <div className="absolute bottom-3 right-3 pointer-events-none px-2.5 py-1 rounded-full bg-slate-900/70 backdrop-blur-xs text-[10px] text-slate-200 flex items-center gap-2 shadow-xs">
          <span>Drag to pan • Scroll to zoom • Double-click to fit</span>
        </div>
      </div>

      {/* Raw Mermaid DSL Drawer */}
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

      {/* Diagram Footer with Legend & Navigation Tips */}
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
            <span className="w-3 h-3 rounded bg-purple-100 border border-purple-400 inline-block" />
            <span>AI / ML</span>
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
