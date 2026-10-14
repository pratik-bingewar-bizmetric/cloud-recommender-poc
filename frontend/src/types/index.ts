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

export type ComponentPricingStatus =
  | "verified"
  | "provisional"
  | "bundled"
  | "unpriced";

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
  pricing_status?: ComponentPricingStatus;
}

export interface CostBreakdown {
  compute: string;
  database: string;
  storage: string;
  networking: string;
  ai: string;
  other: string;
  subtotal: string;
  verified_subtotal?: string;
  safety_buffer_amount: string;
  total_monthly: string;
  total_five_month: string;
  total_annual: string;
  is_complete?: boolean;
  estimate_status?: "complete" | "incomplete" | string;
  unpriced_component_count?: number;
  unpriced_service_ids?: string[];
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
  monthly_workload_quantity?: string;
  source_url?: string;
  source_api_or_url?: string;
  retrieval_timestamp: string;
  provenance_source?: string;
  service_name?: string | null;
  product_name?: string | null;
  sku_name?: string | null;
  meter_name?: string | null;
  arm_region_name?: string | null;
  tier_minimum_units?: number | null;
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
  components: ArchitectureComponent[];
  pricing_provenance: PricingReference[];
  missing_price_warnings: string[];
  assumptions?: string[];
  calculation_timestamp?: string;
}

export interface ApiErrorDetail {
  error_code?: string;
  message?: string;
  missing_variables?: string[];
  guidance?: string;
}

// Subscription & Project Hierarchy Types (Azure & GCP)
export interface HierarchyNode {
  node_id: string;
  name: string;
  node_type:
    | "azure_tenant"
    | "azure_management_group"
    | "azure_subscription"
    | "azure_resource_group"
    | "gcp_organization"
    | "gcp_folder"
    | "gcp_project";
  parent_id?: string | null;
  state_or_status: string;
  location?: string | null;
}

export interface ResourceRelationship {
  source_resource_id: string;
  target_resource_id: string;
  target_resource_name: string;
  relationship_type:
    | "verified_arm_hierarchy"
    | "verified_property_reference"
    | "verified_hosting_plan"
    | "inferred_co_located";
  is_verified: boolean;
  direction: "parent_to_child" | "hosted_on" | "depends_on" | "secures" | "co_located";
  evidence: string;
}

export interface ResourceWasteFinding {
  id: string;
  resource_id: string;
  resource_name: string;
  native_resource_type: string;
  provider: CloudProvider;
  scope_id: string;
  group_name: string;
  category:
    | "idle_compute"
    | "oversized_compute"
    | "stopped_compute"
    | "unattached_storage"
    | "stale_snapshot"
    | "unattached_ip"
    | "idle_database"
    | "overprovisioned_database"
    | "redundant_network"
    | "unutilized_service";
  severity: "critical" | "high" | "medium" | "low";
  title: string;
  description: string;
  evidence: string;
  metric_observed?: string | null;
  current_monthly_spend: string;
  potential_monthly_savings: string;
  spend_basis: "observed_billing" | "catalog_estimate" | "unpriced";
  confidence: "high" | "medium" | "provisional";
  remediation_recommendation: string;
  pre_remediation_considerations: string[];
  double_counting_prevention_note?: string | null;
}

export interface TechnicalDebtItem {
  id: string;
  resource_id: string;
  resource_name: string;
  native_resource_type: string;
  provider: CloudProvider;
  scope_id: string;
  group_name: string;
  debt_category:
    | "missing_monitoring"
    | "missing_backup"
    | "missing_tagging"
    | "legacy_runtime_or_os"
    | "legacy_sku"
    | "unrestricted_network"
    | "single_point_of_failure";
  severity: "critical" | "high" | "medium" | "low";
  title: string;
  description: string;
  evidence: string;
  remediation_steps: string[];
  architectural_risk: string;
}

export interface TelemetryCoverageSummary {
  metric_window_days: number;
  telemetry_source: string;
  monitored_resources_count: number;
  unmonitored_resources_count: number;
  coverage_percentage: string;
  last_telemetry_sync: string;
  is_cached: boolean;
  confidence_score: string;
  limitations_and_gaps: string[];
}

export interface DiscoveredResource {
  provider: CloudProvider;
  resource_id: string;
  resource_name: string;
  native_resource_type: string;
  canonical_service_id: string;
  service_category: ServiceCategory;
  region: string;
  sku_or_tier?: string | null;
  kind?: string | null;
  parent_scope_id: string;
  subscription_id?: string | null;
  resource_group?: string | null; // Strictly null for GCP
  project_id?: string | null; // Strictly null for Azure
  folder_id?: string | null;
  organization_id?: string | null;
  tags_or_labels: Record<string, string>;
  configuration: Record<string, unknown>;
  relationships: ResourceRelationship[];
  origin: "discovered" | "ai_proposed" | "mock_fixture";
  pricing_status: ComponentPricingStatus;
  estimated_monthly_cost: string;
  actual_monthly_spend?: string | null;
  workload_quantity?: string | null;
  workload_unit?: string | null;
  calculation_explanation: string;
  missing_price_warning?: string | null;
  pricing_reference?: PricingReference | null;
  discovery_timestamp: string;
  waste_findings?: ResourceWasteFinding[];
  technical_debt_items?: TechnicalDebtItem[];
}

