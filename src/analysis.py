# How a game is judged, as Lichess does it (lila's AccuracyPercent and
# Advice, scalachess' WinPercent and Divider), plus the tags that say what
# kind of mistake each one was
import math
import statistics

import chess
import chess.engine

INACCURACY, MISTAKE, BLUNDER = "?!", "?", "??"
NAMES = {INACCURACY: "inaccuracy", MISTAKE: "mistake", BLUNDER: "blunder"}
# the PGN annotation glyphs: $6, $2, $4
NAGS = {INACCURACY: 6, MISTAKE: 2, BLUNDER: 4}
VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
}
# what each tag is trained with (chess-puzzle --theme)
THEMES = {
    "lost material": ["hangingPiece", "defensiveMove"],
    "missed material": ["fork", "pin", "skewer", "discoveredAttack"],
    "missed mate": ["mateIn2", "mateIn3"],
    "allowed mate": ["defensiveMove", "exposedKing"],
    "king safety": ["exposedKing", "kingsideAttack", "defensiveMove"],
    "endgame": ["endgame", "rookEndgame", "pawnEndgame"],
}


def winning_chances(cp):
    # [-1, 1], cp capped at 1000 (a mate counts as 1000)
    cp = max(-1000, min(1000, cp))
    return 2 / (1 + math.exp(-0.00368208 * cp)) - 1


def win_percent(cp):
    return 50 + 50 * winning_chances(cp)


def cp_of(score):
    """A white-POV score as Lichess forces it into centipawns."""
    if score.is_mate():
        return 100000 if score.mate() > 0 else -100000
    return score.score()


def describe(cp, score=None):
    if score is not None and score.white().is_mate():
        return f"#{score.white().mate()}"
    # mated: #0 when White gave it, #-0 when Black did
    if abs(cp) >= 100000:
        return "#0" if cp > 0 else "#-0"
    return f"{cp / 100:+.2f}"


def move_accuracy(before, after):
    if after >= before:
        return 100.0
    raw = 103.1668100711649 * math.exp(-0.04354415386753951 * (before - after))
    raw += -3.166924740191411
    # Lichess' "uncertainty bonus (due to imperfect analysis)"
    return max(0.0, min(100.0, raw + 1))


