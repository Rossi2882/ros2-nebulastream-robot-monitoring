import math
import time
import paho.mqtt.client as mqtt

MQTT_BROKER   = "localhost"
MQTT_PORT     = 1883
ALERT_TOPIC   = "robot/collision_alerts"
THRESHOLD_DEG = 0.00002

positions = {}


def haversine_deg(lat1, lon1, lat2, lon2):
    return math.sqrt((lat1 - lat2)**2 + (lon1 - lon2)**2)


def on_connect(client, userdata, flags, rc):
    print(f"Connected (rc={rc})")
    for robot_id in [1, 2, 3]:
        client.subscribe(f"robot/gps/{robot_id}", qos=1)
    print(f"   Subscribing to robot/gps/1,2,3 | Threshold: {THRESHOLD_DEG}° ~ {THRESHOLD_DEG*111000:.0f}m")
    print(f"   Alerts -> {ALERT_TOPIC}")


def on_message(client, userdata, msg):
    try:
        parts = msg.payload.decode().strip().split(",")
        robot_id = int(parts[0])
        lat = float(parts[1])
        lon = float(parts[2])
    except (ValueError, IndexError):
        return

    positions[robot_id] = (lat, lon, time.time())

    for other_id, (other_lat, other_lon, other_ts) in list(positions.items()):
        if other_id == robot_id:
            continue
        if time.time() - other_ts > 5.0:
            continue
        dist = haversine_deg(lat, lon, other_lat, other_lon)
        if dist < THRESHOLD_DEG:
            payload = f"{robot_id},{other_id},{lat},{lon}\n"
            client.publish(ALERT_TOPIC, payload, qos=1)
            print(f"COLLISION: robot {robot_id} <-> robot {other_id} — {dist*111000:.1f}m")


def main():
    client = mqtt.Client(client_id="CollisionDetector")
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_forever()


if __name__ == "__main__":
    main()
