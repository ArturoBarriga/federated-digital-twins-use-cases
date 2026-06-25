
# Shared data models used by the central manager and farm adapters.
# Adapters translate each DT backend representation into these normalized models.


from pydantic import BaseModel
from datetime import datetime

class NormalizedFarmData(BaseModel):
    farm_id: str
    timestamp: datetime
    soil_humidity_40cm_pct: float
    rainfall_mm: float
    area_ha: float
    crop_type: str
    temperature_c: float
    wind_direction: float                    
    wind_speed: float                           

class ActuatorCommand(BaseModel):
    farm_id: str
    command: str                              
    quota_m3: float
    valve_open_hours: float
    valid_from: datetime
    valid_until: datetime

class AllocationResult(BaseModel):
    farm_id: str
    allocated_quota_m3: float
    valve_hours: float
    reason: str                   
    eligible: bool

class FarmStatus(BaseModel):
    farm_id: str
    last_telemetry: NormalizedFarmData | None = None
    last_allocation: AllocationResult | None = None
    current_quota_m3: float = 0.0
