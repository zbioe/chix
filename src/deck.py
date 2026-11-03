# Your mistakes as training cards ($CHESS_DIR/training.json), Leitner boxes:
# found again, a card waits longer; missed, it comes back the next day
import json
from datetime import date, timedelta

from common import CHESS_DIR

PATH = CHESS_DIR / "training.json"
# days a card waits in each box
INTERVALS = [0, 1, 3, 7, 16, 35, 90]


def load():
    return json.loads(PATH.read_text()) if PATH.exists() else {}


def save(cards):
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cards, indent=1))
    tmp.replace(PATH)


def add(cards, card):
    """False when the card was already there (its progress is kept)."""
    if card["id"] in cards:
        return False
    cards[card["id"]] = card | {"box": 0, "due": date.today().isoformat()}
    return True


def due(cards, today=None):
    today = (today or date.today()).isoformat()
    return sorted(
        (c for c in cards.values() if c["due"] <= today),
        key=lambda c: (c["due"], c["box"]),
    )


def answer(card, right):
    card["box"] = min(card["box"] + 1, len(INTERVALS) - 1) if right else 0
    wait = INTERVALS[card["box"]] if right else 1
    card["due"] = (date.today() + timedelta(days=wait)).isoformat()
    card.setdefault("history", []).append([date.today().isoformat(), right])
