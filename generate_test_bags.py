#!/usr/bin/env python3
"""
generate_test_bags.py — synthetic ROS2 bag generator with natural collisions.
Robots 2 and 3 travel towards each other along the same axis (lon=3.4285).

Usage:
  python3 generate_test_bags.py ~/magisterka/data/robots/
"""

import argparse
import json
import math
from pathlib import Path

import rclpy
from rclpy.serialization import serialize_message
from sensor_msgs.msg import NavSatFix, Imu, BatteryState
from nav_msgs.msg import Odometry
from std_msgs.msg import Header
from geometry_msgs.msg import Quaternion, Vector3, Twist, Pose, Point
from builtin_interfaces.msg import Time
from rosbag2_py import SequentialWriter, StorageOptions, ConverterOptions, TopicMetadata

GEOFENCE = {
    "min_lon": 3.4249509, "max_lon": 3.4304526,
    "min_lat": 46.3378456, "max_lat": 46.3408670,
}

COLLISION_LON = 3.4285
R2_START_LAT  = 46.3406
R2_END_LAT    = 46.3380
R3_START_LAT  = 46.3380
R3_END_LAT    = 46.3406
LON_EAST_SAFE = 3.4295
LON_OUT       = GEOFENCE["max_lon"] + 0.003

COLLISION_THRESHOLD_DEG = 0.00002
RATE_GPS, RATE_IMU, RATE_ODOM, RATE_BATTERY = 10, 100, 10, 2


def lerp(a, b, t):
    return a + (b - a) * t


def smooth_step(t):
    return t * t * (3 - 2 * t)


def waypoints_interp(t, wps):
    if t <= wps[0][0]:
        return wps[0][1], wps[0][2]
    if t >= wps[-1][0]:
        return wps[-1][1], wps[-1][2]
    for i in range(len(wps) - 1):
        t0, lat0, lon0 = wps[i]
        t1, lat1, lon1 = wps[i + 1]
        if t0 <= t <= t1:
            s = smooth_step((t - t0) / (t1 - t0))
            return lerp(lat0, lat1, s), lerp(lon0, lon1, s)
    return wps[-1][1], wps[-1][2]


def gps_robot1(t, sc):
    wps = [
        (0,   46.3382, 3.4280),
        (20,  46.3388, 3.4285),
        (40,  46.3392, LON_EAST_SAFE),
        (50,  46.3392, GEOFENCE["max_lon"] + 0.001),
        (60,  46.3392, LON_OUT),
        (70,  46.3392, GEOFENCE["max_lon"] + 0.001),
        (80,  46.3392, LON_EAST_SAFE),
        (95,  46.3395, 3.4290),
        (110, 46.3400, 3.4290),
        (120, 46.3404, 3.4285),
    ]
    lat, lon = waypoints_interp(t, wps)
    lat += 0.00015 * math.sin(t * 0.4)
    return lat, lon


def gps_robot2(t, sc):
    wps = [
        (0,   R2_START_LAT, COLLISION_LON),
        (60,  R2_END_LAT,   COLLISION_LON),
        (90,  R2_END_LAT,   COLLISION_LON),
        (120, R2_START_LAT, COLLISION_LON),
    ]
    lat, lon = waypoints_interp(t, wps)
    lon += 0.00005 * math.sin(t * 0.3)
    return lat, lon


def gps_robot3(t, sc):
    wps = [
        (0,   R3_START_LAT, COLLISION_LON),
        (60,  R3_END_LAT,   COLLISION_LON),
        (90,  R3_END_LAT,   COLLISION_LON),
        (120, R3_START_LAT, COLLISION_LON),
    ]
    lat, lon = waypoints_interp(t, wps)
    lon -= 0.00005 * math.sin(t * 0.3)
    return lat, lon


GPS_FUNCTIONS = {
    "robot_1_test": gps_robot1,
    "robot_2_test": gps_robot2,
    "robot_3_test": gps_robot3,
}

SCENARIOS = {
    "robot_1_test": {
        "duration_s": 120,
        "battery_start": 1.00, "battery_end": 0.10, "battery_threshold": 0.20,
        "speed_high_windows": [(20, 60), (90, 115)],
        "speed_low": 0.04, "speed_high": 0.28,
        "geofence_outside_event": (40, 75),
        "collision_windows": [],
    },
    "robot_2_test": {
        "duration_s": 120,
        "battery_start": 1.00, "battery_end": 0.13, "battery_threshold": 0.20,
        "speed_high_windows": [(15, 55), (80, 110)],
        "speed_low": 0.05, "speed_high": 0.22,
        "geofence_outside_event": None,
        "collision_windows": [(55, 65)],
    },
    "robot_3_test": {
        "duration_s": 120,
        "battery_start": 1.00, "battery_end": 0.16, "battery_threshold": 0.20,
        "speed_high_windows": [(25, 65), (88, 112)],
        "speed_low": 0.06, "speed_high": 0.20,
        "geofence_outside_event": None,
        "collision_windows": [(55, 65)],
    },
}


def is_in_window(t, windows):
    return any(s <= t < e for s, e in windows)


def make_time(t_s):
    sec = int(t_s)
    return Time(sec=sec, nanosec=int((t_s - sec) * 1e9))


def make_gps(t, lat, lon):
    msg = NavSatFix()
    msg.header = Header(stamp=make_time(t), frame_id="gps")
    msg.latitude, msg.longitude, msg.altitude = lat, lon, 278.0
    return msg


def make_imu(t):
    msg = Imu()
    msg.header = Header(stamp=make_time(t), frame_id="imu")
    msg.orientation = Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)
    msg.linear_acceleration = Vector3(x=0.0, y=0.0, z=9.81)
    msg.angular_velocity = Vector3(x=0.0, y=0.0, z=0.0)
    return msg


