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

export interface ServiceIntegration {
  service_type: "arm" | "databricks" | "fabric" | "gcp_core";
  display_name: string;
  status: "connected" | "ready_to_connect" | "standby" | "unauthorized" | "not_configured";
  auth_method: string;
  capabilities: string[];
  details?: string;
}

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
  service_integrations?: ServiceIntegration[];
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
export * from "./navigation";

// ----------------------------------------------------------------------------
// Resource Configuration & Scope Selection Types
// ----------------------------------------------------------------------------

export type ScopeType =
  | "tenant"
  | "subscription"
  | "resource_group"
  | "resource"
  | "databricks_workspace"
  | "organization"
  | "folder"
  | "project"
  | "account";

export type SelectionState = "included" | "excluded" | "all_children";

export interface ScopeDiscoveryNode {
  id: string;
  name: string;
  scope_type: ScopeType | string;
  scope_identifier: string;
  parent_scope_identifier?: string | null;
  resource_type?: string | null;
  region?: string | null;
  is_leaf?: boolean;
  metadata?: Record<string, unknown>;
  children?: ScopeDiscoveryNode[];
}

export interface ScopeDiscoveryResponse {
  provider: CloudProvider | string;
  connection_id: string;
  tenant_or_org_id?: string | null;
  status: "ready" | "permission_denied" | "unsupported" | "empty";
  status_message: string;
  last_discovered_at: string;
  tree: ScopeDiscoveryNode[];
  total_discovered_resources: number;
  databricks_workspaces_count: number;
}

export interface ConfiguredScopeItemCreate {
  scope_type: string;
  scope_identifier: string;
  parent_scope_identifier?: string | null;
  display_name: string;
  resource_type?: string | null;
  region?: string | null;
  selection_state: SelectionState;
  metadata?: Record<string, unknown>;
}