def game_accuracy(cps, white_first=True):
    """Each side's accuracy from the white-POV cp of every position, the
    first one included: a mean of the volatility-weighted mean and the
    harmonic mean of the move accuracies."""
    wps = [win_percent(cp) for cp in cps]
    if len(wps) < 2:
        return {}
    size = max(2, min(8, (len(cps) - 1) // 10))
    windows = [wps[:size]] * (min(size, len(wps)) - 2)
    windows += [wps[i : i + size] for i in range(len(wps) - size + 1)]
    weights = [max(0.5, min(12.0, statistics.pstdev(w))) for w in windows]
    moves = {chess.WHITE: [], chess.BLACK: []}
    for i, ((prev, nxt), w) in enumerate(zip(zip(wps, wps[1:]), weights)):
        color = chess.WHITE if (i % 2 == 0) == white_first else chess.BLACK
        acc = move_accuracy(prev, nxt) if color else move_accuracy(nxt, prev)
        moves[color].append((acc, w))
    result = {}
    for color, accs in moves.items():
        if not accs:
            continue
        weighted = sum(a * w for a, w in accs) / sum(w for _, w in accs)
        harmonic = len(accs) / sum(1 / max(1.0, a) for a, _ in accs)
        result[color] = (weighted + harmonic) / 2
    return result


def judge(before, after, mover):
    """Lichess' judgement of a move from the scores before and after it."""
    b, a = before.pov(mover), after.pov(mover)
    if not b.is_mate() and not a.is_mate():
        delta = winning_chances(b.score()) - winning_chances(a.score())
        for limit, mark in ((0.3, BLUNDER), (0.2, MISTAKE), (0.1, INACCURACY)):
            if delta >= limit:
                return mark
        return None
    b_cp = 0 if b.is_mate() else b.score()
    a_cp = 0 if a.is_mate() else a.score()
    mated_after = a.is_mate() and a.mate() <= 0
    if not b.is_mate() and mated_after:  # mate created
        return INACCURACY if b_cp < -999 else MISTAKE if b_cp < -700 else BLUNDER
    if b.is_mate() and b.mate() > 0 and (not a.is_mate() or mated_after):  # mate lost
        return INACCURACY if a_cp > 999 else MISTAKE if a_cp > 700 else BLUNDER
    return None


def _majors_minors(board):
    return chess.popcount(board.occupied & ~(board.kings | board.pawns))


def _backrank_sparse(board):
    white = chess.popcount(chess.BB_RANK_1 & board.occupied_co[chess.WHITE])
    black = chess.popcount(chess.BB_RANK_8 & board.occupied_co[chess.BLACK])
    return white < 4 or black < 4


def _score(y, white, black):
    table = {
        0: {
            1: 1 + y,
            2: 2 + (6 - y) if y < 6 else 0,
            3: 3 + (7 - y) if y < 7 else 0,
            4: 3 + (7 - y) if y < 7 else 0,
        },
        1: {0: 1 + (8 - y), 1: 5 + abs(4 - y), 2: 4 + (7 - y), 3: 5 + (7 - y)},
        2: {0: 2 + (y - 2) if y > 2 else 0, 1: 4 + (y - 1), 2: 7},
        3: {0: 3 + (y - 1) if y > 1 else 0, 1: 5 + (y - 1)},
        4: {0: 3 + (y - 1) if y > 1 else 0},
    }
    return table.get(white, {}).get(black, 0)


def _mixedness(board):
    acc = 0
    for i in range(49):
        y, x = divmod(i, 7)
        region = 0x0303 << (x + 8 * y)
        white = chess.popcount(board.occupied_co[chess.WHITE] & region)
        black = chess.popcount(board.occupied_co[chess.BLACK] & region)
        acc += _score(y + 1, white, black)
    return acc


def divide(boards):
    """(first middlegame ply, first endgame ply), as scalachess' Divider."""
    middle = next(
        (
            i
            for i, b in enumerate(boards)
            if _majors_minors(b) <= 10 or _backrank_sparse(b) or _mixedness(b) > 150
        ),
        None,
    )
    end = None
    if middle is not None:
        end = next((i for i, b in enumerate(boards) if _majors_minors(b) <= 6), None)
        if end is not None and middle >= end:
            middle = None
    return middle, end


def phase_of(ply, division):
    middle, end = division
    if middle is None or ply < middle:
        return "opening"
    if end is not None and ply >= end:
        return "endgame"
    return "middlegame"


def material(board, color):
    return sum(
        VALUES.get(p.piece_type, 0)
        for p in board.piece_map().values()
        if p.color == color
    )


def balance(board, color):
    return material(board, color) - material(board, not color)


def _after(board, moves, plies=4):
    b = board.copy(stack=False)
    for m in moves[:plies]:
        if not b.is_legal(m):
            break
        b.push(m)
    return b


def tags(before_board, best_pv, after_board, reply_pv, before, after, mover):
    """What kind of mistake: material lost or missed, mates, king safety."""
    out = []
    b, a = before.pov(mover), after.pov(mover)
    if b.is_mate() and b.mate() > 0 and not (a.is_mate() and a.mate() > 0):
        out.append("missed mate")
    if a.is_mate() and a.mate() <= 0:
        out.append("allowed mate")
    if (
        balance(_after(after_board, reply_pv), mover) - balance(after_board, mover)
        <= -2
    ):
        out.append("lost material")
    if (
        balance(_after(before_board, best_pv), mover) - balance(before_board, mover)
        >= 2
    ):
        out.append("missed material")
    b2 = after_board.copy(stack=False)
    for m in reply_pv[:3]:
        if not b2.is_legal(m):
            break
        b2.push(m)
        if b2.turn == mover and b2.is_check():
            out.append("king safety")
            break
    return out


def analyse(game, engine, progress=None):
    """Every position of the main line: its score (None once mated), its
    white-POV centipawns and the engine's best line."""
    board = game.board()
    nodes = list(game.mainline())
    boards = [board] + [n.board() for n in nodes]
    infos = []
    for i, b in enumerate(boards):
        if b.is_checkmate():
            cp = -100000 if b.turn == chess.WHITE else 100000
            infos.append({"score": None, "pv": [], "cp": cp})
        elif b.is_game_over():
            score = chess.engine.PovScore(chess.engine.Cp(0), b.turn)
            infos.append({"score": score, "pv": [], "cp": 0})
        else:
            info = engine.analyse(b)
            infos.append({**info, "cp": cp_of(info["score"].white())})
        if progress:
            progress(i, len(boards) - 1)
    return nodes, boards, infos


def parse_eval(text):
    """White-POV cp of what describe() wrote."""
    if text.startswith("#"):
        return -100000 if text.startswith("#-") else 100000
    return round(float(text) * 100)
