from flask import Flask, request, jsonify
from flask_cors import CORS
import ChessEngine, ChessAi

app = Flask(__name__)
CORS(app)

def rebuild_state(move_history):
    gs = ChessEngine.GameState()
    for m in move_history:
        valid = gs.getValidMoves()
        match = next((v for v in valid
                      if v.startRow == m["sr"] and v.startCol == m["sc"]
                      and v.endRow == m["er"] and v.endCol == m["ec"]
                      and (not v.isPawnPromotion or v.promotionChoice == m.get("promo", "Q"))),
                     None)
        if match:
            gs.makeMove(match)
    return gs

@app.route("/move", methods=["POST"])
def get_move():
    data = request.json
    move_history = data.get("moves", [])
    depth = int(data.get("depth", 6))
    depth = max(1, min(depth, 10))  # clamp 1–10
    ChessAi.DEPTH = depth

    gs = rebuild_state(move_history)
    valid_moves = gs.getValidMoves()

    if gs.checkmate or gs.stalemate or gs.draw or not valid_moves:
        return jsonify({"status": "game_over",
                        "checkmate": gs.checkmate,
                        "stalemate": gs.stalemate,
                        "draw": gs.draw,
                        "drawReason": gs.drawReason})

    best = ChessAi.findBestMove(gs, valid_moves)
    if best is None:
        return jsonify({"error": "no move found"}), 500

    eval_score = ChessAi.lastScore if ChessAi.lastScore != 0 else ChessAi.scoreBoard(gs)

    return jsonify({
        "status": "ok",
        "move": {
            "sr": best.startRow, "sc": best.startCol,
            "er": best.endRow,   "ec": best.endCol,
            "promo": best.promotionChoice if best.isPawnPromotion else None,
            "notation": best.getChessNotation()
        },
        "eval": round(eval_score, 2)
    })

@app.route("/health")
def health():
    return jsonify({"status": "alive"})

if __name__ == "__main__":
    app.run(debug=False)