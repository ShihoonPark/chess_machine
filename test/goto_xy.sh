#!/bin/bash

ARM=${1}
X=${2}
Y=${3}
Z=${4:-100}

F=700
POSE="A0 B0 C0"

if [ -z "$ARM" ] || [ -z "$X" ] || [ -z "$Y" ]; then
  echo "Usage: ./test/goto_xy.sh arm1|arm2 X Y [Z]"
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

CMD="M20 G90 G0 X${X} Y${Y} Z${Z} ${POSE} F${F}"

echo "ARM: $ARM"
echo "TOPIC: $TOPIC"
echo "SEND: $CMD"

source /opt/ros/humble/setup.bash
source /root/chess_robot_project/ros_ws/install/setup.bash

ros2 topic pub --once "$TOPIC" std_msgs/msg/String "{data: '$CMD'}"
