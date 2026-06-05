#!/usr/bin/env python3
import os
import sys
import time
import termios
import select

BAUD = termios.B115200


def open_serial(path):
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    attrs = termios.tcgetattr(fd)

    attrs[0] = 0
    attrs[1] = 0
    attrs[2] = termios.CS8 | termios.CLOCAL | termios.CREAD
    attrs[3] = 0
    attrs[4] = BAUD
    attrs[5] = BAUD
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 1

    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    return fd


def read_some(fd, duration=1.0):
    end = time.time() + duration
    buf = b""

    while time.time() < end:
        rlist, _, _ = select.select([fd], [], [], 0.1)
        if fd not in rlist:
            continue

        try:
            data = os.read(fd, 4096)
        except BlockingIOError:
            continue

        if data:
            buf += data

    return buf.decode(errors="ignore")


def send(fd, text):
    os.write(fd, text.encode())


def send_line(fd, text):
    send(fd, text + "\n")


def print_block(title, text):
    print("\n========== " + title + " ==========")
    print(text)


def ensure_login_and_shell(fd):
    # Wake console
    send(fd, "\n")
    time.sleep(0.3)
    out = read_some(fd, 1.0)
    print_block("WAKE", out)

    if "login:" in out:
        send_line(fd, "root")
        time.sleep(0.3)
        out += read_some(fd, 1.0)
        print_block("LOGIN USER", out)

    if "Password:" in out or "password:" in out:
        send_line(fd, "root")
        time.sleep(0.5)
        out += read_some(fd, 1.5)
        print_block("LOGIN PASS", out)

    # Try to get clean shell prompt
    send(fd, "\x03")
    time.sleep(0.3)
    send_line(fd, "")
    out = read_some(fd, 1.0)
    print_block("SHELL CHECK", out)

    return out


def start_rule_checker(fd):
    send_line(fd, "cd /home/root")
    time.sleep(0.2)
    read_some(fd, 0.5)

    send_line(fd, "chmod +x rule_checker.py")
    time.sleep(0.2)
    read_some(fd, 0.5)

    send_line(fd, "./rule_checker.py")
    time.sleep(0.8)
    out = read_some(fd, 2.0)
    print_block("START RULE CHECKER", out)

    if "TOPST_RULE_CHECKER_READY" not in out:
        print("WARN: rule_checker ready message not detected.")
        print("Check whether /home/root/rule_checker.py exists on TOPST.")


def send_rule_cmd(fd, cmd, wait=1.0):
    print("\n>>> " + cmd)
    send_line(fd, cmd)
    time.sleep(0.2)
    out = read_some(fd, wait)
    print(out)
    return out


def main():
    port = "/dev/ttyUSB0"
    if len(sys.argv) >= 2:
        port = sys.argv[1]

    fd = open_serial(port)

    try:
        ensure_login_and_shell(fd)
        start_rule_checker(fd)

        send_rule_cmd(fd, "REQ A2 A4 pawn")
        send_rule_cmd(fd, "BOARD", wait=1.5)
        send_rule_cmd(fd, "COMMIT")
        send_rule_cmd(fd, "REQ B2 B4 pawn")
        send_rule_cmd(fd, "REQ A7 A5 pawn")
        send_rule_cmd(fd, "CANCEL")
        send_rule_cmd(fd, "BOARD", wait=1.5)

        # Stop rule_checker and return to shell
        send(fd, "\x03")
        time.sleep(0.3)
        out = read_some(fd, 1.0)
        print_block("STOP", out)

    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
