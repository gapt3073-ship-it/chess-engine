# user input, display
import pygame as p
import datetime
import os
import sys
import threading
import copy
from Chess import ChessEngine, ChessAi
from Chess.ChessEngine import GameState

# ---------------------------------------------------------------------------
# Stockfish integration (optional — only used when SF mode is selected)
# ---------------------------------------------------------------------------
STOCKFISH_PATH = os.environ.get(
    "STOCKFISH_PATH",
    r"C:\Users\jonas\Chess\Chess\stockfish\stockfish-windows-x86-64-avx2.exe"
)
SF_ELO_DEFAULT = 1500

def _load_chess_lib():
    try:
        import chess, chess.engine
        return chess, chess.engine
    except ImportError:
        return None, None

def gs_to_chess_board(gs):
    import chess
    board = chess.Board()
    board.clear()
    pt_map = {"P": chess.PAWN, "N": chess.KNIGHT, "B": chess.BISHOP,
              "R": chess.ROOK,  "Q": chess.QUEEN,  "K": chess.KING}
    for r in range(8):
        for c in range(8):
            sq = gs.board[r][c]
            if sq == "--": continue
            color = chess.WHITE if sq[0] == "w" else chess.BLACK
            board.set_piece_at(chess.square(c, 7 - r),
                               chess.Piece(pt_map[sq[1]], color))
    board.turn = chess.WHITE if gs.whiteToMove else chess.BLACK
    rights = 0
    cr = gs.currentCastlingRight
    if cr.wks: rights |= chess.BB_H1
    if cr.wqs: rights |= chess.BB_A1
    if cr.bks: rights |= chess.BB_H8
    if cr.bqs: rights |= chess.BB_A8
    board.castling_rights = rights
    if gs.enpassantPossible:
        ep_r, ep_c = gs.enpassantPossible
        board.ep_square = chess.square(ep_c, 7 - ep_r)
    else:
        board.ep_square = None
    board.halfmove_clock  = gs.halfMoveClock
    board.fullmove_number = len(gs.moveLog) // 2 + 1
    return board

def uci_to_gs_move(uci_move, gs, valid_moves):
    import chess
    fr = 7 - chess.square_rank(uci_move.from_square)
    fc =     chess.square_file(uci_move.from_square)
    tr = 7 - chess.square_rank(uci_move.to_square)
    tc =     chess.square_file(uci_move.to_square)
    promo_map = {chess.QUEEN: "Q", chess.ROOK: "R",
                 chess.BISHOP: "B", chess.KNIGHT: "N"}
    promo = promo_map.get(uci_move.promotion, "Q")
    for m in valid_moves:
        if m.startRow == fr and m.startCol == fc and \
                m.endRow == tr and m.endCol == tc:
            if m.isPawnPromotion:
                if m.promotionChoice == promo:
                    return m
            else:
                return m
    return None


