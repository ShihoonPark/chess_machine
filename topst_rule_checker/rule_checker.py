#!/usr/bin/env python3
import sys
import os
import termios
import select

FILES = "ABCDEFGH"
RANKS = "12345678"
RELAY_FILES = ["C", "D", "E", "F"]

VALID_COLORS = ["white", "black"]
VALID_PIECES = ["king", "queen", "rook", "bishop", "knight", "pawn", "piece"]

board = {}
current_turn = "white"
pending_move = None


def other_color(color):
    if color == "white":
        return "black"
    return "white"


def file_idx(file_char):
    file_char = file_char.upper()

    if file_char not in FILES:
        return None

    return FILES.index(file_char)


def idx_file(idx):
    if idx < 0 or idx >= 8:
        return None

    return FILES[idx]


def make_cell(file_idx_value, rank):
    file_char = idx_file(file_idx_value)

    if file_char is None:
        return None

    if rank < 1 or rank > 8:
        return None

    return f"{file_char}{rank}"


def parse_cell(cell):
    cell = cell.upper().strip()

    if len(cell) != 2:
        return None

    file_char = cell[0]
    rank_char = cell[1]

    fidx = file_idx(file_char)

    if fidx is None:
        return None

    if rank_char not in RANKS:
        return None

    rank = int(rank_char)
    return fidx, rank


def normalize_cell(cell):
    return cell.upper().strip()


def is_valid_cell(cell):
    return parse_cell(cell) is not None


def get_arm(cell):
    parsed = parse_cell(cell)

    if parsed is None:
        return None

    _, rank = parsed

    if rank <= 4:
        return "arm1"

    return "arm2"


def init_standard_board():
    global board, current_turn, pending_move

    board = {}
    current_turn = "white"
    pending_move = None

    board["A1"] = {"color": "white", "type": "rook"}
    board["B1"] = {"color": "white", "type": "knight"}
    board["C1"] = {"color": "white", "type": "bishop"}
    board["D1"] = {"color": "white", "type": "queen"}
    board["E1"] = {"color": "white", "type": "king"}
    board["F1"] = {"color": "white", "type": "bishop"}
    board["G1"] = {"color": "white", "type": "knight"}
    board["H1"] = {"color": "white", "type": "rook"}

    for file_char in FILES:
        board[f"{file_char}2"] = {"color": "white", "type": "pawn"}

    board["A8"] = {"color": "black", "type": "rook"}
    board["B8"] = {"color": "black", "type": "knight"}
    board["C8"] = {"color": "black", "type": "bishop"}
    board["D8"] = {"color": "black", "type": "queen"}
    board["E8"] = {"color": "black", "type": "king"}
    board["F8"] = {"color": "black", "type": "bishop"}
    board["G8"] = {"color": "black", "type": "knight"}
    board["H8"] = {"color": "black", "type": "rook"}

    for file_char in FILES:
        board[f"{file_char}7"] = {"color": "black", "type": "pawn"}


def clear_board():
    global board, current_turn, pending_move

    board = {}
    current_turn = "white"
    pending_move = None


def pending_to_string():
    if pending_move is None:
        return "pending=none"

    return (
        f"pending={pending_move['start']}->{pending_move['end']}"
        f" {pending_move['piece']['color']}_{pending_move['piece']['type']}"
    )


def board_to_string():
    items = []

    for rank in range(1, 9):
        for file_char in FILES:
            cell = f"{file_char}{rank}"

            if cell in board:
                piece = board[cell]
                items.append(f"{cell}:{piece['color']}_{piece['type']}")

    prefix = f"BOARD turn={current_turn} {pending_to_string()}"

    if not items:
        return f"{prefix} EMPTY"

    return prefix + " " + " ".join(items)


def path_between(start, end):
    s = parse_cell(start)
    e = parse_cell(end)

    if s is None or e is None:
        return []

    sx, sy = s
    ex, ey = e

    dx = ex - sx
    dy = ey - sy

    step_x = 0
    step_y = 0

    if dx > 0:
        step_x = 1
    elif dx < 0:
        step_x = -1

    if dy > 0:
        step_y = 1
    elif dy < 0:
        step_y = -1

    cells = []

    x = sx + step_x
    y = sy + step_y

    while x != ex or y != ey:
        cell = make_cell(x, y)

        if cell is not None:
            cells.append(cell)

        x += step_x
        y += step_y

    return cells


