# Agricultural Robot Fleet Monitoring System

A real-time monitoring system for agricultural robot fleets, built on ROS2 and NebulaStream stream processing engine.

**Thesis project:** *"Design and Evaluation of a Robotic Device Integration Layer Based on ROS and Nebula Software"*
Politechnika Poznańska, TPD specialization.

---

## System Architecture

```
ROS2 bags (/robot_1, /robot_2, /robot_3)
         │
         ▼
ros2_mqtt_bridge_multi.py ──── soil_temp_simulator.py (SMT100)
         │                              │
         └──────────► Mosquitto (MQTT broker) ◄──────────┘
                              │
              ┌───────────────┼───────────────┬──────────────┐
              ▼               ▼               ▼              ▼
        NebulaStream    NebulaStream    NebulaStream  NebulaStream
        worker-1        worker-3        worker-4      worker-2
        (geofencing     (speed          (battery      (soil temp
         567 PAL)        threshold)      < 20%)        > 25°C)
              │               │               │              │
              └───────────────┴───────┬───────┴──────────────┘
                                      │
                              robot/*_alerts
                                      │
                    collision_detector.py (Python service)
                                      │
                                 Telegraf
                                      │
                                 InfluxDB
                                      │
                          ┌───────────┴───────────┐
                          ▼                       ▼
                  REST API (FastAPI)          Grafana
                  9 GET endpoints        Robot Monitoring Dashboard
```

## Alert Types

| Type | Component | Condition |
|---|---|---|
| Geofencing | NebulaStream worker-1 | Robot exits parcel 567 PAL boundary |
| Speed exceeded | NebulaStream worker-3 | Velocity > 0.10 m/s |
| Low battery | NebulaStream worker-4 | Battery level < 20% |
| Soil temperature | NebulaStream worker-2 | SMT100 sensor > 25°C |
| Collision risk | Python service | Two robots within 2m of each other |

## Technology Stack

| Layer | Technology |
|---|---|
| Robot / Environment | ROS2 Jazzy (Ubuntu 24, WSL2) |
| ROS2 → MQTT bridge | Python (`rclpy`, `paho-mqtt`) |
| Message broker | Mosquitto (Docker, port 1883) |
| Stream processing | NebulaStream (`worker:mqtt` image, 5 workers) |
| Metrics collector | Telegraf 1.30 |
| Time-series database | InfluxDB 2.7 |
| REST API | FastAPI + Uvicorn (port 8000) |
| Visualization | Grafana 10.4 (port 3000) |
| Containerization | Docker Compose |

## Data Sources

- **GPS bags** — Real field data from Montoldre, France (RTK Septentrio F9P, 10 Hz), three robots operating within parcel 567 PAL
- **Parcelles.xlsx** — 36 agricultural parcels in WKB format (MultiPolygon geometry, SRID=4326)
- **NinsarPlot_SoilTemperature_data.xlsx** — SMT100 sensor measurements at 10 cm and 20 cm depth

## Project Structure

```
magisterka/
├── api.py                      # REST API (FastAPI, 9 endpoints)
├── ros2_mqtt_bridge_multi.py   # ROS2 → MQTT bridge (N robots)
├── collision_detector.py       # Collision detection service
├── soil_temp_simulator.py      # SMT100 soil temperature simulator
├── generate_test_bags.py       # Synthetic ROS2 bag generator with ground truth
├── play_test_bags.sh           # Start all test bags simultaneously
├── perf_measure.py             # Performance measurement script
├── run_perf_tests.sh           # Automated performance test series
├── plot_perf_results.py        # Performance charts generator
├── perf_results.csv            # Performance test results
├── perf_fleet.png              # Chart: fleet axis throughput & latency
├── perf_freq.png               # Chart: frequency axis throughput & latency
├── perf_components.png         # Chart: per-component latency breakdown
└── pipeline/
    ├── docker-compose.yaml     # Full stack definition
    ├── mosquitto.conf          # MQTT broker config
    ├── telegraf.conf           # Metrics collector config
    ├── topology.yaml           # NebulaStream: geofencing query
    ├── topology_battery.yaml   # NebulaStream: battery alert query
    ├── topology_odom.yaml      # NebulaStream: speed alert query
    ├── topology_soil.yaml      # NebulaStream: soil temperature query
    └── topology_collision.yaml # NebulaStream: collision JOIN attempt (unsupported)
```

## Prerequisites

