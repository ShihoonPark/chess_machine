#!/bin/bash

ARM=${1}
Z_SAFE=${2:-${HOME_Z:-90}}

F=${F_HOME:-1800}
SLEEP_TIME=${SLEEP_TIME:-0.15}
POSE="A0 B0 C0"

if [ -z "$ARM" ]; then
  echo "Usage: ./test/goto_home.sh arm1|arm2 [Z]"
  exit 1
fi

if [ "$ARM" = "arm1" ]; then
  TOPIC="/arm1/raw_cmd"
elif [ "$ARM" = "arm2" ]; then
  TOPIC="/arm2/raw_cmd"
else
  echo "ARM must be arm1 or arm2"
  exit 1
fi

X=200
Y=0

CMD_OFF="M3S0"
CMD_HOME="M20 G90 G0 X${X} Y${Y} Z${Z_SAFE} ${POSE} F${F}"

echo "ARM: $ARM"
echo "TOPIC: $TOPIC"
echo "SEND suction off: $CMD_OFF"
echo "SEND home: $CMD_HOME"

source /opt/ros/humble/setup.bash
source /root/chess_robot_project/ros_ws/install/setup.bash

ros2 topic pub --once "$TOPIC" std_msgs/msg/String "{data: '$CMD_OFF'}"
sleep "$SLEEP_TIME"
ros2 topic pub --once "$TOPIC" std_msgs/msg/String "{data: '$CMD_HOME'}"
