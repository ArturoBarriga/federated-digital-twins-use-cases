# Use Case 3: Peer-to-peer Federation for Anomaly Detection

For a video illustration of the implementation and execution of Use Case 3, refer to minute 06:22 of the following video: https://youtu.be/ZBd1h645gfw

## Overview
A set of ten Digital Twins (DTs) is deployed across trees belonging to the same orchard, measuring leaf-turgor pressure (a water stress indicator). Each tree DT periodically sends heartbeat messages to all other DTs to announce its presence. For anomaly detection, each DT reads sensor data directly from every peer's AAS server, computes the population mean and standard deviation, and compares its own reading against the group. 

If a tree's reading deviates significantly from its peers, beyond a configurable threshold, the DT raises a local anomaly flag, which can indicate either a diseased or stressed tree or a malfunctioning sensor. Each DT makes this decision independently, without any central mediator. A DT can leave the network at any time simply by stopping its heartbeats. The remaining peers detect the absence automatically and exclude it from subsequent analyses. A returning twin is reintegrated without negotiation when it resumes sending heartbeats.

## Federation Strategy

Detecting anomalies such as diseased trees or faulty sensors requires comparing the measurements of one tree against those of its neighbours under the same environmental conditions. This task does not require a central coordinator. Each tree DT can independently query its peers, compare values, and flag anomalies. Peer-to-peer federation is the appropriate choice since no DT has authority over another, and no global state is required.

## Architecture

The architecture is flat and symmetric:
- Tree DTs (peers): Each DT monitors its own tree, maintains a local registry of known peers populated from a static configuration, tracks peer liveness via periodic heartbeat messages, reads sensor data directly from each peer's AAS server, and runs a local anomaly detection algorithm.
- Peer Liveness Tracking: A heartbeat-based mechanism lets each DT know which peers are currently active. If a peer stops sending heartbeats, it is automatically removed from the registry after a configurable timeout. Rejoining is automatic when heartbeats resume.
- No central component: All coordination, comparison, and decision logic resides within each DT. There is no federation coordinator.

<img width="322" height="295" alt="image" src="https://github.com/user-attachments/assets/e7184f5c-fff3-4a0a-9e4b-f5853c6ce8cb" />

## Repository Structure

```text
Use_Case_3_Peer_to_Peer_Federation/
├── config.yaml   
├── docker-compose.yml
└── tree_dt/
    ├── dt_logic/
    │   ├── Dockerfile
    │   ├── app.py
    │   └── requirements.txt
    ├── init/  
    │   ├── Dockerfile
    │   └── init.sh
    └── simulator/
        ├── Dockerfile
        ├── simulator_service.py
        └── requirements.txt
```

## Requirements

Docker Engine with Compose v2

## How to Run

From the root of the repository, enter the folder of this use case:

```bash
cd Use_Case_3_Peer_to_Peer_Federation
```

Build and start all containers:

```bash
docker compose build
docker compose up -d
```

This builds the Docker images for the simulators and logic services, and then starts all the required containers.

## How to Check That the Containers Are Running

To inspect the running containers, execute:

```bash
docker ps
```

This use case starts **40 services** in total. The main long-running containers are:

```text
tree1_aas   tree1_simulator   tree1_logic
tree2_aas   tree2_simulator   tree2_logic
tree3_aas   tree3_simulator   tree3_logic
tree4_aas   tree4_simulator   tree4_logic
tree5_aas   tree5_simulator   tree5_logic
tree6_aas   tree6_simulator   tree6_logic
tree7_aas   tree7_simulator   tree7_logic
tree8_aas   tree8_simulator   tree8_logic
tree9_aas   tree9_simulator   tree9_logic
tree10_aas  tree10_simulator  tree10_logic
```

The following initialization containers run once and then exit with status `Exited (0)` after creating the DT shell and submodel structures:

```text
tree1_init  tree2_init  tree3_init  tree4_init  tree5_init
tree6_init  tree7_init  tree8_init  tree9_init  tree10_init
```

## How to Inject an Anomaly

First, check that the simulators are periodically pushing sensor data. The simulators generate new values every minute:

```bash
docker compose logs tree3_simulator
```

The expected output should include lines showing successful `PUT` requests, usually with HTTP status `200`, together with the generated sensor values.

To trigger a simulated anomaly on tree 3, where the turgor pressure is forced to `0.05 kPa`, execute:

```bash
curl -X POST http://127.0.0.1:9003/inject_anomaly -H "Content-Type: application/json" -d "{\"turgor_pressure_kPa\":0.05}"
```

After approximately 90 seconds, corresponding to one simulator push cycle plus one logic analysis cycle, the anomaly should be detected.

Verify the anomaly status by checking the logic logs:

```bash
docker compose logs tree3_logic
```

## How to Restore Normal Behavior

To clear the anomaly override on the simulator and reset the sensor values to a random normal range, execute:

```bash
curl -X POST http://127.0.0.1:9003/clear_anomaly -H "Content-Type: application/json" -d "{}"
```

After approximately 90 seconds, the tree will resume normal readings and the anomaly flag will be cleared.

## How to Make One Tree DT Leave the Federation

To remove tree 5 from the peer network, execute:

```bash
curl -X POST http://127.0.0.1:8005/leave -H "Content-Type: application/json" -d "{}"
```

Then stop the corresponding logic container:

```bash
docker stop tree5_logic
```

The remaining peers will detect the departure after approximately 180 seconds, which corresponds to the peer timeout interval, and will exclude tree 5 from subsequent analyses.

## How to Make One Tree DT Re-join the Federation

To make tree 5 re-join the federation, restart the stopped logic container:

```bash
docker start tree5_logic
```

The container resumes sending heartbeats, and the remaining peers automatically reintegrate it into the group within one discovery cycle, approximately 30 seconds.

To verify the topology before and after the re-joining process, execute:

```bash
curl http://127.0.0.1:8001/topology
```

