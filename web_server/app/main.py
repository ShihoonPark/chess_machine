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
MOVE_PIECE_SCRIPT = ROS_WS / "test" / "move_piece_8x8.sh"

TOPST_PORT = "/dev/ttyUSB3"
TOPST_RULE_PATH = "/home/root/rule_checker.py"

FILES = "ABCDEFGH"
RANKS = "12345678"
ALLOWED_CELLS = {f"{file}{rank}" for file in FILES for rank in RANKS}

CAPTURE_SLOTS = {
    "arm1": ["CAP1_1", "CAP1_2", "CAP1_3", "CAP1_4"],
    "arm2": ["CAP2_1", "CAP2_2", "CAP2_3"],
}

capture_next_index = {
    "arm1": 0,
    "arm2": 0,
}

robot_lock = threading.Lock()
topst_lock = threading.Lock()
capture_lock = threading.Lock()


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


def rank_of_cell(cell: str) -> int:
    return int(cell[1])


def arm_for_cell(cell: str) -> str:
    rank = rank_of_cell(cell)

    if 1 <= rank <= 4:
        return "arm1"

    if 5 <= rank <= 8:
        return "arm2"

    raise ValueError(f"Invalid rank in cell: {cell}")


def reset_capture_slots():
    with capture_lock:
        capture_next_index["arm1"] = 0
        capture_next_index["arm2"] = 0


def get_capture_status():
    with capture_lock:
        return {
            "arm1": {
                "used": capture_next_index["arm1"],
                "total": len(CAPTURE_SLOTS["arm1"]),
                "slots": CAPTURE_SLOTS["arm1"],
            },
            "arm2": {
                "used": capture_next_index["arm2"],
                "total": len(CAPTURE_SLOTS["arm2"]),
                "slots": CAPTURE_SLOTS["arm2"],
            },
        }


def peek_next_capture_slot(arm: str) -> str:
    with capture_lock:
        idx = capture_next_index[arm]
        slots = CAPTURE_SLOTS[arm]

        if idx >= len(slots):
            raise RuntimeError(f"No capture slot left for {arm}")

        return slots[idx]


def mark_capture_slot_used(arm: str, slot: str):
    with capture_lock:
        idx = capture_next_index[arm]
        slots = CAPTURE_SLOTS[arm]

        if idx < len(slots) and slots[idx] == slot:
            capture_next_index[arm] += 1
            return

        if slot in slots:
            slot_idx = slots.index(slot)
            capture_next_index[arm] = max(capture_next_index[arm], slot_idx + 1)
            return

        raise RuntimeError(f"Invalid capture slot {slot} for {arm}")


def parse_capture_from_topst_response(response: str):
    tokens = response.split()

    for idx, token in enumerate(tokens):
        if token == "CAPTURE":
            if idx + 1 < len(tokens):
                return tokens[idx + 1]
            return "unknown"

        if token.startswith("CAPTURE="):
            value = token.split("=", 1)[1].strip()
            return value or "unknown"

    return None


