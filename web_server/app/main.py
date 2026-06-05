from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path
import subprocess
import threading
import shlex
import os
import time
import termios
import select


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ROS_WS = Path("/root/chess_robot_project/ros_ws")
EXECUTE_SCRIPT = ROS_WS / "test" / "execute_move_8x8.sh"

TOPST_PORT = "/dev/ttyUSB0"
TOPST_RULE_PATH = "/home/root/rule_checker.py"

FILES = "ABCDEFGH"
RANKS = "12345678"
ALLOWED_CELLS = {f"{file}{rank}" for file in FILES for rank in RANKS}

robot_lock = threading.Lock()
topst_lock = threading.Lock()


class ExecuteRequest(BaseModel):
    start: str
    end: str
    piece: str = "piece"


class TopstConsole:
    def __init__(self, port: str):
        self.port = port
        self.fd = None
        self.started = False

    def open(self):
        if self.fd is not None:
            return

        if not os.path.exists(self.port):
            raise RuntimeError(f"TOPST port not found: {self.port}")

        self.fd = os.open(self.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)

        attrs = termios.tcgetattr(self.fd)
        attrs[0] = 0
        attrs[1] = 0
        attrs[2] = termios.CS8 | termios.CLOCAL | termios.CREAD
        attrs[3] = 0
        attrs[4] = termios.B115200
        attrs[5] = termios.B115200
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 1

        termios.tcsetattr(self.fd, termios.TCSANOW, attrs)

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
            self.started = False

    def send(self, text: str):
        self.open()
        os.write(self.fd, text.encode())

    def send_line(self, text: str):
        self.send(text + "\n")

    def read_some(self, duration: float = 1.0) -> str:
        self.open()
        end_time = time.time() + duration
        buf = b""

        while time.time() < end_time:
            rlist, _, _ = select.select([self.fd], [], [], 0.1)

            if self.fd not in rlist:
                continue

            try:
                data = os.read(self.fd, 4096)
            except BlockingIOError:
                continue

            if data:
                buf += data

        return buf.decode(errors="ignore")

    def wake_and_login(self):
        self.open()

        self.send("\n")
        time.sleep(0.3)
        out = self.read_some(1.0)

        if "login:" in out:
            self.send_line("root")
            time.sleep(0.3)
            out += self.read_some(1.0)

        if "Password:" in out or "password:" in out:
            self.send_line("root")
            time.sleep(0.5)
            out += self.read_some(1.5)

        # rule_checker가 이미 떠 있거나 콘솔이 꼬였을 수도 있으니 한 번 정리
        self.send("\x03")
        time.sleep(0.3)
        self.send_line("")
        self.read_some(1.0)

    def start_rule_checker(self):
        self.open()

        self.wake_and_login()

        self.send_line("cd /home/root")
        time.sleep(0.2)
        self.read_some(0.5)

        self.send_line(f"chmod +x {TOPST_RULE_PATH}")
        time.sleep(0.2)
        self.read_some(0.5)

        self.send_line(TOPST_RULE_PATH)
        time.sleep(0.8)
        out = self.read_some(2.0)

        if "TOPST_RULE_CHECKER_READY" not in out:
            raise RuntimeError(
                "TOPST rule_checker did not start. "
                f"Output was:\n{out}"
            )

        self.started = True

    def ensure_started(self):
        if not self.started:
            self.start_rule_checker()

    def extract_response(self, raw: str, command: str):
        command = command.strip()
        result = None

        lines = raw.replace("\r", "\n").split("\n")

        for line in lines:
            clean = line.strip()

            if not clean:
                continue

            # echo된 명령은 제외
            if clean == command:
                continue

            # 안내 문구/프롬프트 제외
            if clean.startswith("TOPST_RULE_CHECKER_READY"):
                continue
            if clean.startswith("CMDS:"):
                continue
            if "root@telechips" in clean:
                continue
            if clean == "^C":
                continue

            # rule_checker의 실제 응답만 채택
            if (
                clean.startswith("OK ")
                or clean.startswith("ERR ")
                or clean.startswith("BOARD ")
            ):
                result = clean

        return result

    def command(self, command: str, timeout: float = 3.0) -> str:
        self.ensure_started()

        self.send_line(command)

        end_time = time.time() + timeout
        raw = ""

        while time.time() < end_time:
            raw += self.read_some(0.3)
            response = self.extract_response(raw, command)

            if response is not None:
                return response

        raise RuntimeError(f"TOPST response timeout for command: {command}\nRAW:\n{raw}")


