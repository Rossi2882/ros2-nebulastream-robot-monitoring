#!/bin/bash
# run_perf_tests_repeated.sh — 12 repetitions per parameter combination
# Outlier removal (2 highest e2e_avg_ms per combination) done by analyze script.
#
# Fleet axis: 1,3,10,20,30,40,50 robots (fixed 10 Hz)
# Frequency axis: 1,20,40,60,80,100 Hz (fixed 3 robots)
# Point (3 robots, 10 Hz) measured once per repetition — shared between axes
#
# Estimated time: ~3.5 hours
#
# Usage:
#   bash ~/magisterka/run_perf_tests_repeated.sh

DURATION=60
WARMUP=3
REPETITIONS=12
OUTPUT=~/magisterka/perf_results_repeated.csv

rm -f $OUTPUT
echo "New results file: $OUTPUT"

echo "========================================"
echo "  PERFORMANCE TESTS — ${REPETITIONS} repetitions"
echo "  $(date)"
echo "========================================"

mosquitto_pub -h localhost -p 1883 -t test/ping -m "ping" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "MQTT broker unavailable — run docker compose up -d"
    exit 1
fi
echo "MQTT broker available"

run_test() {
    local N_ROBOTS=$1
    local HZ=$2
    local RUN_ID=$3

    echo ""
    echo ">>> Run ${RUN_ID}/${REPETITIONS}: ${N_ROBOTS} robots x ${HZ} Hz"

    # Restart worker-1 before each run for clean state
    cd ~/magisterka/pipeline
    docker compose restart worker-1 > /dev/null 2>&1
    sleep 8
    QUERY_ID=$(docker compose exec -T nes-cli nes-cli start 2>/dev/null)
    cd ~

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
    for RUN_ID in $(seq 1 $REPETITIONS); do
        run_test $N_ROBOTS 10 $RUN_ID
    done
    echo ""
    echo "=== Completed all ${REPETITIONS} runs for ${N_ROBOTS} robots x 10 Hz ==="
    echo ""
done

echo ""
echo "════════════════════════════════════════════════════"
echo "  FREQUENCY AXIS — fixed fleet 3 robots"
echo "  Hz: 1, 20, 40, 60, 80, 100"
echo "  (10 Hz already measured in fleet axis)"
echo "════════════════════════════════════════════════════"

for HZ in 1 20 40 60 80 100; do
    for RUN_ID in $(seq 1 $REPETITIONS); do
        run_test 3 $HZ $RUN_ID
    done
    echo ""
    echo "=== Completed all ${REPETITIONS} runs for 3 robots x ${HZ} Hz ==="
    echo ""
done

echo ""
echo "========================================"
echo "  ALL TESTS COMPLETED — $(date)"
echo "  Raw results: $OUTPUT"
echo "========================================"
echo ""
echo "Next step — analyze results:"
echo "  python3 ~/magisterka/analyze_repeated.py"
