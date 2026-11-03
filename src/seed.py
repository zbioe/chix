# seed.py ENGINES.json: adds the engines En Croissant and ChessX don't list
# yet; what is already there (yours or changed by you) is left alone
import json
import sys
from pathlib import Path

home = Path.home()
engines = json.loads(Path(sys.argv[1]).read_text())


def en_croissant():
    path = home / ".local/share/org.encroissant.app/engines/engines.json"
    try:
        current = json.loads(path.read_text()) if path.exists() else []
    except json.JSONDecodeError:
        print(f"seed: {path} is not JSON, left as it is", file=sys.stderr)
        return
    ids = {e.get("id") for e in current}
    added = [
        {
            "type": "local",
            "id": e["id"],
            "name": e["name"],
            "version": "",
            "path": e["command"],
            "elo": e.get("elo"),
            "loaded": True,
            "go": e["go"],
            "settings": [{"name": k, "value": v} for k, v in e["settings"].items()],
        }
        for e in engines
        if e["id"] not in ids
    ]
    if added:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(current + added, indent=4))


def chessx():
    # QSettings' ini: [Engines] with N\Name, N\Command... numbered from 0
    path = home / ".config/chessx/chessx.ini"
    lines = path.read_text().splitlines() if path.exists() else []
    try:
        start = lines.index("[Engines]") + 1
    except ValueError:
        lines += ["", "[Engines]"]
        start = len(lines)
    end = start
    while end < len(lines) and not lines[end].startswith("["):
        end += 1
    keys = dict(line.split("=", 1) for line in lines[start:end] if "=" in line)
    commands = {v for k, v in keys.items() if k.endswith("\\Command")}
    n = len({k.split("\\")[0] for k in keys})
    new = []
    for e in engines:
        if e["command"] in commands:
            continue
        new += [
            f"{n}\\Command={e['command']}",
            f"{n}\\Name={e['name']}",
            f"{n}\\Protocol=UCI",
            f"{n}\\Logging=false",
            f"{n}\\SendHistory=true",
        ]
        n += 1
    if new:
        # the blank line before the next section stays after the new keys
        while end > start and not lines[end - 1].strip():
            end -= 1
        lines[end:end] = new
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n")


en_croissant()
chessx()
