#!/bin/bash

START=${1^^}
END=${2^^}
PIECE=${3:-piece}

SCRIPT_DIR="/root/chess_robot_project/ros_ws/test"
MOVE_SCRIPT="${SCRIPT_DIR}/move_piece_8x8.sh"
HOME_SCRIPT="${SCRIPT_DIR}/goto_home.sh"

if [ -z "$START" ] || [ -z "$END" ]; then
  echo "Usage: ./test/execute_move_8x8.sh START END [piece]"
  echo "Example: ./test/execute_move_8x8.sh A1 G7 knight"
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
    *)
      echo "ERR"
      ;;
  esac
}

abs() {
  N=$1
  if [ "$N" -lt 0 ]; then
    echo $(( -N ))
  else
    echo "$N"
  fi
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

relay_score() {
  START_CELL=$1
  END_CELL=$2
  RELAY_FILE=$3

  SFILE=$(get_file "$START_CELL")
  EFILE=$(get_file "$END_CELL")
  SRANK=$(get_rank "$START_CELL")
  ERANK=$(get_rank "$END_CELL")

  SIDX=$(file_idx "$SFILE")
  EIDX=$(file_idx "$EFILE")
  RIDX=$(file_idx "$RELAY_FILE")

  DF1=$(abs $((SIDX - RIDX)))
  DF2=$(abs $((EIDX - RIDX)))

  # relay rank is 4.5
  # multiply by 2 to avoid decimal:
  # distance from rank r to 4.5 = abs(2*r - 9)
  DR1=$(abs $((2 * SRANK - 9)))
  DR2=$(abs $((2 * ERANK - 9)))

  # file distance also multiply by 2 to match scale
  SCORE=$((2 * DF1 + DR1 + 2 * DF2 + DR2))

  echo "$SCORE"
}

choose_relay() {
  START_CELL=$1
  END_CELL=$2

  BEST_RELAY=""
  BEST_SCORE=999999

  for RFILE in C D E F; do
    SCORE=$(relay_score "$START_CELL" "$END_CELL" "$RFILE")

    if [ "$SCORE" -lt "$BEST_SCORE" ]; then
      BEST_SCORE=$SCORE
      BEST_RELAY="${RFILE}45"
    fi
  done

  echo "$BEST_RELAY"
}

check_cell "$START"
check_cell "$END"

START_ARM=$(get_arm_by_rank "$START")
END_ARM=$(get_arm_by_rank "$END")

echo "======================================"
echo "EXECUTE 8x8 MOVE"
echo "START: $START"
echo "END:   $END"
echo "PIECE: $PIECE"
echo "START_ARM: $START_ARM"
echo "END_ARM:   $END_ARM"
echo "======================================"

echo "[INIT] Move both arms home"
"$HOME_SCRIPT" arm1
"$HOME_SCRIPT" arm2

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

echo "[SAFETY] Return $START_ARM home"
"$HOME_SCRIPT" "$START_ARM"

"$MOVE_SCRIPT" "$END_ARM" "$RELAY" "$END"

echo "[SAFETY] Return $END_ARM home"
"$HOME_SCRIPT" "$END_ARM"

echo "[DONE] relay move complete"
