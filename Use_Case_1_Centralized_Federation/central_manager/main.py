
# FastAPI application that acts as the federation's central water-allocation manager

import os
import sys
import time
import threading
import requests
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.models import NormalizedFarmData, AllocationResult, ActuatorCommand, FarmStatus
from central_manager.allocator import compute_allocation

CENTRAL_PORT = int(os.getenv("CENTRAL_PORT", "8000"))
ALLOCATION_INTERVAL_HOURS = float(os.getenv("ALLOCATION_INTERVAL_HOURS", "72"))
AVAILABLE_WATER_M3 = float(os.getenv("AVAILABLE_WATER_M3", "10000"))

# Adapter URLs
ADAPTER_URLS: dict[str, str] = {
    "farm1_ditto": os.getenv("ADAPTER_FARM1_URL", "http://farm1-adapter:8001"),
    "farm2_aas": os.getenv("ADAPTER_FARM2_URL", "http://farm2-adapter:8001"),
    "farm3_ngsild": os.getenv("ADAPTER_FARM3_URL", "http://farm3-adapter:8001"),
}

farms_data: dict[str, NormalizedFarmData] = {}      
last_allocations: dict[str, AllocationResult] = {} 
last_allocation_time: datetime | None = None


"""
Execute one full allocation cycle:
1. Fetch telemetry on-demand from each farm adapter via REST.
2. Run the allocation algorithm on the fresh data.
3. Push irrigation commands synchronously to each eligible adapter.
"""
def run_allocation():

    global last_allocations, last_allocation_time
    now = datetime.now(timezone.utc)
    print(f"[CentralManager] Running allocation at {now.isoformat()}")

    # 1. Fetch telemetry on-demand from each adapter
    for farm_id, adapter_url in ADAPTER_URLS.items():
        try:
            r = requests.get(f"{adapter_url}/telemetry", timeout=10)
            if r.status_code == 200:
                data = NormalizedFarmData(**r.json())
                farms_data[data.farm_id] = data
                print(f"[CentralManager] Fetched telemetry from {farm_id}")
            else:
                print(f"[CentralManager] {farm_id} returned {r.status_code}")
        except Exception as e:
            print(f"[CentralManager] Failed to fetch telemetry from {farm_id}: {e}")

    print(f"[CentralManager] Farms reporting: {list(farms_data.keys())}")

    # 2. Run allocation
    results = compute_allocation(farms_data, AVAILABLE_WATER_M3)
    last_allocations = results
    last_allocation_time = now

    for fid, result in results.items():
        print(
            f"  {fid}: eligible={result.eligible}, "
            f"quota={result.allocated_quota_m3}m3, reason={result.reason}"
        )
        if result.eligible and result.allocated_quota_m3 > 0:
            cmd = ActuatorCommand(
                farm_id=fid,
                command="irrigate",
                quota_m3=result.allocated_quota_m3,
                valve_open_hours=result.valve_hours,
                valid_from=now,
                valid_until=datetime.fromtimestamp(
                    now.timestamp() + ALLOCATION_INTERVAL_HOURS * 3600,
                    tz=timezone.utc,
                ),
            )
            # 3. Push command synchronously to the adapter
            adapter_url = ADAPTER_URLS.get(fid)
            if adapter_url:
                try:
                    r2 = requests.post(
                        f"{adapter_url}/command",
                        json=cmd.model_dump(mode="json"),
                        timeout=10,
                    )
                    r2.raise_for_status()
                    print(f"[CentralManager] Command sent to {fid}: {cmd.quota_m3}m3")
                except Exception as e:
                    print(f"[CentralManager] Failed to send command to {fid}: {e}")

    print(f"[CentralManager] Allocation complete.")


def allocation_loop():
    while True:
        run_allocation()
        time.sleep(ALLOCATION_INTERVAL_HOURS * 3600)


# FastAPI lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    t = threading.Thread(target=allocation_loop, daemon=True)
    t.start()
    print(f"[CentralManager] Allocation every {ALLOCATION_INTERVAL_HOURS}h")
    yield


app = FastAPI(title="Central Federation Manager - Water Allocation", lifespan=lifespan)


# REST endpoints

@app.get("/api/health")
def health():
    """Liveness check — shows how many farms are reporting."""
    return {
        "status": "ok",
        "farms_reporting": len(farms_data),
        "last_allocation": last_allocation_time.isoformat()
        if last_allocation_time
        else None,
    }


@app.get("/api/farm-data")
def get_all_farm_data():
    """Return the latest telemetry for every farm (last fetched on allocation)."""
    return {fid: d.model_dump(mode="json") for fid, d in farms_data.items()}


@app.get("/api/farm-data/{farm_id}")
def get_farm_data(farm_id: str):
    """Return the latest telemetry for a specific farm."""
    if farm_id not in farms_data:
        raise HTTPException(404, "Farm not found")
    return farms_data[farm_id].model_dump(mode="json")

#Manually trigger an allocation cycle (outside the normal schedule)
@app.post("/api/allocation/trigger")
def trigger_allocation():
    run_allocation()
    return {
        "status": "allocated",
        "results": {
            fid: r.model_dump(mode="json") for fid, r in last_allocations.items()
        },
    }


@app.get("/api/allocation/latest")
def get_latest_allocation():
    return {
        "timestamp": last_allocation_time.isoformat()
        if last_allocation_time
        else None,
        "results": {
            fid: r.model_dump(mode="json") for fid, r in last_allocations.items()
        },
    }


@app.get("/api/farms/status")
def get_all_farm_status():
    statuses = {}
    for fid, data in farms_data.items():
        alloc = last_allocations.get(fid)
        statuses[fid] = FarmStatus(
            farm_id=fid,
            last_telemetry=data,
            last_allocation=alloc,
        ).model_dump(mode="json")
    return statuses


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=CENTRAL_PORT)
