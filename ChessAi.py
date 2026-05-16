import random
import time

try:
    from Chess.ChessEngine import ZOBRIST_SIDE, ZOBRIST_EP
except ImportError:
    from ChessEngine import ZOBRIST_SIDE, ZOBRIST_EP

# Syzygy tablebase probing (optional — gracefully disabled if path not set)
try:
    from syzygy_probe import syzygy_probe_best_move, syzygy_score_adjust
    _SYZYGY_AVAILABLE = True
except ImportError:
    _SYZYGY_AVAILABLE = False
    def syzygy_probe_best_move(gs, moves): return None
    def syzygy_score_adjust(gs, score): return score

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
pieceScores = {"K": 0, "Q": 10, "R": 5, "B": 3, "N": 3, "P": 1}
CHECKMATE   = 10000
STALEMATE   = 0
DEPTH       = 6
MAX_TT_SIZE = 1_000_000
TB_WIN_SCORE = 900.0

# ---------------------------------------------------------------------------
# Opening book  (Zobrist key → best move as (startRow,startCol,endRow,endCol))
# Common openings: 1.d4/e4 mainlines, Sicilian, French, Caro-Kann, QGD, KID
# Stored as SAN sequences; built into a hash map at import time.
# ---------------------------------------------------------------------------
_OPENING_LINES = [
    # --- 1.d4 — White lines ---
    ["d4","d5","Nf3","Nf6","e3","e6","Bd3","c5","c3","Nc6","O-O","Bd6"],
    ["d4","d5","c4","e6","Nc3","Nf6","Bg5","Be7","e3","O-O","Nf3","h6"],
    ["d4","Nf6","c4","g6","Nc3","Bg7","e4","d6","Nf3","O-O","Be2","e5"],
    ["d4","d5","c4","c6","Nf3","Nf6","Nc3","e6","e3","Nbd7","Bd3","dxc4"],
    ["d4","d5","c4","e6","Nc3","c5","cxd5","exd5","Nf3","Nc6","g3","Nf6"],
    ["d4","Nf6","c4","e6","Nc3","Bb4","e3","O-O","Bd3","d5","Nf3","c5"],
    ["d4","d5","Nf3","Nf6","c4","e6","Nc3","Be7","Bg5","h6","Bh4","O-O"],
    ["d4","f5","Nf3","Nf6","g3","e6","Bg2","Be7","O-O","O-O","c4","d6"],
    ["d4","Nf6","Nf3","g6","g3","Bg7","Bg2","O-O","O-O","d6","c4","Nc6"],
    # --- 1.e4 — White lines ---
    ["e4","e5","Nf3","Nc6","Bb5","a6","Ba4","Nf6","O-O","Be7","Re1","b5"],
    ["e4","e5","Nf3","Nc6","Bc4","Bc5","c3","Nf6","d4","exd4","cxd4","Bb4"],
    ["e4","c5","Nf3","d6","d4","cxd4","Nxd4","Nf6","Nc3","a6","Be3","e6"],
    ["e4","c5","Nf3","Nc6","d4","cxd4","Nxd4","g6","Nc3","Bg7","Be3","Nf6"],
    ["e4","e6","d4","d5","Nc3","Nf6","Bg5","Be7","e5","Nfd7","Bxe7","Qxe7"],
    ["e4","c6","d4","d5","Nc3","dxe4","Nxe4","Bf5","Ng3","Bg6","h4","h6"],
    ["e4","d5","exd5","Qxd5","Nc3","Qa5","d4","Nf6","Nf3","Bf5","Bc4","e6"],
    ["e4","e5","Nf3","Nc6","d4","exd4","Nxd4","Bc5","Be3","Qf6","c3","Nge7"],
    ["e4","e5","f4","exf4","Nf3","d5","exd5","Nf6","Nc3","Bd6","d4","O-O"],
    ["e4","e5","Nf3","Nc6","Nc3","Nf6","Bb5","Nd4","Nxd4","exd4","e5","dxc3"],
    ["e4","c5","Nf3","e6","d4","cxd4","Nxd4","a6","Nc3","Qc7","Be2","Nf6"],
    ["e4","c5","Nc3","Nc6","g3","g6","Bg2","Bg7","d3","d6","Be3","e6"],
    ["e4","e5","Nf3","Nc6","Bb5","Nf6","O-O","Nxe4","d4","Nd6","Bxc6","dxc6"],
    # --- Symmetrical / English / flank — White lines ---
    ["c4","e5","Nc3","Nf6","g3","d5","cxd5","Nxd5","Bg2","Nb6","Nf3","Nc6"],
    ["Nf3","d5","d4","Nf6","c4","e6","Nc3","Be7","Bg5","h6","Bh4","O-O"],
    ["c4","Nf6","Nc3","e6","Nf3","d5","d4","Be7","Bg5","h6","Bh4","O-O"],
    ["c4","c5","Nf3","Nf6","Nc3","d5","cxd5","Nxd5","d4","Nxc3","bxc3","g6"],
    ["Nf3","Nf6","c4","g6","g3","Bg7","Bg2","O-O","O-O","d6","Nc3","Nbd7"],
    ["c4","e5","g3","Nf6","Bg2","d5","cxd5","Nxd5","Nc3","Nb6","Nf3","Nc6"],
    # --- Black responses to 1.e4 ---
    # French Defence: solid, counterattacking
    ["e4","e6","d4","d5","Nd2","Nf6","e5","Nfd7","Bd3","c5","c3","Nc6"],
    ["e4","e6","d4","d5","Nc3","Bb4","e5","c5","a3","Bxc3+","bxc3","Ne7"],
    ["e4","e6","d4","d5","e5","c5","c3","Nc6","Nf3","Qb6","a3","Nh6"],
    # Caro-Kann: solid structure, good endgame prospects
    ["e4","c6","d4","d5","Nd2","dxe4","Nxe4","Bf5","Ng3","Bg6","h4","h6"],
    ["e4","c6","d4","d5","e5","Bf5","Nf3","e6","Be2","c5","O-O","Nc6"],
    ["e4","c6","Nc3","d5","Nf3","Bg4","h3","Bxf3","Qxf3","e6","d4","Nf6"],
    # Sicilian Najdorf: sharpest Black try vs 1.e4
    ["e4","c5","Nf3","d6","d4","cxd4","Nxd4","Nf6","Nc3","a6","Be2","e5"],
    ["e4","c5","Nf3","d6","d4","cxd4","Nxd4","Nf6","Nc3","a6","Bg5","e6"],
    # Berlin Defence: solid endgame weapon vs Ruy Lopez
    ["e4","e5","Nf3","Nc6","Bb5","Nf6","O-O","Nxe4","d4","Nd6","Bxc6","dxc6","dxe5","Nf5"],
    # Pirc/Modern: hypermodern, flexible
    ["e4","d6","d4","Nf6","Nc3","g6","Nf3","Bg7","Be2","O-O","O-O","c6"],
    ["e4","g6","d4","Bg7","Nc3","d6","Nf3","Nf6","Be2","O-O","O-O","Nbd7"],
    # --- Black responses to 1.d4 ---
    # King's Indian: aggressive, counterattacking
    ["d4","Nf6","c4","g6","Nc3","Bg7","e4","d6","Be2","O-O","Nf3","e5","O-O","Nc6"],
    ["d4","Nf6","c4","g6","Nc3","Bg7","e4","d6","f3","O-O","Be3","e5","Nge2","c6"],
    # Nimzo-Indian: positional pressure on c4
    ["d4","Nf6","c4","e6","Nc3","Bb4","Qc2","O-O","a3","Bxc3+","Qxc3","d5"],
    ["d4","Nf6","c4","e6","Nc3","Bb4","e3","O-O","Bd3","d5","Nf3","Nc6"],
    # Grünfeld: counterattack the centre
    ["d4","Nf6","c4","g6","Nc3","d5","cxd5","Nxd5","e4","Nxc3","bxc3","Bg7","Bc4","O-O"],
    # Queen's Gambit Accepted: active equalisation
    ["d4","d5","c4","dxc4","Nf3","Nf6","e3","e6","Bxc4","c5","O-O","a6"],
    # Slav: rock-solid
    ["d4","d5","c4","c6","Nf3","Nf6","Nc3","dxc4","a4","Bf5","e3","e6","Bxc4","Bb4"],
    # --- Black responses to 1.Nf3 / 1.c4 ---
    ["Nf3","d5","d4","Nf6","c4","e6","Nc3","Be7","Bg5","O-O","e3","h6","Bh4","b6"],
    ["c4","e5","Nc3","Nf6","g3","Bb4","Bg2","O-O","Nf3","Re8","O-O","Bxc3","bxc3","e4"],
    # Black vs 1.c3 - seize centre
    ["c3","e5","d4","exd4","cxd4","d5","Nc3","Nf6","Bg5","Be7","e3","O-O"],
    ["c3","d5","d4","Nf6","Nf3","e6","Bf4","Bd6","Bxd6","Qxd6","e3","O-O"],
    ["c3","c5","Nf3","Nf6","g3","g6","Bg2","Bg7","O-O","O-O","d4","cxd4"],
    ["c3","e5","Nf3","e4","Nd4","Nf6","d3","exd3","exd3","d5","Be2","Bd6"],
    # Black vs 1.b3 / 1.b4
    ["b3","e5","Bb2","Nc6","e3","Nf6","Bb5","Bd6","Na3","O-O","Nc4","Re8"],
    ["b4","e5","Bb2","Bxb4","Bxe5","Nf6","Nf3","O-O","e3","d5","Be2","Re8"],
    # KID deeper: Maroczy Bind and Be3 systems
    ["d4","Nf6","c4","g6","Nc3","Bg7","e4","d6","Be3","O-O","Nf3","e5","d5","a5"],
    ["d4","Nf6","c4","g6","Nc3","Bg7","e4","d6","Be3","O-O","Qd2","Nc6","Nge2","Rb8"],
    ["d4","Nf6","c4","g6","Nc3","Bg7","e4","d6","Be2","O-O","Be3","Nc6","d5","Ne8"],
    # Sicilian Dragon
    ["e4","c5","Nf3","d6","d4","cxd4","Nxd4","Nf6","Nc3","g6","Be3","Bg7","f3","O-O"],
    # Sicilian Kan
    ["e4","c5","Nf3","e6","d4","cxd4","Nxd4","a6","Nc3","Qc7","Bd3","Nf6","O-O","Bc5"],
    # QGD Orthodox
    ["d4","d5","c4","e6","Nc3","Nf6","Bg5","Be7","e3","O-O","Nf3","Nbd7","Rc1","c6"],
    # Budapest Gambit
    ["d4","Nf6","c4","e5","dxe5","Ng4","Nf3","Bc5","e3","Nc6","Be2","O-O","O-O","Re8"],
]

