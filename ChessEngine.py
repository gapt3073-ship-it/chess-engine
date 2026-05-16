import random as _random

# ---------------------------------------------------------------------------
# Zobrist hashing – built once at import time
# ---------------------------------------------------------------------------
_PIECES = ["wP","wR","wN","wB","wQ","wK","bP","bR","bN","bB","bQ","bK"]
_PIECE_IDX = {p: i for i, p in enumerate(_PIECES)}

_rng = _random.Random(0xDEADBEEF)          # deterministic seed
ZOBRIST_PIECE   = [[_rng.getrandbits(64) for _ in range(64)] for _ in range(12)]
ZOBRIST_SIDE    = _rng.getrandbits(64)      # XOR in when black to move
ZOBRIST_CASTLE  = [_rng.getrandbits(64) for _ in range(16)]   # 4-bit mask
ZOBRIST_EP      = [_rng.getrandbits(64) for _ in range(8)]    # one per file


def _piece_hash(piece, sq):
    """Return Zobrist contribution for a piece on square index sq (0-63)."""
    idx = _PIECE_IDX.get(piece)
    if idx is None:
        return 0
    return ZOBRIST_PIECE[idx][sq]


def _castle_mask(cr):
    return (cr.wks << 3) | (cr.wqs << 2) | (cr.bks << 1) | cr.bqs


