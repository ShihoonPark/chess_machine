#!/bin/bash

# Usage:
#   ./test/execute_move_8x8.sh A2 A4 pawn
#   ./test/execute_move_8x8.sh A7 A5 pawn
#   ./test/execute_move_8x8.sh A2 A6 pawn
#
# Role:
#   This script only decides direct vs relay and calls move_piece_8x8.sh.
#   It must NOT set Z values, home values, or raw_cmd directly.
#   All actual robot movement, Z, suction, timing, and home return are handled by move_piece_8x8.sh.

START=${1^^}
END=${2^^}
PIECE=${3,,}

if [ -z "$START" ] || [ -z "$END" ]; then
  echo "Usage: $0 START END [piece]"
  echo "Example: $0 A2 A4 pawn"
  exit 1
fi

if [ -z "$PIECE" ]; then
  PIECE="piece"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MOVE_SCRIPT="${SCRIPT_DIR}/move_piece_8x8.sh"

if [ ! -x "$MOVE_SCRIPT" ]; then
  echo "ERROR: move script not executable or not found: $MOVE_SCRIPT"
  exit 1
fi

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
    *)
      echo "ERROR"
      ;;
  esac
}

validate_cell() {
  local CELL="$1"
  local FILE="${CELL:0:1}"
  local RANK="${CELL:1}"

  if ! [[ "$FILE" =~ ^[A-H]$ ]]; then
    echo "ERROR: invalid file in cell $CELL"
    exit 1
  fi

  if ! [[ "$RANK" =~ ^[1-8]$ ]]; then
    echo "ERROR: invalid rank in cell $CELL"
    exit 1
  fi
}

arm_for_cell() {
  local CELL="$1"
  local RANK="${CELL:1}"

  if [ "$RANK" -le 4 ]; then
    echo "arm1"
  else
    echo "arm2"
  fi
}

choose_relay() {
  local START_CELL="$1"
  local END_CELL="$2"

  local SFILE="${START_CELL:0:1}"
  local EFILE="${END_CELL:0:1}"

  local SIDX
  local EIDX
  SIDX=$(file_index "$SFILE")
  EIDX=$(file_index "$EFILE")

  if [ "$SIDX" = "ERROR" ] || [ "$EIDX" = "ERROR" ]; then
    echo "ERROR"
    return 1
  fi

  # Pick a relay file near the average file, clamped to C~F.
  # C=2, D=3, E=4, F=5
  local AVG=$(((SIDX + EIDX) / 2))

  if [ "$AVG" -lt 2 ]; then
    AVG=2
  fi

  if [ "$AVG" -gt 5 ]; then
    AVG=5
  fi

  case "$AVG" in
    2) echo "C45" ;;
    3) echo "D45" ;;
    4) echo "E45" ;;
    5) echo "F45" ;;
    *)
      echo "D45"
      ;;
  esac
}

run_move() {
  local ARM="$1"
  local FROM="$2"
  local TO="$3"

  echo "RUN: $MOVE_SCRIPT $ARM $FROM $TO"
  "$MOVE_SCRIPT" "$ARM" "$FROM" "$TO"

  local RC=$?
  if [ "$RC" -ne 0 ]; then
    echo "ERROR: move failed: $ARM $FROM -> $TO"
    exit "$RC"
  fi
}

validate_cell "$START"
validate_cell "$END"

if [ "$START" = "$END" ]; then
  echo "ERROR: START and END are the same: $START"
  exit 1
fi

START_ARM=$(arm_for_cell "$START")
END_ARM=$(arm_for_cell "$END")

echo "START=$START"
echo "END=$END"
echo "PIECE=$PIECE"
echo "START_ARM=$START_ARM"
echo "END_ARM=$END_ARM"

if [ "$START_ARM" = "$END_ARM" ]; then
  echo "MODE=direct"
  run_move "$START_ARM" "$START" "$END"
  echo "DONE: direct $START -> $END"
  exit 0
fi

RELAY=$(choose_relay "$START" "$END")

if [ "$RELAY" = "ERROR" ] || [ -z "$RELAY" ]; then
  echo "ERROR: failed to choose relay"
  exit 1
fi

echo "MODE=relay"
echo "RELAY=$RELAY"

# Relay sequence:
# 1. start-side arm moves start -> relay
# 2. move_piece_8x8.sh returns that arm home
# 3. end-side arm moves relay -> end
# 4. move_piece_8x8.sh returns that arm home
run_move "$START_ARM" "$START" "$RELAY"
run_move "$END_ARM" "$RELAY" "$END"

echo "DONE: relay $START -> $RELAY -> $END"