def _build_opening_book():
    """
    Replay each opening line from the starting position and record
    Zobrist key → list of moves (one per line) for each position.
    """
    try:
        try:
            from Chess.ChessEngine import GameState
        except ImportError:
            from ChessEngine import GameState
    except Exception:
        return {}, {}

    # White's acceptable first moves — prevents fringe lines ("Black vs 1.c3"
    # etc.) from injecting c3/b3/b4 into the starting-position candidate pool.
    _WHITE_FIRST_MOVES = {"e4", "d4", "c4", "Nf3"}

    book = {}       # key → first move (legacy fallback)
    multi = {}      # key → list of candidate moves
    _initial_key = GameState()._boardFingerprint()

    for line in _OPENING_LINES:
        gs = GameState()
        for san in line:
            # FIX 1: match using full SAN (with gs) so that both check symbols
            # and disambiguation are handled correctly.
            # - getChessNotation(gs=None) skips '+'/# AND skips disambiguation
            #   (e.g. returns "Nd7" instead of "Nbd7"), so many book entries
            #   silently break the rest of their line.
            # - We strip check/mate symbols from both sides so that "Bxc3+"
            #   in the book matches "Bxc3+" generated by getChessNotation(gs).
            san_clean = san.rstrip("+#")

            valid = gs.getValidMoves()
            move  = next(
                (m for m in valid
                 if m.getChessNotation(gs).rstrip("+#") == san_clean),
                None,
            )
            if move is None:
                break

            key = gs._boardFingerprint()

            # FIX 2: at the starting position, only allow canonical White
            # first moves.  Lines like ["c3", "e5", ...] (labeled "Black vs
            # 1.c3") start from the root and would otherwise add c3/b3/b4 as
            # valid White candidates, causing the engine to occasionally open
            # with those fringe moves.
            if key == _initial_key and san_clean not in _WHITE_FIRST_MOVES:
                break

            if key not in book:
                book[key] = move
            if key not in multi:
                multi[key] = []
            # Add if not already in list (same move from different lines)
            if move not in multi[key]:
                multi[key].append(move)
            gs.makeMove(move)
    return book, multi

_OPENING_BOOK: dict = {}  # populated lazily on first call
# Maps Zobrist key → list of candidate moves (one per line that reaches the pos)
_OPENING_BOOK_MULTI: dict = {}

def _book_move(gs):
    """Return a randomly chosen book move if available, else None."""
    global _OPENING_BOOK, _OPENING_BOOK_MULTI
    if not _OPENING_BOOK:
        _OPENING_BOOK, _OPENING_BOOK_MULTI = _build_opening_book()
    key = gs._boardFingerprint()
    candidates = _OPENING_BOOK_MULTI.get(key)
    if candidates:
        return random.choice(candidates)
    return _OPENING_BOOK.get(key)

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------
transposition_table: dict = {}
_tt_generation = 0
nextMove   = None
counter    = 0
lastScore  = 0

_MAX_DEPTH = DEPTH + 16
killers: list = [[None, None] for _ in range(_MAX_DEPTH + 1)]
history: dict = {}

def _init_history():
    global history
    history = {p: [0] * 64 for p in "PNBRQK"}
_init_history()

def clearTranspositionTable():
    global _tt_generation
    transposition_table.clear()
    _tt_generation = 0
    for i in range(len(killers)):
        killers[i] = [None, None]
    _init_history()

def newMove():
    global _tt_generation
    _tt_generation += 1

def findRandomMove(validMoves):
    return validMoves[random.randint(0, len(validMoves) - 1)]

# ---------------------------------------------------------------------------
# Contempt
# ---------------------------------------------------------------------------
def _contempt(gs):
    material     = scoreMaterial(gs.board)
    our_material = material if gs.whiteToMove else -material
    # Base: always dislike draws slightly (avoid accidental repetition)
    base = -0.4
    # When clearly winning: strongly avoid draw
    if our_material >= 3.0:
        return -min(our_material * 1.0, 8.0)
    elif our_material >= 1.5:
        return -our_material * 0.6
    elif our_material >= 0.5:
        return -0.3
    # When losing: accept/seek draws
    elif our_material <= -2.0:
        return min(abs(our_material) * 0.4, 4.0)
    elif our_material <= -0.5:
        return 0.2
    return base

# ---------------------------------------------------------------------------
# SEE  (Static Exchange Evaluation)
# Estimates the material outcome of a sequence of captures on a square.
# Returns the net material gain for the side making the first capture.
# Used to avoid moving pieces to squares where they lose material.
# ---------------------------------------------------------------------------
def _find_lva_sq(board, to_r, to_c, color):
    """
    Return the board square (row, col) of `color`'s least valuable attacker
    of (to_r, to_c), or None if no attacker exists.
    Mirrors the least_valuable_attacker logic inside _see but as a standalone
    function so the caller can get the attacker's position (not just its value).
    """
    best_val = 999; best_sq = None
    # Pawns
    pawn_src_r = to_r + 1 if color == "w" else to_r - 1
    for dc in (-1, 1):
        ar, ac = pawn_src_r, to_c + dc
        if 0 <= ar <= 7 and 0 <= ac <= 7 and board[ar][ac] == color + "P":
            if 1 < best_val: best_val = 1; best_sq = (ar, ac)
    if best_val == 1: return best_sq
    # Knights
    for dr, dc in ((-2,-1),(-2,1),(-1,-2),(-1,2),(1,-2),(1,2),(2,-1),(2,1)):
        ar, ac = to_r+dr, to_c+dc
        if 0 <= ar <= 7 and 0 <= ac <= 7 and board[ar][ac] == color + "N":
            if 3 < best_val: best_val = 3; best_sq = (ar, ac)
    if best_val == 3: return best_sq
    # Bishops / diagonal sliders
    for dr, dc in ((-1,-1),(-1,1),(1,-1),(1,1)):
        for i in range(1, 8):
            ar, ac = to_r+dr*i, to_c+dc*i
            if not (0<=ar<=7 and 0<=ac<=7): break
            sq = board[ar][ac]
            if sq != "--":
                if sq[0] == color and sq[1] in ("B","Q") and pieceScores[sq[1]] < best_val:
                    best_val = pieceScores[sq[1]]; best_sq = (ar, ac)
                break
    # Rooks / orthogonal sliders
    for dr, dc in ((-1,0),(1,0),(0,-1),(0,1)):
        for i in range(1, 8):
            ar, ac = to_r+dr*i, to_c+dc*i
            if not (0<=ar<=7 and 0<=ac<=7): break
            sq = board[ar][ac]
            if sq != "--":
                if sq[0] == color and sq[1] in ("R","Q") and pieceScores[sq[1]] < best_val:
                    best_val = pieceScores[sq[1]]; best_sq = (ar, ac)
                break
    # King
    for dr, dc in ((-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)):
        ar, ac = to_r+dr, to_c+dc
        if 0 <= ar <= 7 and 0 <= ac <= 7 and board[ar][ac] == color + "K":
            if 0 < best_val: best_val = 0; best_sq = (ar, ac)
    return best_sq


def _pinned_lva_check(board, ar, ac, to_r, to_c, color):
    """
    Return True if the piece at (ar, ac) of `color` is pinned to its king
    AND the target square (to_r, to_c) is NOT on the pin ray — meaning the
    capture from (ar,ac) to (to_r,to_c) would be illegal (exposes own king).

    This catches the common false-positive in the hanging-piece penalty where
    SEE finds a pinned attacker (e.g. Nc3 pinned by Bb4 cannot take Qd5).
    """
    opp = "b" if color == "w" else "w"
    # Find own king
    kr = kc = -1
    for r2 in range(8):
        for c2 in range(8):
            if board[r2][c2] == color + "K":
                kr, kc = r2, c2
                break
        if kr != -1: break
    if kr == -1: return False

    # Direction from king toward the attacker
    dr, dc = ar - kr, ac - kc
    if dr == 0 and dc != 0:
        sr, sc = 0, (1 if dc > 0 else -1)
        sliders = {"R", "Q"}
    elif dc == 0 and dr != 0:
        sr, sc = (1 if dr > 0 else -1), 0
        sliders = {"R", "Q"}
    elif abs(dr) == abs(dc) and dr != 0:
        sr, sc = (1 if dr > 0 else -1), (1 if dc > 0 else -1)
        sliders = {"B", "Q"}
    else:
        return False  # Not on a ray with the king → cannot be pinned

    # The path from king to attacker must be completely clear
    cr, cc = kr + sr, kc + sc
    while (cr, cc) != (ar, ac):
        if not (0 <= cr <= 7 and 0 <= cc <= 7): return False
        if board[cr][cc] != "--": return False
        cr += sr; cc += sc

    # Look for an enemy slider beyond the attacker on the same ray
    cr, cc = ar + sr, ac + sc
    pinner = None
    while 0 <= cr <= 7 and 0 <= cc <= 7:
        sq = board[cr][cc]
        if sq == "--": cr += sr; cc += sc; continue
        if sq[0] == opp and sq[1] in sliders:
            pinner = (cr, cc)
        break   # anything (friend, non-slider foe) stops the search

    if pinner is None: return False  # Not pinned

    # The piece IS pinned.  The capture is legal only if (to_r, to_c) lies
    # on the pin ray between the attacker and the pinner (blocking the ray)
    # OR equals the pinner itself (capturing it).
    if (to_r, to_c) == pinner:
        return False  # Legal — captures the pinner

    # Walk from attacker toward pinner; if target is on that segment → legal
    cr, cc = ar + sr, ac + sc
    while (cr, cc) != pinner:
        if (cr, cc) == (to_r, to_c):
            return False  # Legal — move blocks the pin
        cr += sr; cc += sc

    return True  # Illegal capture — piece is pinned off the target ray