topst = TopstConsole(TOPST_PORT)


def normalize_cell(cell: str) -> str:
    return cell.upper().strip()


def validate_cell(cell: str):
    if cell not in ALLOWED_CELLS:
        raise HTTPException(status_code=400, detail=f"Invalid cell: {cell}")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "execute_script_exists": EXECUTE_SCRIPT.exists(),
        "topst_port": TOPST_PORT,
        "topst_port_exists": os.path.exists(TOPST_PORT),
        "mode": "8x8_dual_arm_execute_with_topst_rule_checker",
    }


@app.get("/topst/board")
def topst_board():
    with topst_lock:
        try:
            response = topst.command("BOARD", timeout=4.0)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return {"status": "success", "response": response}


@app.post("/topst/reset")
def topst_reset():
    with topst_lock:
        try:
            response = topst.command("RESET", timeout=3.0)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return {"status": "success", "response": response}


@app.post("/execute")
def execute_move(req: ExecuteRequest):
    start = normalize_cell(req.start)
    end = normalize_cell(req.end)
    piece = req.piece.lower().strip() if req.piece else "piece"

    validate_cell(start)
    validate_cell(end)

    if start == end:
        raise HTTPException(status_code=400, detail="start and end are same")

    if not EXECUTE_SCRIPT.exists():
        raise HTTPException(status_code=500, detail="execute_move_8x8.sh not found")

    with robot_lock:
        with topst_lock:
            # 1. TOPST 규칙 검사
            try:
                topst_req = topst.command(f"REQ {start} {end} {piece}", timeout=4.0)
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail={
                        "message": "TOPST REQ failed",
                        "error": str(e),
                    },
                )

            if topst_req.startswith("ERR "):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": "TOPST rejected move",
                        "topst_response": topst_req,
                    },
                )

            if not topst_req.startswith("OK "):
                raise HTTPException(
                    status_code=500,
                    detail={
                        "message": "Unexpected TOPST response",
                        "topst_response": topst_req,
                    },
                )

            # 2. 로봇 실제 실행
            cmd = (
                f"cd {shlex.quote(str(ROS_WS))} && "
                f"bash {shlex.quote(str(EXECUTE_SCRIPT))} "
                f"{shlex.quote(start)} {shlex.quote(end)} {shlex.quote(piece)}"
            )

            try:
                result = subprocess.run(
                    ["bash", "-lc", cmd],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
            except subprocess.TimeoutExpired:
                try:
                    cancel_response = topst.command("CANCEL", timeout=3.0)
                except Exception as cancel_error:
                    cancel_response = f"CANCEL_FAILED {cancel_error}"

                raise HTTPException(
                    status_code=500,
                    detail={
                        "message": "Robot execute timeout",
                        "topst_req": topst_req,
                        "topst_cancel": cancel_response,
                    },
                )

            # 3. 로봇 실패 시 TOPST 상태 업데이트 취소
            if result.returncode != 0:
                try:
                    cancel_response = topst.command("CANCEL", timeout=3.0)
                except Exception as cancel_error:
                    cancel_response = f"CANCEL_FAILED {cancel_error}"

                raise HTTPException(
                    status_code=500,
                    detail={
                        "message": "Robot execute failed",
                        "topst_req": topst_req,
                        "topst_cancel": cancel_response,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    },
                )

            # 4. 로봇 성공 시 COMMIT
            try:
                commit_response = topst.command("COMMIT", timeout=3.0)
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail={
                        "message": "Robot moved, but TOPST COMMIT failed",
                        "topst_req": topst_req,
                        "error": str(e),
                        "stdout": result.stdout,
                    },
                )

    return {
        "status": "success",
        "start": start,
        "end": end,
        "piece": piece,
        "topst_req": topst_req,
        "topst_commit": commit_response,
        "stdout": result.stdout,
    }


app.mount("/", StaticFiles(directory="web", html=True), name="web")
