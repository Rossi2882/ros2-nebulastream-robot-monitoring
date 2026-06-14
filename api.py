"""
REST API for agricultural robot fleet monitoring system.
Usage: python3 api.py
Dependencies: pip install fastapi uvicorn influxdb-client

InfluxDB data structure (based on telegraf.conf + topology.yaml):
  measurement : mqtt_consumer
  tag         : robot_id (values: "1", "2", "3" — UINT64 from NebulaStream as string)
  fields      : latitude (float), longitude (float)
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from influxdb_client import InfluxDBClient
from influxdb_client.client.exceptions import InfluxDBError
from datetime import datetime, timezone
import uvicorn

# ── Configuration ─────────────────────────────────────────────────────────────
INFLUX_URL    = "http://localhost:8086"
INFLUX_TOKEN  = "mytoken123"
INFLUX_ORG    = "robotics"
INFLUX_BUCKET = "geofencing"
MEASUREMENT   = "mqtt_consumer"

client    = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
query_api = client.query_api()

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Agricultural Robot Fleet Monitoring API",
    description=(
        "REST API for real-time monitoring of an agricultural robot fleet.\n\n"
        "**Pipeline:** ROS2 bags → MQTT bridge → NebulaStream (stream processing) → Telegraf → InfluxDB\n\n"
        "**Alert types:**\n"
        "- Geofencing — robot exits parcel 567 PAL boundary (bounding box)\n"
        "- Speed — robot exceeds velocity threshold (0.10 m/s)\n"
        "- Battery — battery level drops below threshold (20%)\n"
        "- Soil temperature — SMT100 sensor exceeds 25°C\n"
        "- Collision risk — two robots within 2m of each other\n\n"
        "**Data source:** Real GPS field data from Montoldre, France (RTK Septentrio, 10 Hz)"
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def run_flux(flux: str) -> list[dict]:
    try:
        tables = query_api.query(flux)
    except InfluxDBError as e:
        raise HTTPException(status_code=502, detail=f"InfluxDB error: {e}")
    records = []
    for table in tables:
        for record in table.records:
            records.append(record.values)
    return records


@app.get("/", tags=["meta"])
def root():
    return {
        "api": "Agricultural Robot Fleet Monitoring API",
        "version": "1.0.0",
        "geofence_condition": "outside parcel 567 PAL (bbox)",
        "robots": ["1", "2", "3"],
        "docs": "http://localhost:8000/docs",
        "endpoints": [
            "GET /api/robots?window=1h",
            "GET /api/robots/{robot_id}/position?window=10m&limit=50",
            "GET /api/alerts?window=10m&limit=100",
            "GET /api/alerts/{robot_id}?window=1h&limit=200",
            "GET /api/stats?window=1h",
            "GET /api/soil?window=10m",
            "GET /api/odom?window=10m",
            "GET /api/battery?window=10m",
            "GET /api/collisions?window=10m",
        ],
    }


@app.get("/api/robots", tags=["robots"])
def get_robots(window: str = Query("1h", description="Time window, e.g. 1h, 30m, 24h")):
    flux_count = f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -{window})
  |> filter(fn: (r) => r._measurement == "{MEASUREMENT}")
  |> filter(fn: (r) => r._field == "latitude")
  |> group(columns: ["robot_id"])
  |> count()
  |> rename(columns: {{_value: "alert_count"}})
"""
    flux_last = f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -{window})
  |> filter(fn: (r) => r._measurement == "{MEASUREMENT}")
  |> filter(fn: (r) => r._field == "latitude")
  |> group(columns: ["robot_id"])
  |> last()