- Ubuntu 24 / WSL2
- ROS2 Jazzy
- Docker Desktop
- Python 3.12 with venv

## Running the System

### 1. Start Docker stack

```bash
cd ~/magisterka/pipeline
docker compose up -d --wait
```

### 2. Start NebulaStream queries

```bash
cd ~/magisterka/pipeline
QUERY_ID=$(docker compose exec -T nes-cli   nes-cli start) && echo "GPS:     $QUERY_ID"
QUERY_ID=$(docker compose exec -T nes-cli-2 nes-cli start) && echo "Soil:    $QUERY_ID"
QUERY_ID=$(docker compose exec -T nes-cli-3 nes-cli start) && echo "Odom:    $QUERY_ID"
QUERY_ID=$(docker compose exec -T nes-cli-4 nes-cli start) && echo "Battery: $QUERY_ID"
```

### 3. Start test bags (separate terminal)

```bash
bash ~/magisterka/play_test_bags.sh
```

### 4. Start ROS2 → MQTT bridge (separate terminal)

```bash
python3 ~/magisterka/ros2_mqtt_bridge_multi.py
```

### 5. Start collision detector (separate terminal)

```bash
python3 ~/magisterka/collision_detector.py
```

### 6. Start soil temperature simulator (separate terminal, venv)

```bash
source ~/magisterka/venv/bin/activate
python3 ~/magisterka/soil_temp_simulator.py
```

### 7. Start REST API (separate terminal, venv)

```bash
source ~/magisterka/venv/bin/activate
python3 ~/magisterka/api.py
```

### 8. Access interfaces

- **Grafana dashboard:** http://localhost:3000 (admin/admin) → Robot Monitoring
- **REST API docs:** http://localhost:8000/docs
- **API stats:** http://localhost:8000/api/stats?window=2m

### Shutdown

```bash
pkill -f ros2_mqtt_bridge_multi.py
pkill -f collision_detector.py
pkill -f soil_temp_simulator.py
pkill -f api.py
pkill -f "ros2 bag play"
cd ~/magisterka/pipeline && docker compose down
```

## Synthetic Test Bags

Generate reproducible test scenarios with known ground truth:

```bash
python3 ~/magisterka/generate_test_bags.py ~/magisterka/data/robots/
```

Three 120-second bags are generated:
- **robot_1_test** — exits geofence boundary, speed exceeded, low battery
- **robot_2_test** — approaches robot 3 (collision), speed exceeded, low battery
- **robot_3_test** — approaches robot 2 (collision), speed exceeded, low battery

Each bag generates a `*_ground_truth.json` file with exact event timestamps for evaluation.

## Performance Evaluation

Run the full test series (fleet axis + frequency axis):

```bash
bash ~/magisterka/run_perf_tests.sh
```

Generate charts from results:

```bash
source ~/magisterka/venv/bin/activate
python3 ~/magisterka/plot_perf_results.py
```

### Key Findings

| Metric | Result |
|---|---|
| Max throughput (50 robots, 10 Hz) | ~480 msg/s published, ~480 alerts/s |
| Broker MQTT latency | 1.8 – 11 ms (scales with fleet size) |
| NebulaStream latency | ~45 – 75 ms (stable, independent of fleet/frequency) |
| End-to-end latency (pub→alert) | ~50 – 85 ms |
| NebulaStream JOIN support | Not supported in `worker:mqtt` version |

## Known Limitations

- **NebulaStream JOIN** — The `worker:mqtt` version does not support JOIN between two streams. Collision detection is implemented as a separate Python service (`collision_detector.py`).
- **NebulaStream `nes-cli start`** — Adds a new query without stopping the previous one. Always restart the worker before starting a new query to avoid duplicate processing.
- **Geofencing** — Implemented as bounding box (not point-in-polygon) due to NebulaStream SQL limitations.
- **Measurement accuracy** — Latency measurements at high frequencies (>50 Hz) are approximate due to the inability to inject message identifiers through NebulaStream.

## Grafana Dashboard

The **Robot Monitoring** dashboard includes 5 panels:
1. **GPS Map** — Three robot trajectories in different colors (parcel 567 PAL, Montoldre)
2. **Robot Speed** — Live odometry per robot
3. **Soil Temperature** — Two lines (10 cm and 20 cm depth)
4. **Battery Level** — Live battery status with alert threshold
5. **Alert Table** — All alert types consolidated: geofencing, speed, battery, collision risk
