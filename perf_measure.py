#!/usr/bin/env python3
"""
perf_measure.py — pipeline latency and throughput measurement per component.

Measures latency at four boundaries:
  t1: publish to MQTT (robot/gps)
  t2: delivery by broker (perf/broker_test)
  t3: alert from NebulaStream (robot/alerts)
  t4: write to InfluxDB (queried after test)

Usage:
  python3 perf_measure.py --robots 3 --hz 10 --duration 30
"""

import argparse
import csv
import os
import subprocess
import threading
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

MQTT_BROKER   = "localhost"
MQTT_PORT     = 1883
INFLUX_URL    = "http://localhost:8086"
INFLUX_TOKEN  = "mytoken123"
INFLUX_ORG    = "robotics"
INFLUX_BUCKET = "geofencing"

GPS_LAT = 46.3392
GPS_LON = 3.4400

# ── Shared variables ────────────────────────────────────────────────────────────
publish_times = {}   # seq_id -> t_publish_ns
broker_times  = {}   # seq_id -> t_broker_ns (received on perf/broker_test)
alert_times   = {}   # seq_id -> t_alert_ns

publish_count = 0
broker_count  = 0
alert_count   = 0
lock          = threading.Lock()
running       = True
seq_counter   = 0


# ── Publisher ───────────────────────────────────────────────────────────────────

def publisher_thread(client, n_robots, hz, duration):
    global publish_count, running, seq_counter
    interval = 1.0 / hz
    t_end    = time.monotonic() + duration

    while time.monotonic() < t_end and running:
        t_loop = time.monotonic()

        for robot_id in range(1, n_robots + 1):
            t_pub = time.time_ns()
            seq   = seq_counter

            with lock:
                seq_counter   += 1
                publish_times[seq] = t_pub
                publish_count += 1

            # GPS topic — standard 4-field format (NebulaStream)
            gps_payload = f"{robot_id},{GPS_LAT},{GPS_LON},{t_pub}\n"
            client.publish("robot/gps", gps_payload)

            # Measurement topic — contains seq and t_publish (broker latency only)
            perf_payload = f"{seq},{t_pub}\n"
            client.publish("perf/broker_test", perf_payload)

        elapsed = time.monotonic() - t_loop
        sleep_t = interval - elapsed
        if sleep_t > 0:
            time.sleep(sleep_t)

    running = False


# ── Broker receiver (perf/broker_test) ─────────────────────────────────────────

def on_broker_message(client, userdata, msg):
    global broker_count
    t_recv = time.time_ns()
    try:
        parts = msg.payload.decode().strip().split(",")
        seq   = int(parts[0])
        with lock:
            broker_times[seq] = t_recv
            broker_count += 1
    except Exception:
        pass


# ── NebulaStream alert receiver (robot/alerts) ─────────────────────────────────

def on_alert_message(client, userdata, msg):
    global alert_count
    t_recv = time.time_ns()
    try:
        # NebulaStream may combine multiple alerts in one payload (separated by \n)
        lines = msg.payload.decode().strip().split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            if len(parts) < 4:
                continue
            t_pub_from_alert = int(float(parts[3]))
            with lock:
                alert_count += 1
                alert_times[t_pub_from_alert] = t_recv
                if t_pub_from_alert not in publish_times:
                    publish_times[t_pub_from_alert] = t_pub_from_alert
    except Exception as e:
        with lock:
            alert_count += 1


# ── InfluxDB query ──────────────────────────────────────────────────────────────