def _see(board, to_r, to_c, side):
    """
    Simple SEE: simulate captures on (to_r, to_c) by alternating sides.
    Returns net material gain (positive = good for `side`).
    """
    # Find least valuable attacker of `side`
    def least_valuable_attacker(brd, r, c, color):
        best_val = 999; best_sq = None
        # Pawns
        # White pawn attacks upward: white pawn attacking (r,c) sits at (r+1,c±1)
        # Black pawn attacks downward: black pawn attacking (r,c) sits at (r-1,c±1)
        pawn_src_r = r + 1 if color == "w" else r - 1
        for dc in (-1, 1):
            ar, ac = pawn_src_r, c + dc
            if 0 <= ar <= 7 and 0 <= ac <= 7 and brd[ar][ac] == color+"P":
                if pieceScores["P"] < best_val:
                    best_val = pieceScores["P"]; best_sq = (ar, ac)
        # Knights
        for dr, dc in ((-2,-1),(-2,1),(-1,-2),(-1,2),(1,-2),(1,2),(2,-1),(2,1)):
            ar, ac = r+dr, c+dc
            if 0 <= ar <= 7 and 0 <= ac <= 7 and brd[ar][ac] == color+"N":
                if pieceScores["N"] < best_val:
                    best_val = pieceScores["N"]; best_sq = (ar, ac)
        # Bishops/diagonal sliders
        for dr, dc in ((-1,-1),(-1,1),(1,-1),(1,1)):
            for i in range(1,8):
                ar, ac = r+dr*i, c+dc*i
                if not (0<=ar<=7 and 0<=ac<=7): break
                sq = brd[ar][ac]
                if sq != "--":
                    if sq[0]==color and sq[1] in ("B","Q"):
                        val = pieceScores[sq[1]]
                        if val < best_val: best_val = val; best_sq = (ar,ac)
                    break
        # Rooks/orthogonal sliders
        for dr, dc in ((-1,0),(1,0),(0,-1),(0,1)):
            for i in range(1,8):
                ar, ac = r+dr*i, c+dc*i
                if not (0<=ar<=7 and 0<=ac<=7): break
                sq = brd[ar][ac]
                if sq != "--":
                    if sq[0]==color and sq[1] in ("R","Q"):
                        val = pieceScores[sq[1]]
                        if val < best_val: best_val = val; best_sq = (ar,ac)
                    break
        # King
        for dr, dc in ((-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)):
            ar, ac = r+dr, c+dc
            if 0 <= ar <= 7 and 0 <= ac <= 7 and brd[ar][ac] == color+"K":
                if pieceScores["K"]+1 < best_val:  # K has value 0, use sentinel
                    best_val = 0; best_sq = (ar, ac)
        return best_sq, best_val

    # Copy board for simulation — use list comprehension, not copy.copy
    brd = [row[:] for row in board]
    target_val = pieceScores.get(brd[to_r][to_c][1], 0) if brd[to_r][to_c] != "--" else 0

    gains = [0] * 32
    d = 0
    current_side = side

    attacker_sq, attacker_val = least_valuable_attacker(brd, to_r, to_c, current_side)
    if attacker_sq is None:
        return 0

    gains[0] = target_val
    while attacker_sq is not None:
        d += 1
        gains[d] = attacker_val - gains[d-1]
        # Remove attacker from board
        brd[attacker_sq[0]][attacker_sq[1]] = "--"
        current_side = "b" if current_side == "w" else "w"
        attacker_sq, attacker_val = least_valuable_attacker(brd, to_r, to_c, current_side)
        if d >= 31: break

    # Negamax the gain sequence
    d -= 1
    while d > 0:
        gains[d-1] = -max(-gains[d-1], gains[d])
        d -= 1
    return gains[0]

# ---------------------------------------------------------------------------
# Mating pattern library
# ---------------------------------------------------------------------------
_EDGE_DIST = [min(r, 7-r, c, 7-c) for r in range(8) for c in range(8)]

def _king_sq(board, color):
    for r in range(8):
        for c in range(8):
            if board[r][c] == color + "K":
                return r, c
    return 0, 0

def _count_pieces(board):
    w, b = 0, 0
    for row in board:
        for sq in row:
            if sq == "--" or sq[1] == "K": continue
            if sq[0] == "w": w += 1
            else: b += 1
    return w, b, w + b

def _piece_set(board, color):
    pieces = set()
    for row in board:
        for sq in row:
            if sq != "--" and sq[0] == color and sq[1] != "K":
                pieces.add(sq[1])
    return pieces

def _mating_eval(board, winning_color):
    """
    Heuristic to guide king-ending conversions (KQ/KR/KBB vs bare king).
    Returns a score that:
      1. Pushes the losing king to the edge/corner
      2. Brings the winning king close to the losing king
      3. Rewards pieces that cut off the losing king (rook/queen on same rank/file)
    All terms are scaled large so they dominate the static eval in the range
    where the engine's material-only score would otherwise plateau.
    """
    win_col = winning_color
    los_col = "b" if win_col == "w" else "w"
    wkr, wkc = _king_sq(board, win_col)
    lkr, lkc = _king_sq(board, los_col)
    losing_sq  = lkr * 8 + lkc

    # Term 1: Push losing king to the edge/corner (max when in corner)
    edge_score = (3 - _EDGE_DIST[losing_sq]) * 15

    # Term 2: Bring the winning king close (Chebyshev proximity)
    king_cheby = max(abs(wkr - lkr), abs(wkc - lkc))
    proximity  = (7 - king_cheby) * 5

    # Term 3: Piece activity — each attacking piece close to the losing king
    piece_bonus = 0
    for r in range(8):
        for c in range(8):
            sq = board[r][c]
            if sq == "--" or sq[0] != win_col or sq[1] == "K":
                continue
            p = sq[1]
            dist = abs(r - lkr) + abs(c - lkc)
            piece_bonus += max(0, 7 - dist) * 2
            # Rook/queen on same rank or file as losing king = cut-off bonus
            if p in ("R", "Q"):
                if r == lkr or c == lkc:
                    piece_bonus += 10
            # Queen diagonal alignment
            if p == "Q" and abs(r - lkr) == abs(c - lkc):
                piece_bonus += 6

    # Term 4: King mobility restriction — count how many of the losing king's
    # 8 escape squares are actually covered by winning pieces.  Each covered
    # escape square is worth a large bonus.  This drives the engine toward
    # quiet restriction moves (e.g. Qa6 cutting off a file) rather than
    # perpetual checks that never corner the king.
    covered_escapes = 0
    for dr, dc in ((-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)):
        kr2, kc2 = lkr + dr, lkc + dc
        if not (0 <= kr2 <= 7 and 0 <= kc2 <= 7):
            covered_escapes += 1   # off-board = naturally restricted
            continue
        for r in range(8):
            for c in range(8):
                sq = board[r][c]
                if sq == "--" or sq[0] != win_col: continue
                p = sq[1]
                attacks = False
                if p == "K":
                    attacks = max(abs(r-kr2), abs(c-kc2)) == 1
                elif p == "Q":
                    attacks = (kr2==r or kc2==c or abs(kr2-r)==abs(kc2-c))
                elif p == "R":
                    attacks = (kr2==r or kc2==c)
                elif p == "B":
                    attacks = abs(kr2-r)==abs(kc2-c) and kr2 != r
                elif p == "N":
                    attacks = (abs(kr2-r), abs(kc2-c)) in ((1,2),(2,1))
                if attacks:
                    covered_escapes += 1
                    break
            else:
                continue
            break

    mobility_restriction = covered_escapes * 18

    return min(300.0, 50.0 + edge_score + proximity + piece_bonus + mobility_restriction)

def _detect_mating_position(board):
    wp, bp, _ = _count_pieces(board)
    # Fast path: both sides have multiple pieces — definitely not a mating pattern
    if wp >= 2 and bp >= 2:
        return None

    if bp == 0 and wp > 0:
        # White has pieces, black is bare king
        wpieces = _piece_set(board, "w")
        if "Q" in wpieces: return ("w", "KQ_vs_K")
        if "R" in wpieces: return ("w", "KR_vs_K")
        if len([p for p in wpieces if p == "B"]) >= 2: return ("w", "KBB_vs_K")
        if "B" in wpieces and "N" in wpieces: return ("w", "KBN_vs_K")
        return None

    if wp == 0 and bp > 0:
        # Black has pieces, white is bare king
        bpieces = _piece_set(board, "b")
        if "Q" in bpieces: return ("b", "KQ_vs_K")
        if "R" in bpieces: return ("b", "KR_vs_K")
        if len([p for p in bpieces if p == "B"]) >= 2: return ("b", "KBB_vs_K")
        if "B" in bpieces and "N" in bpieces: return ("b", "KBN_vs_K")
        return None

    if wp > 0 and bp > 0:
        # One side has only pawns, the other has a queen/rook AND no pawns
        # (e.g. KQ vs KP) — guide the winning side to promote/advance
        wpieces = _piece_set(board, "w")
        bpieces = _piece_set(board, "b")
        w_only_pawns = (wpieces <= {"P"})
        b_only_pawns = (bpieces <= {"P"})
        # Only activate mating heuristic if the dominant side has NO pawns
        # (avoids triggering in normal middlegame with 1 piece each)
        w_has_major = bool(wpieces & {"Q", "R"})
        b_has_major = bool(bpieces & {"Q", "R"})
        if b_only_pawns and w_has_major and not ("P" in wpieces):
            return ("w", "KQR_vs_KP")
        if w_only_pawns and b_has_major and not ("P" in bpieces):
            return ("b", "KQR_vs_KP")

    return None

# ---------------------------------------------------------------------------
# Move ordering  (SEE integrated for captures)
# ---------------------------------------------------------------------------
def _move_score(move, tt_move, killer_list, hist, board):
    if move == tt_move: return 20_000
    # Queen promotions are almost always best — rank them just below TT move
    if move.isPawnPromotion and move.promotionChoice == "Q":
        return 19_000
    if move.pieceCaptured != "--":
        # MVV-LVA: rank by (victim value * 10 - attacker value) within SEE bucket
        victim   = pieceScores[move.pieceCaptured[1]]
        attacker = pieceScores[move.pieceMoved[1]]
        mvvlva   = victim * 10 - attacker
        see_val  = _see(board, move.endRow, move.endCol, move.pieceMoved[0])
        if see_val >= 0:
            # Good captures: SEE-positive, sub-ranked by MVV-LVA
            return 10_000 + see_val * 100 + mvvlva
        else:
            # Bad captures: below killers, sub-ranked by MVV-LVA
            return 4_000 + mvvlva
    if move in killer_list: return 9_000
    to_sq = move.endRow * 8 + move.endCol
    return hist.get(move.pieceMoved[1], [0]*64)[to_sq]

def orderMoves(moves, tt_move, depth, board):
    kl = killers[depth] if depth < len(killers) else [None, None]
    return sorted(moves,
                  key=lambda m: _move_score(m, tt_move, kl, history, board),
                  reverse=True)

def _store_killer(move, depth):
    if depth >= len(killers) or move.pieceCaptured != "--": return
    slot = killers[depth]
    if slot[0] != move:
        slot[1] = slot[0]
        slot[0] = move

def _update_history(move, depth):
    if move.pieceCaptured != "--": return
    history[move.pieceMoved[1]][move.endRow * 8 + move.endCol] += depth * depth

# ---------------------------------------------------------------------------
# TT
# ---------------------------------------------------------------------------
_TT_MAX_AGE = 8

def _tt_lookup(key, depth, alpha, beta):
    entry = transposition_table.get(key)
    if entry is None: return False, 0, None
    tt_depth, tt_score, tt_flag, tt_move, tt_gen = entry
    if _tt_generation - tt_gen > _TT_MAX_AGE:
        return False, 0, tt_move
    if tt_depth >= depth:
        if tt_flag == "EXACT":   return True, tt_score, tt_move
        if tt_flag == "LOWERBOUND" and tt_score >= beta: return True, tt_score, tt_move
        if tt_flag == "UPPERBOUND" and tt_score <= alpha: return True, tt_score, tt_move
    return False, 0, tt_move

def _tt_store(key, depth, score, flag, move):
    if len(transposition_table) >= MAX_TT_SIZE:
        _tt_evict()
    transposition_table[key] = (depth, score, flag, move, _tt_generation)