def is_path_clear(start, end):
    for cell in path_between(start, end):
        if cell in board:
            return False, cell

    return True, None


def validate_piece_motion(start, end, piece_type, color):
    s = parse_cell(start)
    e = parse_cell(end)

    if s is None or e is None:
        return False, "INVALID_CELL"

    sx, sy = s
    ex, ey = e

    dx = ex - sx
    dy = ey - sy

    adx = abs(dx)
    ady = abs(dy)

    target_piece = board.get(end)

    if start == end:
        return False, "SAME_CELL"

    if piece_type == "bishop":
        if adx != ady:
            return False, "INVALID_BISHOP_MOVE"

        clear, block_cell = is_path_clear(start, end)

        if not clear:
            return False, f"PATH_BLOCKED_AT_{block_cell}"

        return True, "OK"

    if piece_type == "rook":
        if not (adx == 0 or ady == 0):
            return False, "INVALID_ROOK_MOVE"

        clear, block_cell = is_path_clear(start, end)

        if not clear:
            return False, f"PATH_BLOCKED_AT_{block_cell}"

        return True, "OK"

    if piece_type == "queen":
        if not (adx == ady or adx == 0 or ady == 0):
            return False, "INVALID_QUEEN_MOVE"

        clear, block_cell = is_path_clear(start, end)

        if not clear:
            return False, f"PATH_BLOCKED_AT_{block_cell}"

        return True, "OK"

    if piece_type == "knight":
        if (adx == 1 and ady == 2) or (adx == 2 and ady == 1):
            return True, "OK"

        return False, "INVALID_KNIGHT_MOVE"

    if piece_type == "king":
        if adx <= 1 and ady <= 1:
            return True, "OK"

        return False, "INVALID_KING_MOVE"

    if piece_type == "pawn":
        if color == "white":
            direction = 1
            start_rank = 2
        else:
            direction = -1
            start_rank = 7

        # Forward 1 cell: target must be empty
        if dx == 0 and dy == direction:
            if target_piece is None:
                return True, "OK"

            return False, "PAWN_FORWARD_BLOCKED"

        # Forward 2 cells from initial rank: middle and target must be empty
        if dx == 0 and dy == 2 * direction and sy == start_rank:
            middle_rank = sy + direction
            middle_cell = make_cell(sx, middle_rank)

            if middle_cell in board:
                return False, f"PAWN_PATH_BLOCKED_AT_{middle_cell}"

            if target_piece is not None:
                return False, "PAWN_FORWARD_BLOCKED"

            return True, "OK"

        # Diagonal capture: target must have enemy piece
        if adx == 1 and dy == direction:
            if target_piece is None:
                return False, "PAWN_DIAGONAL_NEEDS_CAPTURE"

            if target_piece["color"] == color:
                return False, "SAME_COLOR_OCCUPIED"

            return True, "OK"

        return False, "INVALID_PAWN_MOVE"

    if piece_type == "piece":
        return True, "OK"

    return False, "UNKNOWN_PIECE"


def choose_relay(start, end):
    s = parse_cell(start)
    e = parse_cell(end)

    sx, _ = s
    ex, _ = e

    avg = (sx + ex) // 2

    if avg < 2:
        avg = 2

    if avg > 5:
        avg = 5

    relay_file = idx_file(avg)

    if relay_file not in RELAY_FILES:
        relay_file = "D"

    return relay_file + "45"


def make_plan(start, end):
    start_arm = get_arm(start)
    end_arm = get_arm(end)

    if start_arm is None or end_arm is None:
        return None, "ERR INVALID_CELL"

    if start_arm == end_arm:
        return {
            "mode": "DIRECT",
            "start_arm": start_arm,
            "end_arm": end_arm,
            "relay": None,
        }, f"OK DIRECT {start_arm} {start} {end}"

    relay = choose_relay(start, end)

    return {
        "mode": "RELAY",
        "start_arm": start_arm,
        "end_arm": end_arm,
        "relay": relay,
    }, f"OK RELAY {relay} {start_arm} {start} {relay} {end_arm} {relay} {end}"


