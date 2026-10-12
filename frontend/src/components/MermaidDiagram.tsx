"use client";

import React, { useEffect, useRef, useState } from "react";

interface MermaidDiagramProps {
  chart: string;
  className?: string;
}

export const MermaidDiagram: React.FC<MermaidDiagramProps> = ({ chart, className = "" }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [svgContent, setSvgContent] = useState<string>("");
  const [renderError, setRenderError] = useState<string | null>(null);

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
          theme: "default",
          securityLevel: "loose",
          fontFamily: "ui-sans-serif, system-ui, sans-serif",
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
          setRenderError(err instanceof Error ? err.message : "Diagram rendering failed");
        }
      }
    }

    renderMermaid();

    return () => {
      isMounted = false;
    };
  }, [chart]);

  if (renderError) {
    return (
      <div className={`p-4 bg-slate-50 border border-slate-200 rounded-lg text-xs font-mono text-slate-700 whitespace-pre overflow-x-auto ${className}`}>
        <div className="text-amber-700 font-semibold mb-2 text-xs">Architecture Topology (Raw View):</div>
        {chart}
      </div>
    );
  }

  if (!svgContent) {
    return (
      <div className={`flex items-center justify-center p-8 bg-slate-50 rounded-lg text-slate-400 text-sm animate-pulse ${className}`}>
        Rendering architecture diagram...
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={`mermaid-diagram overflow-x-auto p-4 bg-white border border-slate-200 rounded-lg flex justify-center items-center ${className}`}
      dangerouslySetInnerHTML={{ __html: svgContent }}
    />
  );
};

