#!/bin/bash

ARM=${1,,}
START=${2^^}
END=${3^^}

if [ -z "$ARM" ] || [ -z "$START" ] || [ -z "$END" ]; then
  echo "Usage: $0 arm1|arm2 START END"
  echo "Example: $0 arm1 A2 A4"
  echo "Example: $0 arm2 H7 H5"
  echo "Example: $0 arm1 D4 CAP1_1"
  echo "Example: $0 arm2 D5 CAP2_1"
  exit 1
fi

case "$ARM" in
  arm1)
    TOPIC="/arm1/raw_cmd"

    DEFAULT_Z_PICK=76
    DEFAULT_Z_PLACE=77

    DEFAULT_TRAVEL_SLEEP=1.5
    DEFAULT_PICK_SETTLE_SLEEP=1.0
    DEFAULT_SUCTION_SLEEP=1.0
    DEFAULT_PLACE_SETTLE_SLEEP=0.3
    DEFAULT_RELEASE_SLEEP=0.2
    DEFAULT_LIFT_SLEEP=0.3
    ;;
  arm2)
    TOPIC="/arm2/raw_cmd"

    DEFAULT_Z_PICK=77
    DEFAULT_Z_PLACE=78

    DEFAULT_TRAVEL_SLEEP=2.0
    DEFAULT_PICK_SETTLE_SLEEP=1.2
    DEFAULT_SUCTION_SLEEP=1.2
    DEFAULT_PLACE_SETTLE_SLEEP=1.0
    DEFAULT_RELEASE_SLEEP=1.0
    DEFAULT_LIFT_SLEEP=0.3
    ;;
  *)
    echo "ERROR: ARM must be arm1 or arm2"
    exit 1
    ;;
esac

# Safe travel height.
Z_UP=${Z_UP:-120}
HOME_Z=${HOME_Z:-120}

# Arm-specific pick/place height.
Z_PICK=${Z_PICK:-$DEFAULT_Z_PICK}
Z_PLACE=${Z_PLACE:-$DEFAULT_Z_PLACE}

F_FAST=${F_FAST:-1800}
F_SLOW=${F_SLOW:-600}
F_HOME=${F_HOME:-1800}

# Keep global command delay short.
SLEEP_TIME=${SLEEP_TIME:-0.15}

# Arm-specific timing defaults.
TRAVEL_SLEEP=${TRAVEL_SLEEP:-$DEFAULT_TRAVEL_SLEEP}
PICK_SETTLE_SLEEP=${PICK_SETTLE_SLEEP:-$DEFAULT_PICK_SETTLE_SLEEP}
SUCTION_SLEEP=${SUCTION_SLEEP:-$DEFAULT_SUCTION_SLEEP}
PLACE_SETTLE_SLEEP=${PLACE_SETTLE_SLEEP:-$DEFAULT_PLACE_SETTLE_SLEEP}
RELEASE_SLEEP=${RELEASE_SLEEP:-$DEFAULT_RELEASE_SLEEP}
LIFT_SLEEP=${LIFT_SLEEP:-$DEFAULT_LIFT_SLEEP}

# Extra wait after home command to prevent next move from starting too early.
HOME_SLEEP=${HOME_SLEEP:-1.5}

# Home closer to robot body to reduce relay collision risk.
HOME_X=${HOME_X:-140}
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
    # arm1 calibration:
    #   A2 = X170 Y145
    #   A4 = X245 Y146
    #   H2 = X177 Y-139
    #
    # rank vector:
    #   A2 -> A4 = 2 ranks = (+75, +1)
    # file vector:
    #   A2 -> H2 = 7 files = (+7, -284)
    X=$((170 + ((RANK - 2) * 75) / 2 + IDX))
    Y=$((145 + ((RANK - 2) * 1) / 2 - (IDX * 284) / 7))
  else
    # arm2 calibration:
    #   H7 = X165 Y150
    #   H5 = X245 Y150
    #   A7 = X180 Y-131
    #
    # rank direction:
    #   rank decreases by 1 -> X +40
    # file direction:
    #   A -> H = X -15, Y +281
    X=$((180 + (7 - RANK) * 40 - (IDX * 15) / 7))
    Y=$((-131 + (IDX * 281) / 7))
  fi

  echo "$X $Y"
}

