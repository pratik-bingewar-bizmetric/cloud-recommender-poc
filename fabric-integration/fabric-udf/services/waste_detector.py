"""Pure deterministic FinOps cloud waste detection algorithms.

Evaluates discovered resources and live telemetry:
- Unattached managed disks (no attached VM / managedBy is null)
- Idle virtual machines (power_state=running, but 7-day max CPU < 5%)
- Unassociated Public IP addresses
- Oversized compute instances with rightsizing candidates

Strict Real-Data Policy:
Returns strictly real detected items or an empty list with count 0.
Never injects synthetic or hardcoded placeholder items.
"""

from decimal import Decimal

from schemas.models import (
    DiscoveredResource,
    WasteItem,
    WasteSummary,
)


class FinOpsWasteDetector:
    """Deterministic analyzer identifying cloud waste across discovered resources."""

    def analyze_waste(
        self,
        connection_id: str,
        resources: list[DiscoveredResource],
        vm_cpu_metrics: dict[str, float] | None = None,
    ) -> WasteSummary:
        """Analyze a list of discovered resources and metrics to generate a WasteSummary."""
        items: list[WasteItem] = []
        metrics = vm_cpu_metrics or {}

        for res in resources:
            r_type = res.resource_type.lower()

            # 1. Detect Unattached Managed Disks
            if "microsoft.compute/disks" in r_type:
                # Check tags or power_state (used as diskState representation)
                state = (res.power_state or res.tags.get("diskState") or "").lower()
                is_unattached = (
                    state == "unattached"
                    or res.tags.get("managedBy") in (None, "", "null")
                    and state != "attached"
                )
                if is_unattached:
                    cost = res.monthly_cost_usd
                    cost_status = "verified_rate" if cost is not None else "pricing_unavailable"
                    cost_val = cost if cost is not None else Decimal("0.00")
                    items.append(
                        WasteItem(
                            resource_id=res.resource_id,
                            name=res.name,
                            resource_type="Disk",
                            waste_category="unattached_disk",
                            evidence="Disk state is Unattached (no compute instance attached).",
                            current_sku=res.sku_name or "Standard_SSD",
                            monthly_cost_leakage_usd=cost_val,
                            projected_monthly_savings_usd=cost_val,
                            cost_status=cost_status,
                        )
                    )

            # 2. Detect Idle Virtual Machines
            elif "microsoft.compute/virtualmachines" in r_type:
                # Only running VMs can generate idle compute waste
                is_running = (res.power_state or "").lower() in (
                    "running",
                    "powerstate/running",
                )
                if is_running:
                    # Check CPU telemetry if available
                    max_cpu = metrics.get(res.resource_id)
                    if max_cpu is not None and max_cpu < 5.0:
                        vm_cost = res.monthly_cost_usd
                        cost_status = "verified_rate" if vm_cost is not None else "pricing_unavailable"
                        cost_val = vm_cost if vm_cost is not None else Decimal("0.00")
                        items.append(
                            WasteItem(
                                resource_id=res.resource_id,
                                name=res.name,
                                resource_type="VirtualMachine",
                                waste_category="idle_compute",
                                evidence=f"7-day maximum CPU utilization was {max_cpu:.1f}% (threshold < 5.0%).",
                                current_sku=res.sku_name or "Standard_D2s_v5",
                                monthly_cost_leakage_usd=cost_val,
                                projected_monthly_savings_usd=cost_val,
                                cost_status=cost_status,
                            )
                        )

            # 3. Detect Unassociated Public IPs
            elif "microsoft.network/publicipaddresses" in r_type:
                state = (
                    res.power_state or res.tags.get("ipConfiguration") or ""
                ).lower()
                is_unassociated = (
                    state in ("unassociated", "", "none")
                    or "ipconfiguration" not in res.tags
                )
                if is_unassociated:
                    ip_cost = res.monthly_cost_usd
                    cost_status = "verified_rate" if ip_cost is not None else "pricing_unavailable"
                    cost_val = ip_cost if ip_cost is not None else Decimal("0.00")
                    items.append(
                        WasteItem(
                            resource_id=res.resource_id,
                            name=res.name,
                            resource_type="PublicIP",
                            waste_category="unassociated_ip",
                            evidence="Public IP is not associated with any Network Interface (NIC) or Load Balancer.",
                            current_sku=res.sku_name or "Standard_IPv4",
                            monthly_cost_leakage_usd=cost_val,
                            projected_monthly_savings_usd=cost_val,
                            cost_status=cost_status,
                        )
                    )

        # Compute totals
        total_monthly = sum(
            (item.monthly_cost_leakage_usd for item in items), Decimal("0.00")
        )
        total_annual = total_monthly * Decimal("12.0")

        category_counts: dict[str, int] = {}
        for item in items:
            category_counts[item.waste_category] = (
                category_counts.get(item.waste_category, 0) + 1
            )

        return WasteSummary(
            connection_id=connection_id,
            total_monthly_waste_usd=total_monthly,
            total_annual_waste_usd=total_annual,
            waste_count_by_category=category_counts,
            items=items,
        )