def _tt_evict():
    global transposition_table
    cur = _tt_generation
    # Fast path: remove all stale entries first
    stale = [k for k, v in transposition_table.items() if cur - v[4] > _TT_MAX_AGE]
    for k in stale:
        del transposition_table[k]
    # If still too large, keep only the half with highest depth (best entries)
    # Use random sampling instead of full sort — O(1) amortized
    if len(transposition_table) >= MAX_TT_SIZE * 3 // 4:
        import random
        keys = list(transposition_table.keys())
        # Randomly remove 25% — fast and good enough
        remove_count = len(keys) // 4
        for k in random.sample(keys, remove_count):
            del transposition_table[k]

def _dynamic_depth(gs):
    if _detect_mating_position(gs.board) is not None:
        _, _, total = _count_pieces(gs.board)
        if total == 1:
            pieces = _piece_set(gs.board,"w") | _piece_set(gs.board,"b")
            if pieces == {"R"}: return 1
    return 0

# ---------------------------------------------------------------------------
# Forced-mate search for bare-king endings
# ---------------------------------------------------------------------------
def _find_forced_mate(gs, valid_moves, max_depth=20, time_limit=8.0):
    """
    Dedicated mate search for positions where one side has only a king.
    Iterates to increasing depth until mate found, max_depth exceeded,
    or time_limit seconds elapsed (prevents infinite hang).
    Returns the best move found or None.
    """
    import time as _time
    mating = _detect_mating_position(gs.board)
    if mating is None:
        return None
    winning_color = mating[0]
    if (winning_color == "w") != gs.whiteToMove:
        return None

    best = [None]
    _MATE_TT.clear()  # clear stale entries from previous search
    deadline = _time.time() + time_limit
    for depth in range(1, max_depth + 1):
        if _time.time() > deadline:
            break
        result = _mate_search(gs, depth, -CHECKMATE, CHECKMATE, best, deadline)
        if result >= CHECKMATE - depth - 1:
            break
    return best[0]

_MATE_TT = {}  # separate TT for mate search, not polluted by regular search

def _mate_search(gs, depth, alpha, beta, best_ref, deadline=None):
    import time as _time
    if deadline is not None and _time.time() > deadline:
        return 0  # abort; caller uses best move found so far
    key = gs._boardFingerprint()
    entry = _MATE_TT.get(key)
    if entry is not None:
        tt_depth, tt_score, tt_flag = entry
        if tt_depth >= depth:
            if tt_flag == "EXACT": return tt_score
            if tt_flag == "LOWERBOUND" and tt_score >= beta: return tt_score
            if tt_flag == "UPPERBOUND" and tt_score <= alpha: return tt_score

    if depth <= 0:
        mating = _detect_mating_position(gs.board)
        winning = mating[0] if mating else ("w" if gs.whiteToMove else "b")
        val = _mating_eval(gs.board, winning)
        return val if gs.whiteToMove == (winning == "w") else -val

    moves = gs.getValidMoves()
    if not moves:
        return (-CHECKMATE - depth) if gs.checkmate else 0

    # Fast static move ordering for mate search:
    # 1. Checks (approximated by piece proximity to enemy king)
    # 2. Captures
    # 3. Moves toward enemy king
    # No make/undo needed - avoids the bottleneck of testing every move
    opp_col = "b" if gs.whiteToMove else "w"
    ekr, ekc = _king_sq(gs.board, opp_col)
    def mate_order(m):
        score = 0
        if m.pieceCaptured != "--": score += 200
        # Reward moving closer to enemy king
        old_dist = abs(m.startRow-ekr) + abs(m.startCol-ekc)
        new_dist = abs(m.endRow-ekr)   + abs(m.endCol-ekc)
        score += (old_dist - new_dist) * 10
        # King restriction: count how many of the enemy king's 8 escape
        # squares this piece would cover from its destination.  This rewards
        # quiet boxing-in moves (e.g. Qa6 cutting a file) ahead of perpetual
        # checks that never actually corner the king.
        p = m.pieceMoved[1]
        er, ec = m.endRow, m.endCol
        restriction = 0
        for dr2, dc2 in ((-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)):
            kr2, kc2 = ekr+dr2, ekc+dc2
            if not (0 <= kr2 <= 7 and 0 <= kc2 <= 7):
                restriction += 1   # off-board always restricted
                continue
            attacks = False
            if p == "Q":
                attacks = (kr2==er or kc2==ec or abs(kr2-er)==abs(kc2-ec))
            elif p == "R":
                attacks = (kr2==er or kc2==ec)
            elif p == "B":
                attacks = abs(kr2-er)==abs(kc2-ec) and kr2 != er
            elif p == "K":
                attacks = max(abs(kr2-er), abs(kc2-ec)) == 1
            if attacks:
                restriction += 1
        score += restriction * 30
        # Piece already on same rank/file/diagonal as enemy king (reduced bonus
        # vs. old 150/100 — raw checks no longer automatically beat restriction)
        if p in ("Q","R"):
            if er == ekr or ec == ekc: score += 60
        if p in ("Q","B"):
            if abs(er-ekr) == abs(ec-ekc): score += 50
        return score

    ordered = sorted(moves, key=mate_order, reverse=True)
    alpha_orig = alpha
    best_score = -CHECKMATE
    best_move = None

    for move in ordered:
        gs.makeMoveForSearch(move)
        score = -_mate_search(gs, depth - 1, -beta, -alpha, [None], deadline)
        gs.undoMoveForSearch()
        if score > best_score:
            best_score = score
            best_move = move
            if best_ref is not None:
                best_ref[0] = move
        if best_score > alpha:
            alpha = best_score
        if alpha >= beta:
            break

    flag = ("UPPERBOUND" if best_score <= alpha_orig
            else "LOWERBOUND" if best_score >= beta
            else "EXACT")
    if len(_MATE_TT) < 50000:
        _MATE_TT[key] = (depth, best_score, flag)
    return best_score

# ---------------------------------------------------------------------------
# Top-level search
# ---------------------------------------------------------------------------
# Time management: soft and hard limits per move.
# Soft limit: finish the current depth iteration, then stop.
# Hard limit: interrupt even mid-depth if exceeded.
# Both are wall-clock seconds. Override via batch_games by setting
# ChessAi.MOVE_TIME_SOFT / ChessAi.MOVE_TIME_HARD before each game.
MOVE_TIME_SOFT = 6.0   # finish current depth, then stop
MOVE_TIME_HARD = 10.0  # absolute cutoff even mid-depth

def findBestMove(gs, validMoves):
    import time as _time
    _t0            = _time.time()
    _soft_deadline = _t0 + MOVE_TIME_SOFT
    _move_deadline = _t0 + MOVE_TIME_HARD
    global nextMove, counter, lastScore
    nextMove = None; counter = 0; lastScore = 0

    # Opening book — pick randomly among all book lines that match
    book = _book_move(gs)
    if book is not None and book in validMoves:
        # Safety check: make sure this book move doesn't allow mate in 1.
        # (Fixes: book played 8...cxd5 without noticing 9.Qxe6#)
        gs.makeMoveForSearch(book)
        allows_mate = False
        for m in gs.getValidMoves():
            gs.makeMoveForSearch(m)
            if gs.checkmate:
                allows_mate = True
                gs.undoMoveForSearch()
                break
            gs.undoMoveForSearch()
        gs.undoMoveForSearch()

        if not allows_mate:
            print(f"Book move: {book.getChessNotation()}")
            lastScore = 0
            return book
        else:
            print(f"Book move {book.getChessNotation()} unsafe (allows mate in 1), searching...")

    # Forced-mate search for bare-king endings
    mating_pos = _detect_mating_position(gs.board)
    if mating_pos is not None and mating_pos[1] in ("KQR_vs_KP", "KQ_vs_K", "KR_vs_K", "KBB_vs_K", "KBN_vs_K"):
        _mate_time = 12.0 if mating_pos[1] in ("KQ_vs_K", "KR_vs_K") else 18.0
        mate_move = _find_forced_mate(gs, validMoves, max_depth=40,
                                      time_limit=_mate_time)
        if mate_move is not None and mate_move in validMoves:
            print(f"Forced-mate move: {mate_move.getChessNotation()}")
            return mate_move

    # Syzygy tablebase probe — after mate search so KQ vs K is handled above.
    # Returns None if piece count > MAX_PROBE_PIECES or tablebases unavailable.
    # Only follow Syzygy when it finds a win or draw (not a loss — let search find stalemate tricks).
    tb_move = syzygy_probe_best_move(gs, validMoves)
    if tb_move is not None:
        lastScore = TB_WIN_SCORE
        return tb_move

    turnMultiplier = 1 if gs.whiteToMove else -1
    random.shuffle(validMoves)

    # Filter underpromotions: never promote to B or R.
    # Only keep knight promotions if they give check (potential smothered mate).
    # Queen promotion is always kept.
    def _keep_promo(m):
        if not m.isPawnPromotion:
            return True
        if m.promotionChoice == "Q":
            return True
        if m.promotionChoice == "N":
            # Keep knight promo only if it gives check
            gs.makeMoveForSearch(m)
            gives_check = gs.inCheck()
            gs.undoMoveForSearch()
            return gives_check
        return False  # drop B and R promotions entirely

    validMoves = [m for m in validMoves if _keep_promo(m)]
    if not validMoves:
        # Shouldn't happen, but safety fallback
        validMoves = gs.getValidMoves()
    for i in range(len(killers)): killers[i] = [None, None]
    _init_history()
    newMove()

    game_history = dict(gs.positionCounts)  # real game positions seen so far
    # Remap: any position already seen once in real game starts at 1 in search_history
    # so a single repeat during search hits the >= 2 threshold → triggers contempt
    # This prevents the engine from treating "first repeat in search" as free
    extra        = _dynamic_depth(gs)
    search_depth = DEPTH + extra
    prev_score   = 0
    best_move_from_prev = None
    start = time.time()
    raw   = 0
    root_best = [None]
    completed_depth = 0

    for current_depth in range(1, search_depth + 1):
        now = _time.time()
        # Hard cutoff: interrupt even mid-depth
        if now > _move_deadline:
            print(f"Hard timeout at depth {current_depth-1}")
            break
        # Soft cutoff: don't START a new depth iteration if we're past the soft limit.
        # Always complete at least depth 1 and 2 (very fast); never skip below depth 3.
        if current_depth > 2 and now > _soft_deadline:
            print(f"Soft timeout after depth {completed_depth}")
            break

        if best_move_from_prev is not None:
            try:
                validMoves.remove(best_move_from_prev)
                validMoves.insert(0, best_move_from_prev)
            except ValueError:
                pass

        if current_depth >= 3:
            WINDOW = 0.75   # wider initial window → fewer mis-fires
            new_best = [None]
            try:
                alpha_w = prev_score - WINDOW
                beta_w  = prev_score + WINDOW
                attempt = prev_score
                for _asp_iter in range(4):   # up to 4 exponential widening steps
                    new_best_iter = [None]
                    _deadline = _soft_deadline if _asp_iter == 0 else _move_deadline
                    attempt = _search(gs, validMoves, current_depth,
                                      alpha_w, beta_w,
                                      turnMultiplier, current_depth, game_history,
                                      new_best_iter, deadline=_deadline)
                    if new_best_iter[0] is not None:
                        new_best[0] = new_best_iter[0]
                    if attempt <= alpha_w:
                        # Fail-low: widen lower bound only
                        alpha_w = max(-CHECKMATE, alpha_w - WINDOW * (2 ** _asp_iter))
                    elif attempt >= beta_w:
                        # Fail-high: widen upper bound only
                        beta_w  = min(CHECKMATE,  beta_w  + WINDOW * (2 ** _asp_iter))
                    else:
                        break   # result inside window — done
                raw = attempt
                if new_best[0] is not None:
                    root_best[0] = new_best[0]
            except _SearchTimeout:
                print(f"Timeout during depth {current_depth}, keeping depth {completed_depth} result")
                break
        else:
            try:
                raw = _search(gs, validMoves, current_depth,
                              -CHECKMATE, CHECKMATE,
                              turnMultiplier, current_depth, game_history,
                              root_best, deadline=_soft_deadline)
            except _SearchTimeout:
                print(f"Timeout during depth {current_depth}, keeping depth {completed_depth} result")
                break

        if root_best[0] is not None:
            nextMove = root_best[0]
        prev_score = raw
        best_move_from_prev = nextMove
        completed_depth = current_depth

    elapsed   = time.time() - start
    extra_str = f"+{extra}" if extra else ""
    print(f"Depth {completed_depth}/{search_depth}({DEPTH}{extra_str}) | "
          f"Nodes: {counter} | TT: {len(transposition_table)} | Time: {elapsed:.2f}s")
    lastScore = raw * turnMultiplier
    return nextMove

# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
class _SearchTimeout(Exception):
    """Raised when the search deadline is hit mid-depth."""
    pass

def _search(gs, validMoves, depth, alpha, beta,
            turnMultiplier, root_depth, search_history, root_best=None,
            deadline=None, ply=0):
    global counter
    counter += 1
    if deadline is not None and counter % 500 == 0:
        import time as _t
        if _t.time() > deadline:
            raise _SearchTimeout()

    key = gs._boardFingerprint()
    # Count visits: combine real game history + in-search history
    # Penalise repetition from the first time a position repeats in search
    # (game_history already has the position once if seen before in the game)
    game_visits   = search_history.get(key, 0)
    if game_visits >= 2:
        c = _contempt(gs)
        # When we are clearly winning, returning to a seen position is
        # extremely costly (draws are worth far less than converting).
        # Penalise heavily so the engine actively avoids the repetition path.
        mat = scoreMaterial(gs.board)
        our_mat = mat if gs.whiteToMove else -mat
        if our_mat >= 2.0:
            return c - 30.0   # Strong disincentive: forces search of non-repeating lines
        return c
    if gs.draw:
        c = _contempt(gs)
        mat = scoreMaterial(gs.board)
        our_mat = mat if gs.whiteToMove else -mat
        if our_mat >= 2.0:
            return c - 30.0
        return c

    alpha_orig           = alpha
    hit, tt_score, tt_move = _tt_lookup(key, depth, alpha, beta)
    if hit and depth != root_depth: return tt_score

    if depth <= 0 or ply >= root_depth * 3:
        return _quiescence(gs, alpha, beta, turnMultiplier)

    if validMoves is None:
        validMoves = gs.getValidMoves()
    if not validMoves:
        return (-CHECKMATE - depth) if gs.checkmate else _contempt(gs)

    # Internal Iterative Deepening: if no TT move at deep nodes, do a quick
    # shallow search to get a good move to try first — dramatically improves
    # move ordering and hence alpha-beta pruning efficiency
    if tt_move is None and depth >= 4 and depth != root_depth:
        _search(gs, validMoves, depth - 2, alpha, beta,
                turnMultiplier, root_depth, search_history, deadline=deadline, ply=ply+1)
        _, _, tt_move = _tt_lookup(key, depth - 2, alpha, beta)

    # Null-move pruning — skip in low-material positions (zugzwang risk)
    _in_check = gs.inCheck()
    wp, bp, _total = _count_pieces(gs.board)
    # Count major/minor pieces (not pawns/kings) to avoid endgame zugzwang
    _w_major = sum(1 for r2 in range(8) for c2 in range(8)
                   if gs.board[r2][c2] not in ("--","wP","wK","bP","bK")
                   and gs.board[r2][c2][0]=="w")
    _b_major = sum(1 for r2 in range(8) for c2 in range(8)
                   if gs.board[r2][c2] not in ("--","wP","wK","bP","bK")
                   and gs.board[r2][c2][0]=="b")
    _enough_material = (_w_major >= 2 and _b_major >= 2)
    if depth >= 3 and not _in_check and _enough_material \
            and abs(scoreMaterial(gs.board)) > 1.5 \
            and depth != root_depth:
        old_ep = gs.enpassantPossible
        if old_ep:
            gs.zobristKey ^= ZOBRIST_EP[old_ep[1]]
            gs.enpassantPossible = ()
        gs.whiteToMove = not gs.whiteToMove
        gs.zobristKey ^= ZOBRIST_SIDE
        null_score = -_search(gs, None, depth-3, -beta, -beta+1,
                              -turnMultiplier, root_depth, search_history,
                              deadline=deadline, ply=ply+1)
        gs.whiteToMove = not gs.whiteToMove
        gs.zobristKey ^= ZOBRIST_SIDE
        if old_ep:
            gs.enpassantPossible = old_ep
            gs.zobristKey ^= ZOBRIST_EP[old_ep[1]]
        if null_score >= beta: return beta

    # Compute static eval once and reuse for RFP, razoring, and futility.
    # Previously called scoreBoard() up to 3x per node - now called at most once.
    _need_static = (depth <= 3 and not _in_check and depth != root_depth)
    static_eval  = (turnMultiplier * scoreBoard(gs)) if _need_static else None

    # Reverse Futility Pruning: static eval far above beta -> prune
    _RFP_MARGIN = [0, 1.5, 3.0, 4.5]
    if (_need_static and abs(beta) < CHECKMATE - 100
            and static_eval - _RFP_MARGIN[depth] >= beta):
        return static_eval

    # Razoring: static eval far below alpha -> drop into quiescence
    if _need_static and depth <= 2:
        razor_margin = 3.0 if depth == 1 else 5.0
        if static_eval + razor_margin <= alpha:
            q = _quiescence(gs, alpha, beta, turnMultiplier)
            if q <= alpha:
                return q

    ordered    = orderMoves(validMoves, tt_move, min(depth, len(killers)-1), gs.board)
    best_score = -CHECKMATE
    best_move  = None

    # Futility pruning: reuse static_eval computed above
    _FUTILITY_MARGIN = [0, 1.5, 3.0, 5.0]
    futility_ok   = (_need_static and abs(alpha) < CHECKMATE - 100)
    futility_base = static_eval if futility_ok else 0

    search_history[key] = search_history.get(key, 0) + 1

    for move_idx, move in enumerate(ordered):
        is_quiet  = move.pieceCaptured == "--" and not move.isPawnPromotion

        # Futility pruning — skip quiet moves that can't possibly raise alpha
        if futility_ok and is_quiet and move_idx > 0:
            if futility_base + _FUTILITY_MARGIN[depth] <= alpha:
                continue

        gs.makeMoveForSearch(move)
        nextMoves = gs.getValidMoves()
        new_check = gs.inCheck()

        # --- Extensions ---
        # 1. Check extension: we give check, or we were in check
        raw_ext = (1 if new_check else 0) + (1 if _in_check else 0)

        # 2. Recapture extension: opponent just captured one of our pieces,
        #    and this move recaptures on that same square. Always search to
        #    full depth — never reduce. Fixes "Rd6+ instead of Bxe3" class.
        if raw_ext == 0 and ply < root_depth:
            if (move_idx == 0 and move.pieceCaptured != "--"
                    and ply > 0):
                # Check if the previous half-move was a capture on the same square
                log = gs.moveLog
                if len(log) >= 2:
                    prev = log[-2]   # the move made before us (opponent's last move)
                    if (prev.pieceCaptured != "--"
                            and prev.endRow == move.endRow
                            and prev.endCol == move.endCol):
                        raw_ext = 1

        # 3. Threat extension: after our move, opponent has a SEE-winning
        #    capture on a rook/queen of ours. Catches quiet threats like Bd7→Re6.
        if raw_ext == 0 and ply < root_depth and depth >= 2:
            opp_color = "b" if gs.whiteToMove else "w"
            own_color = "w" if gs.whiteToMove else "b"
            for r2 in range(8):
                for c2 in range(8):
                    sq2 = gs.board[r2][c2]
                    if sq2 == "--" or sq2[0] != own_color: continue
                    if pieceScores.get(sq2[1], 0) >= 5:
                        if _see(gs.board, r2, c2, opp_color) > 0:
                            raw_ext = 1
                            break
                if raw_ext: break

        extension = raw_ext if ply < root_depth else 0

        # LMR: only reduce truly quiet, late, non-tactical moves.
        # NEVER reduce recaptures (move_idx==0 and pieceCaptured != "--").
        is_recapture = (move.pieceCaptured != "--" and move_idx == 0)
        do_lmr = (depth >= 3 and move_idx >= 3 and is_quiet
                  and not _in_check and not new_check and extension == 0
                  and not move.isPawnPromotion and not is_recapture)

        if do_lmr:
            # Conservative reduction: 1 ply for moves 3-7, 2 ply for 8+
            reduction = 1 if move_idx < 8 else 2
            reduction = min(reduction, depth - 2)
            score = -_search(gs, nextMoves, depth-1-reduction,
                             -alpha-1, -alpha, -turnMultiplier,
                             root_depth, search_history,
                             deadline=deadline, ply=ply+1)
            if score > alpha:
                score = -_search(gs, nextMoves, depth-1+extension,
                                 -beta, -alpha, -turnMultiplier,
                                 root_depth, search_history,
                                 deadline=deadline, ply=ply+1)
        elif move_idx > 0 and depth >= 2 and is_quiet:
            # PVS: search later quiet moves with null window first
            score = -_search(gs, nextMoves, depth-1+extension,
                             -alpha-1, -alpha, -turnMultiplier,
                             root_depth, search_history,
                             deadline=deadline, ply=ply+1)
            if score > alpha:
                score = -_search(gs, nextMoves, depth-1+extension,
                                 -beta, -alpha, -turnMultiplier,
                                 root_depth, search_history,
                                 deadline=deadline, ply=ply+1)
        else:
            score = -_search(gs, nextMoves, depth-1+extension,
                             -beta, -alpha, -turnMultiplier,
                             root_depth, search_history,
                             deadline=deadline, ply=ply+1)

        gs.undoMoveForSearch()

        if score > best_score:
            best_score = score
            best_move  = move
            if root_best is not None and depth == root_depth:
                root_best[0] = move
        if best_score > alpha:
            alpha = best_score
        if alpha >= beta:
            _store_killer(move, min(depth, len(killers)-1))
            _update_history(move, depth)
            break

    search_history[key] -= 1
    if search_history[key] == 0:
        del search_history[key]

    flag = ("UPPERBOUND" if best_score <= alpha_orig
            else "LOWERBOUND" if best_score >= beta
            else "EXACT")
    _tt_store(key, depth, best_score, flag, best_move)
    return best_score

