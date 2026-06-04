from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pathlib import Path
from typing import List, Optional
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

# 현재 실제 move_piece.sh는 아직 3x3 기준으로 검증된 상태
MOVE_ALLOWED_CELLS = {
    "A1", "B1", "C1",
    "A2", "B2", "C2",
    "A3", "B3", "C3",
}

# planner는 8x8 체스판 기준
FILES = "ABCDEFGH"
RANKS = "12345678"
PLAN_ALLOWED_CELLS = {f"{file}{rank}" for file in FILES for rank in RANKS}

# 실제 물리 배치 기준:
# arm1 = rank 1 쪽, 아래쪽 팔
# arm2 = rank 8 쪽, 위쪽 팔
ARM1_REACHABLE = set()
ARM2_REACHABLE = set()

# arm1: 아래쪽 rank 1~4 담당
for file in FILES:
    for rank in "1234":
        ARM1_REACHABLE.add(f"{file}{rank}")

# arm2: 위쪽 rank 5~8 담당
for file in FILES:
    for rank in "5678":
        ARM2_REACHABLE.add(f"{file}{rank}")

# 두 팔이 모두 접근 가능한 중계 후보 영역
# 실제 8x8 보드에서 중앙부인 rank 4~5 근처
RELAY_CANDIDATES = [
    "C4", "D4", "E4", "F4",
    "C5", "D5", "E5", "F5",
]

# relay 후보는 두 팔 모두 접근 가능하게 추가
for relay in RELAY_CANDIDATES:
    ARM1_REACHABLE.add(relay)
    ARM2_REACHABLE.add(relay)

robot_lock = threading.Lock()


class MoveRequest(BaseModel):
    start: str
    end: str


class PlanRequest(BaseModel):
    start: str
    end: str
    piece: Optional[str] = "piece"
    occupied: List[str] = Field(default_factory=list)


def normalize_cell(cell: str) -> str:
    return cell.upper().strip()


def validate_plan_cell(cell: str):
    if cell not in PLAN_ALLOWED_CELLS:
        raise HTTPException(status_code=400, detail=f"Invalid 8x8 cell: {cell}")


def cell_to_xy_index(cell: str):
    file = cell[0]
    rank = cell[1]

    x = FILES.index(file)
    y = RANKS.index(rank)

    return x, y


def board_distance(a: str, b: str) -> int:
    ax, ay = cell_to_xy_index(a)
    bx, by = cell_to_xy_index(b)

    return abs(ax - bx) + abs(ay - by)


def reachable_arms(cell: str):
    arms = []

    if cell in ARM1_REACHABLE:
        arms.append("arm1")

    if cell in ARM2_REACHABLE:
        arms.append("arm2")

    return arms


def make_move_vector(start: str, end: str, piece: str):
    sx, sy = cell_to_xy_index(start)
    ex, ey = cell_to_xy_index(end)

    piece_map = {
        "pawn": 0,
        "rook": 1,
        "knight": 2,
        "bishop": 3,
        "queen": 4,
        "king": 5,
        "piece": 9,
    }

    piece_code = piece_map.get(piece.lower(), 9)

    return [sx, sy, ex, ey, piece_code]


def choose_direct_arm(start: str, end: str):
    start_arms = set(reachable_arms(start))
    end_arms = set(reachable_arms(end))

    common_arms = list(start_arms.intersection(end_arms))

    if not common_arms:
        return None

    # 둘 다 가능하면 실제 배치 기준으로 start 쪽에 더 가까운 팔 우선
    start_rank = int(start[1])

    if "arm1" in common_arms and start_rank <= 4:
        return "arm1"

    if "arm2" in common_arms and start_rank >= 5:
        return "arm2"

    if "arm1" in common_arms:
        return "arm1"

    if "arm2" in common_arms:
        return "arm2"

    return common_arms[0]


def choose_relay(start: str, end: str, occupied_cells: set):
    start_arms = reachable_arms(start)
    end_arms = reachable_arms(end)

    best_plan = None
    best_score = 999999

    for source_arm in start_arms:
        for target_arm in end_arms:
            if source_arm == target_arm:
                continue

            for relay in RELAY_CANDIDATES:
                if relay in occupied_cells:
                    continue

                if relay not in ARM1_REACHABLE:
                    continue

                if relay not in ARM2_REACHABLE:
                    continue

                if source_arm == "arm1" and relay not in ARM1_REACHABLE:
                    continue

                if source_arm == "arm2" and relay not in ARM2_REACHABLE:
                    continue

                if target_arm == "arm1" and relay not in ARM1_REACHABLE:
                    continue

                if target_arm == "arm2" and relay not in ARM2_REACHABLE:
                    continue

                score = board_distance(start, relay) + board_distance(relay, end)

                if score < best_score:
                    best_score = score
                    best_plan = {
                        "relay": relay,
                        "score": score,
                        "steps": [
                            {
                                "arm": source_arm,
                                "start": start,
                                "end": relay,
                            },
                            {
                                "arm": target_arm,
                                "start": relay,
                                "end": end,
                            },
                        ],
                    }

    return best_plan


@app.get("/health")
def health():
    return {
        "status": "ok",
        "move_script_exists": MOVE_SCRIPT.exists(),
        "planner_mode": "rank_based_dual_arm",
        "arm1_area": "rank 1~4",
        "arm2_area": "rank 5~8",
        "relay_candidates": RELAY_CANDIDATES,
    }


@app.post("/move")
def move_piece(req: MoveRequest):
    start = normalize_cell(req.start)
    end = normalize_cell(req.end)

    if start not in MOVE_ALLOWED_CELLS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid move start cell for current 3x3 robot script: {start}",
        )

    if end not in MOVE_ALLOWED_CELLS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid move end cell for current 3x3 robot script: {end}",
        )

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


@app.post("/plan")
def plan_move(req: PlanRequest):
    start = normalize_cell(req.start)
    end = normalize_cell(req.end)
    piece = req.piece.lower().strip() if req.piece else "piece"
    occupied_cells = {normalize_cell(cell) for cell in req.occupied}

    validate_plan_cell(start)
    validate_plan_cell(end)

    if start == end:
        raise HTTPException(status_code=400, detail="start and end are same")

    for cell in occupied_cells:
        validate_plan_cell(cell)

    move_vector = make_move_vector(start, end, piece)

    start_arms = reachable_arms(start)
    end_arms = reachable_arms(end)

    if not start_arms:
        raise HTTPException(status_code=400, detail=f"No arm can reach start cell: {start}")

    if not end_arms:
        raise HTTPException(status_code=400, detail=f"No arm can reach end cell: {end}")

    direct_arm = choose_direct_arm(start, end)

    if direct_arm:
        return {
            "status": "success",
            "mode": "direct",
            "piece": piece,
            "move_vector": move_vector,
            "start_arms": start_arms,
            "end_arms": end_arms,
            "steps": [
                {
                    "arm": direct_arm,
                    "start": start,
                    "end": end,
                }
            ],
        }

    relay_plan = choose_relay(start, end, occupied_cells)

    if not relay_plan:
        raise HTTPException(
            status_code=400,
            detail="No valid relay point found",
        )

    return {
        "status": "success",
        "mode": "relay",
        "piece": piece,
        "move_vector": move_vector,
        "start_arms": start_arms,
        "end_arms": end_arms,
        "relay": relay_plan["relay"],
        "score": relay_plan["score"],
        "steps": relay_plan["steps"],
    }


app.mount("/", StaticFiles(directory="web", html=True), name="web")