def get_last_influx_time(t_start_iso):
    """Returns timestamp of the last alert record stored in InfluxDB."""
    try:
        flux = (
            f'from(bucket:"{INFLUX_BUCKET}")'
            f' |> range(start: {t_start_iso})'
            f' |> filter(fn:(r)=> r._measurement=="mqtt_consumer"'
            f' and r.topic=="robot/alerts")'
            f' |> last()'
        )
        req = urllib.request.Request(
            f"{INFLUX_URL}/api/v2/query?org={INFLUX_ORG}",
            data=flux.encode(),
            headers={
                "Authorization": f"Token {INFLUX_TOKEN}",
                "Content-Type": "application/vnd.flux",
                "Accept": "application/csv",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            lines = resp.read().decode().strip().split("\n")
            for line in lines:
                parts = line.split(",")
                if len(parts) > 5 and "T" in parts[5]:
                    # _time column in ISO format
                    t_str = parts[5].strip()
                    dt = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
                    return dt.timestamp() * 1e9  # ns
    except Exception as e:
        print(f"  [WARN] InfluxDB read error: {e}")
    return None


def count_influx_records(t_start_iso):
    try:
        flux = (
            f'from(bucket:"{INFLUX_BUCKET}")'
            f' |> range(start: {t_start_iso})'
            f' |> filter(fn:(r)=> r._measurement=="mqtt_consumer"'
            f' and r.topic=="robot/alerts"'
            f' and r._field=="latitude")'
            f' |> count()'
        )
        req = urllib.request.Request(
            f"{INFLUX_URL}/api/v2/query?org={INFLUX_ORG}",
            data=flux.encode(),
            headers={
                "Authorization": f"Token {INFLUX_TOKEN}",
                "Content-Type": "application/vnd.flux",
                "Accept": "application/csv",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            lines = resp.read().decode().strip().split("\n")
            total = 0
            for line in lines:
                parts = line.split(",")
                if len(parts) > 5 and parts[5].strip().lstrip("-").isdigit():
                    total += int(parts[5].strip())
            return total
    except Exception as e:
        print(f"  [WARN] InfluxDB count error: {e}")
        return -1


def collect_docker_stats():
    try:
        result = subprocess.run(
            ["docker", "stats", "--no-stream", "--format",
             "{{.Name}},{{.CPUPerc}},{{.MemUsage}}"],
            capture_output=True, text=True, timeout=10
        )
        stats = {}
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split(",")
            if len(parts) >= 3:
                name = parts[0].strip()
                cpu  = parts[1].strip().replace("%", "")
                mem  = parts[2].strip().split("/")[0].strip()
                stats[name] = {"cpu_pct": cpu, "mem": mem}
        return stats
    except Exception:
        return {}


# ── Main measurement function ───────────────────────────────────────────────────

def run_measurement(n_robots, hz, duration):
    global publish_count, broker_count, alert_count, running, seq_counter
    publish_count = 0
    broker_count  = 0
    alert_count   = 0
    running       = True
    seq_counter   = 0
    publish_times.clear()
    broker_times.clear()
    alert_times.clear()

    print(f"\n{'='*60}")
    print(f"  TEST: {n_robots} robots x {hz} Hz x {duration}s")
    print(f"  Expected messages: {int(n_robots * hz * duration)}")
    print(f"{'='*60}")

    # Publishing client
    pub_client = mqtt.Client(client_id="PerfPublisher_v2")
    pub_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    pub_client.loop_start()

    # Broker measurement client (perf/broker_test)
    broker_client = mqtt.Client(client_id="PerfBrokerReceiver")
    broker_client.on_message = on_broker_message
    broker_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    broker_client.subscribe("perf/broker_test", qos=0)
    broker_client.loop_start()

    # NebulaStream alert receiver client
    alert_client = mqtt.Client(client_id="PerfAlertReceiver_v2")
    alert_client.on_message = on_alert_message
    alert_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    alert_client.subscribe("robot/alerts", qos=1)
    alert_client.loop_start()

    t_start     = time.time()
    t_start_iso = datetime.fromtimestamp(t_start, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("  Collecting docker stats (before)...")
    stats_before = collect_docker_stats()

    print(f"  Starting publisher...")
    pub_thread = threading.Thread(
        target=publisher_thread,
        args=(pub_client, n_robots, hz, duration)
    )
    pub_thread.start()
    pub_thread.join()

    t_end = time.time()

    print("  Waiting for alerts and InfluxDB write (5s)...")
    time.sleep(5)

    print("  Collecting docker stats (after)...")
    stats_after = collect_docker_stats()

    print("  Querying InfluxDB...")
    influx_count    = count_influx_records(t_start_iso)
    last_influx_ns  = get_last_influx_time(t_start_iso)

    # ── Compute latencies ───────────────────────────────────────────────────────
    actual_duration = t_end - t_start

    # 1. Broker latency: t_broker - t_publish
    broker_latencies = []
    with lock:
        for seq, t_pub in publish_times.items():
            if seq in broker_times:
                lat = (broker_times[seq] - t_pub) / 1e6
                if 0 < lat < 1000:
                    broker_latencies.append(lat)


    # 2. End-to-end: t_alert - t_publish (key = t_publish encoded in ALTITUDE)
    e2e_latencies = []
    with lock:
        for t_pub, t_alert in alert_times.items():
            lat = (t_alert - t_pub) / 1e6
            if 0 < lat < 10000:
                e2e_latencies.append(lat)

    # 3. NebulaStream latency: e2e - broker_avg
    nebula_latencies = []
    if broker_latencies and e2e_latencies:
        broker_avg = sum(broker_latencies) / len(broker_latencies)
        for e2e_lat in e2e_latencies:
            nebula_lat = e2e_lat - broker_avg
            if 0 < nebula_lat < 10000:
                nebula_latencies.append(nebula_lat)
    # 4. Telegraf + InfluxDB latency: t_influx - t_alert (last alert)
    telegraf_lat = None
    with lock:
        if alert_times and last_influx_ns:
            last_alert_ns = max(alert_times.values())
            telegraf_lat  = (last_influx_ns - last_alert_ns) / 1e6

    def stats_ms(lats):
        if not lats:
            return None, None, None, None
        avg = sum(lats) / len(lats)
        p95 = sorted(lats)[int(len(lats) * 0.95)]
        return round(avg, 2), round(min(lats), 2), round(max(lats), 2), round(p95, 2)

    br_avg, br_min, br_max, br_p95 = stats_ms(broker_latencies)
    nb_avg, nb_min, nb_max, nb_p95 = stats_ms(nebula_latencies)
    e2_avg, e2_min, e2_max, e2_p95 = stats_ms(e2e_latencies)

    throughput_pub    = publish_count / actual_duration
    throughput_alert  = alert_count   / actual_duration
    throughput_influx = influx_count  / actual_duration if influx_count > 0 else 0

    # ── Print results ───────────────────────────────────────────────────────────
    print(f"\n  --- RESULTS ---")
    print(f"  Duration:              {actual_duration:.1f}s")
    print(f"  Published:             {publish_count} ({throughput_pub:.1f}/s)")
    print(f"  Alerts (NebulaStream): {alert_count} ({throughput_alert:.1f}/s)")
    print(f"  Records (InfluxDB):    {influx_count} ({throughput_influx:.1f}/s)")
    print(f"\n  --- LATENCY PER COMPONENT ---")
    if br_avg:
        print(f"  Broker MQTT:           avg={br_avg}ms  p95={br_p95}ms")
    else:
        print(f"  Broker MQTT:           no data")
    if nb_avg:
        print(f"  NebulaStream:          avg={nb_avg}ms  p95={nb_p95}ms")
    else:
        print(f"  NebulaStream:          no data")
    if telegraf_lat is not None:
        print(f"  Telegraf + InfluxDB:   ~{telegraf_lat:.1f}ms (estimate from last alert)")
    else:
        print(f"  Telegraf + InfluxDB:   no data")
    if e2_avg:
        print(f"  End-to-end (pub→alert):avg={e2_avg}ms  p95={e2_p95}ms")
    else:
        print(f"  End-to-end:            no data")

    print(f"\n  --- CPU/RAM (after test) ---")
    for name, stat in stats_after.items():
        if any(k in name for k in ["worker", "telegraf", "influx", "mqtt"]):
            print(f"  {name}: CPU={stat['cpu_pct']}% RAM={stat['mem']}")

    pub_client.loop_stop();   pub_client.disconnect()
    broker_client.loop_stop(); broker_client.disconnect()
    alert_client.loop_stop();  alert_client.disconnect()

    return {
        "timestamp":          datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "n_robots":           n_robots,
        "hz":                 hz,
        "duration_s":         round(actual_duration, 2),
        "published":          publish_count,
        "throughput_pub":     round(throughput_pub, 2),
        "alerts":             alert_count,
        "throughput_alert":   round(throughput_alert, 2),
        "influx_records":     influx_count,
        "throughput_influx":  round(throughput_influx, 2),
        "broker_avg_ms":      br_avg,
        "broker_p95_ms":      br_p95,
        "nebula_avg_ms":      nb_avg,
        "nebula_p95_ms":      nb_p95,
        "telegraf_est_ms":    round(telegraf_lat, 2) if telegraf_lat else None,
        "e2e_avg_ms":         e2_avg,
        "e2e_p95_ms":         e2_p95,
    }


# ── CLI ─────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Pipeline latency and throughput measurement")
    parser.add_argument("--robots",   type=int,   default=3)
    parser.add_argument("--hz",       type=float, default=10)
    parser.add_argument("--duration", type=int,   default=30)
    parser.add_argument("--output",   type=str,
                        default=os.path.expanduser("~/magisterka/perf_results_v2.csv"))
    args = parser.parse_args()

    print("Performance measurement script — latency per component")
    print(f"Bucket: {INFLUX_BUCKET}")

    result = run_measurement(args.robots, args.hz, args.duration)

    file_exists = os.path.isfile(args.output)
    with open(args.output, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=result.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(result)
    print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    main()
