#!/bin/bash
# Measurement duration: 60s
# Fleet axis: 1,3,10,20,30,40,50 robots (fixed 10 Hz)
# Frequency axis: 1,10,20,40,60,80,100 Hz (fixed 3 robots)
# Point (3 robots, 10 Hz) measured once — shared between both series

DURATION=60
WARMUP=3
OUTPUT=~/magisterka/perf_results.csv

# Remove old CSV file — overwrite
rm -f $OUTPUT
echo "New results file: $OUTPUT"

echo "========================================"
echo "  PERFORMANCE TESTS"
echo "  $(date)"
echo "========================================"

# Check broker
mosquitto_pub -h localhost -p 1883 -t test/ping -m "ping" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "MQTT broker unavailable — run docker compose up -d"
    exit 1
fi
echo "MQTT broker available"

# Restart worker-1 and start GPS query
echo "Restarting worker-1 and starting GPS query..."
cd ~/magisterka/pipeline
docker compose restart worker-1
sleep 10
QUERY_ID=$(docker compose exec -T nes-cli nes-cli start)
echo "GPS query: $QUERY_ID"
cd ~

run_test() {
    local N_ROBOTS=$1
    local HZ=$2
    echo ""
    echo ">>> Run: ${N_ROBOTS} robots x ${HZ} Hz"

    pkill -f ros2_mqtt_bridge_multi.py 2>/dev/null
    pkill -f ros2_load_generator.py 2>/dev/null
    sleep 2

    python3 ~/magisterka/perf_measure.py \
        --robots $N_ROBOTS --hz $HZ --duration $DURATION \
        --output $OUTPUT

    echo "    Waiting 5s before next run..."
    sleep 5
}

echo ""
echo "════════════════════════════════════════════════════"
echo "  FLEET AXIS — fixed frequency 10 Hz"
echo "  Robots: 1, 3, 10, 20, 30, 40, 50"
echo "════════════════════════════════════════════════════"

for N_ROBOTS in 1 3 10 20 30 40 50; do
    run_test $N_ROBOTS 10
done

echo ""
echo "════════════════════════════════════════════════════"
echo "  FREQUENCY AXIS — fixed fleet 3 robots"
echo "  Hz: 1, 20, 40, 60, 80, 100"
echo "  (10 Hz already measured in fleet axis — reusing that result)"
echo "════════════════════════════════════════════════════"

for HZ in 1 20 40 60 80 100; do
    run_test 3 $HZ
done

echo ""
echo "========================================"
echo "  TESTS COMPLETED — $(date)"
echo "  Results: $OUTPUT"
echo "========================================"

python3 - << 'PYEOF'
import csv, os
path = os.path.expanduser('~/magisterka/perf_results.csv')
with open(path) as f:
    rows = list(csv.DictReader(f))
    print(f"\nTotal runs: {len(rows)}")
    print(f"\n{'robots':>6} {'hz':>6} {'pub/s':>8} {'alert/s':>8} {'broker':>8} {'nebula':>8} {'e2e':>8}")
    print("-" * 58)
    for r in rows:
        broker = r['broker_avg_ms'] if r['broker_avg_ms'] != 'None' else '—'
        nebula = r['nebula_avg_ms'] if r['nebula_avg_ms'] != 'None' else '—'
        e2e    = r['e2e_avg_ms']    if r['e2e_avg_ms']    != 'None' else '—'
        print(f"{r['n_robots']:>6} {r['hz']:>6} "
              f"{r['throughput_pub']:>8} {r['throughput_alert']:>8} "
              f"{str(broker):>8} {str(nebula):>8} {str(e2e):>8}")
PYEOF
