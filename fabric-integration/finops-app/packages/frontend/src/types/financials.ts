import { CloudProvider, TimeWindowPreset } from "@/types";

export type FinancialKpiType =
  | "spend"
  | "savings"
  | "annual_savings"
  | "realized_savings"
  | "resources"
  | "category"
  | "finding";

export interface FinancialCategoryItem {
  name: string;
  category_key: "compute" | "database" | "storage" | "ai" | "networking" | "other";
  amount_usd: number;
  percentage_of_total: number;
  color_class: string;
  resource_count?: number;
  description?: string;
}

export interface FinancialFindingDetail {
  id: string;
  resource_id: string;
  resource_name: string;
  category: string;
  severity: "critical" | "high" | "medium" | "low";
  title: string;
  description: string;
  evidence: string;
  current_monthly_spend: number;
  potential_monthly_savings: number;
  calculation_formula: string;
  pricing_source: string;
  confidence: "high" | "medium" | "low" | "provisional";
  attribution_group?: string;
  remediation_recommendation?: string;
  pre_remediation_considerations?: string;
  potential_overlaps?: string[];
}

export interface CanonicalFinancialSummary {
  provider: CloudProvider;
  scope_id: string;
  scope_name: string;
  reporting_period: string; // e.g. "30d" or "30-Day Projected Monthly"
  time_window: TimeWindowPreset;
  currency: "USD" | "INR";
  exchange_rate: number;
  data_provenance: "live_authenticated" | "verified_pricing_catalog" | "simulation_benchmark";
  pricing_source: string;
  rate_effective_date: string;
  last_updated: string;

  // 1. Spend Metrics
  estimated_monthly_spend: number;
  actual_billed_monthly_spend: number | null;
  spend_basis: "actual_billed" | "estimated_public_list" | "hybrid";
  spend_formula: string;

  // 2. Savings & Optimization Opportunities
  potential_monthly_savings: number;
  projected_annual_savings: number;
  realized_monthly_savings: number; // Strictly 0.00 (Zero-Execution policy)
  savings_percentage_of_spend: number;
  findings_count: number;
  savings_formula: string;

  // 3. Reconciled Category Breakdown (Sum of amounts must equal estimated_monthly_spend)
  categories: FinancialCategoryItem[];

  // 4. Reconciled Itemized Findings (Sum of findings savings must equal potential_monthly_savings)
  findings: FinancialFindingDetail[];

  // 5. Inclusions, Exclusions, Assumptions & Limitations
  included_resources_count: number;
  unmonitored_or_unpriced_count: number;
  assumptions: string[];
  limitations: string[];
}