def make_odom(t, v):
    msg = Odometry()
    msg.header = Header(stamp=make_time(t), frame_id="odom")
    msg.child_frame_id = "base_link"
    msg.pose.pose = Pose(position=Point(x=0.0, y=0.0, z=0.0),
                         orientation=Quaternion(x=0.0, y=0.0, z=0.0, w=1.0))
    msg.twist.twist = Twist()
    msg.twist.twist.linear = Vector3(x=v, y=0.0, z=0.0)
    msg.twist.twist.angular = Vector3(x=0.0, y=0.0, z=0.0)
    return msg


def make_battery(t, pct):
    msg = BatteryState()
    msg.header = Header(stamp=make_time(t), frame_id="")
    msg.voltage = 48.0 + pct * 6.0
    msg.percentage = pct
    msg.current = -3.0
    msg.charge = pct * 155.0
    msg.capacity = msg.design_capacity = 155.0
    msg.present = True
    return msg


def battery_at(t, sc):
    s, e, d = sc["battery_start"], sc["battery_end"], sc["duration_s"]
    return s + (e - s) * (t / d)


def ground_truth(name, sc):
    events = []
    d = sc["duration_s"]
    if sc.get("geofence_outside_event"):
        out_s, out_e = sc["geofence_outside_event"]
        events.append({"time_s": out_s, "type": "geofence_exit",
                       "description": "Exit from parcel 567 PAL boundary"})
        events.append({"time_s": out_e, "type": "geofence_enter",
                       "description": "Return to parcel 567 PAL"})
    for s, e in sc["speed_high_windows"]:
        events.append({"time_s": s, "type": "speed_high_enter",
                       "description": "Speed threshold exceeded (>0.10 m/s)"})
        if e < d:
            events.append({"time_s": e, "type": "speed_high_exit",
                           "description": "Speed returned to normal"})
    s_b, e_b, thr = sc["battery_start"], sc["battery_end"], sc["battery_threshold"]
    t_cross = (thr - s_b) / (e_b - s_b) * d
    if 0 < t_cross < d:
        events.append({"time_s": round(t_cross, 1), "type": "battery_low",
                       "description": f"Battery dropped below {int(thr*100)}%"})
    for s, e in sc.get("collision_windows", []):
        events.append({"time_s": s, "type": "collision_risk",
                       "description": "Collision risk — robots approaching each other"})
    events.sort(key=lambda x: x["time_s"])
    return events


def generate(name, sc, output_dir):
    out = output_dir / name
    if out.exists():
        print(f"  Skipping {name} — directory already exists")
        return
    gps_fn = GPS_FUNCTIONS[name]
    writer = SequentialWriter()
    writer.open(
        StorageOptions(uri=str(out), storage_id="sqlite3"),
        ConverterOptions(input_serialization_format="cdr",
                         output_serialization_format="cdr"),
    )
    topics = [
        ("/gps/fix",                               "sensor_msgs/msg/NavSatFix"),
        ("/imu/data",                              "sensor_msgs/msg/Imu"),
        ("/alpo_driver/ackermann_controller/odom", "nav_msgs/msg/Odometry"),
        ("/power_supply/battery_status",           "sensor_msgs/msg/BatteryState"),
    ]
    for i, (n, typ) in enumerate(topics):
        writer.create_topic(TopicMetadata(id=i, name=n, type=typ,
                            serialization_format="cdr", offered_qos_profiles=[]))
    d = sc["duration_s"]
    events = []
    for i in range(int(d * RATE_GPS)):
        t = i / RATE_GPS
        lat, lon = gps_fn(t, sc)
        events.append((t, "/gps/fix", serialize_message(make_gps(t, lat, lon))))
    for i in range(int(d * RATE_IMU)):
        t = i / RATE_IMU
        events.append((t, "/imu/data", serialize_message(make_imu(t))))
    for i in range(int(d * RATE_ODOM)):
        t = i / RATE_ODOM
        v = sc["speed_high"] if is_in_window(t, sc["speed_high_windows"]) else sc["speed_low"]
        events.append((t, "/alpo_driver/ackermann_controller/odom",
                       serialize_message(make_odom(t, v))))
    for i in range(int(d * RATE_BATTERY)):
        t = i / RATE_BATTERY
        events.append((t, "/power_supply/battery_status",
                       serialize_message(make_battery(t, battery_at(t, sc)))))
    events.sort(key=lambda x: x[0])
    for ts, topic, data in events:
        writer.write(topic, data, int(ts * 1e9))
    print(f"  {name}: {len(events)} messages ({d}s)")
    gt = {
        "bag": name, "duration_s": d,
        "geofence_bbox": GEOFENCE,
        "speed_threshold_mps": 0.10,
        "battery_threshold": sc["battery_threshold"],
        "collision_threshold_deg": COLLISION_THRESHOLD_DEG,
        "collision_axis_lon": COLLISION_LON,
        "events": ground_truth(name, sc),
    }
    gt_path = output_dir / f"{name}_ground_truth.json"
    gt_path.write_text(json.dumps(gt, indent=2, ensure_ascii=False))
    print(f"  Ground truth ({len(gt['events'])} events):")
    for e in gt["events"]:
        print(f"    t={e['time_s']:>5.1f}s  {e['type']:<20s}  {e['description']}")
    print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir")
    args = parser.parse_args()
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    rclpy.init()
    try:
        for name, sc in SCENARIOS.items():
            print(f"Generating {name}...")
            generate(name, sc, output_dir)
    finally:
        rclpy.shutdown()
    print("Done!")


if __name__ == "__main__":
    main()
