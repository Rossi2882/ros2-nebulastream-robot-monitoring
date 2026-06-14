#!/usr/bin/env python3
"""
ros2_mqtt_bridge_multi.py — ROS2 to MQTT bridge for N robots.

Usage:
  python3 ros2_mqtt_bridge_multi.py               # default 3 robots
  python3 ros2_mqtt_bridge_multi.py --robots 10   # 10 robots
"""
import argparse
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import NavSatFix, Imu, BatteryState
from nav_msgs.msg import Odometry
import paho.mqtt.client as mqtt

MQTT_BROKER = 'localhost'
MQTT_PORT   = 1883

BAG_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    history=HistoryPolicy.KEEP_LAST,
    depth=10
)


class GpsMultiBridge(Node):
    def __init__(self, n_robots: int):
        super().__init__('gps_multi_bridge')

        self.mqtt_client = mqtt.Client(client_id="ROS2_MultiBridge")
        try:
            self.mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
            self.mqtt_client.loop_start()
            self.get_logger().info(f'Connected to MQTT {MQTT_BROKER}:{MQTT_PORT}')
        except Exception as e:
            self.get_logger().error(f'MQTT connection error: {e}')
            return

        robots = {f'/robot_{i}': i for i in range(1, n_robots + 1)}
        self.get_logger().info(f'Handling {n_robots} robots: robot_1..robot_{n_robots}')

        for prefix, robot_id in robots.items():
            self.create_subscription(
                NavSatFix, f'{prefix}/gps/fix',
                lambda msg, rid=robot_id: self.gps_callback(msg, rid), BAG_QOS)
            self.create_subscription(
                BatteryState, f'{prefix}/power_supply/battery_status',
                lambda msg, rid=robot_id: self.battery_callback(msg, rid), BAG_QOS)
            self.create_subscription(
                Odometry, f'{prefix}/alpo_driver/ackermann_controller/odom',
                lambda msg, rid=robot_id: self.odom_callback(msg, rid), BAG_QOS)
            self.create_subscription(
                Imu, f'{prefix}/imu/data',
                lambda msg, rid=robot_id: self.imu_callback(msg, rid), BAG_QOS)

        self.get_logger().info('Bridge started')

    def gps_callback(self, msg, robot_id):
        payload = f'{robot_id},{msg.latitude},{msg.longitude},{msg.altitude}\n'
        self.mqtt_client.publish('robot/gps', payload)
        self.mqtt_client.publish(f'robot/gps/{robot_id}', payload)

    def odom_callback(self, msg, robot_id):
        payload = f'{robot_id},{msg.twist.twist.linear.x:.4f},{msg.twist.twist.angular.z:.4f}\n'
        self.mqtt_client.publish('robot/odom', payload)

    def imu_callback(self, msg, robot_id):
        ax = msg.linear_acceleration.x
        ay = msg.linear_acceleration.y
        az = msg.linear_acceleration.z
        gz = msg.angular_velocity.z
        payload = f'{robot_id},{ax:.4f},{ay:.4f},{az:.4f},{gz:.4f}\n'
        self.mqtt_client.publish('robot/imu', payload)

    def battery_callback(self, msg, robot_id):
        payload = f'{robot_id},{msg.voltage:.2f},{msg.percentage:.4f},{msg.current:.2f}\n'
        self.mqtt_client.publish('robot/battery', payload)


def main():
    parser = argparse.ArgumentParser(description='ROS2 to MQTT bridge for N robots')
    parser.add_argument('--robots', type=int, default=3,
                        help='Number of robots (default: 3)')
    args = parser.parse_args()

    rclpy.init()
    bridge = GpsMultiBridge(n_robots=args.robots)
    try:
        rclpy.spin(bridge)
    except KeyboardInterrupt:
        pass
    bridge.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
