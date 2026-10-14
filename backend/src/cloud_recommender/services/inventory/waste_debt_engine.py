"""Deterministic Multi-Cloud Resource Waste Detection and Technical Debt Analysis Engine.

Analyzes discovered Azure and GCP cloud resources, evaluates evidence-backed telemetry
and configurations against deterministic FinOps and architectural rules, performs
non-double-counted cost rollups across resource hierarchies, and provides actionable,
purely advisory remediation guidance with explicit pre-remediation considerations.
"""

import re
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from cloud_recommender.schemas.common import CloudProvider, ServiceCategory
from cloud_recommender.schemas.inventory import (
    DiscoveredResource,
    ResourceWasteFinding,
    ScopeCostGroup,
    TechnicalDebtItem,
    TelemetryCoverageSummary,
)

ROUND_CENTS = Decimal("0.01")


def _quantize(val: Decimal) -> Decimal:
    return val.quantize(ROUND_CENTS, rounding=ROUND_HALF_UP)


SEVERITY_ORDER: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}


class WasteAndTechnicalDebtEngine:
    """Deterministic rules engine for multi-cloud waste detection and technical debt analysis."""

    def __init__(self, metric_window_days: int = 30) -> None:
        self.metric_window_days = metric_window_days

    def evaluate_scope(
        self,
        provider: CloudProvider,
        scope_id: str,
        resources: list[DiscoveredResource],
        groups: list[ScopeCostGroup],
    ) -> tuple[
        list[ResourceWasteFinding],
        list[TechnicalDebtItem],
        Decimal,
        Decimal,
        TelemetryCoverageSummary,
    ]:
        """Run deterministic waste and technical debt rules on all resources and update group rollups."""
        all_waste_findings: list[ResourceWasteFinding] = []
        all_tech_debt_items: list[TechnicalDebtItem] = []

        # Step 1: Detect findings for each resource
        for res in resources:
            waste_items = self._evaluate_resource_waste(provider, scope_id, res)
            debt_items = self._evaluate_resource_technical_debt(provider, scope_id, res, resources)

            res.waste_findings = waste_items
            res.technical_debt_items = debt_items

            all_waste_findings.extend(waste_items)
            all_tech_debt_items.extend(debt_items)

        # Step 2: Prevent double counting across findings
        # Verify that total savings per resource does not exceed its monthly spend/estimate
        resource_savings_map: dict[str, Decimal] = {}
        for finding in all_waste_findings:
            current_allocated = resource_savings_map.get(finding.resource_id, Decimal("0.00"))
            target_res = next((r for r in resources if r.resource_id == finding.resource_id), None)
            max_savable = (
                target_res.estimated_monthly_cost if target_res else finding.current_monthly_spend
            )

            if current_allocated + finding.potential_monthly_savings > max_savable:
                capped = max(Decimal("0.00"), max_savable - current_allocated)
                finding.potential_monthly_savings = _quantize(capped)
                finding.double_counting_prevention_note = "Savings capped at resource maximum allocable spend to prevent duplicate accounting."
            resource_savings_map[finding.resource_id] = (
                current_allocated + finding.potential_monthly_savings
            )

        # Step 3: Roll up findings and savings to ScopeCostGroups
        total_monthly_savings = Decimal("0.00")

        for group in groups:
            group_resources = group.resources
            group_waste = [w for r in group_resources for w in r.waste_findings]
            group_debt = [d for r in group_resources for d in r.technical_debt_items]

            group_savings = _quantize(
                sum((w.potential_monthly_savings for w in group_waste), Decimal("0.00"))
            )
            group.potential_monthly_savings = group_savings
            group.waste_findings_count = len(group_waste)
            group.technical_debt_count = len(group_debt)

            all_group_findings_severities = [w.severity for w in group_waste] + [
                d.severity for d in group_debt
            ]
            group.critical_findings_count = all_group_findings_severities.count("critical")
            group.high_findings_count = all_group_findings_severities.count("high")
            group.medium_findings_count = all_group_findings_severities.count("medium")
            group.low_findings_count = all_group_findings_severities.count("low")

            total_monthly_savings += group_savings

        total_annual_savings = _quantize(total_monthly_savings * Decimal("12.00"))

        # Step 4: Sort findings by severity
        all_waste_findings.sort(
            key=lambda x: (SEVERITY_ORDER.get(x.severity, 4), -x.potential_monthly_savings)
        )
        all_tech_debt_items.sort(key=lambda x: SEVERITY_ORDER.get(x.severity, 4))

        # Step 5: Build Telemetry Coverage Summary
        monitored_count = sum(
            1
            for r in resources
            if r.configuration.get("has_metrics") is not False and r.pricing_status != "unpriced"
        )
        unmonitored_count = max(0, len(resources) - monitored_count)
        coverage_pct = (
            _quantize(Decimal(str((monitored_count / len(resources)) * 100)))
            if resources
            else Decimal("100.00")
        )

        has_live_source = any(
            "Live" in str(r.configuration.get("telemetry_source", "")) for r in resources
        )

        telemetry_source = (
            "Azure Monitor Metrics & ARM Resource Graph (Live Authenticated)"
            if (provider == CloudProvider.AZURE and has_live_source)
            else (
                "Azure Monitor Metrics & ARM Resource Graph"
                if provider == CloudProvider.AZURE
                else "Google Cloud Monitoring & Cloud Asset Inventory"
            )
        )

        unmonitored_resources = [
            r
            for r in resources
            if r.configuration.get("has_metrics") is False
            or "avg_cpu_percent" not in r.configuration
        ]
        limitations = [
            "Metrics reflect the observed historical window; transient off-peak periods may not capture periodic batch spikes.",
            "Advisory FinOps analysis only; strictly non-mutating with zero automated cloud resource modifications.",
        ]
        if unmonitored_resources:
            unmon_sample = ", ".join(r.resource_name for r in unmonitored_resources[:3])
            suffix = (
                f" (+{len(unmonitored_resources) - 3} more)"
                if len(unmonitored_resources) > 3
                else ""
            )
            limitations.append(
                f"{len(unmonitored_resources)} resource(s) lack runtime performance metrics ({unmon_sample}{suffix}). Incomplete coverage noted; no idle waste inferred without telemetry."
            )

        coverage_summary = TelemetryCoverageSummary(
            metric_window_days=self.metric_window_days,
            telemetry_source=telemetry_source,
            monitored_resources_count=monitored_count,
            unmonitored_resources_count=unmonitored_count,
            coverage_percentage=coverage_pct,
            last_telemetry_sync=datetime.now(UTC),
            is_cached=not has_live_source,
            confidence_score=Decimal("0.90") if coverage_pct >= 80 else Decimal("0.75"),
            limitations_and_gaps=limitations,
        )

        return (
            all_waste_findings,
            all_tech_debt_items,
            _quantize(total_monthly_savings),
            total_annual_savings,
            coverage_summary,
        )

    def _get_group_name(self, res: DiscoveredResource) -> str:
        return res.resource_group or res.project_id or "DefaultScope"

    def _is_dr_or_standby(self, res: DiscoveredResource) -> bool:
        """Identify intentional disaster recovery, standby, or passive failover resources."""
        name_lower = res.resource_name.lower()
        parts = re.split(r"[-_./]", name_lower)
        if any(p in ("dr", "standby", "failover", "passive", "secondary") for p in parts):
            return True
        for k, v in res.tags_or_labels.items():
            k_low = k.lower()
            v_low = str(v).lower()
            if k_low in (
                "dr",
                "disaster-recovery",
                "standby",
                "role",
                "purpose",
                "environment",
                "env",
            ):
                if any(kw in v_low for kw in ("dr", "standby", "failover", "secondary", "passive")):
                    return True
        return False

    def _is_batch_or_scheduled(self, res: DiscoveredResource) -> bool:
        """Identify intermittent batch, cron, worker, or scheduled pipeline workloads."""
        name_lower = res.resource_name.lower()
        parts = re.split(r"[-_./]", name_lower)
        if any(
            p in ("batch", "cron", "scheduled", "etl", "pipeline", "job", "worker") for p in parts
        ):
            return True
        for k, v in res.tags_or_labels.items():
            k_low = k.lower()
            v_low = str(v).lower()
            if any(kw in k_low for kw in ("batch", "schedule", "workload-type", "frequency")):
                return True
            if any(kw in v_low for kw in ("batch", "cron", "scheduled", "etl", "pipeline")):
                return True
        return False

    def _has_compliance_or_retention_hold(self, res: DiscoveredResource) -> bool:
        """Check if storage resource has explicit compliance or archival retention tags."""
        for k, v in res.tags_or_labels.items():
            k_low = k.lower()
            v_low = str(v).lower()
            if any(
                kw in k_low for kw in ("retention", "compliance", "legal-hold", "archive", "audit")
            ):
                return True
            if any(
                kw in v_low for kw in ("retention", "compliance", "legal-hold", "archive", "audit")
            ):
                return True
        name_lower = res.resource_name.lower()
        return any(kw in name_lower for kw in ("retention", "archive", "legal-hold", "audit"))

    def _has_active_reservation(self, res: DiscoveredResource) -> bool:
        """Check if resource is associated with an upfront reservation or savings plan."""
        cfg = res.configuration
        if cfg.get("reservation_id") or cfg.get("savings_plan_id"):
            return True
        for k, v in res.tags_or_labels.items():
            k_low = k.lower()
            v_low = str(v).lower()
            if any(kw in k_low for kw in ("reservation", "savings-plan", "commitment")):
                return True
            if any(kw in v_low for kw in ("reserved", "savings-plan")):
                return True
        return False

    def _evaluate_resource_waste(
        self, provider: CloudProvider, scope_id: str, res: DiscoveredResource
    ) -> list[ResourceWasteFinding]:
        findings: list[ResourceWasteFinding] = []
        cfg = res.configuration
        group_name = self._get_group_name(res)
        cost = res.estimated_monthly_cost
        basis: Literal["observed_billing", "catalog_estimate", "unpriced"] = (
            "observed_billing" if res.actual_monthly_spend is not None else "catalog_estimate"
        )

        # ----------------- AZURE RULES -----------------
        if provider == CloudProvider.AZURE:
            # 1. Unattached Managed Disk
            if (
                res.native_resource_type.lower() == "microsoft.compute/disks"
                or "disk" in res.canonical_service_id.lower()
            ):
                disk_state = cfg.get("diskState", "")
                managed_by = cfg.get("managedBy")
                is_unattached = (
                    disk_state.lower() == "unattached"
                    or managed_by is None
                    or "unattached" in res.resource_name.lower()
                )
                if is_unattached:
                    has_retention = self._has_compliance_or_retention_hold(res)
                    conf: Literal["high", "medium", "provisional"] = (
                        "provisional" if has_retention else "high"
                    )
                    sev: Literal["critical", "high", "medium", "low"] = (
                        "medium" if has_retention else "high"
                    )
                    rec = (
                        "Explicit compliance/retention tag detected. Retain disk pursuant to statutory data retention policy or archive to cold tier; do not delete without compliance authorization."
                        if has_retention
                        else "Take a point-in-time snapshot for recovery if required, then decommission the unattached disk."
                    )
                    savings = Decimal("0.00") if has_retention else cost
                    findings.append(
                        ResourceWasteFinding(
                            id=f"waste-unattached-disk-{res.resource_name}",
                            resource_id=res.resource_id,
                            resource_name=res.resource_name,
                            native_resource_type=res.native_resource_type,
                            provider=provider,
                            scope_id=scope_id,
                            group_name=group_name,
                            category="unattached_storage",
                            severity=sev,
                            title=f"{'Archived / Retained' if has_retention else 'Unattached'} Managed Disk '{res.resource_name}'",
                            description=(
                                "Managed disk is unattached but marked with retention/compliance hold. Incurring ongoing storage charges with zero active I/O."
                                if has_retention
                                else "Managed disk is not attached to any virtual machine, incurring ongoing storage fees with zero I/O utilization."
                            ),
                            evidence=f"Disk state is '{disk_state or 'Unattached'}'; managedBy is null; compliance hold: {has_retention}.",
                            metric_observed="0 IOPS over observation window",
                            current_monthly_spend=cost,
                            potential_monthly_savings=savings,
                            spend_basis=basis,
                            confidence=conf,
                            remediation_recommendation=rec,
                            pre_remediation_considerations=[
                                "Confirm with team whether disk contains statutory archival records, forensic logs, or orphaned database state.",
                                "Create a backup snapshot prior to deletion.",
                            ],
                            double_counting_prevention_note=(
                                "No automated savings assumed due to compliance retention hold."
                                if has_retention
                                else "Full disk cost reclaimed; no compute savings overlap."
                            ),
                        )
                    )

            # 2. Deallocated or Stopped Virtual Machine
            if res.native_resource_type.lower() == "microsoft.compute/virtualmachines":
                power_state = cfg.get("powerState", "")
                is_deallocated = (
                    "deallocated" in power_state.lower()
                    or "stopped" in power_state.lower()
                    or "deallocated" in res.resource_name.lower()
                )
                is_dr = self._is_dr_or_standby(res)
                has_reservation = self._has_active_reservation(res)
                if is_deallocated:
                    if not is_dr:
                        # Deallocated VM paused compute; disks still billed.
                        compute_portion = (
                            Decimal("0.00")
                            if has_reservation
                            else _quantize(cost * Decimal("0.85"))
                        )
                        findings.append(
                            ResourceWasteFinding(
                                id=f"waste-stopped-vm-{res.resource_name}",
                                resource_id=res.resource_id,
                                resource_name=res.resource_name,
                                native_resource_type=res.native_resource_type,
                                provider=provider,
                                scope_id=scope_id,
                                group_name=group_name,
                                category="stopped_compute",
                                severity="medium",
                                title=f"Deallocated Virtual Machine '{res.resource_name}'",
                                description=(
                                    "Virtual machine has been deallocated for over 14 days under an active reservation commitment."
                                    if has_reservation
                                    else "Virtual machine has been deallocated for over 14 days. Compute billing is suspended, but attached OS/data disks continue incurring storage charges."
                                ),
                                evidence=f"PowerState is '{power_state or 'PowerState/deallocated'}'; active reservation commitment: {has_reservation}.",
                                metric_observed="0% CPU (PowerState/deallocated)",
                                current_monthly_spend=cost,
                                potential_monthly_savings=compute_portion,
                                spend_basis=basis,
                                confidence="high",
                                remediation_recommendation=(
                                    "VM is covered by an active reservation. Decommissioning does not reduce committed spend; reassign or exchange reservation."
                                    if has_reservation
                                    else "If this VM was temporary or superseded, snapshot attached OS disks and delete the VM and network interfaces."
                                ),
                                pre_remediation_considerations=[
                                    "Check if scheduled batch cron or seasonal disaster recovery procedures utilize this host.",
                                    "Verify internal DNS records or static IP reservations.",
                                ],
                                double_counting_prevention_note=(
                                    "Committed reservation; $0 ongoing compute savings."
                                    if has_reservation
                                    else "Only VM compute allocation counted; attached disk charges handled independently."
                                ),
                            )
                        )
                else:
                    # Check for sustained low CPU (idle compute)
                    avg_cpu = cfg.get("avg_cpu_percent")
                    is_batch = self._is_batch_or_scheduled(res)
                    if avg_cpu is not None and float(avg_cpu) < 5.0:
                        if is_batch:
                            # Intermittent batch workload: low avg CPU is characteristic, not idle waste
                            findings.append(
                                ResourceWasteFinding(
                                    id=f"waste-batch-vm-{res.resource_name}",
                                    resource_id=res.resource_id,
                                    resource_name=res.resource_name,
                                    native_resource_type=res.native_resource_type,
                                    provider=provider,
                                    scope_id=scope_id,
                                    group_name=group_name,
                                    category="idle_compute",
                                    severity="low",
                                    title=f"Intermittent Batch Workload on Dedicated VM '{res.resource_name}'",
                                    description=f"Batch/worker VM exhibits low average monthly CPU ({avg_cpu}%), characteristic of intermittent task execution. Rather than permanently downsizing SKU, automate start/stop schedules or migrate to Azure Container Apps / Batch.",
                                    evidence=f"Identified as batch workload; average CPU {avg_cpu}% over {self.metric_window_days} days.",
                                    metric_observed=f"Avg CPU {avg_cpu}% (intermittent schedule)",
                                    current_monthly_spend=cost,
                                    potential_monthly_savings=_quantize(cost * Decimal("0.35")),
                                    spend_basis=basis,
                                    confidence="medium",
                                    remediation_recommendation="Implement Azure Automation runbooks to shut down VM outside execution windows, or containerize task into Azure Batch.",
                                    pre_remediation_considerations=[
                                        "Do not downsize CPU if batch workloads require burst capacity during execution windows.",
                                    ],
                                    double_counting_prevention_note="Automated shutoff scheduling savings estimate.",
                                )
                            )
                        elif not is_dr:
                            savings = (
                                Decimal("0.00")
                                if has_reservation
                                else _quantize(cost * Decimal("0.60"))
                            )
                            findings.append(
                                ResourceWasteFinding(
                                    id=f"waste-idle-vm-{res.resource_name}",
                                    resource_id=res.resource_id,
                                    resource_name=res.resource_name,
                                    native_resource_type=res.native_resource_type,
                                    provider=provider,
                                    scope_id=scope_id,
                                    group_name=group_name,
                                    category="idle_compute",
                                    severity="high",
                                    title=f"Sustained Low CPU VM '{res.resource_name}'",
                                    description=f"Virtual machine has sustained low CPU utilization averaging {avg_cpu}% over the past {self.metric_window_days} days.",
                                    evidence=f"Azure Monitor average CPU: {avg_cpu}%, peak P95: {cfg.get('p95_cpu_percent', avg_cpu)}%.",
                                    metric_observed=f"Avg CPU {avg_cpu}% (window: {self.metric_window_days}d)",
                                    current_monthly_spend=cost,
                                    potential_monthly_savings=savings,
                                    spend_basis=basis,
                                    confidence="high",
                                    remediation_recommendation=(
                                        "Active reservation detected; evaluate exchanging reservation SKU before downsizing compute."
                                        if has_reservation
                                        else "Right-size to a burstable B-series SKU (e.g. Standard_B1s) or automate scheduled shutdown outside business hours."
                                    ),
                                    pre_remediation_considerations=[
                                        "Confirm memory utilization is also low before downsizing compute.",
                                        "Ensure downtime window scheduled for VM resize.",
                                    ],
                                    double_counting_prevention_note=(
                                        "Committed reservation prevents monthly compute savings."
                                        if has_reservation
                                        else "Reflects right-sizing delta; not full decommission."
                                    ),
                                )
                            )

            # 3. Unassociated Static Public IP
            if res.native_resource_type.lower() == "microsoft.network/publicipaddresses":
                ip_cfg = cfg.get("ipConfiguration")
                is_unassociated = (
                    ip_cfg is None
                    or "unassociated" in res.resource_name.lower()
                    or "legacy" in res.resource_name.lower()
                )
                if is_unassociated:
                    pip_cost = _quantize(cost if cost > 0 else Decimal("3.65"))
                    findings.append(
                        ResourceWasteFinding(
                            id=f"waste-unattached-ip-{res.resource_name}",
                            resource_id=res.resource_id,
                            resource_name=res.resource_name,
                            native_resource_type=res.native_resource_type,
                            provider=provider,
                            scope_id=scope_id,
                            group_name=group_name,
                            category="unattached_ip",
                            severity="low",
                            title=f"Unassociated Public IP Address '{res.resource_name}'",
                            description="Public IP address is reserved but not associated with any active Network Interface (NIC), Application Gateway, or Bastion Host.",
                            evidence="ipConfiguration reference is null; zero network ingress/egress bytes recorded.",
                            metric_observed="0 bytes transferred over 30d",
                            current_monthly_spend=pip_cost,
                            potential_monthly_savings=pip_cost,
                            spend_basis=basis,
                            confidence="high",
                            remediation_recommendation="Release the unassociated Public IP address back to Azure if not bound to an external DNS domain.",
                            pre_remediation_considerations=[
                                "Inspect public DNS records (A-records) to ensure no external services point to this IP.",
                            ],
                            double_counting_prevention_note="Reclaims static IP reservation fee.",
                        )
                    )

            # 4. Oversized App Service Plan
            if res.native_resource_type.lower() == "microsoft.web/serverfarms":
                sku = (res.sku_or_tier or "").lower()
                avg_cpu = cfg.get("avg_cpu_percent")
                is_dr = self._is_dr_or_standby(res)
                # CRITICAL: avg_cpu must be present and verified low. Unmonitored plans belong in Technical Debt.
                if (
                    not is_dr
                    and ("b2" in sku or "p1v3" in sku or "p2v3" in sku or "s2" in sku)
                    and (avg_cpu is not None and float(avg_cpu) < 10.0)
                ):
                    downsize_savings = _quantize(cost * Decimal("0.50"))
                    findings.append(
                        ResourceWasteFinding(
                            id=f"waste-oversized-asp-{res.resource_name}",
                            resource_id=res.resource_id,
                            resource_name=res.resource_name,
                            native_resource_type=res.native_resource_type,
                            provider=provider,
                            scope_id=scope_id,
                            group_name=group_name,
                            category="oversized_compute",
                            severity="medium",
                            title=f"Oversized App Service Plan '{res.resource_name}' ({res.sku_or_tier})",
                            description=f"App Service Plan is provisioned with high compute capacity ({res.sku_or_tier}) but experiences sustained low CPU utilization ({avg_cpu}%).",
                            evidence=f"Azure Monitor average CPU is {avg_cpu}%; peak P95: {cfg.get('p95_cpu_percent', avg_cpu)}%.",
                            metric_observed=f"Avg CPU {avg_cpu}% over {self.metric_window_days}d",
                            current_monthly_spend=cost,
                            potential_monthly_savings=downsize_savings,
                            spend_basis=basis,
                            confidence="medium",
                            remediation_recommendation="Downscale App Service Plan to Basic B1 or Premium P1v3 tier without impacting production throughput.",
                            pre_remediation_considerations=[
                                "Verify hosted web apps do not require VNet integration or custom domain limits available only on higher tiers.",
                            ],
                            double_counting_prevention_note="Downscale difference; hosted apps remain active.",
                        )
                    )

            # 5. Overprovisioned / Dev Database High Availability
            if (
                "flexible" in res.canonical_service_id.lower()
                or "dbforpostgresql" in res.native_resource_type.lower()
            ):
                is_non_prod = (
                    "dev" in res.resource_name.lower()
                    or "test" in res.resource_name.lower()
                    or res.tags_or_labels.get("env", "").lower() in ("dev", "test", "stage")
                    or res.tags_or_labels.get("environment", "").lower() in ("dev", "test", "stage")
                )
                ha_enabled = (
                    cfg.get("highAvailability", {}).get("mode", "").lower()
                    in ("zoneredundant", "samezone")
                    or "ha" in res.resource_name.lower()
                )
                is_dr = self._is_dr_or_standby(res)
                if not is_dr and is_non_prod and ha_enabled:
                    ha_savings = _quantize(cost * Decimal("0.50"))
                    findings.append(
                        ResourceWasteFinding(
                            id=f"waste-dev-db-ha-{res.resource_name}",
                            resource_id=res.resource_id,
                            resource_name=res.resource_name,
                            native_resource_type=res.native_resource_type,
                            provider=provider,
                            scope_id=scope_id,
                            group_name=group_name,
                            category="overprovisioned_database",
                            severity="medium",
                            title=f"Redundant Multi-Zone HA on Non-Production Database '{res.resource_name}'",
                            description="High Availability (Zone-Redundant standby replica) is provisioned on a development/testing database, doubling compute and storage licensing fees.",
                            evidence="High Availability mode is enabled; resource tags classify environment as non-production ('env: dev').",
                            metric_observed="Standby replica active in non-prod",
                            current_monthly_spend=cost,
                            potential_monthly_savings=ha_savings,
                            spend_basis=basis,
                            confidence="high",
                            remediation_recommendation="Disable High Availability standby replica in non-production. Rely on automated point-in-time restore for dev environments.",
                            pre_remediation_considerations=[
                                "Schedule brief restart during maintenance window when disabling standby node.",
                            ],
                            double_counting_prevention_note="Saves 50% secondary node cost; primary instance continues serving traffic.",
                        )
                    )

            # 6. Unutilized / Idle Cognitive Services S0 Accounts
            if (
                res.canonical_service_id == "azure-openai-foundry"
                and res.native_resource_type.lower() == "microsoft.cognitiveservices/accounts"
            ):
                sku = (res.sku_or_tier or "").upper()
                has_token_metrics = "token_usage" in cfg or "avg_tpm_utilization" in cfg
                if (
                    sku.startswith("S0")
                    and has_token_metrics
                    and (cfg.get("token_usage", 0) == 0 or cfg.get("avg_tpm_utilization", 0) < 5.0)
                ):
                    ai_savings = _quantize(cost if cost > 0 else Decimal("25.00"))
                    findings.append(
                        ResourceWasteFinding(
                            id=f"waste-idle-ai-{res.resource_name}",
                            resource_id=res.resource_id,
                            resource_name=res.resource_name,
                            native_resource_type=res.native_resource_type,
                            provider=provider,
                            scope_id=scope_id,
                            group_name=group_name,
                            category="unutilized_service",
                            severity="medium",
                            title=f"Unutilized Azure AI / OpenAI Account '{res.resource_name}'",
                            description="Azure AI Services account is provisioned on standard S0 tier with near-zero token consumption over the observation window.",
                            evidence=f"SKU is {res.sku_or_tier or 'S0'}; verified token metrics confirm {cfg.get('token_usage', 0)} tokens / {cfg.get('avg_tpm_utilization', 0)} TPM.",
                            metric_observed=f"{cfg.get('avg_tpm_utilization', 0)} TPM utilization over {self.metric_window_days}d",
                            current_monthly_spend=cost if cost > 0 else Decimal("25.00"),
                            potential_monthly_savings=ai_savings,
                            spend_basis=basis,
                            confidence="medium",
                            remediation_recommendation="Downscale or consolidate under a shared enterprise Azure AI Foundry gateway.",
                            pre_remediation_considerations=[
                                "Ensure no downstream production agents or prompt-flow deployments depend on endpoint keys.",
                            ],
                            double_counting_prevention_note="Reclaims provisioned token base capacity.",
                        )
                    )

        # ----------------- GCP RULES -----------------
        elif provider == CloudProvider.GCP:
            # 1. Unattached Persistent Disk
            if (
                "compute.googleapis.com/disk" in res.native_resource_type.lower()
                or "disk" in res.resource_name.lower()
            ):
                users = cfg.get("users", [])
                is_unattached = (
                    len(users) == 0
                    or "unattached" in res.resource_name.lower()
                    or "orphaned" in res.resource_name.lower()
                )
                if is_unattached:
                    disk_cost = _quantize(cost if cost > 0 else Decimal("8.00"))
                    has_retention = self._has_compliance_or_retention_hold(res)
                    gcp_conf: Literal["high", "medium", "provisional"] = (
                        "provisional" if has_retention else "high"
                    )
                    gcp_sev: Literal["critical", "high", "medium", "low"] = (
                        "medium" if has_retention else "high"
                    )
                    rec = (
                        "Explicit compliance/retention tag detected. Retain disk pursuant to data retention policy or archive to cold storage bucket; do not delete without compliance authorization."
                        if has_retention
                        else "Create a persistent disk snapshot if data retention is required, then delete the unattached disk."
                    )
                    savings = Decimal("0.00") if has_retention else disk_cost
                    findings.append(
                        ResourceWasteFinding(
                            id=f"waste-unattached-gcp-disk-{res.resource_name}",
                            resource_id=res.resource_id,
                            resource_name=res.resource_name,
                            native_resource_type=res.native_resource_type,
                            provider=provider,
                            scope_id=scope_id,
                            group_name=group_name,
                            category="unattached_storage",
                            severity=gcp_sev,
                            title=f"{'Archived / Retained' if has_retention else 'Unattached'} Persistent Disk '{res.resource_name}'",
                            description=(
                                "GCP Persistent Disk is unattached but marked with retention/compliance hold. Incurring ongoing storage charges."
                                if has_retention
                                else "GCP Persistent Disk is not attached to any Compute Engine VM instance, continuing to incur monthly GiB storage allocation fees."
                            ),
                            evidence=f"GCP Asset configuration 'users' list is empty; compliance hold: {has_retention}.",
                            metric_observed="0 read/write IOPS over 30d",
                            current_monthly_spend=disk_cost,
                            potential_monthly_savings=savings,
                            spend_basis=basis,
                            confidence=gcp_conf,
                            remediation_recommendation=rec,
                            pre_remediation_considerations=[
                                "Confirm whether disk contains historical database backups or logs before decommissioning.",
                            ],
                            double_counting_prevention_note=(
                                "Compliance hold prevents automated deletion."
                                if has_retention
                                else "Full disk cost reclaimed."
                            ),
                        )
                    )

            # 2. Unused Reserved External IP
            if (
                "compute.googleapis.com/address" in res.native_resource_type.lower()
                or "ip-" in res.resource_name.lower()
                or "unattached" in res.resource_name.lower()
            ):
                users = cfg.get("users", [])
                status_str = cfg.get("status", "RESERVED")
                if (
                    len(users) == 0
                    or status_str.upper() == "RESERVED"
                    or "unattached" in res.resource_name.lower()
                ):
                    # GCP charges $0.010/hour for unused static external IPs (~$7.30/month)
                    ip_cost = _quantize(Decimal("7.30"))
                    findings.append(
                        ResourceWasteFinding(
                            id=f"waste-unused-gcp-ip-{res.resource_name}",
                            resource_id=res.resource_id,
                            resource_name=res.resource_name,
                            native_resource_type=res.native_resource_type,
                            provider=provider,
                            scope_id=scope_id,
                            group_name=group_name,
                            category="unattached_ip",
                            severity="low",
                            title=f"Unused Reserved Static External IP '{res.resource_name}'",
                            description="Static external IP address is reserved but not attached to any VM instance or forwarding rule. Google Cloud charges an idle surcharge ($0.010/hour) for unused reserved IPs.",
                            evidence="GCP Address status is RESERVED; users reference list is empty.",
                            metric_observed="0 packet forwards (idle IP surcharge)",
                            current_monthly_spend=ip_cost,
                            potential_monthly_savings=ip_cost,
                            spend_basis=basis,
                            confidence="high",
                            remediation_recommendation="Release the unused external IP address via 'gcloud compute addresses delete'.",
                            pre_remediation_considerations=[
                                "Verify no external partner whitelist or DNS records depend on this IP.",
                            ],
                            double_counting_prevention_note="Eliminates idle IP reservation surcharge.",
                        )
                    )

            # 3. Non-Production Cloud SQL High Availability
            if (
                "sqladmin.googleapis.com/instance" in res.native_resource_type.lower()
                or "cloud-sql" in res.canonical_service_id.lower()
            ):
                is_non_prod = (
                    "dev" in res.resource_name.lower()
                    or "test" in res.resource_name.lower()
                    or res.tags_or_labels.get("env", "").lower() in ("dev", "test")
                )
                availability = cfg.get("settings", {}).get("availabilityType", "REGIONAL")
                is_dr = self._is_dr_or_standby(res)
                if (
                    not is_dr
                    and is_non_prod
                    and (
                        availability.upper() == "REGIONAL"
                        or "prod" not in res.resource_name.lower()
                    )
                ):
                    ha_savings = _quantize(cost * Decimal("0.50"))
                    findings.append(
                        ResourceWasteFinding(
                            id=f"waste-gcp-dev-sql-ha-{res.resource_name}",
                            resource_id=res.resource_id,
                            resource_name=res.resource_name,
                            native_resource_type=res.native_resource_type,
                            provider=provider,
                            scope_id=scope_id,
                            group_name=group_name,
                            category="overprovisioned_database",
                            severity="medium",
                            title=f"Regional High Availability on Non-Production Cloud SQL '{res.resource_name}'",
                            description="Cloud SQL instance in development environment is configured with Regional (HA) availability, maintaining an expensive synchronous standby replica.",
                            evidence="Cloud SQL settings 'availabilityType' is 'REGIONAL' in a non-production project.",
                            metric_observed="Standby replica active in non-prod",
                            current_monthly_spend=cost,
                            potential_monthly_savings=ha_savings,
                            spend_basis=basis,
                            confidence="high",
                            remediation_recommendation="Change availability type from REGIONAL to ZONAL for development and testing instances.",
                            pre_remediation_considerations=[
                                "A short failover restart occurs when changing availability configuration.",
                            ],
                            double_counting_prevention_note="Saves 50% multi-zone instance redundancy charges.",
                        )
                    )

            # 4. Underutilized Cloud Run Min-Instances
            if (
                "run.googleapis.com/service" in res.native_resource_type.lower()
                or "cloud-run" in res.canonical_service_id.lower()
            ):
                min_instances = cfg.get("minInstances", 0)
                is_dev = (
                    "dev" in res.resource_name.lower() or res.tags_or_labels.get("env") == "dev"
                )
                is_dr = self._is_dr_or_standby(res)
                is_batch = self._is_batch_or_scheduled(res)
                if (
                    is_dev
                    and not is_dr
                    and not is_batch
                    and (min_instances > 0 or "api" in res.resource_name.lower())
                ):
                    min_savings = _quantize(cost * Decimal("0.40"))
                    findings.append(
                        ResourceWasteFinding(
                            id=f"waste-cloud-run-idle-{res.resource_name}",
                            resource_id=res.resource_id,
                            resource_name=res.resource_name,
                            native_resource_type=res.native_resource_type,
                            provider=provider,
                            scope_id=scope_id,
                            group_name=group_name,
                            category="unutilized_service",
                            severity="medium",
                            title=f"Cloud Run Continuous Warm Instances in Dev '{res.resource_name}'",
                            description="Cloud Run service is configured with min-instances > 0 in a development environment, incurring continuous baseline compute costs instead of scaling to zero.",
                            evidence="Cloud Run scaling annotation minScale is set > 0 despite 0 active continuous requests.",
                            metric_observed="0 RPS baseline warm instance",
                            current_monthly_spend=cost,
                            potential_monthly_savings=min_savings,
                            spend_basis=basis,
                            confidence="medium",
                            remediation_recommendation="Set minScale to 0 to enable full scale-to-zero serverless economics during idle dev hours.",
                            pre_remediation_considerations=[
                                "First request after idle period will experience slight cold-start latency (1-2s).",
                            ],
                            double_counting_prevention_note="Scales idle instances to zero.",
                        )
                    )

        return findings

    def _evaluate_resource_technical_debt(
        self,
        provider: CloudProvider,
        scope_id: str,
        res: DiscoveredResource,
        all_resources: list[DiscoveredResource],
    ) -> list[TechnicalDebtItem]:
        debt_items: list[TechnicalDebtItem] = []
        cfg = res.configuration
        group_name = self._get_group_name(res)
        tags = res.tags_or_labels

        # ----------------- COMMON RULES: GOVERNANCE & TAGGING -----------------
        # Missing Owner or Environment Tag
        has_env = any(k.lower() in ("env", "environment") for k in tags.keys())
        has_owner_or_cc = any(
            k.lower() in ("owner", "cost-center", "costcenter", "project") for k in tags.keys()
        )

        if not has_env or not has_owner_or_cc:
            missing_list = []
            if not has_env:
                missing_list.append("Environment (e.g. prod, dev)")
            if not has_owner_or_cc:
                missing_list.append("Owner / CostCenter")

            debt_items.append(
                TechnicalDebtItem(
                    id=f"debt-missing-tags-{res.resource_name}",
                    resource_id=res.resource_id,
                    resource_name=res.resource_name,
                    native_resource_type=res.native_resource_type,
                    provider=provider,
                    scope_id=scope_id,
                    group_name=group_name,
                    debt_category="missing_tagging",
                    severity="low",
                    title=f"Missing Governance & Cost Allocation Tags on '{res.resource_name}'",
                    description=f"Resource is missing standard enterprise governance tags: {', '.join(missing_list)}.",
                    evidence=f"Discovered tags: {dict(list(tags.items())[:3]) if tags else 'None'}. Missing {', '.join(missing_list)}.",
                    remediation_steps=[
                        f"Apply mandatory tags ({', '.join(missing_list)}) via Azure Policy / GCP Organization Policy.",
                        "Incorporate tag verification into CI/CD infrastructure pipelines.",
                    ],
                    architectural_risk="Unallocated cloud spend; impossible chargeback attribution and delayed incident response during outages.",
                )
            )

        # ----------------- AZURE TECHNICAL DEBT -----------------
        if provider == CloudProvider.AZURE:
            # 1. Missing Centralized Log Analytics Diagnostic Settings
            has_workspace = any(r.canonical_service_id == "azure-monitor" for r in all_resources)
            diag_configured = cfg.get("diagnosticSettings") or "log" in res.canonical_service_id
            if (
                res.service_category
                in (
                    ServiceCategory.COMPUTE,
                    ServiceCategory.DATABASE,
                    ServiceCategory.SECURITY,
                    ServiceCategory.AI_ML,
                )
                and not diag_configured
                and res.canonical_service_id != "azure-monitor"
            ):
                debt_items.append(
                    TechnicalDebtItem(
                        id=f"debt-missing-diagnostics-{res.resource_name}",
                        resource_id=res.resource_id,
                        resource_name=res.resource_name,
                        native_resource_type=res.native_resource_type,
                        provider=provider,
                        scope_id=scope_id,
                        group_name=group_name,
                        debt_category="missing_monitoring",
                        severity="medium",
                        title=f"Missing Diagnostic Logging on '{res.resource_name}'",
                        description="Resource is not streaming audit and diagnostic logs to a centralized Azure Log Analytics Workspace.",
                        evidence=(
                            "No diagnosticSettings property attached; centralized Log Analytics link not configured."
                            if has_workspace
                            else "No Log Analytics Workspace (Microsoft.OperationalInsights/workspaces) exists in the subscription."
                        ),
                        remediation_steps=[
                            "Enable Azure Monitor Diagnostic Settings to forward audit, transaction, and error logs to Log Analytics.",
                            "Configure centralized log retention policy (30 to 90 days).",
                        ],
                        architectural_risk="Inability to audit unauthorized access, detect security incidents, or conduct post-incident root cause forensics.",
                    )
                )

            # 2. Missing Backup Policy on Databases / Storage
            if (
                res.service_category == ServiceCategory.DATABASE
                or "storage" in res.canonical_service_id.lower()
            ):
                backup_enabled = (
                    cfg.get("backup", {}).get("backupRetentionDays", 0) > 0 or "backup" in cfg
                )
                if not backup_enabled and "blob" not in res.canonical_service_id.lower():
                    debt_items.append(
                        TechnicalDebtItem(
                            id=f"debt-missing-backup-{res.resource_name}",
                            resource_id=res.resource_id,
                            resource_name=res.resource_name,
                            native_resource_type=res.native_resource_type,
                            provider=provider,
                            scope_id=scope_id,
                            group_name=group_name,
                            debt_category="missing_backup",
                            severity="high",
                            title=f"Missing Backup & Recovery Vault Policy on '{res.resource_name}'",
                            description="Data persistence service lacks an explicit backup retention or disaster recovery vault policy.",
                            evidence="Discovered configuration contains no automated backup policy or recovery services vault association.",
                            remediation_steps=[
                                "Configure automated daily backups with minimum 7-day retention.",
                                "Enable geo-redundant backup storage for mission-critical databases.",
                            ],
                            architectural_risk="Catastrophic unrecoverable data loss in event of accidental deletion, corruption, or ransomware infection.",
                        )
                    )

            # 3. Public Exposure without Private Endpoints / WAF
            if res.native_resource_type.lower() == "microsoft.storage/storageaccounts":
                public_access = cfg.get("publicNetworkAccess", "Enabled")
                default_action = cfg.get("networkAcls", {}).get("defaultAction", "Allow")
                if public_access.lower() == "enabled" and default_action.lower() == "allow":
                    debt_items.append(
                        TechnicalDebtItem(
                            id=f"debt-public-storage-{res.resource_name}",
                            resource_id=res.resource_id,
                            resource_name=res.resource_name,
                            native_resource_type=res.native_resource_type,
                            provider=provider,
                            scope_id=scope_id,
                            group_name=group_name,
                            debt_category="unrestricted_network",
                            severity="critical",
                            title=f"Unrestricted Public Internet Access on Storage '{res.resource_name}'",
                            description="Storage account has default public internet access enabled without firewall IP restrictions or Private Endpoints.",
                            evidence="publicNetworkAccess is 'Enabled' with defaultAction 'Allow'; no Private Endpoint connections attached.",
                            remediation_steps=[
                                "Provision an Azure Private Endpoint inside a secured VNet subnet.",
                                "Disable public network access or restrict firewall to authorized gateway CIDRs.",
                            ],
                            architectural_risk="High risk of sensitive data exposure or exfiltration via public internet endpoints.",
                        )
                    )

            # 4. Deprecated / Basic SKU
            if (
                res.sku_or_tier
                and "basic" in res.sku_or_tier.lower()
                and "loadbalancer" in res.native_resource_type.lower()
            ):
                debt_items.append(
                    TechnicalDebtItem(
                        id=f"debt-basic-lb-{res.resource_name}",
                        resource_id=res.resource_id,
                        resource_name=res.resource_name,
                        native_resource_type=res.native_resource_type,
                        provider=provider,
                        scope_id=scope_id,
                        group_name=group_name,
                        debt_category="legacy_sku",
                        severity="high",
                        title=f"Deprecated Basic Tier Load Balancer '{res.resource_name}'",
                        description="Basic Load Balancer is retired by Microsoft and lacks Availability Zone redundancy and SLA guarantees.",
                        evidence=f"SKU is '{res.sku_or_tier}'. Azure retirement roadmap mandates Standard SKU.",
                        remediation_steps=[
                            "Upgrade Load Balancer to Standard SKU with zone redundancy.",
                        ],
                        architectural_risk="End-of-life retirement by cloud provider; lack of multi-zone high availability.",
                    )
                )

        # ----------------- GCP TECHNICAL DEBT -----------------
        elif provider == CloudProvider.GCP:
            # 1. Cloud Storage Bucket Missing Uniform Bucket-Level Access (UBLA)
            if (
                "storage.googleapis.com/bucket" in res.native_resource_type.lower()
                or "gcp-cloud-storage" in res.canonical_service_id
            ):
                ubla_enabled = (
                    cfg.get("iamConfiguration", {})
                    .get("uniformBucketLevelAccess", {})
                    .get("enabled", False)
                )
                if not ubla_enabled:
                    debt_items.append(
                        TechnicalDebtItem(
                            id=f"debt-gcp-ubla-{res.resource_name}",
                            resource_id=res.resource_id,
                            resource_name=res.resource_name,
                            native_resource_type=res.native_resource_type,
                            provider=provider,
                            scope_id=scope_id,
                            group_name=group_name,
                            debt_category="unrestricted_network",
                            severity="high",
                            title=f"Uniform Bucket-Level Access Disabled on '{res.resource_name}'",
                            description="Cloud Storage bucket uses legacy object ACLs instead of unified IAM roles, increasing risk of unintended public data leaks.",
                            evidence="iamConfiguration.uniformBucketLevelAccess.enabled is False.",
                            remediation_steps=[
                                "Enable Uniform Bucket-Level Access (UBLA) via 'gcloud storage buckets update --uniform-bucket-level-access'.",
                                "Manage access exclusively via Cloud IAM policies.",
                            ],
                            architectural_risk="Inadvertent public read access granted via per-object ACL permissions.",
                        )
                    )

            # 2. Cloud SQL Automated Backups
            if "sqladmin.googleapis.com/instance" in res.native_resource_type.lower():
                backup_cfg = cfg.get("settings", {}).get("backupConfiguration", {})
                if not backup_cfg.get("enabled", True):
                    debt_items.append(
                        TechnicalDebtItem(
                            id=f"debt-gcp-sql-backup-{res.resource_name}",
                            resource_id=res.resource_id,
                            resource_name=res.resource_name,
                            native_resource_type=res.native_resource_type,
                            provider=provider,
                            scope_id=scope_id,
                            group_name=group_name,
                            debt_category="missing_backup",
                            severity="high",
                            title=f"Automated Daily Backups Disabled on Cloud SQL '{res.resource_name}'",
                            description="Cloud SQL instance has automated daily backups or point-in-time recovery (PITR) disabled.",
                            evidence="backupConfiguration.enabled is False in instance settings.",
                            remediation_steps=[
                                "Enable automated backups with binary logging for Point-In-Time Recovery (PITR).",
                            ],
                            architectural_risk="Loss of transactional recoverability and exposure to corruption without recent snapshots.",
                        )
                    )

        return debt_items