export interface ScopeCostGroup {
  group_id: string;
  group_name: string;
  group_type: "azure_resource_group" | "gcp_service_domain" | "gcp_folder";
  location: string;
  resource_count: number;
  verified_monthly_subtotal: string;
  total_monthly: string;
  total_five_month: string;
  total_annual: string;
  unpriced_resource_count: number;
  is_complete: boolean;
  potential_monthly_savings?: string;
  waste_findings_count?: number;
  technical_debt_count?: number;
  critical_findings_count?: number;
  high_findings_count?: number;
  medium_findings_count?: number;
  low_findings_count?: number;
  resources: DiscoveredResource[];
}

export interface SubscriptionRecommendation {
  id: string;
  category:
    | "right_sizing"
    | "redundancy_consolidation"
    | "cost_optimization"
    | "resilience_security_observability"
    | "architecture_modernization";
  title: string;
  target_resource_ids: string[];
  target_resource_names: string[];
  evidence: string;
  rationale: string;
  estimated_monthly_impact: string;
  impact_type: "monthly_savings" | "cost_neutral" | "resilience_investment";
  assumptions: string[];
  limitations: string[];
}

export interface ProviderConnectionStatus {
  provider: CloudProvider;
  inventory_auth_ready: boolean;
  inventory_auth_method: string;
  pricing_api_ready: boolean;
  pricing_api_source: string;
  authorized_scopes_count: number;
  status_message: string;
  access_limitations: string[];
}

export interface CloudScopeSummary {
  provider: CloudProvider;
  scope_id: string;
  display_name: string;
  tenant_or_org_id?: string | null;
  parent_scope_id?: string | null;
  state: string;
  data_source: "live_authenticated" | "mock_fixture";
}

export interface SubscriptionOrProjectAnalysis {
  provider: CloudProvider;
  scope_id: string;
  scope_name: string;
  scope_type: "azure_subscription" | "gcp_project";
  tenant_or_org_id?: string | null;
  hierarchy_nodes: HierarchyNode[];
  data_source: "live_authenticated" | "ai_proposed" | "mock_fixture";
  spend_label: "estimated_public_list_pricing" | "actual_billed_spend" | "hybrid";
  actual_billed_monthly_spend?: string | null;
  resource_count: number;
  group_count: number;
  groups: ScopeCostGroup[];
  resources: DiscoveredResource[];
  cost_breakdown: CostBreakdown;
  pricing_provenance: PricingReference[];
  architecture_mermaid: string;
  recommendations: SubscriptionRecommendation[];
  total_potential_monthly_savings?: string;
  total_potential_annual_savings?: string;
  waste_findings?: ResourceWasteFinding[];
  technical_debt_items?: TechnicalDebtItem[];
  telemetry_coverage?: TelemetryCoverageSummary | null;
  access_limitations: string[];
  assumptions: string[];
  completeness_warning?: string | null;
  analyzed_at: string;
}

export interface CrossCloudServiceMapping {
  capability: string;
  category: ServiceCategory;
  azure_service_id: string;
  azure_service_name: string;
  azure_sku: string;
  azure_monthly_cost: string;
  azure_pricing_status: string;
  gcp_service_id: string;
  gcp_service_name: string;
  gcp_sku: string;
  gcp_monthly_cost: string;
  gcp_pricing_status: string;
  monthly_delta_gcp_minus_azure: string;
  notes: string;
}

export interface MultiCloudComparisonRequest {
  workload_profile: {
    name: string;
    description: string;
    category: WorkloadCategory;
    target_traffic_rps: number;
    monthly_active_users: number;
    primary_region: string;
    cost_buffer_percentage?: string;
  };
  workload_assumptions: WorkloadAssumptions;
  clarifications?: ClarifyingAnswer[];
  azure_region?: string;
  gcp_region?: string;
}

export interface MultiCloudComparisonResponse {
  azure_report: RecommendationReport;
  gcp_report: RecommendationReport;
  service_mappings: CrossCloudServiceMapping[];
  azure_total_monthly: string;
  gcp_total_monthly: string;
  monthly_delta_gcp_minus_azure: string;
  annual_delta_gcp_minus_azure: string;
  cheaper_provider?: CloudProvider | null;
  comparison_assumptions: string[];
  trade_off_summary: string;
  generated_at: string;
}