# ---------------------------------------------------------------------------
# PGN export
# ---------------------------------------------------------------------------
def generatePGN(gs, playerOne, playerTwo):
    import chess as _chess
    os.makedirs("Chess/PGN", exist_ok=True)
    date_str    = datetime.date.today().strftime("%Y.%m.%d")
    white_name  = "Human"  if playerOne else "Engine"
    black_name  = "Human"  if playerTwo else "Engine"

    if gs.checkmate:
        result = "0-1" if gs.whiteToMove else "1-0"
    elif gs.stalemate or gs.draw:
        result = "1/2-1/2"
    else:
        result = "*"

    headers = (
        f'[Event "Chess Game"]\n'
        f'[Site "Local"]\n'
        f'[Date "{date_str}"]\n'
        f'[White "{white_name}"]\n'
        f'[Black "{black_name}"]\n'
        f'[Result "{result}"]\n'
    )

    def _move_to_uci(move):
        fr = _chess.square(move.startCol, 7 - move.startRow)
        to = _chess.square(move.endCol,   7 - move.endRow)
        promo = None
        if move.isPawnPromotion:
            promo = {"Q": _chess.QUEEN, "R": _chess.ROOK,
                     "B": _chess.BISHOP, "N": _chess.KNIGHT
                     }.get(move.promotionChoice, _chess.QUEEN)
        return _chess.Move(fr, to, promotion=promo)

    chess_board = _chess.Board()
    moves_text = ""
    for i, move in enumerate(gs.moveLog):
        if i % 2 == 0:
            moves_text += f"{i // 2 + 1}. "
        uci_move = _move_to_uci(move)
        try:
            notation = chess_board.san(uci_move)
            chess_board.push(uci_move)
        except Exception:
            notation = move.getChessNotation()
            try:
                chess_board.push(uci_move)
            except Exception:
                pass
        moves_text += notation + " "
    moves_text += result

    words = moves_text.split(" ")
    lines, current_line = [], ""
    for word in words:
        if not word:
            continue
        if len(current_line) + len(word) + 1 > 80:
            lines.append(current_line)
            current_line = word
        else:
            current_line = (current_line + " " + word).strip()
    if current_line:
        lines.append(current_line)

    pgn = headers + "\n" + "\n".join(lines) + "\n"
    print("\n" + "=" * 60)
    print("PGN:")
    print("=" * 60)
    print(pgn)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = f"Chess/PGN/game_{timestamp}.pgn"
    with open(filename, "w") as f:
        f.write(pgn)
    print(f"PGN saved to {filename}")
    print("=" * 60 + "\n")
    return pgn


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
p.init()
BOARD_WIDTH    = BOARD_HEIGHT = 512
LOG_PANEL_WIDTH = 200
EVAL_BAR_WIDTH  = 24
WIDTH           = EVAL_BAR_WIDTH + BOARD_WIDTH + LOG_PANEL_WIDTH
HEIGHT          = BOARD_HEIGHT
DIMENSION       = 8
SQUARE_SIZE     = BOARD_HEIGHT // DIMENSION
MAX_FPS         = 15
IMAGES          = {}

PROMO_PIECES    = ["Q", "R", "B", "N"]     # order shown in picker


# ---------------------------------------------------------------------------
# Image loading
# ---------------------------------------------------------------------------
def load_images():
    pieces = ["wP","wR","wB","wQ","wK","wN","bN","bP","bR","bB","bQ","bK"]
    for piece in pieces:
        IMAGES[piece] = p.transform.scale(
            p.image.load("images/" + piece + ".png"),
            (SQUARE_SIZE, SQUARE_SIZE),
        )


# ---------------------------------------------------------------------------
# Promotion picker
# ---------------------------------------------------------------------------
def drawPromotionPicker(screen, color):
    """
    Draw a semi-transparent overlay with 4 piece choices.
    Returns the (x, y, w, h) rects for each piece in order Q R B N
    so the caller can hit-test clicks.
    """
    overlay = p.Surface((BOARD_WIDTH, HEIGHT), p.SRCALPHA)
    overlay.fill((0, 0, 0, 160))
    screen.blit(overlay, (EVAL_BAR_WIDTH, 0))

    picker_w  = SQUARE_SIZE * 4
    picker_h  = SQUARE_SIZE + 16
    picker_x  = EVAL_BAR_WIDTH + (BOARD_WIDTH - picker_w) // 2
    picker_y  = (HEIGHT - picker_h) // 2

    p.draw.rect(screen, p.Color(40, 40, 40),
                (picker_x - 4, picker_y - 4, picker_w + 8, picker_h + 8),
                border_radius=6)
    p.draw.rect(screen, p.Color(220, 220, 220),
                (picker_x, picker_y, picker_w, picker_h),
                border_radius=4)

    font  = p.font.SysFont("Helvetica", 11, bold=True)
    label = font.render("Choose promotion piece", True, p.Color(30, 30, 30))
    screen.blit(label,
                (picker_x + (picker_w - label.get_width()) // 2,
                 picker_y - 20))

    rects = []
    for i, piece_type in enumerate(PROMO_PIECES):
        px = picker_x + i * SQUARE_SIZE
        py = picker_y + 8
        piece_key = color + piece_type
        screen.blit(IMAGES[piece_key], p.Rect(px, py, SQUARE_SIZE, SQUARE_SIZE))
        rects.append(p.Rect(px, py, SQUARE_SIZE, SQUARE_SIZE))

    return rects