export interface ConfiguredScopeItemResponse {
  item_id: string;
  configuration_id: string;
  scope_type: string;
  scope_identifier: string;
  parent_scope_identifier?: string | null;
  display_name: string;
  resource_type?: string | null;
  region?: string | null;
  selection_state: SelectionState | string;
  metadata?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ResourceConfigurationCreate {
  connection_id: string;
  provider: string;
  created_by?: string;
  scope_items: ConfiguredScopeItemCreate[];
}

export interface ResourceConfigurationResponse {
  configuration_id: string;
  connection_id: string;
  provider: string;
  configuration_version: number;
  active_status: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  scope_items: ConfiguredScopeItemResponse[];
  total_items: number;
}

export interface EffectiveSelectionResponse {
  configuration_id: string;
  connection_id: string;
  provider: string;
  configuration_version: number;
  effective_resource_ids: string[];
  effective_subscriptions: string[];
  effective_resource_groups: string[];
  databricks_workspaces: Array<{
    resource_id: string;
    name: string;
    resource_group?: string;
    region?: string;
    workspace_url?: string;
    workspace_id?: string;
    pricing_tier?: string;
  }>;
  total_selected_resources: number;
}

export interface ConfigurationStatusResponse {
  connection_id: string;
  has_configuration: boolean;
  configuration_id?: string | null;
  configuration_version?: number | null;
  active_status?: string | null;
  selected_resource_count: number;
  databricks_workspaces_count: number;
  ingestion_readiness: "ready" | "not_configured" | "no_selection";
  updated_at?: string | null;
}

// ---------------------------------------------------------------------------
// Scope-Aware Ingestion & Enforcement Types
// ---------------------------------------------------------------------------

export type IngestionReadinessState =
  | "ready"
  | "not_configured"
  | "no_resources_selected"
  | "connection_error"
  | "permission_denied"
  | "configuration_invalid";

export type IngestionRunStatus =
  | "pending"
  | "running"
  | "completed"
  | "partial_failure"
  | "failed";

export type ResourceIngestionStatus = "success" | "failed" | "skipped";

export interface IngestionReadinessResponse {
  connection_id: string;
  provider: string;
  readiness_state: IngestionReadinessState;
  can_start_ingestion: boolean;
  has_configuration: boolean;
  configuration_id?: string | null;
  configuration_version?: number | null;
  selected_resource_count: number;
  selected_workspace_count: number;
  effective_resource_ids: string[];
  effective_workspace_ids: string[];
  details: string;
  missing_requirements: string[];
  checked_at: string;
}

export interface IngestionResourceStatusResponse {
  resource_id: string;
  resource_type?: string | null;
  region?: string | null;
  status: ResourceIngestionStatus;
  inventory_extracted: boolean;
  cost_extracted: boolean;
  metrics_extracted: boolean;
  extracted_records_count: number;
  error_message?: string | null;
}

export interface IngestionRunResponse {
  run_id: string;
  connection_id: string;
  provider: string;
  configuration_id: string;
  configuration_version: number;
  status: IngestionRunStatus;
  triggered_by: string;
  started_at: string;
  completed_at?: string | null;
  total_resources_scoped: number;
  successful_resources_count: number;
  failed_resources_count: number;
  error_message?: string | null;
  scope_snapshot: Record<string, unknown>;
  resource_statuses: IngestionResourceStatusResponse[];
}

export interface IngestionRunSummaryResponse {
  run_id: string;
  connection_id: string;
  provider: string;
  configuration_version: number;
  status: IngestionRunStatus;
  triggered_by: string;
  started_at: string;
  completed_at?: string | null;
  total_resources_scoped: number;
  successful_resources_count: number;
  failed_resources_count: number;
  error_message?: string | null;
}

// ---------------------------------------------------------------------------
// Databricks Workspace Connectivity & Discovery Types
// ---------------------------------------------------------------------------

export type DatabricksCloud = "azure" | "aws" | "gcp";

export type CategoryDiscoveryStatus =
  | "available"
  | "permission_denied"
  | "unsupported"
  | "no_resources_found"
  | "connection_error"
  | "not_yet_discovered";

export type DatabricksConnectionStatus =
  | "ready_to_connect"
  | "connected"
  | "auth_failed"
  | "permission_denied"
  | "connection_error";

export interface DatabricksConnection {
  connection_id: string;
  workspace_id: string;
  workspace_name: string;
  workspace_url: string;
  cloud: DatabricksCloud;
  region?: string | null;
  auth_method: string;
  profile_name?: string | null;
  status: DatabricksConnectionStatus;
  last_connected_at?: string | null;
  last_error?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CategoryDiscoveryResult {
  category: string;
  status: CategoryDiscoveryStatus;
  resource_count: number;
  error_message?: string | null;
  discovered_at?: string | null;
}

export interface DiscoveredResourceItem {
  id: string;
  name: string;
  resource_type: string;
  workspace_id: string;
  status?: string | null;
  creator?: string | null;
  source_api: string;
  metadata: Record<string, unknown>;
  discovered_at: string;
}

export interface DatabricksWorkspaceDiscovery {
  connection_id: string;
  workspace_id: string;
  workspace_name: string;
  workspace_url: string;
  cloud: DatabricksCloud;
  overall_status: "completed" | "partial_failure" | "failed";
  categories: Record<string, CategoryDiscoveryResult>;
  resources: DiscoveredResourceItem[];
  total_resources_count: number;
  discovered_at: string;
}

export interface DatabricksConnectionTestResponse {
  connection_id: string;
  workspace_id: string;
  workspace_url: string;
  success: boolean;
  status: DatabricksConnectionStatus;
  current_user?: string | null;
  details: string;
  tested_at: string;
}

export interface DatabricksConnectionHealth {
  connection_id: string;
  workspace_id: string;
  cloud: DatabricksCloud;
  status: DatabricksConnectionStatus;
  authenticated_user?: string | null;
  last_verified_at?: string | null;
  categories_summary: Record<string, CategoryDiscoveryStatus>;
  resource_counts_by_type: Record<string, number>;
  capabilities: string[];
  limitations: string[];
}

// -------------------------------------------------------------
// FinOps Command Center 15-Module Types
// -------------------------------------------------------------

export type FinOpsModule =
  | "overview"
  | "cost"
  | "allocation"
  | "compute"
  | "ai"
  | "data"
  | "network"
  | "recommend"
  | "forecast"
  | "anomaly"
  | "governance"
  | "chargeback"
  | "workloads"
  | "reports"
  | "settings";

export type KpiAvailabilityStatus =
  | "AVAILABLE"
  | "PARTIAL"
  | "NO_DATA"
  | "PERMISSION_DENIED"
  | "UNSUPPORTED"
  | "STALE"
  | "ERROR"
  | "LIVE"
  | "BASELINE"
  | "ESTIMATED"
  | "STOPPED_WAREHOUSE"
  | "UNAVAILABLE";

export interface FinOpsKpiMetric {
  value: number | null;
  formatted_value: string;
  unit: string;
  currency?: string | null;
  metric_id?: string | null;
  period_start?: string | null;
  period_end?: string | null;
  comparison_value?: number | null;
  change_absolute?: number | null;
  change_percentage?: number | null;
  delta_label?: string | null;
  is_favorable?: boolean | null;
  status: KpiAvailabilityStatus;
  data_freshness: string;
  source: string;
  workspace_id: string;
  resource_type?: string | null;
  resource_id?: string | null;
  data_source?: string | null;
  last_refreshed?: string | null;
  aggregation_method?: string | null;
  formula?: string | null;
  record_count?: number | null;
  caveats?: string | null;
  configuration_version: number;
  calculation_version: string;
  coverage: number;
  limitations?: string | null;
}

export interface CanonicalKpiResponse {
  metric_id: string;
  metric: FinOpsKpiMetric;
}

export interface FinOpsDecisionItem {
  id: string;
  priority: number;
  title: string;
  description: string;
  estimated_savings_monthly: number;
  formatted_savings: string;
  impact: string;
  status: string;
  confidence_pct: number;
  effort: string;
  owner: string;
  evidence: string;
  category?: string;
  resource_name?: string;
  resource_id?: string;
  finding?: string;
  current_cost?: string;
  potential_savings_range?: string;
  verified_realized_savings?: number;
  formatted_realized_savings?: string;
  performance_impact?: string;
  risk?: string;
  complexity?: string;
  validation_method?: string;
  lifecycle_stage?: string;
  calculation_methodology?: string;
  recommended_action?: string;
}

export interface ExecutiveOverviewData {
  kpis: Record<string, FinOpsKpiMetric>;
  spend_trend: Array<{ day: string; actual: number; forecast: number; budget_pace: number }>;
  spend_composition: Array<{ family: string; share: number; amount: number; color: string }>;
  top_cost_drivers: Array<{
    driver: string;
    workspace_owner: string;
    spend: number;
    formatted_spend: string;
    change: string;
    signal: string;
  }>;
  decisions_requiring_attention: FinOpsDecisionItem[];
  global_filters: Record<string, unknown>;
}

export interface CostExplorerData {
  kpis: Record<string, FinOpsKpiMetric>;
  daily_trend: Array<{ date: string; cost: number; dbu: number }>;
  cost_by_product_family: Array<{ product: string; cost: number; share: number }>;
  billing_ledger: Array<{
    date: string;
    product: string;
    sku: string;
    workspace: string;
    usage_qty: number;
    unit: string;
    list_cost: number;
    effective_cost: number;
    owner_tag: string;
    allocation_status: string;
  }>;
}

export interface CostAllocationData {
  kpis: Record<string, FinOpsKpiMetric>;
  spend_by_bu: Array<{ business_unit: string; spend: number }>;
  allocation_completeness: Record<string, number>;
  rulebook: Array<{
    priority: number;
    rule_name: string;
    match_condition: string;
    allocation_target: string;
    method: string;
    status: string;
  }>;
}

export interface ComputeWarehousesData {
  kpis: Record<string, FinOpsKpiMetric>;
  clusters: Array<{
    cluster_id: string;
    name: string;
    type: string;
    owner: string;
    node_profile: string;
    runtime_hrs: number;
    cpu_utilization: string;
    dbu_mtd: number;
    cost_mtd: number;
    state: string;
    finding: string;
  }>;
  warehouses: Array<{
    warehouse_id: string;
    name: string;
    warehouse_class: string;
    size: string;
    uptime: string;
    avg_utilization: string;
    queue_p95: string;
    auto_stop_mins: number;
    cost_mtd: number;
    state: string;
    recommendation: string;
  }>;
  jobs: Array<{
    job_id: string;
    name: string;
    runs: number;
    success_rate: string;
    retries: number;
    avg_duration: string;
    dbu_per_run: number;
    cost_per_run: number;
    cost_per_tb: number;
    signal: string;
  }>;
  heatmap_utilization: number[];
}

export interface AiEconomicsData {
  kpis: Record<string, FinOpsKpiMetric>;
  token_consumption_by_model: Array<{ model: string; tokens: number; spend: number }>;
  token_cost_drivers: Array<{ driver: string; amount: string; is_deduction: boolean }>;
  model_economics: Array<{
    model_name: string;
    serving_mode: string;
    input_tokens: string;
    output_tokens: string;
    cached_tokens: string;
    requests: string;
    cost_mtd: number;
    avg_latency: string;
    cost_per_1k_output: string;
  }>;
  serving_endpoints: Array<{
    endpoint_name: string;
    model: string;
    serving_type: string;
    requests_per_day: string;
    capacity_utilization: string;
    p95_latency: string;
    availability: string;
    monthly_cost: number;
    action: string;
  }>;
  genie_scorecard: Array<{
    space_name: string;
    business_owner: string;
    questions: number;
    answer_rate: string;
    warehouse: string;
    spend: number;
    cost_per_success: string;
    quality_score: number;
  }>;
  agents: Array<{
    agent_name: string;
    runs: number;
    success_rate: string;
    avg_steps: number;
    llm_cost: number;
    tool_cost: number;
    total_cost: number;
    cost_per_success: string;
    outcome: string;
  }>;
  training: Array<{
    experiment_name: string;
    workload: string;
    compute_hrs: string;
    runs: number;
    artifact_storage: string;
    spend: number;
    quality_lift: string;
    decision: string;
  }>;
  unit_economics: Array<Record<string, string>>;
}

export interface DataStorageData {
  kpis: Record<string, FinOpsKpiMetric>;
  storage_tiers: Array<{ tier: string; share: number; tb: number }>;
  lifecycle_opportunities: Array<{ opportunity: string; metric: string }>;
  tables: Array<{
    catalog_schema_table: string;
    storage_type: string;
    size: string;
    last_read: string;
    retention: string;
    growth_month: string;
    monthly_cost: number;
    recommendation: string;
  }>;
}

export interface NetworkCloudData {
  kpis: Record<string, FinOpsKpiMetric>;
  components: Array<{
    provider: string;
    service: string;
    resource: string;
    region: string;
    usage_driver: string;
    cost_mtd: number;
    allocation: string;
    opportunity: string;
  }>;
}

export interface OptimizationAdvisorData {
  kpis: Record<string, FinOpsKpiMetric>;
  recommendations: FinOpsDecisionItem[];
}

export interface ScenarioSimulationResult {
  baseline_spend: number;
  adjusted_spend: number;
  formatted_spend: string;
  savings_vs_baseline: number;
  delta_label: string;
  is_favorable: boolean;
  budget_variance: number;
}

export interface ForecastBudgetsData {
  kpis: Record<string, FinOpsKpiMetric>;
  budget_burn: Array<{ day: string; actual: number; budget: number }>;
  budget_controls: Array<{
    budget_scope: string;
    owner: string;
    budget: number;
    actual: number;
    forecast: number;
    threshold: string;
    burn_pct: number;
    status: string;
  }>;
  default_scenario: ScenarioSimulationResult;
}

export interface AnomalyItemData {
  id: string;
  detected: string;
  severity: string;
  signal: string;
  resource: string;
  baseline: string;
  observed: string;
  estimated_impact: string;
  likely_cause: string;
  evidence_detail: string;
  resource_type?: string;
  workspace_id?: string;
  metric?: string;
  absolute_deviation?: string;
  percentage_deviation?: string;
  detection_methodology?: string;
  confidence?: string;
  status?: string;
  root_cause_hypotheses?: string[];
  ai_explanation?: string;
  recommended_action?: string;
  potential_savings?: string;
  verification_procedure?: string;
  historical_trend?: Array<{ date: string; spend: number }>;
  sku_contribution?: Array<{ sku: string; pct: number; amount: string }>;
  related_workloads?: string[];
}

export interface FinOpsAiOpportunity {
  title: string;
  description: string;
  resource_id?: string;
  estimated_savings: string;
  effort?: string;
  risk?: string;
  confidence_pct?: number;
}

export interface FinOpsAiAnalysis {
  module_id: string;
  workspace_id: string;
  executive_summary: string;
  important_findings: string[];
  cost_drivers: string[];
  unusual_changes: string[];
  optimization_opportunities: FinOpsAiOpportunity[];
  expected_savings: string;
  risk_assessment: string;
  data_quality_warnings: string[];
  suggested_investigations: string[];
  confidence_score: number;
  source_references: string[];
  analysis_timestamp: string;
  is_ai_live: boolean;
}

export interface AnomalyDetectionData {
  kpis: Record<string, FinOpsKpiMetric>;
  anomalies: AnomalyItemData[];
}

export interface GovernancePoliciesData {
  kpis: Record<string, FinOpsKpiMetric>;
  policies: Array<{
    policy_name: string;
    scope: string;
    control: string;
    enforcement: string;
    owner: string;
    exceptions: number;
    status: string;
  }>;
  checklist: Array<{ label: string; checked: boolean }>;
  workflow_steps: string[];
}

export interface ShowbackChargebackData {
  kpis: Record<string, FinOpsKpiMetric>;
  statements: Array<{
    business_unit: string;
    direct_compute: number;
    ai_tokens: number;
    storage: number;
    shared_allocation: number;
    total: number;
    budget_variance: string;
    trend: string;
  }>;
}

export interface WorkloadEconomicsData {
  kpis: Record<string, FinOpsKpiMetric>;
  workloads: Array<{
    workload: string;
    workload_type: string;
    owner: string;
    monthly_spend: number;
    volume: string;
    unit_cost: string;
    sla_quality: string;
    business_outcome: string;
    efficiency_trend: string;
  }>;
}

export interface ReportsAuditData {
  report_packs: Array<{
    report_id: string;
    title: string;
    subtitle: string;
    format: string;
  }>;
  audit_events: Array<{
    timestamp: string;
    actor: string;
    event: string;
    resource: string;
    before: string;
    after: string;
    approval_ref: string;
  }>;
}

export interface SettingsIntegrationsData {
  connected_sources: Array<{
    source_name: string;
    status: string;
    last_verified: string;
    details: string;
  }>;
  pipeline_health: Array<{ metric_name: string; metric_value: string }>;
  rate_cards: Array<{
    provider: string;
    sku_family: string;
    region: string;
    list_rate: string;
    contract_rate: string;
    discount: string;
    effective_date: string;
    source: string;
  }>;
  system_tables_readiness: {
    catalog: string;
    schemas_verified: string[];
    key_tables: Array<{ name: string; columns_count: number; status: string }>;
    sql_execution_state: string;
    sql_execution_note: string;
  };
}

export interface QueryHistoryItem {
  query_id: string;
  start_time: string;
  duration_ms: number;
  duration_formatted: string;
  status: string;
  warehouse_id: string;
  warehouse_name: string;
  rows_produced: number;
  bytes_read: number;
  bytes_written: number;
  user: string;
  sql_statement: string;
  query_type: string;
  cost_correlation_dbu?: number | null;
  error_message?: string | null;
}

export interface QueryHistoryData {
  records: QueryHistoryItem[];
  total_count: number;
  duration_histogram: Array<{ bucket: string; count: number; percentage: number }>;
  status_distribution: Array<{ status: string; count: number; percentage: number; color?: string }>;
  daily_volume: Array<{ date: string; queries: number; avg_duration_ms: number }>;
  active_filters: Record<string, unknown>;
}

export interface SystemTableItem {
  table_name: string;
  catalog: string;
  schema_name: string;
  description: string;
  status: string;
  columns_count: number;
  columns: Array<{ name: string; type: string; comment?: string }>;
  row_count?: number | null;
  latest_record_time?: string | null;
  query_duration_ms?: number | null;
  notes: string;
  sample_records: Array<Record<string, unknown>>;
}

export interface SystemTablesExplorerData {
  tables: SystemTableItem[];
  catalog_status: string;
  warehouse_state: string;
  governance_model: string;
}

// --- Milestone 3H: Live Databricks Financial Ingestion & Reconciliation Types ---

export interface BillingUsageRecord {
  record_id: string;
  workspace_id: string;
  account_id?: string | null;
  sku_name: string;
  cloud: string;
  usage_start_time: string;
  usage_end_time: string;
  usage_date: string;
  usage_unit: string;
  usage_quantity: number;
  record_type: string;
  ingestion_date?: string | null;
  billing_origin_product?: string | null;
  product_features?: Record<string, unknown>;
  usage_metadata?: Record<string, unknown>;
  custom_tags?: Record<string, string>;
  identity_metadata?: Record<string, unknown>;
  effective_cost?: number | null;
  pricing_matched: boolean;
  currency?: string | null;
}

export interface BillingPriceRecord {
  sku_name: string;
  cloud: string;
  currency_code: string;
  price_per_unit: number;
  pricing_unit: string;
  price_start_time: string;
  price_end_time?: string | null;
}

export interface BillingIngestionStatusResponse {
  connection_status: string;
  warehouse_status: string;
  warehouse_id: string;
  warehouse_name: string;
  system_tables_status: string;
  last_successful_ingestion?: string | null;
  total_usage_records_ingested: number;
  total_dbu_consumed: number;
  active_configuration_version: number;
  next_action: string;
}

export interface IngestionRunCreateRequest {
  workspace_id?: string;
  start_date?: string;
  end_date?: string;
  is_approved?: boolean;
  limit?: number;
}

export interface BillingIngestionRunResponse {
  run_id: string;
  workspace_id: string;
  source_table: string;
  requested_period_start: string;
  requested_period_end: string;
  started_at: string;
  completed_at?: string | null;
  status: string;
  extracted_count: number;
  inserted_count: number;
  duplicate_count: number;
  retraction_count: number;
  error_count: number;
  error_message?: string | null;
  approval_request?: Record<string, unknown> | null;
}

export interface BillingSummaryResponse {
  workspace_id: string;
  resource_id?: string | null;
  total_dbu: number;
  net_dbu: number;
  retraction_dbu: number;
  total_spend_verified?: number | null;
  currency: string;
  dbu_by_product: Array<Record<string, unknown>>;
  dbu_by_sku: Array<Record<string, unknown>>;
  daily_trend: Array<Record<string, unknown>>;
  matched_pricing_count: number;
  unmatched_pricing_count: number;
  data_status: string;
  last_refreshed: string;
}

export interface BillingReconciliationResponse {
  workspace_id: string;
  usage_record_count: number;
  price_record_count: number;
  matched_records_count: number;
  unmatched_records_count: number;
  retraction_records_count: number;
  gross_dbu: number;
  retraction_dbu: number;
  net_dbu: number;
  gross_cost: number;
  net_cost: number;
  currency: string;
  reconciliation_status: string;
  audit_notes: string[];
}

export interface IngestionPreviewResponse {
  workspace_id: string;
  period_start: string;
  period_end: string;
  source: string;
  preview_records: BillingUsageRecord[];
  total_available_in_preview: number;
  status: string;
}

export interface IngestionValidateResponse {
  valid: boolean;
  workspace_id: string;
  warehouse_id: string;
  warehouse_name?: string;
  warehouse_state: string;
  system_tables_ready: boolean;
  allowed_tables?: string[];
  query_plan_preview?: string;
  expected_result_size?: string;
  expected_operational_cost?: string;
  approval_status?: string;
  duplicate_handling?: string;
  can_run?: boolean;
  diagnostic_messages: string[];
}




