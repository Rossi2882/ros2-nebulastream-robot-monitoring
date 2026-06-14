#!/bin/bash
# play_test_bags.sh — starts three test bags simultaneously from a single time point.
# This ensures robot phases are repeatable and collision always occurs at the same moment.

BAGS_DIR=~/magisterka/data/robots

echo "Stopping previous playbacks..."
pkill -f "ros2 bag play" 2>/dev/null
sleep 2

echo "Starting three bags simultaneously (--loop)..."
ros2 bag play "$BAGS_DIR/robot_1_test_ns" --loop &
PID1=$!
ros2 bag play "$BAGS_DIR/robot_2_test_ns" --loop &
PID2=$!
ros2 bag play "$BAGS_DIR/robot_3_test_ns" --loop &
PID3=$!

echo "Started PIDs: robot_1=$PID1  robot_2=$PID2  robot_3=$PID3"
echo "Press Ctrl+C to stop all three."

cleanup() {
    echo ""
    echo "Stopping bags..."
    kill $PID1 $PID2 $PID3 2>/dev/null
    pkill -f "ros2 bag play" 2>/dev/null
    exit 0
}
trap cleanup INT TERM

wait
