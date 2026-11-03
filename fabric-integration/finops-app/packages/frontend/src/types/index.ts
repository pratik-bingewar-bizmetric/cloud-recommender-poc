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

// ----------------------------------------------------------------------------
// Centralized Monitoring, Telemetry & Historical Log Intelligence Types
// ----------------------------------------------------------------------------

export type TimeWindowPreset = "1h" | "24h" | "7d" | "30d" | "90d" | "custom";
export type MetricInterval = "1m" | "5m" | "15m" | "1h" | "1d";
export type LogSeverity = "critical" | "error" | "warning" | "informational" | "verbose";
export type AlertSeverity = "critical" | "high" | "medium" | "low" | "info";
export type ResourceHealthState = "healthy" | "degraded" | "failing" | "unmonitored" | "stopped";

export interface MonitoringQueryRequest {
  provider: CloudProvider;
  scope_id: string;
  resource_id?: string | null;
  resource_group_filter?: string | null;
  time_window?: TimeWindowPreset;
  custom_start_time?: string | null;
  custom_end_time?: string | null;
  interval?: MetricInterval | null;
  force_refresh?: boolean;
}

export interface MetricDataPoint {
  timestamp: string;
  value: number;
  min_value?: number | null;
  max_value?: number | null;
  sample_count?: number;
}

export interface MetricSummary {
  avg?: number | null;
  max?: number | null;
  min?: number | null;
  current?: number | null;
  p95?: number | null;
}

export interface MetricTimeSeries {
  metric_name: string;
  display_name: string;
  unit: string;
  resource_id: string;
  resource_name: string;
  data_points: MetricDataPoint[];
  summary: MetricSummary;
}

export interface LogEntry {
  id: string;
  timestamp: string;
  severity: LogSeverity;
  resource_id: string;
  resource_name: string;
  service_type: string;
  operation_name: string;
  status: string;
  message: string;
  error_code?: string | null;
  caller?: string | null;
  correlation_id?: string | null;
  raw_details?: Record<string, unknown>;
}

export interface ActiveAlertItem {
  id: string;
  title: string;
  category:
    | "capacity_exhaustion"
    | "high_utilization"
    | "elevated_error_rate"
    | "elevated_latency"
    | "service_failure"
    | "connection_saturation"
    | "unhealthy_replica"
    | "security_risk"
    | "unmonitored_service";
  severity: AlertSeverity;
  affected_resource_id: string;
  affected_resource_name: string;
  hierarchy_path: string;
  status: "active" | "resolved" | "acknowledged";
  observation_window: string;
  supporting_evidence: string;
  threshold_rule: string;
  confidence: "high" | "medium" | "provisional";
  urgency: "urgent" | "action_required" | "informational";
  first_observed: string;
  last_observed: string;
  recommendation: string;
  remediation_steps: string[];
}

export type ResourceKind =
  | "infrastructure_resource"
  | "api_service"
  | "configuration_metadata"
  | "security_credential";

export interface ResourceHealthRecord {
  resource_id: string;
  resource_name: string;
  native_type: string;
  health_state: ResourceHealthState;
  summary: string;
  reason?: string | null;
  last_checked: string;
  telemetry_source: string;
  resource_kind?: ResourceKind;
}

export interface MonitoringKPIStrip {
  total_resources: number;
  infrastructure_resources_count?: number;
  api_services_count?: number;
  configuration_records_count?: number;
  healthy_count: number;
  degraded_count: number;
  failing_count: number;
  unmonitored_count: number;
  active_alerts_count: number;
  error_event_count: number;
  error_rate_percentage?: string | null;
  telemetry_coverage_percentage: string;
  observed_monthly_spend?: string | null;
  estimated_monthly_cost: string;
  potential_monthly_savings: string;
  technical_debt_items_count: number;
}

export interface ResourceGroupMonitoringSummary {
  group_id: string;
  group_name: string;
  resource_count: number;
  healthy_count: number;
  failing_count: number;
  active_alerts_count: number;
  total_monthly_cost: string;
  potential_monthly_savings: string;
  telemetry_coverage_pct: string;
}

export interface RecurringErrorSummary {
  error_signature: string;
  error_code?: string | null;
  affected_resources: string[];
  frequency: number;
  first_seen: string;
  last_seen: string;
  severity: LogSeverity;
}

export interface MonitoringOverviewResponse {
  provider: CloudProvider;
  scope_id: string;
  scope_name: string;
  time_window: string;
  aggregation_interval: string;
  start_time: string;
  end_time: string;
  query_timestamp: string;
  is_live: boolean;
  data_source: string;
  telemetry_source: string;
  kpis: MonitoringKPIStrip;
  cpu_utilization_series: MetricTimeSeries[];
  memory_utilization_series: MetricTimeSeries[];
  error_rate_series: MetricTimeSeries[];
  active_alerts: ActiveAlertItem[];
  recent_failures: LogEntry[];
  recurring_errors: RecurringErrorSummary[];
  health_records: ResourceHealthRecord[];
  resource_groups_summary: ResourceGroupMonitoringSummary[];
  limitations_and_gaps: string[];
}

export interface ResourceCostAndUtilization {
  monthly_cost?: string | number;
  currency?: string;
  utilization_summary?: string | number;
  waste_identified?: boolean;
  savings_potential?: string | number;
  [key: string]: string | number | boolean | undefined;
}