def handle_req(parts):
    global pending_move

    if len(parts) != 4:
        return "ERR FORMAT_USE_REQ_START_END_PIECE"

    if pending_move is not None:
        return "ERR PENDING_MOVE_EXISTS_USE_COMMIT_OR_CANCEL"

    _, start, end, requested_piece = parts

    start = normalize_cell(start)
    end = normalize_cell(end)
    requested_piece = requested_piece.lower().strip()

    if not is_valid_cell(start):
        return f"ERR INVALID_START_CELL {start}"

    if not is_valid_cell(end):
        return f"ERR INVALID_END_CELL {end}"

    if requested_piece not in VALID_PIECES:
        return f"ERR UNKNOWN_PIECE {requested_piece}"

    moving_piece = board.get(start)

    if moving_piece is None:
        return f"ERR NO_PIECE_AT_START {start}"

    actual_color = moving_piece["color"]
    actual_type = moving_piece["type"]

    if actual_color != current_turn:
        return f"ERR WRONG_TURN current={current_turn} piece={actual_color}"

    if requested_piece != "piece" and requested_piece != actual_type:
        return f"ERR PIECE_MISMATCH actual={actual_type} requested={requested_piece}"

    target_piece = board.get(end)

    if target_piece is not None and target_piece["color"] == actual_color:
        return f"ERR SAME_COLOR_OCCUPIED {end}"

    valid, reason = validate_piece_motion(start, end, actual_type, actual_color)

    if not valid:
        return f"ERR {reason}"

    plan, plan_text = make_plan(start, end)

    if plan is None:
        return plan_text

    captured_text = ""

    if target_piece is not None:
        captured_text = f" CAPTURE {target_piece['color']}_{target_piece['type']}"

    next_turn = other_color(current_turn)

    pending_move = {
        "start": start,
        "end": end,
        "requested_piece": requested_piece,
        "piece": {"color": actual_color, "type": actual_type},
        "captured": target_piece,
        "plan": plan,
        "plan_text": plan_text,
        "next_turn": next_turn,
    }

    return f"{plan_text} PENDING next={next_turn}{captured_text}"


def handle_commit(parts):
    global board, current_turn, pending_move

    if len(parts) != 1:
        return "ERR FORMAT_USE_COMMIT"

    if pending_move is None:
        return "ERR NO_PENDING_MOVE"

    start = pending_move["start"]
    end = pending_move["end"]
    moving_piece = pending_move["piece"]
    next_turn = pending_move["next_turn"]
    captured = pending_move["captured"]

    if start not in board:
        pending_move = None
        return f"ERR COMMIT_FAILED_START_EMPTY {start}"

    current_piece = board[start]

    if current_piece["color"] != moving_piece["color"] or current_piece["type"] != moving_piece["type"]:
        pending_move = None
        return f"ERR COMMIT_FAILED_START_CHANGED {start}"

    board[end] = moving_piece
    del board[start]

    current_turn = next_turn

    captured_text = ""

    if captured is not None:
        captured_text = f" CAPTURED {captured['color']}_{captured['type']}"

    pending_move = None

    return f"OK COMMIT {start} {end} NEXT_TURN {current_turn}{captured_text}"


def handle_cancel(parts):
    global pending_move

    if len(parts) != 1:
        return "ERR FORMAT_USE_CANCEL"

    if pending_move is None:
        return "ERR NO_PENDING_MOVE"

    start = pending_move["start"]
    end = pending_move["end"]

    pending_move = None

    return f"OK CANCEL {start} {end}"


def handle_set(parts):
    global board

    if pending_move is not None:
        return "ERR PENDING_MOVE_EXISTS_USE_COMMIT_OR_CANCEL"

    if len(parts) != 4:
        return "ERR FORMAT_USE_SET_CELL_COLOR_PIECE"

    _, cell, color, piece_type = parts

    cell = normalize_cell(cell)
    color = color.lower().strip()
    piece_type = piece_type.lower().strip()

    if not is_valid_cell(cell):
        return f"ERR INVALID_CELL {cell}"

    if color not in VALID_COLORS:
        return f"ERR INVALID_COLOR {color}"

    if piece_type not in VALID_PIECES or piece_type == "piece":
        return f"ERR INVALID_PIECE {piece_type}"

    board[cell] = {"color": color, "type": piece_type}

    return f"OK SET {cell} {color}_{piece_type}"


