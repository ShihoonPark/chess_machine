from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path
import subprocess
import threading
import shlex

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

FILES = "ABCDEFGH"
RANKS = "12345678"
ALLOWED_CELLS = {f"{file}{rank}" for file in FILES for rank in RANKS}

robot_lock = threading.Lock()


class ExecuteRequest(BaseModel):
    start: str
    end: str
    piece: str = "piece"


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
        "mode": "8x8_dual_arm_execute",
        "note": "Piece rule validation will be handled by TOPST later.",
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

    cmd = (
        f"cd {shlex.quote(str(ROS_WS))} && "
        f"bash {shlex.quote(str(EXECUTE_SCRIPT))} "
        f"{shlex.quote(start)} {shlex.quote(end)} {shlex.quote(piece)}"
    )

    with robot_lock:
        try:
            result = subprocess.run(
                ["bash", "-lc", cmd],
                capture_output=True,
                text=True,
                timeout=240,
            )
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=500, detail="Robot execute timeout")

        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "execute_move_8x8.sh failed",
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                },
            )

    return {
        "status": "success",
        "start": start,
        "end": end,
        "piece": piece,
        "stdout": result.stdout,
    }


app.mount("/", StaticFiles(directory="web", html=True), name="web")
