#!/bin/bash

ARM=${1,,}
START=${2^^}
END=${3^^}

if [ -z "$ARM" ] || [ -z "$START" ] || [ -z "$END" ]; then
  echo "Usage: $0 arm1|arm2 START END"
  echo "Example: $0 arm1 A2 A4"
  echo "Example: $0 arm1 D4 CAP1_1"
  exit 1
fi

case "$ARM" in
  arm1)
    TOPIC="/arm1/raw_cmd"
    ;;
  arm2)
    TOPIC="/arm2/raw_cmd"
    ;;
  *)
    echo "ERROR: ARM must be arm1 or arm2"
    exit 1
    ;;
esac

# New board defaults: old Z values +10mm for 1cm urethane board.
Z_UP=${Z_UP:-100}
HOME_Z=${HOME_Z:-100}
Z_PICK=${Z_PICK:-69}
Z_PLACE=${Z_PLACE:-70}

F_FAST=${F_FAST:-1800}
F_SLOW=${F_SLOW:-600}
F_HOME=${F_HOME:-1800}

SLEEP_TIME=${SLEEP_TIME:-0.15}
RELEASE_SLEEP=${RELEASE_SLEEP:-0.1}

HOME_X=${HOME_X:-200}
HOME_Y=${HOME_Y:-0}

SUCTION_ON=${SUCTION_ON:-M3S1000}
SUCTION_OFF=${SUCTION_OFF:-M3S0}

send_cmd() {
  local CMD="$1"
  echo "SEND[$ARM]: $CMD"
  ros2 topic pub --once "$TOPIC" std_msgs/msg/String "{data: '$CMD'}"
  sleep "$SLEEP_TIME"
}

file_index() {
  case "$1" in
    A) echo 0 ;;
    B) echo 1 ;;
    C) echo 2 ;;
    D) echo 3 ;;
    E) echo 4 ;;
    F) echo 5 ;;
    G) echo 6 ;;
    H) echo 7 ;;
    *) echo "ERROR" ;;
  esac
}

regular_cell_xy() {
  local ARM_NAME="$1"
  local CELL="$2"

  local FILE="${CELL:0:1}"
  local RANK="${CELL:1}"

  local IDX
  IDX=$(file_index "$FILE")

  if [ "$IDX" = "ERROR" ]; then
    echo "ERROR: invalid file in cell $CELL" >&2
    return 1
  fi

  if ! [[ "$RANK" =~ ^[1-8]$ ]]; then
    echo "ERROR: invalid rank in cell $CELL" >&2
    return 1
  fi

  local X
  local Y

  if [ "$ARM_NAME" = "arm1" ]; then
    # arm1 new board calibration:
    # A2 = X145 Y145
    # A4 = X225 Y145
    # H2 = X145 Y-140
    # X direction: 40mm per rank
    # Y direction: A~H total 285mm, divided by 7 intervals
    X=$((105 + (RANK - 1) * 40))
    Y=$((145 - (IDX * 285) / 7))
  else
    # arm2 is still using previous calibration.
    # Recalibrate arm2 after arm1 test.
    X=$((120 + (8 - RANK) * 40))
    Y=$((-130 + IDX * 40))
  fi

  echo "$X $Y"
}

relay_xy() {
  local ARM_NAME="$1"
  local RELAY="$2"

  local FILE="${RELAY:0:1}"
  local IDX
  IDX=$(file_index "$FILE")

  if [ "$IDX" = "ERROR" ]; then
    echo "ERROR: invalid relay $RELAY" >&2
    return 1
  fi

  local X=260
  local Y

  if [ "$ARM_NAME" = "arm1" ]; then
    Y=$((145 - (IDX * 285) / 7))
  else
    Y=$((-130 + IDX * 40))
  fi

  echo "$X $Y"
}

capture_xy() {
  local ARM_NAME="$1"
  local CAP="$2"

  case "$ARM_NAME:$CAP" in
    arm1:CAP1_1) echo "105 -180" ;;
    arm1:CAP1_2) echo "145 -180" ;;
    arm1:CAP1_3) echo "185 -180" ;;
    arm1:CAP1_4) echo "225 -180" ;;

    arm2:CAP2_1) echo "95 185" ;;
    arm2:CAP2_2) echo "135 185" ;;
    arm2:CAP2_3) echo "175 185" ;;
    arm2:CAP2_4) echo "215 185" ;;

    arm1:CAP2_*|arm2:CAP1_*)
      echo "ERROR: $CAP is not for $ARM_NAME" >&2
      return 1
      ;;

    *)
      echo "ERROR: unknown capture slot $CAP for $ARM_NAME" >&2
      return 1
      ;;
  esac
}

cell_xy() {
  local ARM_NAME="$1"
  local CELL="$2"

  case "$CELL" in
    CAP1_*|CAP2_*)
      capture_xy "$ARM_NAME" "$CELL"
      ;;
    C45|D45|E45|F45)
      relay_xy "$ARM_NAME" "$CELL"
      ;;
    [A-H][1-8])
      regular_cell_xy "$ARM_NAME" "$CELL"
      ;;
    *)
      echo "ERROR: unknown cell or slot: $CELL" >&2
      return 1
      ;;
  esac
}

START_XY=$(cell_xy "$ARM" "$START") || exit 1
END_XY=$(cell_xy "$ARM" "$END") || exit 1

START_X=$(echo "$START_XY" | awk '{print $1}')
START_Y=$(echo "$START_XY" | awk '{print $2}')
END_X=$(echo "$END_XY" | awk '{print $1}')
END_Y=$(echo "$END_XY" | awk '{print $2}')

echo "ARM: $ARM"
echo "TOPIC: $TOPIC"
echo "START: $START -> X$START_X Y$START_Y"
echo "END:   $END -> X$END_X Y$END_Y"
echo "Z_UP=$Z_UP Z_PICK=$Z_PICK Z_PLACE=$Z_PLACE HOME_Z=$HOME_Z"
echo "F_FAST=$F_FAST F_SLOW=$F_SLOW F_HOME=$F_HOME"

send_cmd "$SUCTION_OFF"

send_cmd "M20 G90 G0 X$START_X Y$START_Y Z$Z_UP A0 B0 C0 F$F_FAST"

send_cmd "M20 G90 G0 X$START_X Y$START_Y Z$Z_PICK A0 B0 C0 F$F_SLOW"
send_cmd "$SUCTION_ON"
sleep "$SLEEP_TIME"

send_cmd "M20 G90 G0 X$START_X Y$START_Y Z$Z_UP A0 B0 C0 F$F_SLOW"

send_cmd "M20 G90 G0 X$END_X Y$END_Y Z$Z_UP A0 B0 C0 F$F_FAST"

send_cmd "M20 G90 G0 X$END_X Y$END_Y Z$Z_PLACE A0 B0 C0 F$F_SLOW"
send_cmd "$SUCTION_OFF"
sleep "$RELEASE_SLEEP"

send_cmd "M20 G90 G0 X$END_X Y$END_Y Z$Z_UP A0 B0 C0 F$F_SLOW"

send_cmd "$SUCTION_OFF"
send_cmd "M20 G90 G0 X$HOME_X Y$HOME_Y Z$HOME_Z A0 B0 C0 F$F_HOME"

echo "DONE: $ARM $START -> $END"
