# ros2-nebulastream-robot-monitoring

A real-time monitoring system for agricultural robot fleets, built on ROS2 and NebulaStream stream processing engine.

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
| Robot / Environment | ROS2 Jazzy (Ubuntu 24 / WSL2) |
| ROS2 → MQTT bridge | Python (`rclpy`, `paho-mqtt`) |
| Message broker | Mosquitto (Docker, port 1883) |
| Stream processing | NebulaStream (`worker:mqtt` image, 4 workers) |
| Metrics collector | Telegraf 1.30 |
| Time-series database | InfluxDB 2.7 |
| REST API | FastAPI + Uvicorn (port 8000) |
| Visualization | Grafana 10.4 (port 3000) |
| Containerization | Docker Compose |

## Data Sources

- **GPS bags** — Real field data from Montoldre, France (RTK Septentrio F9P, 10 Hz), three robots operating within parcel 567 PAL
- **Parcelles.xlsx** — Agricultural parcels in WKB format (MultiPolygon geometry, SRID=4326)
- **NinsarPlot_SoilTemperature_data.xlsx** — SMT100 sensor measurements at 10 cm and 20 cm depth

## Repository Structure

```
├── api.py                          # REST API (FastAPI, 9 endpoints)
├── ros2_mqtt_bridge_multi.py       # ROS2 → MQTT bridge (N robots, --robots flag)
├── collision_detector.py           # Collision detection service
├── soil_temp_simulator.py          # SMT100 soil temperature simulator
├── generate_test_bags.py           # Synthetic ROS2 bag generator with ground truth
├── play_test_bags.sh               # Start all test bags simultaneously
│
├── perf_measure.py                 # Performance measurement script (per-component latency)
├── run_perf_tests.sh               # Automated single-run performance test series
├── run_perf_tests_repeated.sh      # Repeated performance tests (12 runs per point)
├── analyze_repeated.py             # Aggregation: removes 2 outliers, computes mean ± std
├── plot_perf_results.py            # Charts from single-run results
│
├── perf_results.csv                # Single-run performance results
├── perf_results_repeated.csv       # Raw repeated results (12 runs × 13 combinations)
├── perf_results_aggregated.csv     # Aggregated results (mean ± std, 10 runs)
│
├── perf_fleet.png                  # Chart: fleet axis (single run)
├── perf_freq.png                   # Chart: frequency axis (single run)
├── perf_components.png             # Chart: per-component latency (single run)
├── perf_fleet_final.png            # Chart: fleet axis (aggregated, with error bars)
├── perf_freq_final.png             # Chart: frequency axis (aggregated, with error bars)
├── perf_components_final.png       # Chart: component latency (aggregated, with error bars)
│
└── pipeline/
    ├── docker-compose.yaml         # Full stack definition
    ├── mosquitto.conf              # MQTT broker config
    ├── telegraf.conf               # Metrics collector config
    ├── topology.yaml               # NebulaStream: geofencing query
    ├── topology_battery.yaml       # NebulaStream: battery alert query
    ├── topology_odom.yaml          # NebulaStream: speed alert query
    ├── topology_soil.yaml          # NebulaStream: soil temperature query
    └── topology_collision.yaml     # NebulaStream: collision JOIN attempt (unsupported)
```

## Prerequisites

- Ubuntu 24 / WSL2
- ROS2 Jazzy
- Docker Desktop
- Python 3.12+

## Installation

Clone the repository and set up the Python virtual environment:

```bash
git clone https://github.com/Rossi2882/ros2-nebulastream-robot-monitoring.git
cd ros2-nebulastream-robot-monitoring
python3 -m venv venv
source venv/bin/activate
pip install fastapi uvicorn paho-mqtt influxdb-client pandas openpyxl matplotlib numpy
```

## Running the System

### 1. Start Docker stack

```bash
cd pipeline
docker compose up -d --wait
```

### 2. Start NebulaStream queries

```bash
cd pipeline
QUERY_ID=$(docker compose exec -T nes-cli   nes-cli start) && echo "GPS:     $QUERY_ID"
QUERY_ID=$(docker compose exec -T nes-cli-2 nes-cli start) && echo "Soil:    $QUERY_ID"
QUERY_ID=$(docker compose exec -T nes-cli-3 nes-cli start) && echo "Odom:    $QUERY_ID"
QUERY_ID=$(docker compose exec -T nes-cli-4 nes-cli start) && echo "Battery: $QUERY_ID"
```

### 3. Start test bags (separate terminal)

```bash
bash play_test_bags.sh
```

### 4. Start ROS2 → MQTT bridge (separate terminal)

```bash
python3 ros2_mqtt_bridge_multi.py
# For a custom fleet size:
python3 ros2_mqtt_bridge_multi.py --robots 5
```

### 5. Start collision detector (separate terminal)

```bash
python3 collision_detector.py
```

### 6. Start soil temperature simulator (separate terminal)

```bash
source venv/bin/activate
python3 soil_temp_simulator.py
```

### 7. Start REST API (separate terminal)

```bash
source venv/bin/activate
python3 api.py
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
cd pipeline && docker compose down
```

## Synthetic Test Bags

Generate reproducible test scenarios with known ground truth:

```bash
python3 generate_test_bags.py <output_directory>
```

Three 120-second bags are generated:
- **robot_1_test** — exits geofence boundary, speed exceeded, low battery
- **robot_2_test** — approaches robot 3 (collision risk), speed exceeded, low battery
- **robot_3_test** — approaches robot 2 (collision risk), speed exceeded, low battery

Each bag generates a `*_ground_truth.json` file with exact event timestamps.

## Performance Evaluation

### Single-run test series

```bash
bash run_perf_tests.sh
source venv/bin/activate
python3 plot_perf_results.py
```

### Repeated tests (12 runs per point, 2 outliers removed)

```bash
bash run_perf_tests_repeated.sh
source venv/bin/activate
python3 analyze_repeated.py
```

`analyze_repeated.py` produces:
- `perf_results_aggregated.csv` — mean ± std for each parameter combination
- `perf_fleet_final.png`, `perf_freq_final.png`, `perf_components_final.png` — charts with error bars

### Key Findings

| Metric | Result |
|---|---|
| Max throughput (50 robots, 10 Hz) | ~480 msg/s published, ~480 alerts/s |
| Broker MQTT latency | 1.8 – 11 ms (scales monotonically with fleet size) |
| NebulaStream latency | ~45 – 75 ms (stable, independent of fleet size and frequency) |
| End-to-end latency (pub→alert) | ~50 – 85 ms |

## Known Limitations

- **NebulaStream JOIN** — The `worker:mqtt` image does not support JOIN between two streams. Collision detection is therefore implemented as a separate Python service.
- **NebulaStream query stacking** — `nes-cli start` adds a new query without stopping the previous one. Always restart the worker before starting a new query to avoid duplicate processing.
- **Geofencing** — Implemented as bounding box rather than point-in-polygon due to NebulaStream SQL limitations.
- **Latency measurement accuracy** — Measurements at high frequencies (>50 Hz) are approximate due to the inability to inject message identifiers through NebulaStream.

## Grafana Dashboard

The **Robot Monitoring** dashboard includes 5 panels:
1. **GPS Map** — Three robot trajectories (parcel 567 PAL, Montoldre, France)
2. **Robot Speed** — Live odometry per robot
3. **Soil Temperature** — Two depth levels (10 cm and 20 cm)
4. **Battery Level** — Live battery status with alert threshold
5. **Alert Table** — All alert types: geofencing, speed, battery, soil temperature, collision risk

## License

Academic project — Poznan University of Technology, 2026
