#!/usr/bin/env python3
"""Live kanban for the Pycreditools Studio PRD queue.

Reads ``docs/prd/PROGRESS.md`` (the single source of truth) and prints the PRDs
grouped by status, marks the next actionable PRD, and flags any blocked by a
dependency that isn't DONE yet.

Usage:
    python scripts/prd_board.py [--no-color]
"""
from __future__ import annotations

import pathlib
import re
import sys

try:  # make Unicode-safe on Windows consoles (cp1252); harmless elsewhere
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROGRESS = ROOT / "docs" / "prd" / "PROGRESS.md"

STATUSES = ["TODO", "IN PROGRESS", "AWAITING APPROVAL", "DONE"]
COL_LABELS = {
    "TODO": "TODO",
    "IN PROGRESS": "IN PROGRESS",
    "AWAITING APPROVAL": "REVIEW",
    "DONE": "DONE",
}
ROW_RE = re.compile(r"^\|\s*(\d{2})\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.*?)\s*\|\s*$")

C = {
    "TODO": "\033[90m",              # grey
    "IN PROGRESS": "\033[93m",       # yellow
    "AWAITING APPROVAL": "\033[95m",  # magenta
    "DONE": "\033[92m",              # green
    "reset": "\033[0m",
    "bold": "\033[1m",
    "blue": "\033[96m",
    "red": "\033[91m",
}

COL_W = 22


def _title(link_cell: str) -> str:
    m = re.search(r"\[([^\]]+)\]", link_cell)
    name = m.group(1) if m else link_cell
    name = re.sub(r"\.md$", "", name)
    name = re.sub(r"^\d+[-_]", "", name)
    return name.replace("-", " ").replace("_", " ").strip().title()


def _parse() -> list[dict]:
    rows: list[dict] = []
    for line in PROGRESS.read_text(encoding="utf-8").splitlines():
        m = ROW_RE.match(line)
        if not m:
            continue
        num, fcell, deps, status, done = m.groups()
        status = status.strip().upper()
        if status not in STATUSES:
            continue
        dep_list = [
            d.strip()
            for d in re.split(r"[,/]", deps)
            if d.strip() and d.strip() not in ("—", "-")
        ]
        rows.append(
            {
                "num": num,
                "title": _title(fcell),
                "deps": dep_list,
                "status": status,
                "done": done.strip(),
            }
        )
    return rows


def main() -> int:
    if not PROGRESS.exists():
        print(f"Not found: {PROGRESS}")
        return 1

    use_color = "--no-color" not in sys.argv and sys.stdout.isatty()

    def col(key: str, s: str) -> str:
        return f"{C.get(key, '')}{s}{C['reset']}" if use_color else s

    rows = _parse()
    if not rows:
        print("No PRD rows found in PROGRESS.md (table format changed?)")
        return 1

    status_by_num = {r["num"]: r["status"] for r in rows}
    by_status = {s: [r for r in rows if r["status"] == s] for s in STATUSES}
    done = len(by_status["DONE"])
    total = len(rows)

    # --- board header ---
    print()
    print(col("bold", f"  Pycreditools Studio — PRD board   ({done}/{total} DONE)"))
    print("  " + "─" * (COL_W * len(STATUSES)))

    # --- column headers ---
    header = "".join(col(s, COL_LABELS[s].ljust(COL_W)) for s in STATUSES)
    print("  " + header)

    # --- column bodies (rows aligned across columns) ---
    height = max((len(by_status[s]) for s in STATUSES), default=0)
    for i in range(height):
        line_cells = []
        for s in STATUSES:
            items = by_status[s]
            if i < len(items):
                r = items[i]
                blocked = s == "TODO" and any(
                    status_by_num.get(d) != "DONE" for d in r["deps"]
                )
                mark = "⛔" if blocked else "•"
                cell = f"{mark} {r['num']} {r['title']}"
                cell = cell[: COL_W - 1].ljust(COL_W)
                line_cells.append(col(s, cell))
            else:
                line_cells.append(" " * COL_W)
        print("  " + "".join(line_cells))

    # --- footer: next actionable + blocked ---
    print()
    nxt = next((r for r in rows if r["status"] != "DONE"), None)
    if nxt is None:
        print(col("DONE", "  ✅ All PRDs DONE — v1 complete."))
    else:
        ready = all(status_by_num.get(d) == "DONE" for d in nxt["deps"])
        tag = {
            "TODO": "next to start",
            "IN PROGRESS": "in progress",
            "AWAITING APPROVAL": "waiting for your approval",
        }.get(nxt["status"], nxt["status"])
        line = f"  → PRD {nxt['num']} ({nxt['title']}) — {tag}"
        print(col("blue", line))
        if not ready:
            missing = [d for d in nxt["deps"] if status_by_num.get(d) != "DONE"]
            print(col("red", f"    ⛔ blocked: needs {', '.join(missing)} DONE first"))
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