"""
    counts    = {r.get("robot_id"): r.get("alert_count", 0) for r in run_flux(flux_count)}
    last_seen = {r.get("robot_id"): r.get("_time")          for r in run_flux(flux_last)}
    robot_ids = set(counts) | set(last_seen)

    if not robot_ids:
        return {"robots": [], "window": window, "message": f"No alerts in -{window}"}

    robots = sorted([
        {
            "robot_id":    rid,
            "alert_count": counts.get(rid, 0),
            "last_alert":  last_seen.get(rid),
        }
        for rid in robot_ids
    ], key=lambda x: x["robot_id"])

    return {"window": window, "count": len(robots), "robots": robots}


@app.get("/api/robots/{robot_id}/position", tags=["robots"])
def get_robot_position(
    robot_id: str,
    window: str = Query("10m"),
    limit:  int = Query(50, ge=1, le=500),
):
    flux = f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -{window})
  |> filter(fn: (r) => r._measurement == "{MEASUREMENT}")
  |> filter(fn: (r) => r.robot_id == "{robot_id}")
  |> filter(fn: (r) => r._field == "latitude" or r._field == "longitude")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: {limit})
"""
    records = run_flux(flux)
    positions = [
        {"timestamp": r.get("_time"), "lat": r.get("latitude"), "lon": r.get("longitude")}
        for r in records
        if r.get("latitude") is not None and r.get("longitude") is not None
    ]
    if not positions:
        raise HTTPException(status_code=404, detail=f"No alerts for robot '{robot_id}' in -{window}.")
    return {"robot_id": robot_id, "window": window, "count": len(positions), "positions": positions}


@app.get("/api/alerts", tags=["alerts"])
def get_alerts(
    window: str = Query("10m"),
    limit:  int = Query(100, ge=1, le=1000),
):
    flux = f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -{window})
  |> filter(fn: (r) => r._measurement == "{MEASUREMENT}")
  |> filter(fn: (r) => r._field == "latitude" or r._field == "longitude")
  |> pivot(rowKey: ["_time", "robot_id"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: {limit})
"""
    records = run_flux(flux)
    alerts = [
        {"timestamp": r.get("_time"), "robot_id": r.get("robot_id", "unknown"),
         "lat": r.get("latitude"), "lon": r.get("longitude")}
        for r in records if r.get("latitude") is not None
    ]
    return {"window": window, "count": len(alerts), "alerts": alerts}


@app.get("/api/alerts/{robot_id}", tags=["alerts"])
def get_alerts_by_robot(
    robot_id: str,
    window: str = Query("1h"),
    limit:  int = Query(200, ge=1, le=1000),
):
    flux = f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -{window})
  |> filter(fn: (r) => r._measurement == "{MEASUREMENT}")
  |> filter(fn: (r) => r.robot_id == "{robot_id}")
  |> filter(fn: (r) => r._field == "latitude" or r._field == "longitude")
  |> pivot(rowKey: ["_time", "robot_id"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: {limit})
"""
    records = run_flux(flux)
    alerts = [
        {"timestamp": r.get("_time"), "robot_id": r.get("robot_id", robot_id),
         "lat": r.get("latitude"), "lon": r.get("longitude")}
        for r in records if r.get("latitude") is not None
    ]
    if not alerts:
        raise HTTPException(status_code=404, detail=f"No alerts for robot '{robot_id}' in -{window}.")
    return {"robot_id": robot_id, "window": window, "count": len(alerts), "alerts": alerts}


@app.get("/api/stats", tags=["stats"])
def get_stats(window: str = Query("1h")):
    flux_count = f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -{window})
  |> filter(fn: (r) => r._measurement == "{MEASUREMENT}")
  |> filter(fn: (r) => r._field == "latitude")
  |> group(columns: ["robot_id"])
  |> count()