def handle_remove(parts):
    global board

    if pending_move is not None:
        return "ERR PENDING_MOVE_EXISTS_USE_COMMIT_OR_CANCEL"

    if len(parts) != 2:
        return "ERR FORMAT_USE_REMOVE_CELL"

    _, cell = parts

    cell = normalize_cell(cell)

    if not is_valid_cell(cell):
        return f"ERR INVALID_CELL {cell}"

    if cell in board:
        del board[cell]

    return f"OK REMOVE {cell}"


def handle_turn(parts):
    global current_turn

    if pending_move is not None:
        return "ERR PENDING_MOVE_EXISTS_USE_COMMIT_OR_CANCEL"

    if len(parts) != 2:
        return "ERR FORMAT_USE_TURN_COLOR"

    _, color = parts

    color = color.lower().strip()

    if color not in VALID_COLORS:
        return f"ERR INVALID_COLOR {color}"

    current_turn = color

    return f"OK TURN {current_turn}"


def handle_line(line):
    line = line.strip()

    if not line:
        return None

    parts = line.split()
    cmd = parts[0].upper()

    if cmd == "REQ":
        return handle_req(parts)

    if cmd == "COMMIT":
        return handle_commit(parts)

    if cmd == "CANCEL":
        return handle_cancel(parts)

    if cmd == "RESET":
        init_standard_board()
        return "OK RESET turn=white pending=none"

    if cmd == "CLEAR":
        clear_board()
        return "OK CLEAR turn=white pending=none"

    if cmd == "BOARD":
        return board_to_string()

    if cmd == "SET":
        return handle_set(parts)

    if cmd == "REMOVE":
        return handle_remove(parts)

    if cmd == "TURN":
        return handle_turn(parts)

    if cmd == "HELP":
        return (
            "CMDS: REQ A1 G7 bishop | COMMIT | CANCEL | RESET | CLEAR | "
            "BOARD | SET A1 white bishop | REMOVE A1 | TURN white"
        )

    return "ERR UNKNOWN_COMMAND"


def run_stdio():
    init_standard_board()

    print("TOPST_RULE_CHECKER_READY")
    print("CMDS: REQ A1 G7 bishop | COMMIT | CANCEL | RESET | CLEAR | BOARD | SET A1 white bishop | TURN white")
    sys.stdout.flush()

    for line in sys.stdin:
        response = handle_line(line)

        if response:
            print(response)
            sys.stdout.flush()


def open_uart(path):
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)

    attrs = termios.tcgetattr(fd)

    baud = termios.B115200

    attrs[0] = 0
    attrs[1] = 0
    attrs[2] = termios.CS8 | termios.CLOCAL | termios.CREAD
    attrs[3] = 0
    attrs[4] = baud
    attrs[5] = baud

    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 1

    termios.tcsetattr(fd, termios.TCSANOW, attrs)

    return fd


def run_uart(path):
    init_standard_board()

    fd = open_uart(path)

    os.write(fd, b"TOPST_RULE_CHECKER_READY\n")

    buf = b""

    while True:
        rlist, _, _ = select.select([fd], [], [], 0.1)

        if fd not in rlist:
            continue

        try:
            data = os.read(fd, 1024)
        except BlockingIOError:
            continue

        if not data:
            continue

        buf += data

        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            text = line.decode(errors="ignore").strip()
            response = handle_line(text)

            if response:
                os.write(fd, (response + "\n").encode())


def main():
    try:
        if len(sys.argv) >= 3 and sys.argv[1] == "--uart":
            run_uart(sys.argv[2])
        else:
            run_stdio()
    except KeyboardInterrupt:
        print("\nTOPST_RULE_CHECKER_STOPPED")


if __name__ == "__main__":
    main()