def run_robot_script(script_path: Path, args: list[str], timeout: int = 300):
    if not script_path.exists():
        raise RuntimeError(f"Robot script not found: {script_path}")

    arg_text = " ".join(shlex.quote(str(arg)) for arg in args)

    cmd = (
        f"cd {shlex.quote(str(ROS_WS))} && "
        f"bash {shlex.quote(str(script_path))} {arg_text}"
    )

    return subprocess.run(
        ["bash", "-lc", cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def format_robot_step(name: str, result: subprocess.CompletedProcess):
    return {
        "name": name,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def cancel_pending_topst():
    try:
        return topst.command("CANCEL", timeout=3.0)
    except Exception as cancel_error:
        return f"CANCEL_FAILED {cancel_error}"


@app.get("/health")
def health():
    return {
        "status": "ok",
        "execute_script_exists": EXECUTE_SCRIPT.exists(),
        "move_piece_script_exists": MOVE_PIECE_SCRIPT.exists(),
        "topst_port": TOPST_PORT,
        "topst_port_exists": os.path.exists(TOPST_PORT),
        "mode": "8x8_dual_arm_execute_with_topst_rule_checker_and_capture",
        "capture_slots": get_capture_status(),
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
    # reset 중 로봇 이동과 섞이면 물리 보드와 논리 보드가 어긋날 수 있으므로 robot_lock도 잡는다.
    with robot_lock:
        with topst_lock:
            try:
                response = topst.command("RESET", timeout=3.0)
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

            reset_capture_slots()

    return {
        "status": "success",
        "response": response,
        "capture_slots": get_capture_status(),
    }


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

    if not MOVE_PIECE_SCRIPT.exists():
        raise HTTPException(status_code=500, detail="move_piece_8x8.sh not found")

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

            captured_piece = parse_capture_from_topst_response(topst_req)
            capture_info = None
            robot_steps = []

            # 2. Capture가 있으면 먼저 end 칸의 잡힌 기물을 CAP slot으로 이동
            if captured_piece is not None:
                capture_arm = arm_for_cell(end)

                try:
                    capture_slot = peek_next_capture_slot(capture_arm)
                except Exception as e:
                    cancel_response = cancel_pending_topst()
                    raise HTTPException(
                        status_code=500,
                        detail={
                            "message": "No capture slot available",
                            "topst_req": topst_req,
                            "topst_cancel": cancel_response,
                            "capture_arm": capture_arm,
                            "capture_slots": get_capture_status(),
                            "error": str(e),
                        },
                    )

                capture_info = {
                    "captured_piece": captured_piece,
                    "capture_arm": capture_arm,
                    "capture_from": end,
                    "capture_slot": capture_slot,
                }

                try:
                    capture_result = run_robot_script(
                        MOVE_PIECE_SCRIPT,
                        [capture_arm, end, capture_slot],
                        timeout=300,
                    )
                except subprocess.TimeoutExpired:
                    cancel_response = cancel_pending_topst()
                    raise HTTPException(
                        status_code=500,
                        detail={
                            "message": "Capture move timeout",
                            "topst_req": topst_req,
                            "topst_cancel": cancel_response,
                            "capture": capture_info,
                        },
                    )
                except Exception as e:
                    cancel_response = cancel_pending_topst()
                    raise HTTPException(
                        status_code=500,
                        detail={
                            "message": "Capture move failed before script execution",
                            "topst_req": topst_req,
                            "topst_cancel": cancel_response,
                            "capture": capture_info,
                            "error": str(e),
                        },
                    )

                robot_steps.append(format_robot_step("capture", capture_result))

                if capture_result.returncode != 0:
                    cancel_response = cancel_pending_topst()
                    raise HTTPException(
                        status_code=500,
                        detail={
                            "message": "Capture move failed",
                            "topst_req": topst_req,
                            "topst_cancel": cancel_response,
                            "capture": capture_info,
                            "stdout": capture_result.stdout,
                            "stderr": capture_result.stderr,
                        },
                    )

                # 실제 잡힌 기물이 CAP slot으로 이동 성공한 뒤에만 slot 사용 처리.
                mark_capture_slot_used(capture_arm, capture_slot)

            # 3. 공격 기물을 start -> end로 이동
            try:
                attack_result = run_robot_script(
                    EXECUTE_SCRIPT,
                    [start, end, piece],
                    timeout=300,
                )
            except subprocess.TimeoutExpired:
                cancel_response = cancel_pending_topst()
                raise HTTPException(
                    status_code=500,
                    detail={
                        "message": "Robot execute timeout",
                        "topst_req": topst_req,
                        "topst_cancel": cancel_response,
                        "capture": capture_info,
                        "robot_steps": robot_steps,
                    },
                )
            except Exception as e:
                cancel_response = cancel_pending_topst()
                raise HTTPException(
                    status_code=500,
                    detail={
                        "message": "Robot execute failed before script execution",
                        "topst_req": topst_req,
                        "topst_cancel": cancel_response,
                        "capture": capture_info,
                        "robot_steps": robot_steps,
                        "error": str(e),
                    },
                )

            robot_steps.append(format_robot_step("attack", attack_result))

            # 4. 공격 기물 이동 실패 시 TOPST 상태 업데이트 취소
            if attack_result.returncode != 0:
                cancel_response = cancel_pending_topst()
                raise HTTPException(
                    status_code=500,
                    detail={
                        "message": "Robot execute failed",
                        "topst_req": topst_req,
                        "topst_cancel": cancel_response,
                        "capture": capture_info,
                        "robot_steps": robot_steps,
                        "stdout": attack_result.stdout,
                        "stderr": attack_result.stderr,
                    },
                )

            # 5. 전체 로봇 동작 성공 시 COMMIT
            try:
                commit_response = topst.command("COMMIT", timeout=3.0)
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail={
                        "message": "Robot moved, but TOPST COMMIT failed",
                        "topst_req": topst_req,
                        "capture": capture_info,
                        "robot_steps": robot_steps,
                        "error": str(e),
                    },
                )

    return {
        "status": "success",
        "start": start,
        "end": end,
        "piece": piece,
        "capture": capture_info,
        "topst_req": topst_req,
        "topst_commit": commit_response,
        "robot_steps": robot_steps,
        "capture_slots": get_capture_status(),
    }


app.mount("/", StaticFiles(directory="web", html=True), name="web")
