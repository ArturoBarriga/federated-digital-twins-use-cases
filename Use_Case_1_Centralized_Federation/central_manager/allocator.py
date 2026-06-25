"""
Water-allocation algorithm used by the central manager.

Strategy (proportional deficit weighting):
  - Farms whose soil moisture is already ≥ 60 % get nothing
  - Farms that received > 10 mm rain in the last timestamp get nothing
  - For every other farm a weight = (60 - humidity) × area  is computed,
    and the total available water is split proportionally across those weights.
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.models import NormalizedFarmData, AllocationResult

# Assumed flow rate in m3 per hour per hectare
FLOW_RATE_PER_HA = 10.0


def compute_allocation(farms_data: dict[str, NormalizedFarmData], available_water_m3: float = 10000.0,) -> dict[str, AllocationResult]:

    results: dict[str, AllocationResult] = {}
    candidates: list[tuple[str, float, NormalizedFarmData]] = []

    # First pass: exclude farms that don't need water
    for fid, data in farms_data.items():
        # Soil already wet enough — skip
        if data.soil_humidity_40cm_pct >= 60:
            results[fid] = AllocationResult(
                farm_id=fid,
                allocated_quota_m3=0,
                valve_hours=0,
                reason="sufficient_humidity",
                eligible=False,
            )
            continue

        # Recent natural rainfall — skip
        if data.rainfall_mm > 10:
            results[fid] = AllocationResult(
                farm_id=fid,
                allocated_quota_m3=0,
                valve_hours=0,
                reason="recent_rainfall",
                eligible=False,
            )
            continue

        # This farm is a candidte so compute its weight
        deficit = 60 - data.soil_humidity_40cm_pct
        weight = deficit * data.area_ha
        candidates.append((fid, weight, data))

    if not candidates:
        return results

    # Second pass: proportional split
    total_weight = sum(w for _, w, _ in candidates)

    for fid, weight, data in candidates:
        quota = (weight / total_weight) * available_water_m3
        hours = (
            quota / (FLOW_RATE_PER_HA * data.area_ha) if data.area_ha > 0 else 0
        )
        results[fid] = AllocationResult(
            farm_id=fid,
            allocated_quota_m3=round(quota, 1),
            valve_hours=round(hours, 1),
            reason="allocated",
            eligible=True,
        )

    return results
