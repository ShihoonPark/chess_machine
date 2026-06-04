#!/bin/bash

ARM=${1}
START=${2^^}
END=${3^^}

Z_UP=${Z_UP:-100}
Z_PICK=${Z_PICK:-59}
Z_PLACE=${Z_PLACE:-60}

F_FAST=${F_FAST:-700}
F_SLOW=${F_SLOW:-300}
F_HOME=${F_HOME:-700}

SLEEP_TIME=${SLEEP_TIME:-1.2}
RELEASE_SLEEP=${RELEASE_SLEEP:-0.8}

POSE="A0 B0 C0"

HOME_X=200
HOME_Y=0
HOME_Z=${HOME_Z:-100}

if [ -z "$ARM" ] || [ -z "$START" ] || [ -z "$END" ]; then
  echo "Usage: ./test/move_piece_8x8.sh arm1|arm2 START END"
  echo "Example: ./test/move_piece_8x8.sh arm1 A1 B1"
  echo "Example: ./test/move_piece_8x8.sh arm2 H8 G8"
  echo ""
  echo "Optional env:"
  echo "  Z_UP=100 Z_PICK=59 Z_PLACE=60 F_FAST=700 F_SLOW=300"
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

file_idx() {
  case "$1" in
    A) echo 0 ;;
    B) echo 1 ;;
    C) echo 2 ;;
    D) echo 3 ;;
    E) echo 4 ;;
    F) echo 5 ;;
    G) echo 6 ;;
    H) echo 7 ;;
    *)
      echo "ERR"
      ;;
  esac
}

check_cell() {
  CELL=$1
  FILE=${CELL:0:1}
  RANK=${CELL:1:1}

  IDX=$(file_idx "$FILE")

  if [ "$IDX" = "ERR" ]; then
    echo "Invalid file in cell: $CELL"
    exit 1
  fi

  if ! [[ "$RANK" =~ ^[1-8]$ ]]; then
    echo "Invalid rank in cell: $CELL"
    exit 1
  fi
}

get_xy() {
  CELL=$1
  FILE=${CELL:0:1}
  RANK=${CELL:1:1}
  IDX=$(file_idx "$FILE")

  if [ "$ARM" = "arm1" ]; then
    # arm1 calibration:
    # A1 = X120, Y150
    # rank increases: X +40
    # A -> H: Y -40
    X=$((120 + (RANK - 1) * 40))
    Y=$((150 - IDX * 40))

    if [ "$RANK" -gt 4 ]; then
      echo "WARNING: arm1 target $CELL is beyond rank 4. Check reachability." >&2
    fi

  elif [ "$ARM" = "arm2" ]; then
    # arm2 calibration:
    # H8 = X120, Y150
    # rank decreases: X +40
    # A -> H: Y +40
    X=$((120 + (8 - RANK) * 40))
    Y=$((-130 + IDX * 40))

    if [ "$RANK" -lt 5 ]; then
      echo "WARNING: arm2 target $CELL is below rank 5. Check reachability." >&2
    fi
  fi

  echo "$X $Y"
}

send_cmd() {
  CMD="$1"
  echo "SEND: $CMD"
  ros2 topic pub --once "$TOPIC" std_msgs/msg/String "{data: '$CMD'}"
  sleep "$SLEEP_TIME"
}

check_cell "$START"
check_cell "$END"

read SX SY <<< "$(get_xy "$START")"
read EX EY <<< "$(get_xy "$END")"

echo "======================================"
echo "MOVE 8x8"
echo "ARM:   $ARM"
echo "TOPIC: $TOPIC"
echo "START: $START -> X$SX Y$SY"
echo "END:   $END -> X$EX Y$EY"
echo "Z_UP:    $Z_UP"
echo "Z_PICK:  $Z_PICK"
echo "Z_PLACE: $Z_PLACE"
echo "======================================"

source /opt/ros/humble/setup.bash
source /root/chess_robot_project/ros_ws/install/setup.bash

# Always turn suction off first
send_cmd "M3S0"

# Move above start
send_cmd "M20 G90 G0 X${SX} Y${SY} Z${Z_UP} ${POSE} F${F_FAST}"

# Down to pick
send_cmd "M20 G90 G0 X${SX} Y${SY} Z${Z_PICK} ${POSE} F${F_SLOW}"

# Suction ON
send_cmd "M3S1000"

# Lift after pick
send_cmd "M20 G90 G0 X${SX} Y${SY} Z${Z_UP} ${POSE} F${F_SLOW}"

# Move above end
send_cmd "M20 G90 G0 X${EX} Y${EY} Z${Z_UP} ${POSE} F${F_FAST}"

# Down to place
send_cmd "M20 G90 G0 X${EX} Y${EY} Z${Z_PLACE} ${POSE} F${F_SLOW}"

# Suction OFF
send_cmd "M3S0"

# Wait after release so the block settles
sleep "$RELEASE_SLEEP"

# Lift after place
send_cmd "M20 G90 G0 X${EX} Y${EY} Z${Z_UP} ${POSE} F${F_SLOW}"

# Return home
send_cmd "M20 G90 G0 X${HOME_X} Y${HOME_Y} Z${HOME_Z} ${POSE} F${F_HOME}"

echo "DONE"