relay_xy() {
  local ARM_NAME="$1"
  local RELAY="$2"

  if [ "$ARM_NAME" = "arm1" ]; then
    # arm1 relay measured directly.
    case "$RELAY" in
      C45) echo "270 66" ;;
      D45) echo "270 26" ;;
      E45) echo "270 -14" ;;
      F45) echo "270 -54" ;;
      *)
        echo "ERROR: invalid relay $RELAY" >&2
        return 1
        ;;
    esac
  else
    # arm2 relay measured directly.
    # Y values were adjusted +5 from the earlier candidates.
    case "$RELAY" in
      C45) echo "277 -46" ;;
      D45) echo "277 -6" ;;
      E45) echo "277 34" ;;
      F45) echo "275 74" ;;
      *)
        echo "ERROR: invalid relay $RELAY" >&2
        return 1
        ;;
    esac
  fi
}

capture_xy() {
  local ARM_NAME="$1"
  local CAP="$2"

  case "$ARM_NAME:$CAP" in
    # arm1 CAP1 slots.
    arm1:CAP1_1) echo "135 -180" ;;
    arm1:CAP1_2) echo "170 -180" ;;
    arm1:CAP1_3) echo "205 -180" ;;
    arm1:CAP1_4) echo "240 -180" ;;

    # arm2 CAP2 slots.
    # CAP2_4 is disabled because X245 Y190 is outside safe workspace.
    arm2:CAP2_1) echo "125 190" ;;
    arm2:CAP2_2) echo "165 190" ;;
    arm2:CAP2_3) echo "205 190" ;;
    arm2:CAP2_4)
      echo "ERROR: CAP2_4 is disabled because it is outside the safe workspace" >&2
      return 1
      ;;

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
echo "SLEEP_TIME=$SLEEP_TIME"
echo "TRAVEL_SLEEP=$TRAVEL_SLEEP PICK_SETTLE_SLEEP=$PICK_SETTLE_SLEEP SUCTION_SLEEP=$SUCTION_SLEEP"
echo "PLACE_SETTLE_SLEEP=$PLACE_SETTLE_SLEEP RELEASE_SLEEP=$RELEASE_SLEEP LIFT_SLEEP=$LIFT_SLEEP HOME_SLEEP=$HOME_SLEEP"
echo "HOME: X$HOME_X Y$HOME_Y Z$HOME_Z"

# Safety: suction off first.
send_cmd "$SUCTION_OFF"

# Move above start.
send_cmd "M20 G90 G0 X$START_X Y$START_Y Z$Z_UP A0 B0 C0 F$F_FAST"
sleep "$TRAVEL_SLEEP"

# Move down to pick height.
send_cmd "M20 G90 G0 X$START_X Y$START_Y Z$Z_PICK A0 B0 C0 F$F_SLOW"
sleep "$PICK_SETTLE_SLEEP"

# Suction on and wait until the block is attached.
send_cmd "$SUCTION_ON"
sleep "$SUCTION_SLEEP"

# Lift fully before horizontal movement.
send_cmd "M20 G90 G0 X$START_X Y$START_Y Z$Z_UP A0 B0 C0 F$F_SLOW"
sleep "$LIFT_SLEEP"

# Move above end.
send_cmd "M20 G90 G0 X$END_X Y$END_Y Z$Z_UP A0 B0 C0 F$F_FAST"
sleep "$TRAVEL_SLEEP"

# Move down to place height.
send_cmd "M20 G90 G0 X$END_X Y$END_Y Z$Z_PLACE A0 B0 C0 F$F_SLOW"
sleep "$PLACE_SETTLE_SLEEP"

# Suction off and wait until the block is released.
send_cmd "$SUCTION_OFF"
sleep "$RELEASE_SLEEP"

# Lift fully before returning home.
send_cmd "M20 G90 G0 X$END_X Y$END_Y Z$Z_UP A0 B0 C0 F$F_SLOW"
sleep "$LIFT_SLEEP"

# Return home.
send_cmd "$SUCTION_OFF"
send_cmd "M20 G90 G0 X$HOME_X Y$HOME_Y Z$HOME_Z A0 B0 C0 F$F_HOME"
sleep "$HOME_SLEEP"

echo "DONE: $ARM $START -> $END"