# ---------------------------------------------------------------------------
# Mode selection screen
# ---------------------------------------------------------------------------
def draw_menu(screen, font_big, font_med, selected, elo):
    screen.fill(p.Color(30, 30, 30))
    title = font_big.render("Chess", True, p.Color(220, 220, 220))
    screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 40))

    options = [
        ("Engine vs Engine",   "engine_engine"),
        ("Human vs Engine",    "human_engine"),
        ("Engine vs Human",    "engine_human"),
        ("Human vs Human",     "human_human"),
        ("Your Engine vs SF",  "engine_sf"),
        ("SF vs Your Engine",  "sf_engine"),
        ("Human vs SF",        "human_sf"),
    ]

    rects = []
    for i, (label, key) in enumerate(options):
        col = i % 2
        row = i // 2
        bw, bh = 260, 44
        bx = WIDTH // 2 - bw - 10 + col * (bw + 20)
        by = 120 + row * (bh + 12)
        is_sel = (key == selected)
        bg  = p.Color(70, 130, 180)  if is_sel else p.Color(55, 55, 55)
        border = p.Color(100, 160, 210) if is_sel else p.Color(80, 80, 80)
        p.draw.rect(screen, bg,     (bx, by, bw, bh), border_radius=6)
        p.draw.rect(screen, border, (bx, by, bw, bh), 2, border_radius=6)
        txt = font_med.render(label, True, p.Color(255, 255, 255))
        screen.blit(txt, (bx + bw // 2 - txt.get_width() // 2,
                          by + bh // 2 - txt.get_height() // 2))
        rects.append((p.Rect(bx, by, bw, bh), key))

    # Elo selector (only relevant for SF modes)
    elo_y = 120 + 4 * (44 + 12) + 10
    elo_label = font_med.render(f"Stockfish Elo: {elo}", True, p.Color(180, 180, 180))
    screen.blit(elo_label, (WIDTH // 2 - elo_label.get_width() // 2, elo_y))
    hint = font_med.render("← → to change Elo", True, p.Color(100, 100, 100))
    screen.blit(hint, (WIDTH // 2 - hint.get_width() // 2, elo_y + 28))

    # Start button
    start_rect = p.Rect(WIDTH // 2 - 100, elo_y + 68, 200, 44)
    p.draw.rect(screen, p.Color(60, 160, 60),  start_rect, border_radius=6)
    p.draw.rect(screen, p.Color(90, 200, 90),  start_rect, 2, border_radius=6)
    start_txt = font_big.render("Start", True, p.Color(255, 255, 255))
    screen.blit(start_txt, (start_rect.x + start_rect.w // 2 - start_txt.get_width() // 2,
                             start_rect.y + start_rect.h // 2 - start_txt.get_height() // 2))

    return rects, start_rect

def run_menu(screen):
    font_big = p.font.SysFont("Helvetica", 28, bold=True)
    font_med = p.font.SysFont("Helvetica", 16)
    selected = "human_engine"
    elo      = SF_ELO_DEFAULT
    elo_step = 100
    elo_min, elo_max = 1000, 2800

    while True:
        rects, start_rect = draw_menu(screen, font_big, font_med, selected, elo)
        p.display.flip()

        for e in p.event.get():
            if e.type == p.QUIT:
                p.quit(); sys.exit()
            elif e.type == p.MOUSEBUTTONDOWN:
                mx, my = p.mouse.get_pos()
                if start_rect.collidepoint(mx, my):
                    return selected, elo
                for rect, key in rects:
                    if rect.collidepoint(mx, my):
                        selected = key
            elif e.type == p.KEYDOWN:
                if e.key == p.K_RETURN:
                    return selected, elo
                if e.key == p.K_RIGHT:
                    elo = min(elo_max, elo + elo_step)
                if e.key == p.K_LEFT:
                    elo = max(elo_min, elo - elo_step)

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main():
    clock  = p.time.Clock()
    screen = p.display.set_mode((WIDTH, HEIGHT))
    p.display.set_caption("Chess")
    load_images()

    # --- Mode selection ---
    mode, sf_elo = run_menu(screen)

    # Translate mode string into player flags
    # playerOne/Two: True=human, False=engine/sf
    # sf_white/sf_black: True if that side is Stockfish
    playerOne  = mode.startswith("human")
    playerTwo  = mode.endswith("human")
    sf_white   = mode.startswith("sf")
    sf_black   = mode.endswith("sf")

    # Start Stockfish if needed
    sf_engine = None
    if sf_white or sf_black:
        chess_lib, chess_engine_lib = _load_chess_lib()
        if chess_lib is None:
            print("python-chess not installed. Run: pip install chess")
            sf_white = sf_black = False
        else:
            try:
                sf_engine = chess_engine_lib.SimpleEngine.popen_uci(STOCKFISH_PATH)
                sf_engine.configure({"UCI_LimitStrength": True, "UCI_Elo": sf_elo})
                print(f"Stockfish started at Elo {sf_elo}")
            except Exception as e:
                print(f"Could not start Stockfish: {e}")
                sf_engine = None
                sf_white = sf_black = False

    screen.fill(p.Color("white"))
    gs          = ChessEngine.GameState()
    validMoves  = gs.getValidMoves()
    moveMade    = False
    animate     = False

    running      = True
    sqSelected   = ()
    playerClicks = []
    gameOver     = False
    evalScore    = 0

    pendingPromoMove = None
    promotionPicker  = False
    promoRects       = []

    # AI threading state
    ai_thinking = False
    ai_thread   = None
    ai_result   = [None]

    try:
      while running:
        is_sf_turn = (gs.whiteToMove and sf_white) or \
                     (not gs.whiteToMove and sf_black)
        humanTurn  = (gs.whiteToMove and playerOne and not sf_white) or \
                     (not gs.whiteToMove and playerTwo and not sf_black)

        for e in p.event.get():
            if e.type == p.QUIT:
                running = False

            elif e.type == p.MOUSEBUTTONDOWN and promotionPicker:
                mx, my = p.mouse.get_pos()
                for i, rect in enumerate(promoRects):
                    if rect.collidepoint(mx, my):
                        choice = PROMO_PIECES[i]
                        color  = "w" if gs.whiteToMove else "b"
                        target = ChessEngine.Move(
                            (pendingPromoMove.startRow, pendingPromoMove.startCol),
                            (pendingPromoMove.endRow,   pendingPromoMove.endCol),
                            gs.board,
                            enpassantMove=pendingPromoMove.isEnpassantMove,
                            promotionChoice=choice,
                        )
                        for vm in validMoves:
                            if vm == target:
                                gs.makeMove(vm)
                                print(vm.getChessNotation())
                                moveMade = True
                                animate  = True
                                break
                        promotionPicker  = False
                        pendingPromoMove = None
                        sqSelected       = ()
                        playerClicks     = []
                        break
                else:
                    promotionPicker  = False
                    pendingPromoMove = None
                    sqSelected       = ()
                    playerClicks     = []

            elif e.type == p.MOUSEBUTTONDOWN:
                if not gameOver and humanTurn and not promotionPicker:
                    location = p.mouse.get_pos()
                    col = (location[0] - EVAL_BAR_WIDTH) // SQUARE_SIZE
                    row = location[1] // SQUARE_SIZE
                    if col >= DIMENSION or col < 0:
                        continue
                    if sqSelected == (row, col):
                        sqSelected   = ()
                        playerClicks = []
                    else:
                        sqSelected = (row, col)
                        playerClicks.append(sqSelected)
                    if len(playerClicks) == 2:
                        move    = ChessEngine.Move(playerClicks[0], playerClicks[1], gs.board)
                        matched = [vm for vm in validMoves if
                                   vm.startRow == move.startRow and
                                   vm.startCol == move.startCol and
                                   vm.endRow   == move.endRow   and
                                   vm.endCol   == move.endCol]
                        if matched:
                            if matched[0].isPawnPromotion and \
                                    len(set(m.promotionChoice for m in matched)) > 1:
                                pendingPromoMove = matched[0]
                                promotionPicker  = True
                            else:
                                gs.makeMove(matched[0])
                                print(matched[0].getChessNotation())
                                moveMade     = True
                                animate      = True
                                sqSelected   = ()
                                playerClicks = []
                        else:
                            if not moveMade:
                                playerClicks = [sqSelected]

            elif e.type == p.KEYDOWN:
                if e.key == p.K_z and not promotionPicker:
                    gs.undoMove()
                    moveMade = True
                    animate  = False
                if e.key == p.K_r:
                    ChessAi.clearTranspositionTable()
                    gs           = ChessEngine.GameState()
                    validMoves   = gs.getValidMoves()
                    sqSelected   = ()
                    playerClicks = []
                    moveMade     = False
                    animate      = False
                    gameOver     = False
                    evalScore    = 0
                    promotionPicker  = False
                    pendingPromoMove = None
                    ai_thinking  = False
                    ai_thread    = None
                    ai_result    = [None]

        # --- Stockfish move ---
        if not gameOver and is_sf_turn and not promotionPicker and sf_engine:
            board    = gs_to_chess_board(gs)
            import chess.engine as _ceng
            sf_result = sf_engine.play(board, _ceng.Limit(depth=12))
            sf_move   = uci_to_gs_move(sf_result.move, gs, validMoves)
            if sf_move:
                gs.makeMove(sf_move)
                print(f"SF: {sf_move.getChessNotation()}")
                moveMade = True
                animate  = True
            else:
                # fallback
                fb = ChessAi.findRandomMove(validMoves)
                if fb:
                    gs.makeMove(fb)
                    moveMade = True
                    animate  = True

        # --- Your engine move (threaded so UI never freezes) ---
        elif not gameOver and not humanTurn and not is_sf_turn and not promotionPicker:
            if not ai_thinking:
                # Deep-copy gs so the search never touches the live board
                _gs_snap    = copy.deepcopy(gs)
                _moves_snap = _gs_snap.getValidMoves()
                ai_thinking = True
                ai_result   = [None]
                def _ai_worker(gs_ref, moves_ref, result_ref):
                    try:
                        m = ChessAi.findBestMove(gs_ref, moves_ref)
                        if m is None:
                            m = ChessAi.findRandomMove(moves_ref)
                        result_ref[0] = m
                    except Exception as e:
                        print(f"AI worker error: {e}")
                        result_ref[0] = ChessAi.findRandomMove(moves_ref)
                _t = threading.Thread(
                    target=_ai_worker,
                    args=(_gs_snap, _moves_snap, ai_result),
                    daemon=True)
                _t.start()
                ai_thread = _t
            elif ai_thread is not None and not ai_thread.is_alive():
                # Thread finished - apply the move
                AIMove = ai_result[0]
                ai_thinking = False
                ai_thread   = None
                if AIMove is not None:
                    gs.makeMove(AIMove)
                    print(AIMove.getChessNotation())
                    moveMade = True
                    animate  = True

        if moveMade:
            if animate:
                animateMove(gs.moveLog[-1], screen, gs.board, clock)
            validMoves = gs.getValidMoves()
            moveMade   = False
            animate    = False
            evalScore  = (ChessAi.lastScore if not humanTurn
                          else ChessAi.scoreBoard(gs))

        # Show "Thinking..." overlay while AI is computing
        drawGameState(screen, gs, validMoves, sqSelected)
        drawEvalBar(screen, evalScore)
        drawMoveLog(screen, gs)

        if promotionPicker:
            color      = "w" if gs.whiteToMove else "b"
            promoRects = drawPromotionPicker(screen, color)

        if gs.checkmate:
            if not gameOver:
                generatePGN(gs, playerOne, playerTwo)
            gameOver = True
            drawText(screen, "Black wins by checkmate"
                     if gs.whiteToMove else "White wins by checkmate")
        elif gs.stalemate:
            if not gameOver:
                generatePGN(gs, playerOne, playerTwo)
            gameOver = True
            drawText(screen, "Stalemate")
        elif gs.draw:
            if not gameOver:
                generatePGN(gs, playerOne, playerTwo)
            gameOver = True
            drawText(screen, gs.drawReason)

        clock.tick(MAX_FPS)
        p.display.flip()

    finally:
        if sf_engine:
            sf_engine.quit()


# ---------------------------------------------------------------------------
# Eval bar
# ---------------------------------------------------------------------------
def drawEvalBar(screen, score):
    CHECKMATE_ = ChessAi.CHECKMATE
    is_mate    = abs(score) >= CHECKMATE_ - ChessAi.DEPTH - 1
    bar_h      = HEIGHT

    p.draw.rect(screen, p.Color(30, 30, 30), p.Rect(0, 0, EVAL_BAR_WIDTH, bar_h))

    if is_mate:
        white_fraction = 1.0 if score > 0 else 0.0
    else:
        MAX_SCORE = 10.0
        clamped   = max(-MAX_SCORE, min(MAX_SCORE, score))
        white_fraction = (clamped + MAX_SCORE) / (2 * MAX_SCORE)

    white_h = int(bar_h * white_fraction)
    black_h = bar_h - white_h
    p.draw.rect(screen, p.Color(40, 40, 40),
                p.Rect(0, 0, EVAL_BAR_WIDTH, black_h))
    p.draw.rect(screen, p.Color(240, 240, 240),
                p.Rect(0, black_h, EVAL_BAR_WIDTH, white_h))
    p.draw.line(screen, p.Color(100, 100, 100),
                (0, bar_h // 2), (EVAL_BAR_WIDTH, bar_h // 2), 1)

    font = p.font.SysFont("Courier", 10, bold=True)
    if is_mate:
        mate_moves  = max(1, (CHECKMATE_ - abs(score) + 1) // 2)
        label       = f"M{mate_moves}"
        label_color = p.Color(255, 80, 80) if score < 0 else p.Color(80, 220, 80)
    else:
        label       = f"{abs(score):.1f}"
        label_color = p.Color(160, 160, 160)

    surf    = font.render(label, True, label_color)
    label_y = black_h + 3 if white_h > 20 else black_h - surf.get_height() - 2
    label_y = max(2, min(bar_h - surf.get_height() - 2, label_y))
    screen.blit(surf, (2, label_y))


# ---------------------------------------------------------------------------
# Move log panel
# ---------------------------------------------------------------------------
def drawMoveLog(screen, gs):
    log_rect = p.Rect(EVAL_BAR_WIDTH + BOARD_WIDTH, 0, LOG_PANEL_WIDTH, HEIGHT)
    p.draw.rect(screen, p.Color(30, 30, 30), log_rect)

    title_font = p.font.SysFont("Helvetica", 14, bold=True)
    title_surf = title_font.render("Move Log", True, p.Color(180, 180, 180))
    screen.blit(title_surf, (EVAL_BAR_WIDTH + BOARD_WIDTH + 10, 8))
    p.draw.line(screen, p.Color(70, 70, 70),
                (EVAL_BAR_WIDTH + BOARD_WIDTH, 28), (WIDTH, 28), 1)

    move_font   = p.font.SysFont("Courier", 16)
    move_log    = gs.moveLog
    line_height = 22
    y_start     = 36
    max_lines   = (HEIGHT - y_start) // line_height

    move_pairs = []
    for i in range(0, len(move_log), 2):
        white = move_log[i].getChessNotation()
        black = move_log[i+1].getChessNotation() if i+1 < len(move_log) else ""
        move_pairs.append((i // 2 + 1, white, black))

    visible = move_pairs[-max_lines:] if len(move_pairs) > max_lines else move_pairs
    x = EVAL_BAR_WIDTH + BOARD_WIDTH + 10

    for idx, (num, white, black) in enumerate(visible):
        y = y_start + idx * line_height
        screen.blit(move_font.render(f"{num}.", True, p.Color(140,140,140)), (x, y))
        screen.blit(move_font.render(white, True, p.Color(255,255,255)), (x+28, y))
        if black:
            screen.blit(move_font.render(black, True, p.Color(200,200,200)),
                        (x+28+68, y))


# ---------------------------------------------------------------------------
# Board drawing helpers
# ---------------------------------------------------------------------------
colors = [p.Color("white"), p.Color("gray")]


def highlightSquares(screen, gs, validMoves, sqSelected):
    # Last-move highlight: yellow tint on from/to squares
    if gs.moveLog:
        last = gs.moveLog[-1]
        lm_surf = p.Surface((SQUARE_SIZE, SQUARE_SIZE))
        lm_surf.set_alpha(80)
        lm_surf.fill(p.Color(255, 255, 0))  # yellow
        for sq_r, sq_c in ((last.startRow, last.startCol),
                            (last.endRow,   last.endCol)):
            screen.blit(lm_surf,
                        (EVAL_BAR_WIDTH + sq_c * SQUARE_SIZE,
                         sq_r * SQUARE_SIZE))
    if sqSelected != ():
        r, c = sqSelected
        if gs.board[r][c][0] == ("w" if gs.whiteToMove else "b"):
            s = p.Surface((SQUARE_SIZE, SQUARE_SIZE))
            s.set_alpha(100)
            s.fill(p.Color("blue"))
            screen.blit(s, (EVAL_BAR_WIDTH + c * SQUARE_SIZE, r * SQUARE_SIZE))
            s.fill(p.Color("lightblue"))
            for move in validMoves:
                if move.startRow == r and move.startCol == c:
                    screen.blit(s, (EVAL_BAR_WIDTH + move.endCol * SQUARE_SIZE,
                                    move.endRow * SQUARE_SIZE))


def drawGameState(screen, gs, validMoves, sqSelected):
    drawBoard(screen)
    highlightSquares(screen, gs, validMoves, sqSelected)
    drawPieces(screen, gs.board)


def drawBoard(screen):
    for r in range(DIMENSION):
        for c in range(DIMENSION):
            color = colors[(r + c) % 2]
            p.draw.rect(screen, color,
                        p.Rect(EVAL_BAR_WIDTH + c * SQUARE_SIZE,
                               r * SQUARE_SIZE, SQUARE_SIZE, SQUARE_SIZE))


def drawPieces(screen, board):
    for r in range(DIMENSION):
        for c in range(DIMENSION):
            piece = board[r][c]
            if piece != "--":
                screen.blit(IMAGES[piece],
                            p.Rect(EVAL_BAR_WIDTH + c * SQUARE_SIZE,
                                   r * SQUARE_SIZE, SQUARE_SIZE, SQUARE_SIZE))


def animateMove(move, screen, board, clock):
    dR = move.endRow - move.startRow
    dC = move.endCol - move.startCol
    framesPerSquare = 5
    frameCount = (abs(dR) + abs(dC)) * framesPerSquare
    for frame in range(frameCount + 1):
        r = move.startRow + dR * frame / frameCount
        c = move.startCol + dC * frame / frameCount
        drawBoard(screen)
        drawPieces(screen, board)
        color     = colors[(move.endRow + move.endCol) % 2]
        endSquare = p.Rect(EVAL_BAR_WIDTH + move.endCol * SQUARE_SIZE,
                           move.endRow * SQUARE_SIZE, SQUARE_SIZE, SQUARE_SIZE)
        p.draw.rect(screen, color, endSquare)
        if move.pieceCaptured != "--":
            if move.isEnpassantMove:
                # Captured pawn sits on the same rank the moving pawn started
                endSquare = p.Rect(EVAL_BAR_WIDTH + move.endCol * SQUARE_SIZE,
                                   move.startRow * SQUARE_SIZE,
                                   SQUARE_SIZE, SQUARE_SIZE)
            screen.blit(IMAGES[move.pieceCaptured], endSquare)
        screen.blit(IMAGES[move.pieceMoved],
                    p.Rect(EVAL_BAR_WIDTH + int(c * SQUARE_SIZE),
                           int(r * SQUARE_SIZE), SQUARE_SIZE, SQUARE_SIZE))
        p.display.flip()
        clock.tick(60)


def drawText(screen, text):
    font       = p.font.SysFont("Helvetica", 32, True, False)
    textObject = font.render(text, 0, p.Color("lightblue"))
    textLocation = p.Rect(EVAL_BAR_WIDTH, 0, BOARD_WIDTH, HEIGHT).move(
        BOARD_WIDTH / 2 - textObject.get_width() / 2,
        HEIGHT / 2 - textObject.get_height() / 2,
    )
    screen.blit(textObject, textLocation)
    screen.blit(font.render(text, 0, p.Color("Blue")),
                textLocation.move(2, 2))


if __name__ == "__main__":
    main()