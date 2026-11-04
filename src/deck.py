# What you train, in Leitner boxes ($CHESS_DIR/NAME.json): your mistakes
# (training) and the opening lines (openings). Found again, an item waits
# longer; missed, it comes back the next day
import json
from datetime import date, timedelta

from common import CHESS_DIR

# days an item waits in each box
INTERVALS = [0, 1, 3, 7, 16, 35, 90]


def path(name):
    return CHESS_DIR / f"{name}.json"


def load(name="training"):
    p = path(name)
    return json.loads(p.read_text()) if p.exists() else {}


def save(cards, name="training"):
    p = path(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(cards, indent=1))
    tmp.replace(p)


def add(cards, card):
    """False when the card was already there (its progress is kept)."""
    if card["id"] in cards:
        return False
    cards[card["id"]] = card | {"box": 0, "due": date.today().isoformat()}
    return True


def is_due(card, today=None):
    return card["due"] <= (today or date.today()).isoformat()


def due(cards, today=None):
    return sorted(
        (c for c in cards.values() if is_due(c, today)),
        key=lambda c: (c["due"], c["box"]),
    )


def answer(card, right):
    card["box"] = min(card.get("box", 0) + 1, len(INTERVALS) - 1) if right else 0
    wait = INTERVALS[card["box"]] if right else 1
    card["due"] = (date.today() + timedelta(days=wait)).isoformat()
    card.setdefault("history", []).append([date.today().isoformat(), right])


def stars(card):
    """0 to 3: how settled it is."""
    box = card.get("box", 0) if card else 0
    return 0 if box == 0 else 1 if box < 3 else 2 if box < 5 else 3
