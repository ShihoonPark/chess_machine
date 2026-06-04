#!/bin/bash

ARM=${1}
START=${2^^}
END=${3^^}

Z_UP=${Z_UP:-90}
Z_PICK=${Z_PICK:-59}
Z_PLACE=${Z_PLACE:-60}

F_FAST=${F_FAST:-1800}
F_SLOW=${F_SLOW:-600}
F_HOME=${F_HOME:-1800}

SLEEP_TIME=${SLEEP_TIME:-0.15}
RELEASE_SLEEP=${RELEASE_SLEEP:-0.1}

POSE="A0 B0 C0"

HOME_X=200
HOME_Y=0
HOME_Z=${HOME_Z:-90}

if [ -z "$ARM" ] || [ -z "$START" ] || [ -z "$END" ]; then
  echo "Usage: ./test/move_piece_8x8.sh arm1|arm2 START END"
  echo "Example:"
  echo "  ./test/move_piece_8x8.sh arm1 A1 B1"
  echo "  ./test/move_piece_8x8.sh arm2 H8 G8"
  echo "  ./test/move_piece_8x8.sh arm1 A1 D45"
  echo "  ./test/move_piece_8x8.sh arm2 D45 G7"
  echo ""
  echo "Relay points: C45 D45 E45 F45"
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
    *) echo "ERR" ;;
  esac
}

is_relay_cell() {
  CELL=$1
  FILE=${CELL:0:1}
  RANK_PART=${CELL:1}

  if [ "$RANK_PART" = "45" ]; then
    case "$FILE" in
      C|D|E|F)
        return 0
        ;;
    esac
  fi

  return 1
}

check_cell() {
  CELL=$1
  FILE=${CELL:0:1}
  RANK_PART=${CELL:1}
  IDX=$(file_idx "$FILE")

  if [ "$IDX" = "ERR" ]; then
    echo "Invalid file in cell: $CELL"
    exit 1
  fi

  if is_relay_cell "$CELL"; then
    return
  fi

  if ! [[ "$RANK_PART" =~ ^[1-8]$ ]]; then
    echo "Invalid cell: $CELL"
    echo "Allowed normal cells: A1~H8"
    echo "Allowed relay points: C45 D45 E45 F45"
    exit 1
  fi
}

get_xy() {
  CELL=$1
  FILE=${CELL:0:1}
  RANK_PART=${CELL:1}
  IDX=$(file_idx "$FILE")

  if [ "$ARM" = "arm1" ]; then
    # arm1:
    # A1 = X120 Y150
    # rank +1 => X +40
    # A -> H => Y -40

    if is_relay_cell "$CELL"; then
      X=260
      Y=$((150 - IDX * 40))
    else
      RANK=$RANK_PART
      X=$((120 + (RANK - 1) * 40))
      Y=$((150 - IDX * 40))

      if [ "$RANK" -gt 4 ]; then
        echo "WARNING: arm1 target $CELL is beyond rank 4. Check reachability." >&2
      fi
    fi

  elif [ "$ARM" = "arm2" ]; then
    # arm2:
    # H8 = X120 Y150
    # rank -1 => X +40
    # A -> H => Y +40

    if is_relay_cell "$CELL"; then
      X=260
      Y=$((-130 + IDX * 40))
    else
      RANK=$RANK_PART
      X=$((120 + (8 - RANK) * 40))
      Y=$((-130 + IDX * 40))

      if [ "$RANK" -lt 5 ]; then
        echo "WARNING: arm2 target $CELL is below rank 5. Check reachability." >&2
      fi
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
echo "MOVE 8x8 / FAST RELAY POINT READY"
echo "ARM:   $ARM"
echo "TOPIC: $TOPIC"
echo "START: $START -> X$SX Y$SY"
echo "END:   $END -> X$EX Y$EY"
echo "Z_UP:    $Z_UP"
echo "Z_PICK:  $Z_PICK"
echo "Z_PLACE: $Z_PLACE"
echo "F_FAST:  $F_FAST"
echo "F_SLOW:  $F_SLOW"
echo "======================================"

source /opt/ros/humble/setup.bash
source /root/chess_robot_project/ros_ws/install/setup.bash

send_cmd "M3S0"

send_cmd "M20 G90 G0 X${SX} Y${SY} Z${Z_UP} ${POSE} F${F_FAST}"
send_cmd "M20 G90 G0 X${SX} Y${SY} Z${Z_PICK} ${POSE} F${F_SLOW}"
send_cmd "M3S1000"
send_cmd "M20 G90 G0 X${SX} Y${SY} Z${Z_UP} ${POSE} F${F_SLOW}"

send_cmd "M20 G90 G0 X${EX} Y${EY} Z${Z_UP} ${POSE} F${F_FAST}"
send_cmd "M20 G90 G0 X${EX} Y${EY} Z${Z_PLACE} ${POSE} F${F_SLOW}"
send_cmd "M3S0"

sleep "$RELEASE_SLEEP"

send_cmd "M20 G90 G0 X${EX} Y${EY} Z${Z_UP} ${POSE} F${F_SLOW}"
send_cmd "M20 G90 G0 X${HOME_X} Y${HOME_Y} Z${HOME_Z} ${POSE} F${F_HOME}"

echo "DONE"
