#!/bin/bash

ARM=${1}
CELL=${2^^}
Z=${3:-70}

F=700
POSE="A0 B0 C0"

if [ -z "$ARM" ] || [ -z "$CELL" ]; then
  echo "Usage: ./test/goto_cell.sh arm1|arm2 CELL [Z]"
  echo "Example: ./test/goto_cell.sh arm1 A1 70"
  exit 1
fi

FILE=${CELL:0:1}
RANK=${CELL:1:1}

case "$FILE" in
  A) FILE_IDX=0 ;;
  B) FILE_IDX=1 ;;
  C) FILE_IDX=2 ;;
  D) FILE_IDX=3 ;;
  E) FILE_IDX=4 ;;
  F) FILE_IDX=5 ;;
  G) FILE_IDX=6 ;;
  H) FILE_IDX=7 ;;
  *)
    echo "Invalid file: $FILE"
    exit 1
    ;;
esac

if ! [[ "$RANK" =~ ^[1-8]$ ]]; then
  echo "Invalid rank: $RANK"
  exit 1
fi

if [ "$ARM" = "arm1" ]; then
  TOPIC="/arm1/raw_cmd"

  # arm1: A1 = X120, Y150
  # rank increases upward: X +40
  # A -> H: Y -40
  X=$((120 + (RANK - 1) * 40))
  Y=$((150 - FILE_IDX * 40))

elif [ "$ARM" = "arm2" ]; then
  TOPIC="/arm2/raw_cmd"

  # arm2: H8 = X120, Y150
  # rank decreases as X +40
  # A -> H: Y +40
  X=$((120 + (8 - RANK) * 40))
  Y=$((-130 + FILE_IDX * 40))

else
  echo "ARM must be arm1 or arm2"
  exit 1
fi

CMD="M20 G90 G0 X${X} Y${Y} Z${Z} ${POSE} F${F}"

echo "ARM: $ARM"
echo "CELL: $CELL"
echo "X: $X"
echo "Y: $Y"
echo "Z: $Z"
echo "TOPIC: $TOPIC"
echo "SEND: $CMD"

source /opt/ros/humble/setup.bash
source /root/chess_robot_project/ros_ws/install/setup.bash

ros2 topic pub --once "$TOPIC" std_msgs/msg/String "{data: '$CMD'}"
