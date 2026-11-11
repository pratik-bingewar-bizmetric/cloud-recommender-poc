/**
 * Bizmetric FinOps Platform - RFC 4180 Compliant CSV Export Generator
 * 
 * Part of Milestone 3J.5 / Part E.
 */

export interface CsvColumn<T> {
  header: string;
  accessor: (row: T) => string | number | boolean | null | undefined;
}

/**
 * Escapes a cell value according to RFC 4180:
 * Encloses in quotes if it contains commas, double quotes, or newlines; escapes double quotes by doubling them.
 */
export function escapeCsvCell(val: string | number | boolean | null | undefined): string {
  if (val === null || val === undefined) return "";
  const str = String(val);
  if (/[",\r\n]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

/**
 * Generates an RFC 4180 CSV string from headers and rows.
 */
export function generateCsvString<T>(
  data: T[],
  columns: CsvColumn<T>[],
  metadataHeader?: string[]
): string {
  const lines: string[] = [];

  if (metadataHeader && metadataHeader.length > 0) {
    for (const meta of metadataHeader) {
      lines.push(`# ${escapeCsvCell(meta)}`);
    }
    lines.push("");
  }

  // Header line
  const headerLine = columns.map((col) => escapeCsvCell(col.header)).join(",");
  lines.push(headerLine);

  // Data rows
  for (const row of data) {
    const rowLine = columns.map((col) => escapeCsvCell(col.accessor(row))).join(",");
    lines.push(rowLine);
  }

  return lines.join("\r\n");
}

/**
 * Triggers a browser download of the CSV data.
 */
export function downloadCsvFile(filename: string, csvContent: string): void {
  const blob = new Blob(["\uFEFF" + csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename.endsWith(".csv") ? filename : `${filename}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

