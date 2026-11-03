"""Read and write JSON Lines files, the format every phase uses to hand data to the next."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator


def read_jsonl(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def write_jsonl(rows: Iterable[dict], path: Path) -> None:
    """Write atomically: a crash never leaves a half-written file in place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    with part.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    part.replace(path)
