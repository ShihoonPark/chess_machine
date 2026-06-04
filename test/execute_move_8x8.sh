#!/bin/bash

START=${1^^}
END=${2^^}
PIECE=${3:-piece}

export Z_UP=${Z_UP:-90}
export Z_PICK=${Z_PICK:-59}
export Z_PLACE=${Z_PLACE:-60}
export HOME_Z=${HOME_Z:-90}

export F_FAST=${F_FAST:-1800}
export F_SLOW=${F_SLOW:-600}
export F_HOME=${F_HOME:-1800}

export SLEEP_TIME=${SLEEP_TIME:-0.15}
export RELEASE_SLEEP=${RELEASE_SLEEP:-0.1}

SCRIPT_DIR="/root/chess_robot_project/ros_ws/test"
MOVE_SCRIPT="${SCRIPT_DIR}/move_piece_8x8.sh"
HOME_SCRIPT="${SCRIPT_DIR}/goto_home.sh"

if [ -z "$START" ] || [ -z "$END" ]; then
  echo "Usage: ./test/execute_move_8x8.sh START END [piece]"
  echo "Example: ./test/execute_move_8x8.sh A1 G7 bishop"
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

idx_file() {
  case "$1" in
    0) echo A ;;
    1) echo B ;;
    2) echo C ;;
    3) echo D ;;
    4) echo E ;;
    5) echo F ;;
    6) echo G ;;
    7) echo H ;;
    *) echo "ERR" ;;
  esac
}

check_cell() {
  CELL=$1
  FILE=${CELL:0:1}
  RANK=${CELL:1:1}

  IDX=$(file_idx "$FILE")

  if [ "$IDX" = "ERR" ]; then
    echo "Invalid file: $CELL"
    exit 1
  fi

  if ! [[ "$RANK" =~ ^[1-8]$ ]]; then
    echo "Invalid rank: $CELL"
    exit 1
  fi
}

get_file() {
  CELL=$1
  echo "${CELL:0:1}"
}

get_rank() {
  CELL=$1
  echo "${CELL:1:1}"
}

get_arm_by_rank() {
  CELL=$1
  RANK=$(get_rank "$CELL")

  if [ "$RANK" -le 4 ]; then
    echo "arm1"
  else
    echo "arm2"
  fi
}

choose_relay() {
  START_CELL=$1
  END_CELL=$2

  SFILE=$(get_file "$START_CELL")
  EFILE=$(get_file "$END_CELL")

  SIDX=$(file_idx "$SFILE")
  EIDX=$(file_idx "$EFILE")

  AVG=$(((SIDX + EIDX) / 2))

  # relay는 C45~F45만 사용
  if [ "$AVG" -lt 2 ]; then
    AVG=2
  fi

  if [ "$AVG" -gt 5 ]; then
    AVG=5
  fi

  RFILE=$(idx_file "$AVG")
  echo "${RFILE}45"
}

check_cell "$START"
check_cell "$END"

PIECE=$(echo "$PIECE" | tr '[:upper:]' '[:lower:]')

START_ARM=$(get_arm_by_rank "$START")
END_ARM=$(get_arm_by_rank "$END")

echo "======================================"
echo "EXECUTE 8x8 FAST MOVE"
echo "START: $START"
echo "END:   $END"
echo "PIECE: $PIECE"
echo "START_ARM: $START_ARM"
echo "END_ARM:   $END_ARM"
echo "Z_UP=$Z_UP Z_PICK=$Z_PICK Z_PLACE=$Z_PLACE HOME_Z=$HOME_Z"
echo "F_FAST=$F_FAST F_SLOW=$F_SLOW F_HOME=$F_HOME"
echo "SLEEP_TIME=$SLEEP_TIME RELEASE_SLEEP=$RELEASE_SLEEP"
echo "NOTE: piece rule validation is handled by TOPST later."
echo "======================================"

echo "[INIT] Move both arms home"
"$HOME_SCRIPT" arm1 "$HOME_Z"
"$HOME_SCRIPT" arm2 "$HOME_Z"

if [ "$START_ARM" = "$END_ARM" ]; then
  echo "[MODE] direct"
  echo "[STEP 1] $START_ARM: $START -> $END"

  "$MOVE_SCRIPT" "$START_ARM" "$START" "$END"

  echo "[DONE] direct move complete"
  exit 0
fi

RELAY=$(choose_relay "$START" "$END")

echo "[MODE] relay"
echo "[RELAY] selected relay point: $RELAY"
echo "[STEP 1] $START_ARM: $START -> $RELAY"
echo "[STEP 2] $END_ARM:   $RELAY -> $END"

"$MOVE_SCRIPT" "$START_ARM" "$START" "$RELAY"

# move_piece_8x8.sh already returns the arm home.
# Do not call goto_home again here.

"$MOVE_SCRIPT" "$END_ARM" "$RELAY" "$END"

# move_piece_8x8.sh already returns the arm home.
# Do not call goto_home again here.

echo "[DONE] relay move complete"
