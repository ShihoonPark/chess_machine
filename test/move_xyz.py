import sys
import time
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Pose


class MoveXYZ(Node):
    def __init__(self):
        super().__init__("move_xyz_test")
        self.pub = self.create_publisher(Pose, "/target_pose_xyz", 10)
        time.sleep(1)

    def move(self, x, y, z):
        msg = Pose()
        msg.position.x = float(x)
        msg.position.y = float(y)
        msg.position.z = float(z)
        msg.orientation.x = 0.0
        msg.orientation.y = 0.0
        msg.orientation.z = 0.0
        msg.orientation.w = 1.0

        self.get_logger().info(f"Move to X={x}, Y={y}, Z={z}")
        self.pub.publish(msg)
        time.sleep(2)


def main():
    if len(sys.argv) != 4:
        print("사용법: python3 test/move_xyz.py X Y Z")
        print("예시: python3 test/move_xyz.py 200 0 200")
        return

    x, y, z = sys.argv[1], sys.argv[2], sys.argv[3]

    rclpy.init()
    node = MoveXYZ()
    node.move(x, y, z)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