# ---------------------------------------------------------------------------
# Quiescence  (SEE-pruned)
# ---------------------------------------------------------------------------
_DELTA_MARGIN = 0.2

def _quiescence(gs, alpha, beta, turnMultiplier, qdepth=0):
    global counter
    counter += 1
    stand_pat = turnMultiplier * scoreBoard(gs)
    if stand_pat >= beta: return beta
    if stand_pat > alpha: alpha = stand_pat
    if qdepth >= 6: return alpha

    # Fast capture-only movegen: use getAllPossibleMoves (no legality filter)
    # then filter to captures only and validate with a make/undo check.
    # This avoids running the full O(n) legality filter for every qnode.
    all_pseudo = gs.getAllPossibleMoves()
    captures = [m for m in all_pseudo if m.pieceCaptured != "--"]

    # Add checks at shallow qdepth for tactical sharpness (extended to qdepth<=2)
    if qdepth <= 2:
        for m in all_pseudo:
            if m.pieceCaptured != "--": continue
            gs.makeMoveForSearch(m)
            gives_check = gs.inCheck()
            gs.undoMoveForSearch()
            if gives_check:
                captures.append(m)

    # SEE-filter and validate legality
    good_captures = []
    for m in captures:
        see_val = _see(gs.board, m.endRow, m.endCol, m.pieceMoved[0])
        if see_val < -pieceScores[m.pieceMoved[1]] * 0.5:
            continue
        # Legality check: make sure move doesn't leave own king in check.
        # After makeMoveForSearch, whiteToMove has flipped to the opponent.
        # Flip it back (with matching Zobrist toggle) to check the king of
        # the side that just moved.
        gs.makeMoveForSearch(m)
        gs.whiteToMove = not gs.whiteToMove
        gs.zobristKey ^= ZOBRIST_SIDE
        legal = not gs.inCheck()
        gs.whiteToMove = not gs.whiteToMove
        gs.zobristKey ^= ZOBRIST_SIDE
        gs.undoMoveForSearch()
        if legal:
            good_captures.append((see_val, m))

    good_captures.sort(key=lambda x: x[0], reverse=True)

    # Hard delta cutoff: if even the best available capture cannot
    # bring us to alpha, there is no point searching any capture.
    if good_captures:
        capture_gains = [pieceScores.get(m.pieceCaptured[1], 0)
                         for _, m in good_captures
                         if m.pieceCaptured != "--"]
        if capture_gains:
            best_gain = max(capture_gains)
            if stand_pat + best_gain + _DELTA_MARGIN <= alpha:
                return alpha

    for _, move in good_captures:
        # Per-move delta: skip if this specific capture cannot raise alpha
        if (move.pieceCaptured != "--" and
                stand_pat + pieceScores[move.pieceCaptured[1]] + _DELTA_MARGIN <= alpha):
            continue
        gs.makeMoveForSearch(move)
        score = -_quiescence(gs, -beta, -alpha, -turnMultiplier, qdepth+1)
        gs.undoMoveForSearch()
        if score >= beta: return beta
        if score > alpha: alpha = score

    return alpha

# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
_PHASE_WEIGHTS = {"Q": 4, "R": 2, "B": 1, "N": 1}