# ---------------------------------------------------------------------------
# GameState
# ---------------------------------------------------------------------------
class GameState():
    def __init__(self):
        self.board = [
            ["bR","bN","bB","bQ","bK","bB","bN","bR"],
            ["bP","bP","bP","bP","bP","bP","bP","bP"],
            ["--","--","--","--","--","--","--","--"],
            ["--","--","--","--","--","--","--","--"],
            ["--","--","--","--","--","--","--","--"],
            ["--","--","--","--","--","--","--","--"],
            ["wP","wP","wP","wP","wP","wP","wP","wP"],
            ["wR","wN","wB","wQ","wK","wB","wN","wR"],
        ]
        self.moveFunctions = {
            "P": self.getPawnMoves, "R": self.getRookMoves,
            "N": self.getKnightMoves, "B": self.getBishopMoves,
            "Q": self.getQueenMoves,  "K": self.getKingMoves,
        }
        self.whiteToMove        = True
        self.moveLog            = []
        self.whiteKingLocation  = (7, 4)
        self.blackKingLocation  = (0, 4)
        self.checkmate          = False
        self.stalemate          = False
        self.draw               = False
        self.drawReason         = ""
        self.halfMoveClock      = 0
        self.halfMoveClockLog   = [0]
        self._search_clock_stack = []   # for makeMoveForSearch/undo
        self.positionCounts     = {}
        self.enpassantPossible  = ()
        self.currentCastlingRight = CastleRights(True, True, True, True)
        self.castleRightsLog    = [
            CastleRights(True, True, True, True)
        ]

        # --- Zobrist ---
        self.zobristKey = self._computeFullHash()

    # ------------------------------------------------------------------
    # Zobrist helpers
    # ------------------------------------------------------------------
    def _computeFullHash(self):
        h = 0
        for r in range(8):
            for c in range(8):
                p = self.board[r][c]
                if p != "--":
                    h ^= _piece_hash(p, r * 8 + c)
        if not self.whiteToMove:
            h ^= ZOBRIST_SIDE
        h ^= ZOBRIST_CASTLE[_castle_mask(self.currentCastlingRight)]
        if self.enpassantPossible:
            h ^= ZOBRIST_EP[self.enpassantPossible[1]]
        return h

    def _boardFingerprint(self):
        """Integer Zobrist key – used as TT key and repetition key."""
        return self.zobristKey

    # ------------------------------------------------------------------
    # makeMove  (full – updates positionCounts and halfMoveClock)
    # ------------------------------------------------------------------
    def makeMove(self, move):
        self._applyMove(move)
        self.halfMoveClockLog.append(self.halfMoveClock)
        fingerprint = self.zobristKey
        self.positionCounts[fingerprint] = \
            self.positionCounts.get(fingerprint, 0) + 1

    # ------------------------------------------------------------------
    # makeMoveForSearch / undoMoveForSearch
    # – skip positionCounts / halfMoveClockLog bookkeeping for speed
    # ------------------------------------------------------------------
    def makeMoveForSearch(self, move):
        # Save halfMoveClock — _applyMove modifies it but _revertMove
        # can't restore it without the log (skipped for speed).
        self._search_clock_stack.append(self.halfMoveClock)
        self._applyMove(move)

    def undoMoveForSearch(self):
        self._revertMove()
        # Restore halfMoveClock from our own stack
        if self._search_clock_stack:
            self.halfMoveClock = self._search_clock_stack.pop()

    # ------------------------------------------------------------------
    # undoMove  (full)
    # ------------------------------------------------------------------
    def undoMove(self):
        if not self.moveLog:
            return
        fingerprint = self.zobristKey
        self._revertMove()
        if fingerprint in self.positionCounts:
            self.positionCounts[fingerprint] -= 1
            if self.positionCounts[fingerprint] == 0:
                del self.positionCounts[fingerprint]
        self.halfMoveClockLog.pop()
        self.halfMoveClock = self.halfMoveClockLog[-1]

    # ------------------------------------------------------------------
    # _applyMove  (shared core)
    # ------------------------------------------------------------------
    def _applyMove(self, move):
        cr_old = _castle_mask(self.currentCastlingRight)
        ep_old = self.enpassantPossible

        # XOR out old state contributions
        self.zobristKey ^= ZOBRIST_CASTLE[cr_old]
        if ep_old:
            self.zobristKey ^= ZOBRIST_EP[ep_old[1]]

        # Remove moving piece from source
        self.zobristKey ^= _piece_hash(move.pieceMoved,
                                       move.startRow * 8 + move.startCol)
        self.board[move.startRow][move.startCol] = "--"

        # Remove captured piece (normal capture)
        if move.pieceCaptured != "--" and not move.isEnpassantMove:
            self.zobristKey ^= _piece_hash(move.pieceCaptured,
                                           move.endRow * 8 + move.endCol)

        # Place piece at destination
        landing = move.pieceMoved
        if move.isPawnPromotion:
            landing = move.pieceMoved[0] + move.promotionChoice
        self.board[move.endRow][move.endCol] = landing
        self.zobristKey ^= _piece_hash(landing,
                                       move.endRow * 8 + move.endCol)

        # En passant capture
        if move.isEnpassantMove:
            cap_row = move.startRow          # same rank as pawn that moved
            self.zobristKey ^= _piece_hash(move.pieceCaptured,
                                           cap_row * 8 + move.endCol)
            self.board[cap_row][move.endCol] = "--"

        # Castling – move the rook
        if move.isCastleMove:
            if move.endCol - move.startCol == 2:   # kingside
                rook_src_col, rook_dst_col = move.endCol + 1, move.endCol - 1
            else:                                   # queenside
                rook_src_col, rook_dst_col = move.endCol - 2, move.endCol + 1
            rook = self.board[move.endRow][rook_src_col]
            self.zobristKey ^= _piece_hash(rook,
                                           move.endRow * 8 + rook_src_col)
            self.board[move.endRow][rook_src_col] = "--"
            self.board[move.endRow][rook_dst_col] = rook
            self.zobristKey ^= _piece_hash(rook,
                                           move.endRow * 8 + rook_dst_col)

        self.moveLog.append(move)
        self.whiteToMove = not self.whiteToMove
        self.zobristKey ^= ZOBRIST_SIDE

        # King location
        if move.pieceMoved == "wK":
            self.whiteKingLocation = (move.endRow, move.endCol)
        elif move.pieceMoved == "bK":
            self.blackKingLocation = (move.endRow, move.endCol)

        # En passant possibility
        if move.pieceMoved[1] == "P" and abs(move.startRow - move.endRow) == 2:
            self.enpassantPossible = (
                (move.startRow + move.endRow) // 2, move.startCol)
        else:
            self.enpassantPossible = ()

        # Half-move clock
        if move.pieceMoved[1] == "P" or move.pieceCaptured != "--":
            self.halfMoveClock = 0
        else:
            self.halfMoveClock += 1

        # Castle rights
        self.updateCastleRights(move)
        self.castleRightsLog.append(
            CastleRights(self.currentCastlingRight.wks,
                         self.currentCastlingRight.bks,
                         self.currentCastlingRight.wqs,
                         self.currentCastlingRight.bqs))

        cr_new = _castle_mask(self.currentCastlingRight)
        self.zobristKey ^= ZOBRIST_CASTLE[cr_new]
        if self.enpassantPossible:
            self.zobristKey ^= ZOBRIST_EP[self.enpassantPossible[1]]

    # ------------------------------------------------------------------
    # _revertMove  (shared core)
    # ------------------------------------------------------------------
    def _revertMove(self):
        if not self.moveLog:
            return

        cr_old = _castle_mask(self.currentCastlingRight)
        ep_old = self.enpassantPossible
        self.zobristKey ^= ZOBRIST_CASTLE[cr_old]
        if ep_old:
            self.zobristKey ^= ZOBRIST_EP[ep_old[1]]

        move = self.moveLog.pop()
        self.whiteToMove = not self.whiteToMove
        self.zobristKey ^= ZOBRIST_SIDE

        # Restore moving piece to source
        self.board[move.startRow][move.startCol] = move.pieceMoved
        self.zobristKey ^= _piece_hash(move.pieceMoved,
                                       move.startRow * 8 + move.startCol)

        # Remove whatever is at destination
        landing = self.board[move.endRow][move.endCol]
        self.zobristKey ^= _piece_hash(landing,
                                       move.endRow * 8 + move.endCol)
        self.board[move.endRow][move.endCol] = move.pieceCaptured

        # Restore normal captured piece hash
        if move.pieceCaptured != "--" and not move.isEnpassantMove:
            self.zobristKey ^= _piece_hash(move.pieceCaptured,
                                           move.endRow * 8 + move.endCol)

        # En passant restore
        if move.isEnpassantMove:
            cap_row = move.startRow
            self.board[move.endRow][move.endCol] = "--"   # clear ghost square
            self.board[cap_row][move.endCol] = move.pieceCaptured
            self.zobristKey ^= _piece_hash(move.pieceCaptured,
                                           cap_row * 8 + move.endCol)
            # Restore the en passant square to the square the capturing pawn
            # moved TO (which is the ep target square for the previous move).
            # We reconstruct it from the previous move in the log.
            if len(self.moveLog) > 0:
                prev = self.moveLog[-1]
                if prev.pieceMoved[1] == "P" and \
                        abs(prev.startRow - prev.endRow) == 2:
                    self.enpassantPossible = (
                        (prev.startRow + prev.endRow) // 2, prev.startCol)
                else:
                    self.enpassantPossible = ()
            else:
                self.enpassantPossible = ()
        elif move.pieceMoved[1] == "P" and abs(move.startRow - move.endRow) == 2:
            self.enpassantPossible = ()
        else:
            # Restore ep from the move before this one
            if len(self.moveLog) > 0:
                prev = self.moveLog[-1]
                if prev.pieceMoved[1] == "P" and \
                        abs(prev.startRow - prev.endRow) == 2:
                    self.enpassantPossible = (
                        (prev.startRow + prev.endRow) // 2, prev.startCol)
                else:
                    self.enpassantPossible = ()
            else:
                self.enpassantPossible = ()

        # Castle rights
        self.castleRightsLog.pop()
        last = self.castleRightsLog[-1]
        self.currentCastlingRight = CastleRights(
            last.wks, last.bks, last.wqs, last.bqs)

        # Undo rook move for castling
        if move.isCastleMove:
            if move.endCol - move.startCol == 2:
                rook_src_col, rook_dst_col = move.endCol + 1, move.endCol - 1
            else:
                rook_src_col, rook_dst_col = move.endCol - 2, move.endCol + 1
            rook = self.board[move.endRow][rook_dst_col]
            self.zobristKey ^= _piece_hash(rook,
                                           move.endRow * 8 + rook_dst_col)
            self.board[move.endRow][rook_dst_col] = "--"
            self.board[move.endRow][rook_src_col] = rook
            self.zobristKey ^= _piece_hash(rook,
                                           move.endRow * 8 + rook_src_col)

        # King location
        if move.pieceMoved == "wK":
            self.whiteKingLocation = (move.startRow, move.startCol)
        elif move.pieceMoved == "bK":
            self.blackKingLocation = (move.startRow, move.startCol)

        self.checkmate  = False
        self.stalemate  = False
        self.draw       = False
        self.drawReason = ""

        cr_new = _castle_mask(self.currentCastlingRight)
        self.zobristKey ^= ZOBRIST_CASTLE[cr_new]
        if self.enpassantPossible:
            self.zobristKey ^= ZOBRIST_EP[self.enpassantPossible[1]]

    # ------------------------------------------------------------------
    # Insufficient material
    # ------------------------------------------------------------------
    def _insufficientMaterial(self):
        whitePieces, blackPieces = [], []
        whiteBishopColor = blackBishopColor = None
        for r in range(8):
            for c in range(8):
                sq = self.board[r][c]
                if sq == "--":
                    continue
                piece = sq[1]
                if sq[0] == "w":
                    if piece in ("Q", "R", "P"):
                        return False
                    whitePieces.append(piece)
                    if piece == "B":
                        whiteBishopColor = (r + c) % 2
                else:
                    if piece in ("Q", "R", "P"):
                        return False
                    blackPieces.append(piece)
                    if piece == "B":
                        blackBishopColor = (r + c) % 2
        w = [p for p in whitePieces if p != "K"]
        b = [p for p in blackPieces if p != "K"]
        if not w and not b:
            return True
        if not w and len(b) == 1 and b[0] in ("N", "B"):
            return True
        if not b and len(w) == 1 and w[0] in ("N", "B"):
            return True
        if len(w) == 1 and w[0] == "B" and len(b) == 1 and b[0] == "B":
            if whiteBishopColor == blackBishopColor:
                return True
        return False

    # ------------------------------------------------------------------
    # Castle rights update
    # ------------------------------------------------------------------
    def updateCastleRights(self, move):
        if move.pieceMoved == "wK":
            self.currentCastlingRight.wks = False
            self.currentCastlingRight.wqs = False
        elif move.pieceMoved == "bK":
            self.currentCastlingRight.bks = False
            self.currentCastlingRight.bqs = False
        elif move.pieceMoved == "wR":
            if move.startRow == 7:
                if move.startCol == 0:
                    self.currentCastlingRight.wqs = False
                elif move.startCol == 7:
                    self.currentCastlingRight.wks = False
        elif move.pieceMoved == "bR":
            if move.startRow == 0:
                if move.startCol == 0:
                    self.currentCastlingRight.bqs = False
                elif move.startCol == 7:
                    self.currentCastlingRight.bks = False
        if move.pieceCaptured == "wR":
            if move.endRow == 7:
                if move.endCol == 0:
                    self.currentCastlingRight.wqs = False
                elif move.endCol == 7:
                    self.currentCastlingRight.wks = False
        elif move.pieceCaptured == "bR":
            if move.endRow == 0:
                if move.endCol == 0:
                    self.currentCastlingRight.bqs = False
                elif move.endCol == 7:
                    self.currentCastlingRight.bks = False

    # ------------------------------------------------------------------
    # Valid move generation
    # ------------------------------------------------------------------
    def getValidMoves(self):
        tempEP     = self.enpassantPossible
        tempCR     = CastleRights(self.currentCastlingRight.wks,
                                  self.currentCastlingRight.bks,
                                  self.currentCastlingRight.wqs,
                                  self.currentCastlingRight.bqs)
        moves = self.getAllPossibleMoves()
        if self.whiteToMove:
            self.getCastleMoves(self.whiteKingLocation[0],
                                self.whiteKingLocation[1], moves)
        else:
            self.getCastleMoves(self.blackKingLocation[0],
                                self.blackKingLocation[1], moves)

        for i in range(len(moves) - 1, -1, -1):
            self.makeMoveForSearch(moves[i])
            # After _applyMove, whiteToMove flipped to the opponent.
            # We need to check if the side that just moved is in check,
            # i.e. the side that is now NOT whiteToMove.
            # Temporarily flip whiteToMove for the check only — but we
            # must also keep zobristKey consistent so we toggle ZOBRIST_SIDE.
            # Simpler: directly check the correct king square.
            self.whiteToMove = not self.whiteToMove
            in_check = self.inCheck()
            self.whiteToMove = not self.whiteToMove
            self.undoMoveForSearch()
            if in_check:
                del moves[i]            # O(1) by index, not O(n) search

        if len(moves) == 0:
            if self.inCheck():
                self.checkmate = True
            else:
                self.stalemate = True
        else:
            self.checkmate  = False
            self.stalemate  = False
            self.draw       = False
            self.drawReason = ""
            if self.halfMoveClock >= 100:
                self.draw = True
                self.drawReason = "Draw by 50-move rule"
            elif self._insufficientMaterial():
                self.draw = True
                self.drawReason = "Draw by insufficient material"
            elif self.positionCounts.get(self.zobristKey, 0) >= 3:
                self.draw = True
                self.drawReason = "Draw by threefold repetition"

        self.enpassantPossible    = tempEP
        self.currentCastlingRight = tempCR
        return moves

    # ------------------------------------------------------------------
    def inCheck(self):
        if self.whiteToMove:
            return self.squareUnderAttack(*self.whiteKingLocation)
        return self.squareUnderAttack(*self.blackKingLocation)

    def squareUnderAttack(self, r, c):
        enemy = "b" if self.whiteToMove else "w"
        b = self.board

        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            while 0 <= nr < 8 and 0 <= nc < 8:
                sq = b[nr][nc]
                if sq != "--":
                    if sq[0] == enemy and sq[1] in ("R", "Q"):
                        return True
                    break
                nr += dr; nc += dc

        for dr, dc in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
            nr, nc = r + dr, c + dc
            while 0 <= nr < 8 and 0 <= nc < 8:
                sq = b[nr][nc]
                if sq != "--":
                    if sq[0] == enemy and sq[1] in ("B", "Q"):
                        return True
                    break
                nr += dr; nc += dc

        for dr, dc in ((-2,-1),(-2,1),(-1,-2),(-1,2),(1,-2),(1,2),(2,-1),(2,1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < 8 and 0 <= nc < 8:
                sq = b[nr][nc]
                if sq[0] == enemy and sq[1] == "N":
                    return True

        for dr, dc in ((-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < 8 and 0 <= nc < 8:
                sq = b[nr][nc]
                if sq[0] == enemy and sq[1] == "K":
                    return True

        pawn_rows = (-1,) if self.whiteToMove else (1,)
        for dr in pawn_rows:
            for dc in (-1, 1):
                nr, nc = r + dr, c + dc
                if 0 <= nr < 8 and 0 <= nc < 8:
                    sq = b[nr][nc]
                    if sq[0] == enemy and sq[1] == "P":
                        return True
        return False

    # ------------------------------------------------------------------
    # Move generators
    # ------------------------------------------------------------------
    def getAllPossibleMoves(self):
        moves = []
        for r in range(8):
            for c in range(8):
                turn = self.board[r][c][0]
                if (turn == "w" and self.whiteToMove) or \
                   (turn == "b" and not self.whiteToMove):
                    piece = self.board[r][c][1]
                    self.moveFunctions[piece](r, c, moves)
        return moves

    def getPawnMoves(self, r, c, moves):
        """Generate pawn moves including all underpromotion choices."""
        PROMO_PIECES = ("Q", "R", "B", "N")

        def add_pawn_move(start, end, ep=False):
            """Append move(s), expanding promotions into all 4 choices."""
            m = Move(start, end, self.board, enpassantMove=ep)
            if m.isPawnPromotion:
                for choice in PROMO_PIECES:
                    moves.append(Move(start, end, self.board,
                                      enpassantMove=ep,
                                      promotionChoice=choice))
            else:
                moves.append(m)

        if self.whiteToMove:
            if r - 1 >= 0 and self.board[r-1][c] == "--":
                add_pawn_move((r, c), (r-1, c))
                if r == 6 and self.board[r-2][c] == "--":
                    add_pawn_move((r, c), (r-2, c))
            if r - 1 >= 0 and c - 1 >= 0:
                if self.board[r-1][c-1] != "--" and self.board[r-1][c-1][0] == "b":
                    add_pawn_move((r, c), (r-1, c-1))
                elif (r-1, c-1) == self.enpassantPossible:
                    add_pawn_move((r, c), (r-1, c-1), ep=True)
            if r - 1 >= 0 and c + 1 <= 7:
                if self.board[r-1][c+1] != "--" and self.board[r-1][c+1][0] == "b":
                    add_pawn_move((r, c), (r-1, c+1))
                elif (r-1, c+1) == self.enpassantPossible:
                    add_pawn_move((r, c), (r-1, c+1), ep=True)
        else:
            if r + 1 <= 7 and self.board[r+1][c] == "--":
                add_pawn_move((r, c), (r+1, c))
                if r == 1 and self.board[r+2][c] == "--":
                    add_pawn_move((r, c), (r+2, c))
            if r + 1 <= 7 and c - 1 >= 0:
                if self.board[r+1][c-1] != "--" and self.board[r+1][c-1][0] == "w":
                    add_pawn_move((r, c), (r+1, c-1))
                elif (r+1, c-1) == self.enpassantPossible:
                    add_pawn_move((r, c), (r+1, c-1), ep=True)
            if r + 1 <= 7 and c + 1 <= 7:
                if self.board[r+1][c+1] != "--" and self.board[r+1][c+1][0] == "w":
                    add_pawn_move((r, c), (r+1, c+1))
                elif (r+1, c+1) == self.enpassantPossible:
                    add_pawn_move((r, c), (r+1, c+1), ep=True)

    def getRookMoves(self, r, c, moves):
        for dr, dc in ((-1,0),(1,0),(0,1),(0,-1)):
            for i in range(1, 8):
                nr, nc = r + dr*i, c + dc*i
                if not (0 <= nr < 8 and 0 <= nc < 8):
                    break
                if self.board[nr][nc] == "--":
                    moves.append(Move((r,c),(nr,nc),self.board))
                else:
                    if self.board[nr][nc][0] != self.board[r][c][0]:
                        moves.append(Move((r,c),(nr,nc),self.board))
                    break

    def getBishopMoves(self, r, c, moves):
        for dr, dc in ((-1,-1),(-1,1),(1,-1),(1,1)):
            for i in range(1, 8):
                nr, nc = r + dr*i, c + dc*i
                if not (0 <= nr < 8 and 0 <= nc < 8):
                    break
                if self.board[nr][nc] == "--":
                    moves.append(Move((r,c),(nr,nc),self.board))
                else:
                    if self.board[nr][nc][0] != self.board[r][c][0]:
                        moves.append(Move((r,c),(nr,nc),self.board))
                    break

    def getQueenMoves(self, r, c, moves):
        self.getRookMoves(r, c, moves)
        self.getBishopMoves(r, c, moves)

    def getKnightMoves(self, r, c, moves):
        for dr, dc in ((2,1),(2,-1),(-2,1),(-2,-1),(1,2),(1,-2),(-1,2),(-1,-2)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < 8 and 0 <= nc < 8:
                if self.board[nr][nc] == "--" or \
                   self.board[nr][nc][0] != self.board[r][c][0]:
                    moves.append(Move((r,c),(nr,nc),self.board))

    def getKingMoves(self, r, c, moves):
        allyColor = "w" if self.whiteToMove else "b"
        for dr, dc in ((-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < 8 and 0 <= nc < 8:
                if self.board[nr][nc][0] != allyColor:
                    moves.append(Move((r,c),(nr,nc),self.board))

    def getCastleMoves(self, r, c, moves):
        if self.squareUnderAttack(r, c):
            return
        if (self.whiteToMove  and self.currentCastlingRight.wks) or \
           (not self.whiteToMove and self.currentCastlingRight.bks):
            self.getKingsideCastleMoves(r, c, moves)
        if (self.whiteToMove  and self.currentCastlingRight.wqs) or \
           (not self.whiteToMove and self.currentCastlingRight.bqs):
            self.getQueensideCastleMoves(r, c, moves)

    def getKingsideCastleMoves(self, r, c, moves):
        if self.board[r][c+1] == "--" and self.board[r][c+2] == "--":
            if not self.squareUnderAttack(r, c+1) and \
               not self.squareUnderAttack(r, c+2):
                moves.append(Move((r,c),(r,c+2),self.board,isCastleMove=True))

    def getQueensideCastleMoves(self, r, c, moves):
        if self.board[r][c-1] == "--" and self.board[r][c-2] == "--" and \
           self.board[r][c-3] == "--":
            if not self.squareUnderAttack(r, c-1) and \
               not self.squareUnderAttack(r, c-2):
                moves.append(Move((r,c),(r,c-2),self.board,isCastleMove=True))


# ---------------------------------------------------------------------------
# CastleRights
# ---------------------------------------------------------------------------
class CastleRights():
    # Parameter order: wks, bks, wqs, bqs  (must match every call site)
    def __init__(self, wks, bks, wqs, bqs):
        self.wks = wks
        self.bks = bks
        self.wqs = wqs
        self.bqs = bqs


# ---------------------------------------------------------------------------
# Move
# ---------------------------------------------------------------------------
class Move():
    ranksToRows = {"1":7,"2":6,"3":5,"4":4,"5":3,"6":2,"7":1,"8":0}
    rowsToRanks = {v: k for k, v in ranksToRows.items()}
    filesToCols = {"a":0,"b":1,"c":2,"d":3,"e":4,"f":5,"g":6,"h":7}
    colsToFiles = {v: k for k, v in filesToCols.items()}

    def __init__(self, startSquare, endSquare, board,
                 enpassantMove=False, isCastleMove=False,
                 promotionChoice="Q"):
        self.startRow  = startSquare[0]
        self.startCol  = startSquare[1]
        self.endRow    = endSquare[0]
        self.endCol    = endSquare[1]
        self.pieceMoved    = board[self.startRow][self.startCol]
        self.pieceCaptured = board[self.endRow][self.endCol]
        self.isPawnPromotion = (
            (self.pieceMoved == "wP" and self.endRow == 0) or
            (self.pieceMoved == "bP" and self.endRow == 7)
        )
        self.promotionChoice = promotionChoice   # "Q","R","B","N"
        self.isEnpassantMove = enpassantMove
        if self.isEnpassantMove:
            self.pieceCaptured = "wP" if self.pieceMoved == "bP" else "bP"
        self.isCastleMove = isCastleMove
        self.moveID = (self.startRow * 1000 + self.startCol * 100 +
                       self.endRow * 10  + self.endCol)

    def __eq__(self, other):
        if isinstance(other, Move):
            return (self.moveID == other.moveID and
                    self.promotionChoice == other.promotionChoice)
        return False

    def __hash__(self):
        return hash((self.moveID, self.promotionChoice))

    def getChessNotation(self, gs=None):
        """
        Return SAN notation. Pass gs (GameState) for full SAN with
        disambiguation and check/checkmate symbols. Without gs, returns
        basic notation (used internally during search for speed).
        """
        if self.isCastleMove:
            if gs is None:
                return "O-O" if self.endCol == 6 else "O-O-O"
            base = "O-O" if self.endCol == 6 else "O-O-O"
            return self._add_check_symbol(base, gs)

        piece     = self.pieceMoved[1]
        endSquare = self.getRankFile(self.endRow, self.endCol)
        capture   = self.pieceCaptured != "--" or self.isEnpassantMove

        if piece == "P":
            notation = (self.colsToFiles[self.startCol] + "x" + endSquare
                        if capture else endSquare)
            if self.isPawnPromotion:
                notation += "=" + self.promotionChoice
            # Do NOT append e.p. — it's non-standard and rejected by chess GUIs
            if gs is not None:
                notation = self._add_check_symbol(notation, gs)
            return notation

        # Disambiguation for non-pawn pieces
        disambig = ""
        if gs is not None:
            disambig = self._get_disambig(gs, piece, endSquare)

        notation = piece + disambig + ("x" if capture else "") + endSquare
        if gs is not None:
            notation = self._add_check_symbol(notation, gs)
        return notation

    def _get_disambig(self, gs, piece, endSquare):
        """Return file, rank, or both if needed to disambiguate.

        Uses only fully legal moves (pins respected) to find genuinely
        ambiguous pieces, preventing bogus output like 'K6g5' or 'Kbc7'
        that appeared when moveFunctions was called on pinned pieces.
        """
        color = self.pieceMoved[0]
        ambiguous = []

        # Get all legal moves for the current position, then filter to
        # pieces of the same type that can also reach the same destination.
        try:
            legal = gs.getValidMoves()
        except Exception:
            return ""

        for m in legal:
            if (m.pieceMoved == color + piece
                    and (m.startRow != self.startRow or m.startCol != self.startCol)
                    and m.endRow == self.endRow and m.endCol == self.endCol):
                ambiguous.append((m.startRow, m.startCol))

        if not ambiguous:
            return ""
        # Disambiguate: prefer file letter, then rank number, then both
        same_file = any(c == self.startCol for r, c in ambiguous)
        same_rank = any(r == self.startRow for r, c in ambiguous)
        if not same_file:
            return self.colsToFiles[self.startCol]
        if not same_rank:
            return self.rowsToRanks[self.startRow]
        return self.colsToFiles[self.startCol] + self.rowsToRanks[self.startRow]

    def _add_check_symbol(self, notation, gs):
        """Append + or # if the move gives check or checkmate.

        Uses makeMoveForSearch/undoMoveForSearch and avoids calling
        getValidMoves() (which has side-effects on checkmate/draw flags and
        positionCounts that would corrupt the live game state).  Instead we
        call the lightweight inCheck() and, only when in check, test legality
        of each pseudo-legal reply to detect checkmate.
        """
        gs.makeMoveForSearch(self)
        in_check = gs.inCheck()
        if in_check:
            # Check for checkmate: test legality of every pseudo-legal move.
            pseudo = gs.getAllPossibleMoves()
            has_legal = False
            for m in pseudo:
                gs.makeMoveForSearch(m)
                # whiteToMove has flipped twice; flip once more to check the
                # king of the side that played m.
                gs.whiteToMove = not gs.whiteToMove
                still_in_check = gs.inCheck()
                gs.whiteToMove = not gs.whiteToMove
                gs.undoMoveForSearch()
                if not still_in_check:
                    has_legal = True
                    break
            gs.undoMoveForSearch()
            return notation + ("#" if not has_legal else "+")
        gs.undoMoveForSearch()
        return notation

    def getRankFile(self, r, c):
        return self.colsToFiles[c] + self.rowsToRanks[r]