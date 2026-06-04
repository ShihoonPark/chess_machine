#!/bin/bash

START=${1^^}
END=${2^^}

Z_UP=90
Z_DOWN=59
F_FAST=1200
F_SLOW=400

get_xy() {
  case "$1" in
    A3) echo "160 -40" ;;
    B3) echo "160 0" ;;
    C3) echo "160 40" ;;
    A2) echo "200 -40" ;;
    B2) echo "200 0" ;;
    C2) echo "200 40" ;;
    A1) echo "240 -40" ;;
    B1) echo "240 0" ;;
    C1) echo "240 40" ;;
    *) echo "ERROR"; exit 1 ;;
  esac
}

send_cmd() {
  echo "SEND: $1"
  ros2 topic pub --once /raw_cmd std_msgs/msg/String "{data: '$1'}"
  sleep 1.2
}

read SX SY <<< $(get_xy "$START")
read TX TY <<< $(get_xy "$END")

echo "MOVE: $START -> $END"

send_cmd "M20 G90 G0 X$SX Y$SY Z$Z_UP A0 B0 C0 F$F_FAST"
send_cmd "M20 G90 G0 X$SX Y$SY Z$Z_DOWN A0 B0 C0 F$F_SLOW"
send_cmd "M3S1000"
send_cmd "M20 G90 G0 X$SX Y$SY Z$Z_UP A0 B0 C0 F300"
send_cmd "M20 G90 G0 X$TX Y$TY Z$Z_UP A0 B0 C0 F$F_FAST"
send_cmd "M20 G90 G0 X$TX Y$TY Z$Z_DOWN A0 B0 C0 F$F_SLOW"
send_cmd "M3S0"
send_cmd "M20 G90 G0 X$TX Y$TY Z$Z_UP A0 B0 C0 F$F_FAST"

echo "DONE"
