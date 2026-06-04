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
MOVE_SCRIPT = ROS_WS / "test" / "move_piece.sh"

ALLOWED_CELLS = {
    "A1", "B1", "C1",
    "A2", "B2", "C2",
    "A3", "B3", "C3",
}

robot_lock = threading.Lock()


class MoveRequest(BaseModel):
    start: str
    end: str


@app.get("/health")
def health():
    return {
        "status": "ok",
        "move_script_exists": MOVE_SCRIPT.exists(),
    }


@app.post("/move")
def move_piece(req: MoveRequest):
    start = req.start.upper().strip()
    end = req.end.upper().strip()

    if start not in ALLOWED_CELLS:
        raise HTTPException(status_code=400, detail=f"Invalid start cell: {start}")

    if end not in ALLOWED_CELLS:
        raise HTTPException(status_code=400, detail=f"Invalid end cell: {end}")

    if start == end:
        raise HTTPException(status_code=400, detail="start and end are same")

    if not MOVE_SCRIPT.exists():
        raise HTTPException(status_code=500, detail="move_piece.sh not found")

    with robot_lock:
        cmd = (
            f"cd {shlex.quote(str(ROS_WS))} && "
            f"source /opt/ros/humble/setup.bash && "
            f"source install/setup.bash && "
            f"bash {shlex.quote(str(MOVE_SCRIPT))} "
            f"{shlex.quote(start)} {shlex.quote(end)}"
        )

        try:
            result = subprocess.run(
                ["bash", "-lc", cmd],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=500, detail="Robot move timeout")

        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "move_piece.sh failed",
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                },
            )

    return {
        "status": "success",
        "start": start,
        "end": end,
        "stdout": result.stdout,
    }


app.mount("/", StaticFiles(directory="web", html=True), name="web")