def scoreBoard(gs):
    if gs.checkmate:
        return -CHECKMATE if gs.whiteToMove else CHECKMATE
    if gs.stalemate:
        return _contempt(gs)

    board = gs.board

    mating = _detect_mating_position(board)
    if mating is not None:
        winning_color, _ = mating
        sign = 1 if winning_color == "w" else -1
        base = scoreMaterial(board) + sign * _mating_eval(board, winning_color)
        # Penalise dawdling under the 50-move clock: if clock > 10, subtract
        # a penalty proportional to the clock so the engine urgently converts
        clock_penalty = max(0, gs.halfMoveClock - 10) * 0.3
        return base - sign * clock_penalty

    # Single pass over board — collect everything needed
    pawn_count = 0; white_bishops = 0; black_bishops = 0; pieces = []
    total_material = 0
    for r in range(8):
        for c in range(8):
            sq = board[r][c]
            if sq == "--": continue
            p = sq[1]; col = sq[0]
            if p == "P": pawn_count += 1
            elif p == "B":
                if col == "w": white_bishops += 1
                else: black_bishops += 1
            if col == "w": total_material += pieceScores[p]
            else:          total_material -= pieceScores[p]
            pieces.append((r, c, col, p))

    wp = sum(1 for _,_,c,p in pieces if c=="w" and p!="K")
    bp = sum(1 for _,_,c,p in pieces if c=="b" and p!="K")
    total_pieces = wp + bp
    score   = float(total_material)  # start with material already counted
    # ---- Eval tapering ----
    # phase=1.0 full middlegame, phase=0.0 full endgame
    phase_val = sum(_PHASE_WEIGHTS.get(p,0) for _,_,_,p in pieces)
    phase = min(1.0, phase_val / 24.0)  # clamp to [0,1]
    endgame = phase < 0.5  # keep flag for conditional blocks

    def taper(mg, eg):
        """Interpolate between middlegame and endgame score."""
        return mg * phase + eg * (1.0 - phase)

    w_major = sum(pieceScores[p] for _,_,c,p in pieces if c=="w" and p!="K" and p!="P")
    b_major = sum(pieceScores[p] for _,_,c,p in pieces if c=="b" and p!="K" and p!="P")

    for (r, c, color, piece) in pieces:
        sign   = 1 if color == "w" else -1
        height = (7 - r) if color == "w" else r
        distC  = abs(r - 3.5) + abs(c - 3.5)
        # material already in score, skip re-adding it here

        # --- Hanging piece penalty via SEE ---
        # Use SEE to detect pieces left en prise to ANY attacker, not just pawns.
        # SEE is called once per non-pawn, non-king piece; it's fast (no make/undo).
        # A negative SEE means the piece loses material if the opponent captures.
        if piece != "P" and piece != "K":
            opp_color = "b" if color == "w" else "w"
            see_val = _see(board, r, c, opp_color)
            if see_val > 0:
                # Pin guard: SEE does not respect pins, so a pinned attacker can
                # produce a large false positive (e.g. Nc3 pinned by Bb4 appears
                # to win Qd5 for free, inflating the eval by ~4 pawns).
                # Check whether the least valuable attacker is actually pinned and
                # therefore cannot legally make the capture.
                lva_sq = _find_lva_sq(board, r, c, opp_color)
                if lva_sq is not None and _pinned_lva_check(
                        board, lva_sq[0], lva_sq[1], r, c, opp_color):
                    see_val = 0   # capture is illegal due to pin -- no penalty
                if see_val > 0:
                    penalty = min(see_val, pieceScores[piece]) * 0.6
                    score -= sign * penalty

        if piece == "P":
            # Advancement: worth more in endgame (closer to queening)
            score += sign * height * taper(0.08, 0.18)
            # Central pawn bonus
            if height in (3,4) and c in (3,4): score += sign * taper(0.30, 0.15)
            # Pawn chain protection
            protect_row = r+1 if color=="w" else r-1
            if 0 <= protect_row <= 7:
                if c+1<=7 and board[protect_row][c+1]==color+"P": score+=sign*0.1
                if c-1>=0 and board[protect_row][c-1]==color+"P": score+=sign*0.1
            opp_p  = ("b" if color=="w" else "w")+"P"
            passed = True
            rng    = range(r-1,-1,-1) if color=="w" else range(r+1,8)
            for ahead in rng:
                for fc in range(max(0,c-1), min(7,c+1)+1):
                    if board[ahead][fc]==opp_p:
                        passed=False; break
                if not passed: break
            # Passed pawn: much more valuable in endgame
            if passed: score += sign * height * taper(0.12, 0.30)
            # Doubled pawn penalty
            for other_r in range(8):
                if other_r!=r and board[other_r][c]==color+"P":
                    score -= sign*taper(0.25, 0.15); break
            # Isolated pawn penalty: worse in endgame
            isolated = True
            for other_r in range(8):
                if c-1>=0 and board[other_r][c-1]==color+"P": isolated=False; break
                if c+1<=7 and board[other_r][c+1]==color+"P": isolated=False; break
            if isolated: score -= sign*taper(0.20, 0.35)

        elif piece == "N":
            # Piece-square table: central squares best, corners/edges worst
            _N_PST = [
                -0.50,-0.40,-0.30,-0.30,-0.30,-0.30,-0.40,-0.50,
                -0.40,-0.20, 0.00, 0.05, 0.05, 0.00,-0.20,-0.40,
                -0.30, 0.05, 0.15, 0.20, 0.20, 0.15, 0.05,-0.30,
                -0.30, 0.05, 0.20, 0.25, 0.25, 0.20, 0.05,-0.30,
                -0.30, 0.05, 0.20, 0.25, 0.25, 0.20, 0.05,-0.30,
                -0.30, 0.05, 0.15, 0.20, 0.20, 0.15, 0.05,-0.30,
                -0.40,-0.20, 0.00, 0.05, 0.05, 0.00,-0.20,-0.40,
                -0.50,-0.40,-0.30,-0.30,-0.30,-0.30,-0.40,-0.50,
            ]
            pst_r = (7 - r) if color == "w" else r
            # PST tapered: endgame PST pulls knight to centre more strongly
            _N_PST_EG = [
                -0.60,-0.40,-0.30,-0.30,-0.30,-0.30,-0.40,-0.60,
                -0.40,-0.20, 0.10, 0.10, 0.10, 0.10,-0.20,-0.40,
                -0.30, 0.10, 0.25, 0.30, 0.30, 0.25, 0.10,-0.30,
                -0.30, 0.10, 0.30, 0.40, 0.40, 0.30, 0.10,-0.30,
                -0.30, 0.10, 0.30, 0.40, 0.40, 0.30, 0.10,-0.30,
                -0.30, 0.10, 0.25, 0.30, 0.30, 0.25, 0.10,-0.30,
                -0.40,-0.20, 0.10, 0.10, 0.10, 0.10,-0.20,-0.40,
                -0.60,-0.40,-0.30,-0.30,-0.30,-0.30,-0.40,-0.60,
            ]
            pst_idx = pst_r * 8 + c
            score += sign * taper(_N_PST[pst_idx], _N_PST_EG[pst_idx])
            # Outpost bonus: advanced, unattackable by enemy pawn
            if height in (4,5,6):
                outpost = True
                for dc2 in (-1,1):
                    ac,ar = c+dc2, r+1 if color=="w" else r-1
                    if 0<=ac<=7 and 0<=ar<=7 and board[ar][ac]==("b" if color=="w" else "w")+"P":
                        outpost=False; break
                if outpost: score += sign*taper(0.35, 0.20)
            # Mobility: each reachable square is worth a small bonus
            mobility = sum(1 for dr2,dc2 in ((-2,-1),(-2,1),(-1,-2),(-1,2),(1,-2),(1,2),(2,-1),(2,1))
                          if 0<=r+dr2<=7 and 0<=c+dc2<=7 and board[r+dr2][c+dc2][0]!=color)
            score += sign*mobility*taper(0.05, 0.06)
            # Knights prefer closed positions (more pawns = better)
            score += sign*pawn_count*0.012
            # Always chase enemy king (scaled by endgame phase)
            opp_kr, opp_kc = (gs.blackKingLocation if color == "w" else gs.whiteKingLocation)
            kn_dist = abs(r - opp_kr) + abs(c - opp_kc)
            score += sign * max(0, (6 - kn_dist) * taper(0.02, 0.09))

        elif piece == "B":
            if color=="w" and white_bishops==2: score+=sign*0.3
            elif color=="b" and black_bishops==2: score+=sign*0.3
            dm=0
            for dr2,dc2 in ((-1,-1),(-1,1),(1,-1),(1,1)):
                s=1
                while True:
                    nr,nc=r+dr2*s,c+dc2*s
                    if not(0<=nr<=7 and 0<=nc<=7): break
                    if board[nr][nc]!="--": break
                    dm+=1; s+=1
            score += sign*dm*0.025
            bsc=(r+c)%2
            blocking=sum(1 for pr2,pc2,c2,p2 in pieces
                         if c2==color and p2=="P" and (pr2+pc2)%2==bsc)
            score -= sign*blocking*0.08
            score += sign*taper(0.3/(distC+1) if distC<3 else -0.02*distC,
                                0.15/(distC+1) if distC<3 else -0.01*distC)
            score -= sign*pawn_count*0.01
            if (color=="w" and r==6 and c in(1,6)) or (color=="b" and r==1 and c in(1,6)):
                score += sign*taper(0.15, 0.05)

        elif piece == "R":
            fp=[board[row][c] for row in range(8)]
            # Open file bonus (no pawns at all)
            if all(s[1]!="P" for s in fp if s!="--"): score+=sign*0.55
            # Semi-open file (no own pawns)
            elif all(s!=color+"P" for s in fp if s!="--"): score+=sign*0.28
            # 7th rank (rank 6 for white / rank 1 for black): strong bonus
            seventh = 1 if color == "w" else 6
            if r == seventh:
                opp2 = "b" if color=="w" else "w"
                # Full 7th rank bonus when enemy pawns or king are on that rank
                if any(board[seventh][pc][0]==opp2 for pc in range(8)):
                    score += sign * taper(0.70, 0.50)
                else:
                    score += sign * taper(0.30, 0.20)
            # Doubled rooks on same file
            for row2 in range(8):
                if row2==r: continue
                sq2=board[row2][c]
                if sq2=="--": continue
                if sq2==color+"R": score+=sign*0.25
                break
            # Rook mobility (open squares on its rank/file)
            rmob = 0
            for dr2,dc2 in ((-1,0),(1,0),(0,-1),(0,1)):
                for s in range(1,8):
                    nr,nc=r+dr2*s,c+dc2*s
                    if not(0<=nr<=7 and 0<=nc<=7): break
                    if board[nr][nc]!="--": break
                    rmob += 1
            score += sign * rmob * taper(0.04, 0.05)
            # King proximity in endgame
            wkr,wkc=gs.whiteKingLocation; bkr,bkc=gs.blackKingLocation
            kd=abs(r-(bkr if color=="w" else wkr))+abs(c-(bkc if color=="w" else wkc))
            score += sign*(0.08/(kd+1))*(1-phase)

        elif piece == "Q":
            score += sign*(0.2/(distC+1)) if distC<3 else -sign*0.02*distC
            qm=0
            for dr2,dc2 in ((-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)):
                s=1
                while True:
                    nr,nc=r+dr2*s,c+dc2*s
                    if not(0<=nr<=7 and 0<=nc<=7): break
                    if board[nr][nc]!="--": break
                    qm+=1; s+=1
            score += sign*qm*0.02
            wkr,wkc=gs.whiteKingLocation; bkr,bkc=gs.blackKingLocation
            kd=abs(r-(bkr if color=="w" else wkr))+abs(c-(bkc if color=="w" else wkc))
            score += sign*(0.2/(kd+1))
            # Early queen development penalty
            sr=7 if color=="w" else 0
            mo=sum(1 for col,pt in ((1,"N"),(6,"N"),(2,"B"),(5,"B")) if board[sr][col]!=color+pt)
            queen_start=(7,3) if color=="w" else (0,3)
            if (r,c)!=queen_start and mo<3: score-=sign*0.5

        elif piece == "K":
            has_castling_rights = (
                (color == "w" and (gs.currentCastlingRight.wks or gs.currentCastlingRight.wqs)) or
                (color == "b" and (gs.currentCastlingRight.bks or gs.currentCastlingRight.bqs))
            )
            back_rank = 7 if color == "w" else 0
            # BUG FIX: castled_position must also check the rank.
            # Previously `c in (2, 6) and not has_castling_rights` was True for
            # ANY king on the c- or g-file without castling rights -- including
            # a king that had walked to c3, c4, g3, g5, etc.  Those positions
            # were awarded a pawn-shield BONUS instead of a danger PENALTY,
            # which caused the engine to actively march the king into the centre
            # (Kd2->Kc3->Kc4 in game 19, similar in game 8).
            castled_position = (c in (2, 6) and not has_castling_rights
                                and r == back_rank)
            opp = "b" if color == "w" else "w"

            # --- Middlegame king safety (fades with phase) ---
            if castled_position:
                sr2 = r-1 if color=="w" else r+1
                if 0 <= sr2 <= 7:
                    sh = sum(1 for sc in range(max(0,c-1), min(7,c+1)+1)
                             if board[sr2][sc] == color+"P")
                    score += sign * sh * phase * 0.35
            else:
                score -= sign * phase * 0.5
                if height > 0:
                    score -= sign * height * phase * 0.8
                if c in (3, 4):
                    score -= sign * phase * 1.2
                elif c in (2, 5):
                    score -= sign * phase * 0.4
                if c == 5 and r == back_rank:
                    score -= sign * phase * 1.5
                if has_castling_rights and height > 0:
                    score -= sign * phase * 0.6

            # Back-rank weakness: penalise if king on back rank and
            # has enemy rook/queen on same rank with no escape
            if r == back_rank and phase > 0.15:
                # Count own pawns shielding the escape squares
                escape_pawns = 0
                for ec in range(max(0, c-1), min(7, c+2)):
                    ep_r = back_rank - 1 if color == "w" else back_rank + 1
                    if 0 <= ep_r <= 7 and board[ep_r][ec] == color + "P":
                        escape_pawns += 1
                # Count enemy back-rank attacking pieces
                opp_back_rank_rq = sum(
                    1 for tc in range(8)
                    if board[back_rank][tc] in (opp+"R", opp+"Q")
                )
                if opp_back_rank_rq > 0 and escape_pawns == 0:
                    score -= sign * opp_back_rank_rq * phase * 1.8
                elif escape_pawns > 0 and opp_back_rank_rq > 0:
                    score -= sign * opp_back_rank_rq * phase * 0.6

            # Open/semi-open file next to king: enemy rooks can penetrate
            if phase > 0.2:
                for fc in range(max(0, c-1), min(7, c+2)):
                    pawns_on_file = sum(1 for row2 in range(8)
                                       if board[row2][fc] == color+"P")
                    if pawns_on_file == 0:
                        # Check if enemy has rook/queen on that file
                        opp_on_file = sum(1 for row2 in range(8)
                                          if board[row2][fc] in (opp+"R", opp+"Q"))
                        score -= sign * opp_on_file * phase * 0.45

            # Enemy queen proximity scales with phase
            opp_q = opp + "Q"
            for qr in range(8):
                for qc in range(8):
                    if board[qr][qc] == opp_q:
                        qdist = abs(r - qr) + abs(c - qc)
                        if qdist <= 3:
                            score -= sign * (4 - qdist) * phase * 0.9

            # --- Endgame king activity (grows as phase decreases) ---
            eg_central = taper(0.0, 0.5/(distC+1) if distC<3 else -0.1*distC)
            score += sign * eg_central
            # King proximity to own pawns in endgame (use pieces list, no board scan)
            if phase < 0.8:  # only compute in semi/full endgame
                eg_weight = (1.0 - phase) * 0.06
                for pr,pc,c2,p2 in pieces:
                    if c2==color and p2=="P":
                        score += sign * eg_weight / (abs(r-pr)+abs(c-pc)+1)
            # King proximity to enemy king in endgame (opposition)
            wkr,wkc=gs.whiteKingLocation; bkr,bkc=gs.blackKingLocation
            kd=abs(r-(bkr if color=="w" else wkr))+abs(c-(bkc if color=="w" else wkc))
            score += sign*(1.0-phase)*(0.35/(kd+1))

    # Tempo bonus
    score += 0.05*(1 if gs.whiteToMove else -1)

    # Simplification bonus when winning
    material = total_material
    if abs(material) >= 2.0:
        pieces_traded = 28 - total_pieces
        simp_coeff = 0.15 + (1.0 - phase) * 0.12
        simplify_bonus = (pieces_traded/28.0)*abs(material)*simp_coeff
        score += simplify_bonus if material>0 else -simplify_bonus

    # Theoretically drawn endings: discount score so engine seeks draw.
    if pawn_count == 0 and total_pieces == 2:
        w_types = frozenset(p for _,_,c,p in pieces if c=="w" and p!="K")
        b_types = frozenset(p for _,_,c,p in pieces if c=="b" and p!="K")
        rn = frozenset(["R","N"]); rb = frozenset(["R","B"]); r = frozenset(["R"])
        if (w_types==rn and b_types==r) or (w_types==r and b_types==rn):
            score *= 0.15
        if (w_types==rb and b_types==r) or (w_types==r and b_types==rb):
            score *= 0.20

    # ---------------------------------------------------------------
    # Minor-piece + pawn endgame evaluation
    # Fires whenever we are in a real endgame with <= 4 non-pawn pieces
    # ---------------------------------------------------------------
    if endgame and total_pieces <= 4:
        wkr,wkc=gs.whiteKingLocation; bkr,bkc=gs.blackKingLocation

        # Collect pawns per side
        w_pawns = [(r2,c2) for r2 in range(8) for c2 in range(8) if board[r2][c2]=="wP"]
        b_pawns = [(r2,c2) for r2 in range(8) for c2 in range(8) if board[r2][c2]=="bP"]

        for pw_r,pw_c in w_pawns:
            h2 = 7 - pw_r
            opp_p = "bP"
            passed2 = all(
                board[ar][fc] != opp_p
                for ar in range(pw_r-1,-1,-1)
                for fc in range(max(0,pw_c-1), min(7,pw_c+1)+1)
            )
            # Passed pawn advancement bonus (stronger in endings)
            if passed2:
                score += h2 * 0.25
                # King must escort: bonus for proximity
                kp = abs(wkr-pw_r)+abs(wkc-pw_c)
                score += max(0, (5-kp)*0.12)
            else:
                score += h2 * 0.08
            # King activity: penalise king far from all own pawns
            kp = abs(wkr-pw_r)+abs(wkc-pw_c)
            score -= kp * 0.04

        for pb_r,pb_c in b_pawns:
            h2 = pb_r
            opp_p = "wP"
            passed2 = all(
                board[ar][fc] != opp_p
                for ar in range(pb_r+1,8)
                for fc in range(max(0,pb_c-1), min(7,pb_c+1)+1)
            )
            if passed2:
                score -= h2 * 0.25
                kp = abs(bkr-pb_r)+abs(bkc-pb_c)
                score -= max(0, (5-kp)*0.12)
            else:
                score -= h2 * 0.08
            kp = abs(bkr-pb_r)+abs(bkc-pb_c)
            score += kp * 0.04

        # King centralisation: in minor-piece endings king must be active
        w_king_centrality = max(0, 3.5 - abs(wkr-3.5) - abs(wkc-3.5))
        b_king_centrality = max(0, 3.5 - abs(bkr-3.5) - abs(bkc-3.5))
        score += w_king_centrality * 0.10
        score -= b_king_centrality * 0.10

        # Wrong-colour bishop: B + rook-pawn on a/h file is a draw
        # if the defending king reaches the promotion corner.
        # Detect and reduce the winning side score accordingly.
        for color2, sign2, own_pawns, def_kr, def_kc in [
                ("w", 1, w_pawns, bkr, bkc),
                ("b", -1, b_pawns, wkr, wkc)]:
            bishops = [(r2,c2) for r2 in range(8) for c2 in range(8)
                       if board[r2][c2]==color2+"B"]
            if len(bishops) == 1 and len(own_pawns) >= 1:
                br2,bc2 = bishops[0]
                bish_color = (br2+bc2) % 2
                for pr2,pc2 in own_pawns:
                    if pc2 in (0,7):  # rook pawn
                        promo_r2 = 0 if color2=="w" else 7
                        promo_c2 = pc2
                        corner_color = (promo_r2+promo_c2) % 2
                        if bish_color != corner_color:
                            # Wrong-colour bishop - draw if defender
                            # king reaches the corner
                            corner_dist = max(abs(def_kr-promo_r2), abs(def_kc-promo_c2))
                            if corner_dist <= 2:
                                score -= sign2 * 1.5  # nearly drawn
                            elif corner_dist <= 4:
                                score -= sign2 * 0.6

        # Pawn breakthrough threat: two or three connected passers
        # that can force promotion regardless of enemy pieces.
        # Simple heuristic: if side has 2+ passed pawns on adjacent
        # files, add a large urgency bonus.
        for color2, sign2, own_pawns in [
                ("w", 1, w_pawns), ("b", -1, b_pawns)]:
            opp_p2 = ("b" if color2=="w" else "w")+"P"
            passed_cols = []
            for pr2,pc2 in own_pawns:
                is_pass = True
                rng3 = range(pr2-1,-1,-1) if color2=="w" else range(pr2+1,8)
                for ar in rng3:
                    for fc in range(max(0,pc2-1), min(7,pc2+1)+1):
                        if board[ar][fc]==opp_p2:
                            is_pass=False; break
                    if not is_pass: break
                if is_pass: passed_cols.append(pc2)
            passed_cols.sort()
            connected = sum(1 for i in range(len(passed_cols)-1)
                           if passed_cols[i+1]-passed_cols[i]==1)
            if connected >= 1:
                score += sign2 * connected * 0.4

        # Piece escort: minor piece should stay close to own passed pawns
        for color2, sign2, own_pawns in [
                ("w", 1, w_pawns), ("b", -1, b_pawns)]:
            minors = [(r2,c2) for r2 in range(8) for c2 in range(8)
                      if board[r2][c2] in (color2+"N", color2+"B")]
            passed_pawns = []
            for pr2,pc2 in own_pawns:
                opp_p3 = ("b" if color2=="w" else "w")+"P"
                is_pass = True
                rng3 = range(pr2-1,-1,-1) if color2=="w" else range(pr2+1,8)
                for ar in rng3:
                    for fc in range(max(0,pc2-1), min(7,pc2+1)+1):
                        if board[ar][fc]==opp_p3:
                            is_pass=False; break
                    if not is_pass: break
                if is_pass: passed_pawns.append((pr2,pc2))
            if minors and passed_pawns:
                for mr2,mc2 in minors:
                    min_dist = min(abs(mr2-pr2)+abs(mc2-pc2)
                                  for pr2,pc2 in passed_pawns)
                    score += sign2 * max(0, (6-min_dist)*0.07)

    # King opposition in pawn endgame
    if total_pieces==0 and pawn_count>0:
        wkr,wkc=gs.whiteKingLocation; bkr,bkc=gs.blackKingLocation
        king_dist=abs(wkr-bkr)+abs(wkc-bkc)
        # Direct opposition bonus
        if king_dist==2:
            score += 0.4*(1 if not gs.whiteToMove else -1)
        # Strong king-pawn proximity reward
        for r2 in range(8):
            for c2 in range(8):
                if board[r2][c2]=="wP":
                    score += 0.15/(abs(wkr-r2)+abs(wkc-c2)+1)
                elif board[r2][c2]=="bP":
                    score -= 0.15/(abs(bkr-r2)+abs(bkc-c2)+1)
        # Square of the pawn rule: if defending king cannot enter the
        # promotion square (chebyshev), the pawn queens by force.
        for r2 in range(8):
            for c2 in range(8):
                sq2 = board[r2][c2]
                if sq2 == "--" or sq2[1] != "P": continue
                pcol = sq2[0]
                promo_r = 0 if pcol == "w" else 7
                steps_to_promo = r2 if pcol == "w" else (7 - r2)
                if steps_to_promo == 0: continue
                def_kr, def_kc = (bkr, bkc) if pcol == "w" else (wkr, wkc)
                def_dist = max(abs(def_kr - promo_r), abs(def_kc - c2))
                # Defending side gets an extra step on their move
                if (pcol == "w") != gs.whiteToMove:
                    in_square = def_dist <= steps_to_promo
                else:
                    in_square = def_dist <= steps_to_promo - 1
                if not in_square:
                    bonus = 2.5 + steps_to_promo * 0.1
                    score += bonus if pcol == "w" else -bonus

    # R+P vs R endgame guidance (Lucena/Philidor principles)
    # Reward: rook behind passed pawn, pawn advance, king support
    if total_pieces == 2 and pawn_count > 0:
        wkr,wkc=gs.whiteKingLocation; bkr,bkc=gs.blackKingLocation
        w_rooks = [(r2,c2) for r2 in range(8) for c2 in range(8) if board[r2][c2]=="wR"]
        b_rooks = [(r2,c2) for r2 in range(8) for c2 in range(8) if board[r2][c2]=="bR"]
        if w_rooks and b_rooks:
            for r2 in range(8):
                for c2 in range(8):
                    sq2 = board[r2][c2]
                    if sq2 == "--" or sq2[1] != "P": continue
                    pcol = sq2[0]; sign2 = 1 if pcol=="w" else -1
                    h2 = (7-r2) if pcol=="w" else r2
                    own_rooks = w_rooks if pcol=="w" else b_rooks
                    def_rooks = b_rooks if pcol=="w" else w_rooks
                    own_kr  = wkr if pcol=="w" else bkr
                    own_kc  = wkc if pcol=="w" else bkc
                    def_kr  = bkr if pcol=="w" else wkr
                    def_kc  = bkc if pcol=="w" else wkc
                    # Rook-behind-passed-pawn bonus
                    for rr,rc in own_rooks:
                        if rc == c2:
                            if (pcol=="w" and rr>r2) or (pcol=="b" and rr<r2):
                                score += sign2 * 0.45
                    # Pawn advancement
                    score += sign2 * h2 * 0.12
                    # King proximity to own pawn
                    kp_dist = abs(own_kr-r2)+abs(own_kc-c2)
                    score += sign2 * max(0, (6-kp_dist)*0.06)
                    # Cut-off: enemy king far from pawn file scores well
                    cutoff_dist = abs(def_kc - c2)
                    score += sign2 * min(cutoff_dist, 4) * 0.08

                    # ---- Lucena position recognition (attacker wins) ----
                    # Conditions: pawn on 6th/7th rank, own king directly in
                    # front of pawn, defending king cut off by >=3 files,
                    # own rook behind the pawn on same file.
                    pawn_height = h2  # 0=rank1, 7=rank8
                    if pawn_height >= 5:   # pawn on rank 6 or 7
                        king_in_front = (
                            own_kc == c2 and
                            ((pcol=="w" and own_kr < r2) or
                             (pcol=="b" and own_kr > r2))
                        )
                        rook_behind = any(
                            rc == c2 and
                            ((pcol=="w" and rr > r2) or (pcol=="b" and rr < r2))
                            for rr, rc in own_rooks
                        )
                        king_cutoff = cutoff_dist >= 3
                        if king_in_front and rook_behind and king_cutoff:
                            score += sign2 * 2.5   # near-certain win

                    # ---- Philidor position recognition (defender draws) ----
                    # Defending rook sits on the 3rd rank (from pawn's side),
                    # i.e. 6th rank from the attacker's perspective, while the
                    # pawn has not yet reached that rank.  This is the standard
                    # Philidor drawing technique.
                    # For white pawn: philidor_row = 2 (rank 6 for black's rook)
                    # For black pawn: philidor_row = 5 (rank 3 for white's rook)
                    philidor_row = 2 if pcol=="w" else 5
                    pawn_past_philidor = (pcol=="w" and r2 <= philidor_row) or \
                                        (pcol=="b" and r2 >= philidor_row)
                    if not pawn_past_philidor:
                        rook_on_philidor = any(rr == philidor_row
                                               for rr, rc in def_rooks)
                        if rook_on_philidor:
                            # Defending side achieves the Philidor placement —
                            # reduce the attacker's score to reflect the draw.
                            score -= sign2 * 0.9

    # 50-move clock urgency
    clock=gs.halfMoveClock
    if clock>20:
        urgency=(clock-20)/80.0
        if _detect_mating_position(gs.board) is not None:
            # Mating position: increase urgency to force quick mate
            if material>0.5:  score += urgency*material*0.3
            elif material<-0.5: score -= urgency*abs(material)*0.3
        else:
            if material>0.5:  score -= urgency*material*0.5
            elif material<-0.5: score += urgency*abs(material)*0.5

    # NOTE: syzygy_score_adjust intentionally removed from here.
    # It was returning ±900 mid-search for any position with ≤5 pieces,
    # even when the engine's chosen move wasn't the Syzygy best move.
    # Syzygy is handled cleanly in findBestMove() instead.

    return score

def scoreMaterial(board):
    score=0
    for row in board:
        for sq in row:
            if sq[0]=="w": score+=pieceScores[sq[1]]
            elif sq[0]=="b": score-=pieceScores[sq[1]]
    return score