"""
    records = run_flux(flux_count)
    per_robot = sorted([
        {"robot_id": r.get("robot_id", "unknown"), "alert_count": r.get("_value", 0)}
        for r in records
    ], key=lambda x: x["robot_id"])
    total = sum(r["alert_count"] for r in per_robot)
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    try:
        secs = int(window[:-1]) * units.get(window[-1], 1)
    except (ValueError, IndexError):
        secs = 0
    return {
        "window": window,
        "total_alerts": total,
        "alerts_per_second": round(total / secs, 3) if secs else None,
        "geofence_condition": "outside parcel 567 PAL (bbox)",
        "per_robot": per_robot,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/soil", tags=["soil"])
def get_soil_alerts(
    window: str = Query("10m"),
    limit:  int = Query(100, ge=1, le=1000),
):
    """Soil temperature alerts from SMT100 sensor."""
    flux = f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -{window})
  |> filter(fn: (r) => r._measurement == "{MEASUREMENT}")
  |> filter(fn: (r) => r.topic == "soil/alerts")
  |> filter(fn: (r) => r._field == "temp_10cm" or r._field == "temp_20cm")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: {limit})
"""
    records = run_flux(flux)
    alerts = [
        {
            "timestamp":  r.get("_time"),
            "temp_10cm":  r.get("temp_10cm"),
            "temp_20cm":  r.get("temp_20cm"),
        }
        for r in records if r.get("temp_10cm") is not None
    ]
    return {"window": window, "threshold_celsius": 25.0, "count": len(alerts), "alerts": alerts}


@app.get("/api/odom", tags=["odom"])
def get_odom_alerts(
    window: str = Query("10m"),
    limit:  int = Query(100, ge=1, le=1000),
):
    """Speed alerts — robot exceeded velocity threshold."""
    flux = f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -{window})
  |> filter(fn: (r) => r._measurement == "{MEASUREMENT}")
  |> filter(fn: (r) => r.topic == "robot/odom_alerts")
  |> filter(fn: (r) => r._field == "linear_x" or r._field == "angular_z")
  |> pivot(rowKey: ["_time", "robot_id"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: {limit})
"""
    records = run_flux(flux)
    alerts = [
        {
            "timestamp": r.get("_time"),
            "robot_id":  r.get("robot_id"),
            "linear_x":  r.get("linear_x"),
            "angular_z": r.get("angular_z"),
        }
        for r in records if r.get("linear_x") is not None
    ]
    return {"window": window, "threshold": 0.10, "count": len(alerts), "alerts": alerts}


@app.get("/api/battery", tags=["battery"])
def get_battery_alerts(
    window: str = Query("10m"),
    limit:  int = Query(100, ge=1, le=1000),
):
    """Battery alerts — robot battery dropped below threshold."""
    flux = f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -{window})
  |> filter(fn: (r) => r._measurement == "{MEASUREMENT}")
  |> filter(fn: (r) => r.topic == "robot/battery_alerts")
  |> filter(fn: (r) => r._field == "voltage" or r._field == "percentage")
  |> pivot(rowKey: ["_time", "robot_id"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: {limit})
"""
    records = run_flux(flux)
    alerts = [
        {
            "timestamp":  r.get("_time"),
            "robot_id":   r.get("robot_id"),
            "voltage":    r.get("voltage"),
            "percentage": r.get("percentage"),
        }
        for r in records if r.get("voltage") is not None
    ]
    return {"window": window, "threshold": 0.20, "count": len(alerts), "alerts": alerts}


@app.get("/api/collisions", tags=["collisions"])
def get_collision_alerts(
    window: str = Query("10m"),
    limit:  int = Query(100, ge=1, le=1000),
):
    """Collision risk alerts — two robots within 2m of each other."""
    flux = f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -{window})
  |> filter(fn: (r) => r._measurement == "collision_alerts")
  |> filter(fn: (r) => r._field == "lat" or r._field == "lon")
  |> pivot(rowKey: ["_time", "robot_id_a", "robot_id_b"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: {limit})
"""
    records = run_flux(flux)
    alerts = [
        {
            "timestamp":  r.get("_time"),
            "robot_id_a": r.get("robot_id_a"),
            "robot_id_b": r.get("robot_id_b"),
            "lat":        r.get("lat"),
            "lon":        r.get("lon"),
        }
        for r in records if r.get("lat") is not None
    ]
    return {"window": window, "count": len(alerts), "alerts": alerts}


if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
