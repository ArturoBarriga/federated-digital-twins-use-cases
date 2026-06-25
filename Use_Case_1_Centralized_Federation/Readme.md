# Use Case 1: Centralized Federation for Water Allocation

For a video illustration of the implementation and execution of Use Case 1, refer to minute 00:06 of the following video: https://youtu.be/ZBd1h645gfw

## Overview

A regional water authority manages a shared water source serving three farms, each owned by a different organization. Every farm has a digital twin that monitors soil moisture, local weather conditions, and current irrigation usage. The farms use different DT platforms: Eclipse Ditto (Farm 1), Eclipse BaSyx AAS (Farm 2), and an NGSI-LD context broker (Farm 3),  exposing different data models and field names.

A central manager requests all farm digital twins through technology-specific adapters. Each adapter reads the farm's native twin, maps platform-specific schema and field names into a canonical schema, and forwards the result to the central manager. The central manager runs a proportional deficit-weighting algorithm that computes water allocation quotas for each farm based on its soil moisture deficit, field area, and available water. Eligible farms receive their quota as a command; the adapter writes it into the farm's native actuator feature. Commands are authoritative, farms cannot override the central decision.

## Federation Strategy

A centralized architecture is appropriate here because the core function, optimizing shared resource allocation, requires a global view that no individual farm DT possesses. The central authority also reflects the real-world governance model of a water authority. High heterogeneity and administrative distribution are handled naturally by the adapter layer, while low autonomy is a deliberate trade-off to enforce fair and coordinated quota allocation

## Architecture

The architecture is organized into four layers: the Farm Physical Layer (simulated), the Farm Digital Twin Layer, the Integration / Adapter Layer, and the Central Manager Layer.
- The Farm Physical Layer consists of simulators that replicate the evolution of soil moisture and weather conditions in the farms.
- The Farm Digital Twin Layer contains three independent Digital Twins, each implemented using a different platform.
- The Integration / Adapter Layer comprises three adapters that are executed on demand by the central manager via HTTP. When requested, they read the corresponding farm twin, normalize the data into a shared canonical format, and send it to the central manager.
- The Central Manager Layer is a FastAPI application that periodically, every 72 hours, requests normalized telemetry, runs a water-allocation algorithm, and enforces the resulting water quotas through actuator commands.

<img width="311" height="341" alt="image" src="https://github.com/user-attachments/assets/5b481548-d6a2-4fbc-92f4-90cd39df2deb" />


## Repository Structure

```text
Use_Case_1_Centralized_Federation/
├── docker-compose.yml
├── central_manager/
│   ├── Dockerfile
│   ├── main.py
│   ├── allocator.py
│   └── __init__.py
├── shared/
│   └── models.py
├── farm_base/
│   └── farm_simulator.py     
└── farms/
    ├── farm1_ditto/            
    │   ├── adapter/adapter.py, Dockerfile   
    │   ├── init/init.sh, Dockerfile                     
    │   └── farm_simulator/farm_simulator.py, Dockerfile  
    ├── farm2_aas/                                 
    │   ├── adapter/adapter.py, Dockerfile  
    │   ├── init/init.sh, Dockerfile                     
    │   └── farm_simulator/farm_simulator.py, Dockerfile  
    └── farm3_ngsild/      
        ├── adapter/adapter.py, Dockerfile    
        ├── init/init.sh, Dockerfile 
        └── farm_simulator/farm_simulator.py, Dockerfile
```
        
## Requirements

Docker with Compose v2

## How to Run

From the root of the repository, enter the folder of this use case:

```bash
cd Use_Case_1_Centralized_Federation
```

Build and start the containers:

```bash
docker compose build
docker compose up -d
```

## How to Check That the Containers Are Running

To inspect the running containers, execute:

```bash
docker ps
```

The use case starts 18 services in total. Most containers should remain running, while the three initialization containers are one-shot services that create the required digital twin structures and then finish.

The main long-running containers are:

```text
central-manager
farm1-mongodb
farm1-ditto-policies
farm1-ditto-things
farm1-ditto-thingsearch
farm1-ditto-gateway
farm1-simulator
farm1-adapter
farm2-aas
farm2-simulator
farm2-adapter
farm3-mongodb
farm3-ngsild-server
farm3-simulator
farm3-adapter
```

The following initialization containers may appear as exited after completing their task:

```text
farm1-init
farm2-init
farm3-init
```

Wait around 60 seconds after startup to allow the initialization containers to create the digital twins and the simulators to start pushing telemetry. During startup, some simulators may temporarily receive `404` responses if they push data before the corresponding twin has been created.

## How to Trigger the Water Allocation Process

The central manager exposes an endpoint to trigger the allocation process manually:

```bash
curl -X POST http://localhost:8000/api/allocation/trigger
```

The central manager also runs the allocation process automatically every 72 hours. This interval can be configured through the `ALLOCATION_INTERVAL_HOURS` environment variable. The POST endpoint forces an immediate allocation cycle.

## Expected Result

The endpoint should return a JSON response with one allocation result per farm:

```json
{
  "status": "allocated",
  "results": {
    "farm1_ditto": {
      "farm_id": "farm1_ditto",
      "allocated_quota_m3": 5027.6,
      "valve_hours": 10.1,
      "reason": "allocated",
      "eligible": true
    },
    "farm2_aas": {
      "farm_id": "farm2_aas",
      "allocated_quota_m3": 3955.8,
      "valve_hours": 13.2,
      "reason": "allocated",
      "eligible": true
    },
    "farm3_ngsild": {
      "farm_id": "farm3_ngsild",
      "allocated_quota_m3": 1016.6,
      "valve_hours": 5.1,
      "reason": "allocated",
      "eligible": true
    }
  }
}
```

The allocation decision is sent from the central manager to each farm's digital twin through its actuator interface. The corresponding simulator then reads the irrigation command from the digital twin and adapts its behavior accordingly. In particular, when an irrigation actuator request is received, the simulator models the effect of irrigation by increasing the simulated soil humidity during the following hours.

To verify that the commands reached the digital twins and were processed by the simulators, inspect the simulator logs:

```bash
docker compose logs farm1-simulator
docker compose logs farm2-simulator
docker compose logs farm3-simulator
```

## Allocation Logic Example

In a typical execution, all three farms are eligible because the simulated soil moisture starts below the 60% threshold and random rainfall remains close to zero. The allocation process follows three steps:

1. **Exclusion**: farms with soil moisture greater than or equal to 60%, or rainfall above 10 mm, are excluded from the allocation process.

2. **Weight calculation**: remaining farms receive a deficit weight based on their soil-moisture deficit and area:

   ```text
   (60 - soil_moisture_pct) × area_ha
   ```

   Larger farms with drier soil will therefore receive a higher weight.


3. **Proportional split**: each eligible farm receives a proportional share of the available water (i.e., 10,000m³):

   ```text
   (farm_weight / total_weight) × 10,000 m³
   ```

For example, suppose the simulators report the following values when the allocation process is triggered:

| Farm           |  Area | Soil moisture | Deficit |         Weight |
| -------------- | ----: | ------------: | ------: | -------------: |
| `farm1_ditto`  | 50 ha |           32% |      28 | 28 × 50 = 1400 |
| `farm2_aas`    | 30 ha |           27% |      33 |  33 × 30 = 990 |
| `farm3_ngsild` | 20 ha |           47% |      13 |  13 × 20 = 260 |

The total weight is:

```text
1400 + 990 + 260 = 2650
```

Each farm quota is then computed as:

```text
farm_quota = (farm_weight / 2650) × 10,000
```

This produces the following allocation:

| Farm           |                            Quota |       
| -------------- | -------------------------------: |
| `farm1_ditto`  | (1400 / 2650) × 10,000 = 5283 m³ |
| `farm2_aas`    |  (990 / 2650) × 10,000 = 3736 m³ |
| `farm3_ngsild` |   (260 / 2650) × 10,000 = 981 m³ |


Exact values may vary between executions because the simulators initialize soil moisture and weather conditions randomly.






