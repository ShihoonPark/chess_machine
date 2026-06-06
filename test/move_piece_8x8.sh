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
    # arm2 recalibration:
    #   Use measured A-D-H anchor points for each rank.
    #   A~D and D~H are interpolated separately to handle board skew.
    #
    # measured anchors:
    #   A8 = X145 Y-130, D8 = X137 Y-10, H8 = X122 Y153
    #   A7 = X185 Y-127, D7 = X177 Y-6,  H7 = X160 Y155
    #   A6 = X225 Y-125, D6 = X215 Y-3,  H6 = X202 Y157
    #   A5 = X260 Y-125, D5 = X253 Y0,   H5 = X242 Y159
    local AX
    local AY
    local DX
    local DY
    local HX
    local HY

    case "$RANK" in
      8)
        AX=145; AY=-130; DX=137; DY=-10; HX=122; HY=153
        ;;
      7)
        AX=185; AY=-127; DX=177; DY=-6; HX=160; HY=155
        ;;
      6)
        AX=225; AY=-125; DX=215; DY=-3; HX=202; HY=157
        ;;
      5)
        AX=260; AY=-125; DX=253; DY=0; HX=242; HY=159
        ;;
      *)
        echo "ERROR: arm2 regular-cell calibration supports ranks 5~8 only: $CELL" >&2
        return 1
        ;;
    esac

    if [ "$IDX" -le 3 ]; then
      # A(0) -> D(3)
      X=$((AX + ((DX - AX) * IDX) / 3))
      Y=$((AY + ((DY - AY) * IDX) / 3))
    else
      # D(3) -> H(7)
      local T=$((IDX - 3))
      X=$((DX + ((HX - DX) * T) / 4))
      Y=$((DY + ((HY - DY) * T) / 4))
    fi
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
      C45) echo "277 -40" ;;
      D45) echo "276 1" ;;
      E45) echo "273 42" ;;
      F45) echo "270 82" ;;
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

EFFECTIVE_Z_PICK="$Z_PICK"
EFFECTIVE_Z_PLACE="$Z_PLACE"

# arm2 A-file measured pickup correction.
# Keep place height unchanged until separate place tests require an override.
if [ "$ARM" = "arm2" ]; then
  case "$START" in
    A5|A6|A7|A8)
      EFFECTIVE_Z_PICK=76
      ;;
  esac
fi

echo "ARM: $ARM"
echo "TOPIC: $TOPIC"
echo "START: $START -> X$START_X Y$START_Y"
echo "END:   $END -> X$END_X Y$END_Y"
echo "Z_UP=$Z_UP Z_PICK=$Z_PICK EFFECTIVE_Z_PICK=$EFFECTIVE_Z_PICK Z_PLACE=$Z_PLACE EFFECTIVE_Z_PLACE=$EFFECTIVE_Z_PLACE HOME_Z=$HOME_Z"
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
send_cmd "M20 G90 G0 X$START_X Y$START_Y Z$EFFECTIVE_Z_PICK A0 B0 C0 F$F_SLOW"
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
send_cmd "M20 G90 G0 X$END_X Y$END_Y Z$EFFECTIVE_Z_PLACE A0 B0 C0 F$F_SLOW"
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
