import time
import pandas as pd
import paho.mqtt.client as mqtt
from pathlib import Path

MQTT_BROKER = "localhost"
MQTT_PORT   = 1883
MQTT_TOPIC  = "soil/data"
INTERVAL_S  = 1.0

XLSX_PATH = Path(__file__).parent / "NinsarPlot_SoilTemperature_data-2025-06-232.xlsx"

df = pd.read_excel(XLSX_PATH)
records = list(zip(df["10 cm"], df["20 cm"]))
print(f"Loaded {len(records)} measurements from {XLSX_PATH.name}")

client = mqtt.Client(client_id="SMT100_Simulator")
client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.loop_start()
print(f"Connected to MQTT {MQTT_BROKER}:{MQTT_PORT}, topic: {MQTT_TOPIC}")
print("Simulation running in loop (Ctrl+C to stop)\n")

idx = 0
try:
    while True:
        temp_10, temp_20 = records[idx % len(records)]
        payload = f"{temp_10},{temp_20}\n"
        client.publish(MQTT_TOPIC, payload)
        print(f"[{idx % len(records):02d}/48] {payload.strip()}")
        idx += 1
        time.sleep(INTERVAL_S)
except KeyboardInterrupt:
    print("\nStopped.")
finally:
    client.loop_stop()
    client.disconnect()