export interface ResourceDetailMonitoringResponse {
  resource: DiscoveredResource;
  health: ResourceHealthRecord;
  time_window: string;
  aggregation_interval: string;
  start_time: string;
  end_time: string;
  metrics: MetricTimeSeries[];
  logs: LogEntry[];
  alerts: ActiveAlertItem[];
  dependencies: Array<{
    target_id: string;
    target_name: string;
    target_type: string;
    relation: string;
    status: string;
    latency_ms?: number;
  }>;
  cost_and_utilization: ResourceCostAndUtilization;
  waste_findings: ResourceWasteFinding[];
  technical_debt_items: TechnicalDebtItem[];
  limitations: string[];
}

export interface LogSearchRequest {
  provider: CloudProvider;
  scope_id: string;
  query?: string | null;
  severity?: LogSeverity | null;
  resource_id?: string | null;
  time_window?: TimeWindowPreset;
  page?: number;
  page_size?: number;
}

export interface LogSearchResponse {
  total_matched: number;
  page_size: number;
  logs: LogEntry[];
  recurring_summaries: RecurringErrorSummary[];
  query_window: string;
  limitations: string[];
}

export interface MonitoringSourcesResponse {
  azure_monitor: {
    status: string;
    is_live: boolean;
    capabilities: string[];
    retention_days: number;
  };
  gcp_monitoring: {
    status: string;
    is_live: boolean;
    capabilities: string[];
    retention_days: number;
  };
  policy: string;
}

export type ConnectionStatus =
  | "connected"
  | "ready_to_connect"
  | "connecting"
  | "validating_access"
  | "discovering_scope"
  | "auth_failed"
  | "permission_denied"
  | "scope_not_found"
  | "simulation_fixture";

export interface CloudConnection {
  id: string;
  name: string;
  provider: CloudProvider;
  scope_id: string;
  display_name: string;
  tenant_or_org_id?: string | null;
  auth_method: string;
  status: ConnectionStatus;
  last_verified_at?: string | null;
  is_live: boolean;
  capabilities: string[];
  access_limitations: string[];
}

export interface ValidateConnectionRequest {
  connection_id?: string | null;
  provider: CloudProvider;
  scope_id: string;
}

export interface ConnectionValidationResponse {
  success: boolean;
  connection_id: string;
  provider: CloudProvider;
  scope_id: string;
  scope_name: string;
  status: ConnectionStatus;
  details: string;
  discovered_resource_count: number;
  discovered_resource_groups: string[];
  permissions_verified: string[];
  is_live: boolean;
  latency_ms: number;
  validated_at: string;
}

export interface CreateConnectionRequest {
  provider: CloudProvider;
  name: string;
  scope_id: string;
  azure_tenant_id?: string;
  azure_client_id?: string;
  azure_client_secret?: string;
  gcp_project_id?: string;
  gcp_service_account_json?: string;
  gcp_access_token?: string;
}

export type TokenDataStatus =
  | "live_telemetry"
  | "no_data_available"
  | "instrumentation_required"
  | "simulation_benchmark"
  | "unavailable_permission_required"
  | "pricing_catalog";

export interface TokenUsageRecord {
  timestamp: string;
  provider: CloudProvider;
  subscription_id?: string | null;
  project_id?: string | null;
  resource_id: string;
  resource_name: string;
  resource_group: string;
  service_name?: string;
  model_name: string;
  model_id?: string | null;
  period_start?: string | null;
  period_end?: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  provider_total_tokens?: number | null;
  normalized_total_tokens?: number;
  total_tokens: number;
  prompt_rate_per_million?: string | number | null;
  completion_rate_per_million?: string | number | null;
  estimated_cost_usd: string | number;
  currency?: string;
  telemetry_status?: TokenDataStatus;
  metric_source?: string;
  rate_meter_source?: string;
  pricing_source?: string;
  attribution_status?: "attributed_to_model" | "attributed_to_resource" | "unattributed" | string;
  last_updated?: string;
}

export interface TokenTrendPoint {
  timestamp: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_cost_usd: string | number;
}

export interface ModelTokenBreakdown {
  model_name: string;
  provider: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  prompt_rate_per_million: string | number;
  completion_rate_per_million: string | number;
  total_cost_usd: string | number;
  percentage_of_total: number;
}

export interface WorkloadTokenBreakdown {
  workload_or_group: string;
  resource_count: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens: number;
  total_cost_usd: string | number;
  percentage_of_total: number;
  pricing_source?: string;
  telemetry_status?: TokenDataStatus;
  attribution_status?: string;
}

export interface ServiceTokenBreakdown {
  service_name: string;
  resource_count: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  total_cost_usd: string | number;
  percentage_of_total: number;
  pricing_source?: string;
  telemetry_status?: TokenDataStatus;
  attribution_status?: string;
}

export interface TokenEconomicsSummary {
  provider: CloudProvider;
  scope_id: string;
  scope_name: string;
  time_window: string;
  data_status: TokenDataStatus;
  status_message: string;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  prompt_cost_usd?: string | number;
  completion_cost_usd?: string | number;
  estimated_cost_usd: string | number;
  unattributed_tokens: number;
  unattributed_percentage: number;
  active_models_count: number;
  discovered_ai_resources_count: number;
  discovered_ai_resources: string[];
  trend_points: TokenTrendPoint[];
  model_breakdowns: ModelTokenBreakdown[];
  workload_breakdowns: WorkloadTokenBreakdown[];
  service_breakdowns?: ServiceTokenBreakdown[];
  usage_records: TokenUsageRecord[];
  diagnostic_setup_guide: string[];
  generated_at: string;
}

export * from "./financials";

