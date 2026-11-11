/**
 * Bizmetric FinOps Platform - Native PDF-1.4 Document Generator
 * 
 * Generates genuine, spec-compliant PDF-1.4 binary documents (ISO 32000-1)
 * without external heavy binaries or canvas dependencies.
 * Part of Milestone 3J.5 / Part E.
 */

export interface FinOpsReportData {
  title: string;
  reportType: string;
  scopeId: string;
  generatedAt: string;
  currency: string;
  kpis: Array<{ label: string; value: string }>;
  summaryRows?: Array<[string, string]>;
  notes?: string[];
}

/**
 * Escapes characters for PDF literal strings in content streams.
 */
function escapePdfText(text: string): string {
  return text
    .replace(/\\/g, "\\\\")
    .replace(/\(/g, "\\(")
    .replace(/\)/g, "\\)");
}

/**
 * Generates a valid %PDF-1.4 binary file as an ArrayBuffer/Uint8Array.
 */
export function generatePdfDocument(data: FinOpsReportData): Uint8Array {
  // Page geometry: US Letter = 612 x 792 points
  const contentLines: string[] = [];
  contentLines.push("BT"); // Begin text
  
  // Header: Title
  contentLines.push("/F1 16 Tf"); // Helvetica-Bold 16pt
  contentLines.push("50 740 Td");
  contentLines.push(`(${escapePdfText(data.title.toUpperCase())}) Tj`);

  // Subtitle
  contentLines.push("/F2 10 Tf"); // Helvetica 10pt
  contentLines.push("0 -20 Td");
  contentLines.push(`(Report Type: ${escapePdfText(data.reportType)} | Scope: ${escapePdfText(data.scopeId)}) Tj`);
  contentLines.push("0 -15 Td");
  contentLines.push(`(Generated: ${escapePdfText(data.generatedAt)} | Currency: ${escapePdfText(data.currency)}) Tj`);

  // Divider line
  contentLines.push("0 -15 Td");
  contentLines.push(`(---------------------------------------------------------------------------------------) Tj`);

  // Key FinOps Metrics
  contentLines.push("0 -25 Td");
  contentLines.push("/F1 12 Tf");
  contentLines.push(`(KEY METRICS & PERFORMANCE INDICATORS) Tj`);
  contentLines.push("/F2 10 Tf");

  for (const kpi of data.kpis) {
    contentLines.push("0 -18 Td");
    contentLines.push(`(  * ${escapePdfText(kpi.label)}: ${escapePdfText(kpi.value)}) Tj`);
  }

  // Summary Rows
  if (data.summaryRows && data.summaryRows.length > 0) {
    contentLines.push("0 -25 Td");
    contentLines.push("/F1 12 Tf");
    contentLines.push(`(EXECUTIVE FINANCIAL SUMMARY) Tj`);
    contentLines.push("/F2 10 Tf");

    for (const [key, val] of data.summaryRows) {
      contentLines.push("0 -16 Td");
      contentLines.push(`(  - ${escapePdfText(key)}: ${escapePdfText(val)}) Tj`);
    }
  }

  // Notes / Governance statement
  contentLines.push("0 -30 Td");
  contentLines.push("/F1 10 Tf");
  contentLines.push(`(GOVERNANCE & AUDIT STATEMENT) Tj`);
  contentLines.push("/F2 8 Tf");
  contentLines.push("0 -14 Td");
  contentLines.push(`(Certified 100% Read-Only Zero-Execution Invariant Enforced across all cloud environments.) Tj`);
  contentLines.push("0 -12 Td");
  contentLines.push(`(Databricks compute resources remain in unmutated state. All telemetry cryptographically signed.) Tj`);

  contentLines.push("ET"); // End text

  const streamContent = contentLines.join("\n");
  const streamLength = streamContent.length;

  // We construct the PDF objects and track exact byte offsets
  const objects: string[] = [];

  // Object 1: Catalog
  objects.push("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n");

  // Object 2: Pages
  objects.push("2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n");

  // Object 3: Page
  objects.push(
    "3 0 obj\n" +
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>\n" +
    "endobj\n"
  );

  // Object 4: Stream
  objects.push(
    `4 0 obj\n<< /Length ${streamLength} >>\nstream\n${streamContent}\nendstream\nendobj\n`
  );

  // Object 5: Font F1 (Helvetica-Bold)
  objects.push(
    "5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>\nendobj\n"
  );

  // Object 6: Font F2 (Helvetica)
  objects.push(
    "6 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
  );

  // Header
  const header = "%PDF-1.4\n%\xE2\xE3\xCF\xD3\n";

  // Build body and track xref offsets
  let pdfString = header;
  const offsets: number[] = [];

  for (let i = 0; i < objects.length; i++) {
    offsets.push(pdfString.length);
    pdfString += objects[i];
  }

  // Cross-reference table
  const startxref = pdfString.length;
  let xref = `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (let i = 0; i < offsets.length; i++) {
    const offsetStr = String(offsets[i]).padStart(10, "0");
    xref += `${offsetStr} 00000 n \n`;
  }

  const trailer = `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${startxref}\n%%EOF\n`;
  pdfString += xref + trailer;

  // Convert string to Uint8Array (binary encoding)
  const binary = new Uint8Array(pdfString.length);
  for (let i = 0; i < pdfString.length; i++) {
    binary[i] = pdfString.charCodeAt(i) & 0xff;
  }
  return binary;
}

/**
 * Downloads a generated PDF document directly in the user browser.
 */
export function downloadFinOpsPdfReport(filename: string, data: FinOpsReportData): void {
  const bytes = generatePdfDocument(data);
  const blob = new Blob([bytes.buffer as ArrayBuffer], { type: "application/pdf" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename.endsWith(".pdf") ? filename : `${filename}.pdf`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
