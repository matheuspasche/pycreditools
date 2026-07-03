#!/usr/bin/env python3
"""Mirror the Pycreditools Studio PRD queue to a GitHub Projects board.

`PROGRESS.md` stays the single source of truth (agents update it). This script
reflects it on GitHub: one issue per PRD + a Projects (v2) board, with status
carried by labels and issue open/closed state.

Subcommands:
    setup [--dry-run]   Create labels, one issue per PRD (idempotent), a Project,
                        add the issues to it, and write scripts/.board-map.json.
    sync  [--dry-run]   Reconcile each issue's status label / open-closed /
                        `blocked` label from PROGRESS.md. Run this after approvals.
    status              Print the board URL and the PRD -> issue map.

Requirements: GitHub CLI (`gh`) authenticated with the `project` scope
    gh auth login -s project -w
The script auto-detects gh on PATH or in common Windows locations.
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROGRESS = ROOT / "docs" / "prd" / "PROGRESS.md"
MAP_FILE = ROOT / "scripts" / ".board-map.json"
PROJECT_TITLE = "Pycreditools Studio"

ROW_RE = re.compile(r"^\|\s*(\d{2})\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.*?)\s*\|\s*$")
STATUSES = {"TODO", "IN PROGRESS", "AWAITING APPROVAL", "DONE"}
STATUS_LABEL = {
    "TODO": "status:todo",
    "IN PROGRESS": "status:in-progress",
    "AWAITING APPROVAL": "status:review",
    "DONE": "status:done",
}
LABELS = [
    ("prd", "1f6feb", "A Pycreditools Studio PRD task"),
    ("status:todo", "8b949e", "Not started"),
    ("status:in-progress", "d4a72c", "Being implemented"),
    ("status:review", "8957e5", "Awaiting owner approval at the gate"),
    ("status:done", "238636", "Approved / complete"),
    ("blocked", "da3633", "A dependency PRD is not DONE yet"),
]

GH_CANDIDATES = [
    r"C:\Program Files\GitHub CLI\gh.exe",
    r"C:\Program Files (x86)\GitHub CLI\gh.exe",
]


def find_gh() -> str:
    import os

    env = os.environ.get("GH_PATH")
    if env and pathlib.Path(env).exists():
        return env
    on_path = shutil.which("gh")
    if on_path:
        return on_path
    for c in GH_CANDIDATES:
        if pathlib.Path(c).exists():
            return c
    sys.exit("gh CLI not found. Install it and/or run: gh auth login -s project -w")


GH = find_gh()
DRY = "--dry-run" in sys.argv


def gh(*args: str, check: bool = True, capture: bool = True) -> str:
    if DRY and args and args[0] in {"label", "issue", "project"} and args[1] in {
        "create", "edit", "close", "reopen", "item-add",
    }:
        print(f"  [dry-run] gh {' '.join(args)}")
        return ""
    res = subprocess.run([GH, *args], capture_output=capture, text=True)
    if check and res.returncode != 0:
        sys.exit(f"gh {' '.join(args)}\n{res.stderr.strip()}")
    return res.stdout.strip()


def ensure_auth() -> None:
    res = subprocess.run([GH, "auth", "status"], capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit("Not logged in. Run:  gh auth login -s project -w")


def parse_progress() -> list[dict]:
    rows = []
    for line in PROGRESS.read_text(encoding="utf-8").splitlines():
        m = ROW_RE.match(line)
        if not m:
            continue
        num, fcell, deps, status, _done = m.groups()
        status = status.strip().upper()
        if status not in STATUSES:
            continue
        link = re.search(r"\[([^\]]+)\]", fcell)
        fname = link.group(1) if link else fcell.strip()
        title = re.sub(r"^\d+[-_]", "", re.sub(r"\.md$", "", fname)).replace("-", " ").title()
        dep_list = [
            d.strip() for d in re.split(r"[,/]", deps)
            if d.strip() and d.strip() not in ("—", "-")
        ]
        rows.append({"num": num, "file": fname, "title": title,
                     "deps": dep_list, "status": status})
    return rows


def repo_branch() -> tuple[str, str]:
    slug = gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner")
    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    return slug, branch


def issue_body(r: dict, slug: str, branch: str) -> str:
    url = f"https://github.com/{slug}/blob/{branch}/docs/prd/{r['file']}"
    deps = ", ".join(f"PRD {d}" for d in r["deps"]) or "none"
    return (
        f"**PRD {r['num']} — {r['title']}**\n\n"
        f"Spec: [{r['file']}]({url})\n\n"
        f"Depends on: {deps}\n\n"
        f"Status is managed from `docs/prd/PROGRESS.md` via "
        f"`scripts/github_board.py` — do not edit labels by hand.\n"
    )


def find_issue(num: str) -> int | None:
    out = gh("issue", "list", "--state", "all", "--limit", "100",
             "--search", f'"PRD {num}:" in:title', "--json", "number,title")
    for it in json.loads(out or "[]"):
        if it["title"].startswith(f"PRD {num}:"):
            return it["number"]
    return None


def ensure_project(slug: str) -> dict:
    out = gh("project", "list", "--owner", "@me", "--format", "json")
    for p in json.loads(out or "{}").get("projects", []):
        if p.get("title") == PROJECT_TITLE:
            return p
    if DRY:
        print(f"  [dry-run] gh project create --owner @me --title {PROJECT_TITLE!r}")
        return {"number": 0, "url": "<dry-run>"}
    out = gh("project", "create", "--owner", "@me", "--title", PROJECT_TITLE,
             "--format", "json")
    return json.loads(out)


def cmd_setup() -> None:
    ensure_auth()
    rows = parse_progress()
    slug, branch = repo_branch()
    print(f"Repo {slug} @ {branch} — {len(rows)} PRDs")

    for name, color, desc in LABELS:
        gh("label", "create", name, "--color", color, "--description", desc, "--force",
           check=False)

    mapping: dict[str, dict] = {}
    for r in rows:
        num = r["num"]
        existing = find_issue(num)
        if existing:
            print(f"  PRD {num}: issue #{existing} exists")
            mapping[num] = {"issue": existing}
            continue
        body = issue_body(r, slug, branch)
        url = gh("issue", "create", "--title", f"PRD {num}: {r['title']}",
                 "--body", body, "--label", "prd", "--label", STATUS_LABEL[r["status"]])
        n = None
        m = re.search(r"/issues/(\d+)", url or "")
        if m:
            n = int(m.group(1))
        print(f"  PRD {num}: created issue {url}")
        mapping[num] = {"issue": n, "url": url}

    proj = ensure_project(slug)
    print(f"Project: {proj.get('url')}")
    for r in rows:
        info = mapping.get(r["num"], {})
        iss_url = info.get("url")
        if not iss_url and info.get("issue"):
            iss_url = f"https://github.com/{slug}/issues/{info['issue']}"
        if iss_url and not DRY:
            gh("project", "item-add", str(proj["number"]), "--owner", "@me",
               "--url", iss_url, check=False)

    if not DRY:
        MAP_FILE.write_text(json.dumps(
            {"project": proj.get("url"), "project_number": proj.get("number"),
             "items": mapping}, indent=2), encoding="utf-8")
        print(f"Wrote {MAP_FILE}")
    print("\nNext: open the project, switch the view to 'Board', and Group by "
          "Label to get status columns. Then run `python scripts/github_board.py sync` "
          "whenever PROGRESS.md changes.")


def cmd_sync() -> None:
    ensure_auth()
    rows = parse_progress()
    status_by_num = {r["num"]: r["status"] for r in rows}
    for r in rows:
        num = r["num"]
        n = find_issue(num)
        if not n:
            print(f"  PRD {num}: no issue yet (run setup) — skipping")
            continue
        want = STATUS_LABEL[r["status"]]
        others = [v for k, v in STATUS_LABEL.items() if v != want]
        blocked = r["status"] == "TODO" and any(
            status_by_num.get(d) != "DONE" for d in r["deps"])
        add = [want] + (["blocked"] if blocked else [])
        remove = others + ([] if blocked else ["blocked"])
        gh("issue", "edit", str(n), "--add-label", ",".join(add),
           "--remove-label", ",".join(remove), check=False)
        if r["status"] == "DONE":
            gh("issue", "close", str(n), check=False)
        else:
            gh("issue", "reopen", str(n), check=False)
        print(f"  PRD {num}: #{n} -> {r['status']}{' (blocked)' if blocked else ''}")
    print("Synced.")


def cmd_status() -> None:
    if MAP_FILE.exists():
        print(MAP_FILE.read_text(encoding="utf-8"))
    else:
        print("No board map yet. Run: python scripts/github_board.py setup")


def main() -> int:
    cmd = next((a for a in sys.argv[1:] if not a.startswith("-")), "status")
    {"setup": cmd_setup, "sync": cmd_sync, "status": cmd_status}.get(cmd, cmd_status)()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
