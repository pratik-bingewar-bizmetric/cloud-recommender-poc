export type CloudProvider = "azure" | "aws" | "gcp";

export type ServiceCategory =
  | "compute"
  | "database"
  | "storage"
  | "networking"
  | "security"
  | "monitoring"
  | "ai_ml"
  | "integration";

export type WorkloadCategory =
  | "web_app"
  | "microservices"
  | "batch_processing"
  | "data_pipeline"
  | "ai_inference"
  | "event_driven"
  | "api_service"
  | "e_commerce";

export interface ClarifyingQuestion {
  id: string;
  category: string;
  question: string;
  rationale: string;
  options: string[];
  default_answer?: string;
  impact_on_architecture?: string;
}

export interface ClarifyingAnswer {
  question_id: string;
  selected_option: string;
}

export interface WorkloadAssumptions {
  customer_count: number;
  monthly_active_users: number;
  requests_per_user_per_day: number;
  peak_rps: number;
  db_storage_gb: number;
  blob_storage_gb: number;
  monthly_egress_gb: number;
  ai_support_monthly_tokens: number;
  target_sla_percentage: number;
  ha_required: boolean;
  backup_retention_days: number;
  target_region: string;
}

export interface WorkloadProfile {
  id: string;
  name: string;
  category: WorkloadCategory;
  description: string;
  expected_monthly_active_users?: number;
  expected_requests_per_second?: number;
  target_availability_percentage: number;
  storage_volume_gb: number;
  monthly_data_egress_gb: number;
  target_regions: string[];
  estimation_assumptions: Record<string, string>;
}

export interface ArchitectureComponent {
  component_id: string;
  category: ServiceCategory;
  service_id: string;
  service_name: string;
  sku_or_tier: string;
  quantity: number;
  monthly_cost: string; // Decimal string (e.g. "134.32")
  region?: string;
  workload_quantity?: string | null;
  workload_unit?: string | null;
  dependencies: string[];
  rationale: string;
  security_considerations?: string | null;
  reliability_considerations?: string | null;
  scaling_considerations?: string | null;
  pricing_assumptions?: string | null;
  known_risks: string[];
  missing_price_warning?: string | null;
}

export interface CostBreakdown {
  compute: string;
  database: string;
  storage: string;
  networking: string;
  ai: string;
  other: string;
  subtotal: string;
  safety_buffer_amount: string;
  total_monthly: string;
  total_five_month: string;
  total_annual: string;
}

export interface TradeOffDimension {
  score: number;
  assessment: string;
}

export interface TradeOffAssessment {
  cost_efficiency: TradeOffDimension;
  security_compliance: TradeOffDimension;
  reliability_resilience: TradeOffDimension;
  scalability_performance: TradeOffDimension;
  operational_complexity: TradeOffDimension;
  summary: string;
}

export interface PricingReference {
  provider: CloudProvider;
  service_id: string;
  meter_or_sku_id: string;
  rate: string;
  unit_description: string;
  monthly_workload_quantity: string;
  source_api_or_url: string;
  retrieval_timestamp: string;
  pricing_tier_or_notes?: string | null;
}

export interface RecommendationReport {
  id: string;
  workload_profile_id: string;
  provider: CloudProvider;
  currency: string;
  status: string;
  architecture_description: string;
  components: ArchitectureComponent[];
  cost_breakdown: CostBreakdown;
  pricing_provenance: PricingReference[];
  trade_offs: TradeOffAssessment;
  assumptions: string[];
  limitations: string[];
  mermaid_diagram: string;
  generated_at: string;
  created_at: string;
}

export interface RequirementsAnalysisResponse {
  workload_profile: WorkloadProfile;
  clarifying_questions: ClarifyingQuestion[];
  workload_assumptions: WorkloadAssumptions;
  missing_critical_requirements: string[];
  ai_provider_used: string;
  status: string;
}

export interface CostSimulationResponse {
  cost_breakdown: CostBreakdown;
  updated_components: ArchitectureComponent[];
  pricing_provenance: PricingReference[];
  calculation_source: string;
  unverified_price_warnings: string[];
}

export interface ApiErrorDetail {
  error_code?: string;
  message?: string;
  missing_variables?: string[];
  guidance?: string;
}

