"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Maximize2,
  Minimize2,
  Code2,
  Layers,
} from "lucide-react";

interface MermaidDiagramProps {
  chart: string;
  className?: string;
}

export const MermaidDiagram: React.FC<MermaidDiagramProps> = ({
  chart,
  className = "",
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [svgContent, setSvgContent] = useState<string>("");
  const [renderError, setRenderError] = useState<string | null>(null);
  const [zoom, setZoom] = useState<number>(100);
  const [isExpanded, setIsExpanded] = useState<boolean>(false);
  const [showSource, setShowSource] = useState<boolean>(false);

  useEffect(() => {
    let isMounted = true;

    async function renderMermaid() {
      if (!chart || !chart.trim()) {
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
            "var(--font-geist-sans), -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
          flowchart: {
            htmlLabels: true,
            curve: "basis",
            nodeSpacing: 45,
            rankSpacing: 55,
            padding: 16,
          },
          themeVariables: {
            primaryColor: "#eff6ff",
            primaryTextColor: "#0f172a",
            primaryBorderColor: "#93c5fd",
            lineColor: "#475569",
            secondaryColor: "#f8fafc",
            tertiaryColor: "#f1f5f9",
            fontSize: "13px",
          },
        });

        const id = `mermaid-${Math.random().toString(36).substring(2, 9)}`;
        const { svg } = await mermaid.render(id, chart);

        if (isMounted) {
          setSvgContent(svg);
          setRenderError(null);
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
  }, [chart]);

  const handleZoomIn = () => setZoom((z) => Math.min(175, z + 15));
  const handleZoomOut = () => setZoom((z) => Math.max(55, z - 15));
  const handleZoomReset = () => setZoom(100);

  if (renderError) {
    return (
      <div
        className={`p-4 bg-slate-50 border border-slate-200 rounded-xl text-xs font-mono text-slate-700 whitespace-pre overflow-x-auto ${className}`}
      >
        <div className="text-amber-700 font-semibold mb-2 text-xs">
          Architecture Topology (Mermaid Definition):
        </div>
        {chart}
      </div>
    );
  }

  if (!svgContent) {
    return (
      <div
        className={`flex items-center justify-center p-12 bg-slate-50/70 border border-slate-200/80 rounded-xl text-slate-400 text-xs animate-pulse ${className}`}
      >
        Rendering topological diagram...
      </div>
    );
  }

  const diagramCanvas = (
    <div
      className={`rounded-xl border border-slate-200/90 bg-slate-50/40 overflow-hidden ${
        isExpanded
          ? "fixed inset-4 z-50 bg-white shadow-floating flex flex-col"
          : className
      }`}
    >
      {/* Diagram Toolbar */}
      <div className="px-3.5 py-2 bg-white border-b border-slate-200/80 flex flex-wrap items-center justify-between gap-2 text-xs">
        <div className="flex items-center gap-2">
          <Layers className="w-3.5 h-3.5 text-blue-600" />
          <span className="font-semibold text-slate-800">
            Azure Deployment Topology
          </span>
          <span className="hidden sm:inline-block text-[11px] text-slate-400">
            • Interactive Viewport
          </span>
        </div>

        {/* Zoom & View Controls */}
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={handleZoomOut}
            aria-label="Zoom out diagram"
            className="p-1.5 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition"
            title="Zoom out"
          >
            <ZoomOut className="w-3.5 h-3.5" />
          </button>
          <span className="text-[11px] font-mono font-semibold text-slate-600 min-w-[42px] text-center">
            {zoom}%
          </span>
          <button
            type="button"
            onClick={handleZoomIn}
            aria-label="Zoom in diagram"
            className="p-1.5 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition"
            title="Zoom in"
          >
            <ZoomIn className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={handleZoomReset}
            aria-label="Reset diagram zoom"
            className="p-1.5 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition"
            title="Reset zoom (100%)"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>

          <span className="mx-1 text-slate-200" aria-hidden="true">
            |
          </span>

          <button
            type="button"
            onClick={() => setShowSource((s) => !s)}
            aria-pressed={showSource}
            className={`inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-medium transition ${
              showSource
                ? "bg-blue-50 text-blue-700 border border-blue-200"
                : "text-slate-600 hover:bg-slate-100"
            }`}
            title="Toggle Mermaid DSL source"
          >
            <Code2 className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">DSL</span>
          </button>

          <button
            type="button"
            onClick={() => setIsExpanded((e) => !e)}
            aria-label={isExpanded ? "Exit full screen diagram" : "Expand diagram"}
            className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition"
            title={isExpanded ? "Close expanded view" : "Expand full screen"}
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

      {/* Scrollable Diagram Viewport */}
      <div
        ref={containerRef}
        className={`overflow-auto p-6 bg-white flex justify-center items-center ${
          isExpanded ? "flex-1 min-h-0" : "max-h-[480px] min-h-[240px]"
        }`}
      >
        <div
          style={{
            transform: `scale(${zoom / 100})`,
            transformOrigin: "center top",
          }}
          className="transition-transform duration-150"
          dangerouslySetInnerHTML={{ __html: svgContent }}
        />
      </div>

      {/* Optional Raw Mermaid DSL Drawer */}
      {showSource && (
        <div className="px-4 py-3 bg-slate-900 text-slate-200 text-xs font-mono overflow-x-auto border-t border-slate-800">
          <pre>{chart}</pre>
        </div>
      )}

      {/* Diagram Legend Footer */}
      <div className="px-3.5 py-2 bg-slate-50 border-t border-slate-200/80 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-500">
        <div className="flex flex-wrap items-center gap-3">
          <span className="font-semibold text-slate-700">Legend:</span>
          <span className="inline-flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-sm bg-blue-100 border border-blue-400" />
            <span>Primary Workload Node</span>
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="w-4 h-0.5 bg-slate-600" />
            <span>Synchronous / Data Flow</span>
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="w-4 h-0.5 border-b border-dashed border-slate-500" />
            <span>Telemetry / Governance</span>
          </span>
        </div>
        <span>Use zoom controls or horizontal scroll on smaller viewports</span>
      </div>
    </div>
  );

  return (
    <>
      {isExpanded && (
        <div
          className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs z-40"
          onClick={() => setIsExpanded(false)}
          aria-hidden="true"
        />
      )}
      {diagramCanvas}
    </>
  );
};
