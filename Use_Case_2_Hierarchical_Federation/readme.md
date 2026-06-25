# Use Case 2 - Hierarchical Federation for Precision Irrigation

For a video illustration of the implementation and execution of Use Case 2, refer to minute 03:24 of the following video: https://youtu.be/ZBd1h645gfw

## Overview

Optimizing irrigation within a single farm requires synthesizing information from several physical entities at different levels of granularity: individual plant organs (leaves, trunk), whole trees, irrigation devices (sprinklers), and the farm plot as a whole. A hierarchical Federated Digital Twins (FDT) mirrors this natural physical hierarchy, enabling progressively more abstract representations of the system state as information flows upward.

A farm owned by a single farmer is equipped with Digital Twins (DTs) at multiple levels. Leaf and trunk DTs measure water stress physiological indicators. A Tree DT aggregates these lower-level measurements and applies a machine learning model to estimate the tree's water stress index. A Sprinkler DT monitors and controls irrigation actuators. At the top, an Orchard DT periodically queries the water stress of the tree and, if water stress exceeds a threshold, issues an irrigation command to the relevant sprinkler.

## Federation Strategy

The hierarchical structure directly reflects the physical composition of the orchard: organs compose trees, trees compose the plot. This compositional structure makes hierarchical federation the natural choice, as it enables modular encapsulation, the Plot DT does not need to know about leaf-level data, only about tree-level stress indices. 

## Architecture

The hierarchy has three levels:
- Level 0: Leaf DT (measures leaf temperature, leaf-turgor pressure, stomatal conductance, and humidity) and Trunk DT (measures diameter variations and sap flow), all these variables are key indicators of crop water stress.
- Level 1: Tree DT: When requested, it retrieves and aggregates data from the Leaf and Trunk DTs. The aggregated data is preprocessed through a REST microservice and then passed to an ML model, also exposed as a REST microservice, to compute a water stress index. The Tree DT therefore acts both as a consumer, by querying lower-level DTs, and as a producer, by reporting the computed water stress index to the plot-level DT.
The Sprinkler DT also belongs to Level 1: Monitors water flow and pressure; receives irrigation commands from the Plot DT.
- Level 2. Plot DT: Orchestrates the federation. It periodically queries Tree DTs for stress index and triggers irrigation commands to Sprinkler DTs when needed.

<img width="556" height="329" alt="image" src="https://github.com/user-attachments/assets/e4523bc6-2853-4113-a9de-778b3dc95a4c" />

## Repository Structure

```text
Use_Case_2_Hierarchical_Federation/
├── docker-compose.yml
└── digital_twins/
    ├── __init__.py
    ├── requirements.txt
    ├── trunk_dt/
    │   ├── init/
    │   │   ├── Dockerfile
    │   │   └── init.sh
    │   └── simulator/
    │       ├── Dockerfile
    │       ├── requirements.txt
    │       └── simulator_service.py
    ├── leaf_dt/
    │   ├── init/
    │   │   ├── Dockerfile
    │   │   └── init.sh
    │   └── simulator/
    │       ├── Dockerfile
    │       ├── requirements.txt
    │       └── simulator_service.py
    ├── tree_dt/
    │   ├── init/
    │   │   ├── Dockerfile
    │   │   └── init.sh
    │   ├── service/
    │   │   ├── Dockerfile
    │   │   └── service.py
    │   ├── data_preprocessor_service/
    │   │   ├── dockerfile
    │   │   └── preprocessor_service.py
    │   └── water_stress_identification_mlmodel/
    │       ├── dockerfile
    │       ├── model_service.py
    │       └── rf-model.pkl
    ├── sprinkler_dt/
    │   ├── init/
    │   │   ├── Dockerfile
    │   │   └── init.sh
    │   └── service/
    │       ├── Dockerfile
    │       └── service.py
    └── farm_dt/
        ├── init/
        │   ├── Dockerfile
        │   └── init.sh
        └── service/
            ├── Dockerfile
            └── service.py
```

## Requirements

Docker Engine with Compose v2

## How to Run

From the root of the repository, enter the folder of this use case:

```bash
cd Use_Case_2_Hierarchical_Federation
```

Build and start all containers:

```bash
docker compose build
docker compose up -d
```

This command builds the Docker images for the simulators, logic services, preprocessor, and ML model, and then starts all the required containers.

## How to Check That the Containers Are Running

To inspect the running containers, execute:

```bash
docker ps
```

The use case starts 17 services in total. The main long-running containers are:

```text
trunk-aas
leaf-aas
tree-aas
sprinkler-aas
farm-aas
trunk-simulator
leaf-simulator
tree-logic
sprinkler-logic
farm-logic
tree-data-preprocessor
tree-ml-model
```

The following initialization containers run once and then exit with status `Exited (0)` after creating the digital twin shell and submodel structures:

```text
trunk-init
leaf-init
tree-init
sprinkler-init
farm-init
```

## How to Trigger a Tree Water Stress Assessment Manually

First, check that the simulators are periodically pushing sensor data. The simulators generate new values every minute:

```bash
docker logs trunk-simulator --tail 5
docker logs leaf-simulator --tail 5
```

The expected output should include lines showing successful `PUT` requests, usually with HTTP status `204`, together with the generated sensor values.

To trigger a complete farm assessment manually, execute:

```bash
curl -X POST http://localhost:5005/trigger
```

If the assessment is not triggered manually, the farm logic service runs it automatically once per day at `08:00 UTC`. This scheduled execution time can be configured through the `SCHEDULED_HOUR` environment variable.

The previous command executes the complete hierarchical pipeline: the Farm DT logic requests the Tree DT assessment, the Tree DT logic retrieves data from the Leaf and Trunk DTs, the data is preprocessed, the ML model computes the water stress index, and the resulting assessment is used by the Farm DT to decide whether irrigation should be activated.

## How to Inspect the Pipeline

The different stages of the pipeline can be inspected through the container logs:

```bash
docker logs tree-data-preprocessor --tail 10
docker logs tree-ml-model --tail 5
docker logs tree-logic --tail 20
docker logs farm-logic --tail 5
```

These logs show the main execution steps:

- `tree-data-preprocessor`: raw and Min-Max normalized feature values.
- `tree-ml-model`: predicted water stress label.
- `tree-logic`: complete assessment pipeline, including data retrieval, preprocessing, classification, and persistence.
- `farm-logic`: final assessment result and irrigation decision.


