#!/usr/bin/env python3
"""Gate 4 of the v0.6 release — the closed list of artifacts, enumerated.

**This file specifies the list. It does not run as a gate.** Ticket 3 owns the
specification; ticket 17 owns wiring it into the release check, where the
five-gate checklist is signed. The split is a dependency edge, not caution: the
list includes ticket 1's ADRs, so gating on it here would leave ticket 3 — which
has no blocker — red until ticket 1 closes.

Run it any time for a status read:

    python3 scripts/check_artifact_gate.py          # human-readable table
    python3 scripts/check_artifact_gate.py --strict # exit 1 on any absence

**Why it enumerates instead of trusting prose** (§6 of the architecture spec):
a decision was recorded citing a commit reachable from no ref; two `CONTEXT.md`
sections were declared present with 0 occurrences on every branch; and the spec
itself stated a test was versioned when it lived only on an unintegrated branch.
Three citations, three false. **A citation is not evidence, and this list treats
it that way** — existence is checked against the tree, never against a mention.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent

# --- Sections that must exist in CONTEXT.md -------------------------------

REQUIRED_SECTIONS: list[tuple[str, str]] = [
    ("CONTEXT.md", r"^#{2,3}\s+Language of the code\b"),
    ("CONTEXT.md", r"^#{2,3}\s+The ladder of remedies\b"),
]

# --- Files that must exist in HEAD ----------------------------------------

REQUIRED_FILES: list[str] = [
    "tests/test_sweep_hard_filter_ceiling.py",
    "tests/test_sweep_rebuild_preserves_stage_fields.py",
    "tests/test_swap_in_anchor_follows_declaration_order.py",
]

# --- Every ADR the roadmap promises ---------------------------------------
#
# Ticket 1 enumerates fifteen source cards, plus the layout ADR — whose number
# 0012 the roadmap reserved and the output contract took — plus the ADR of
# "the choice criterion is not the package's", which §9.3 lists separately and
# measures as "never written, though declared as a deliverable".
#
# NOTE: that totals SEVENTEEN. Ticket 3's prose says "the 16 ADRs of ticket 1",
# which undercounts by one. The count is left at seventeen here because ticket 1
# names each item explicitly and its enumeration is the authority; the "16" is
# recorded as a discrepancy for the owner, not silently reconciled.
PROMISED_ADRS: list[tuple[str, str]] = [
    ("#117", "score_cols and the calibration cascade die"),
    ("#118", "the outcome axis"),
    ("#119", "types and the boundary"),
    ("#120", "the schema, crossing two tickets"),
    ("#121", "premises"),
    ("#122", "truth values"),
    ("#125", "the table (probabilistic decision stage)"),
    ("#126", "rating"),
    ("#127", "the functional core / calculate-present boundary"),
    ("#129", "identity and the .rate collapse"),
    ("#139", "the stage surface"),
    ("#142", "the baseline population"),
    ("#145", "by="),
    ("#152", "the contract axis"),
    ("#155", "the verb family"),
    ("layout", "the docs/engine + docs/studio layout — number 0012 was taken"),
    ("choice-criterion", "the choice criterion is not the package's"),
]

ADR_DIR = "docs/adr"

# **An ADR owns a promise only when it DECLARES that it does.** A card number
# appearing in prose, or in another ADR's "Consumes" list, is a citation — and
# the whole reason this gate enumerates is that citations were three-for-three
# false. Measured before this check was written: `#117` appears in `docs/adr/`
# five times, in all five as a card some *other* ADR consumes, and zero times as
# an ADR that decides it. A substring search would have called that present.
#
# Two accepted forms of declaration:
#
#   - the house style already in use — `- **Tickets:** #131 (this ADR). ...`
#     (ADRs 0010, 0012, 0013 and 0014 carry it), which is why the fifteen
#     card-numbered promises need no retrofit; and
#   - `- **Decides:** layout` — for the two promises that have no card of their
#     own. Ticket 1 writes the line when it writes the ADR.

DECLARATION_FORMS = (
    r"^-\s+\*\*Tickets:\*\*.*?{key}\s+\(this ADR\)",
    r"^-\s+\*\*Decides:\*\*.*?{key}\b",
)


def _section_present(relpath: str, pattern: str) -> bool:
    path = REPO / relpath
    if not path.is_file():
        return False
    return re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE) is not None


def _adr_owner(key: str) -> str | None:
    """The ADR file that declares it decides `key`, or None."""
    directory = REPO / ADR_DIR
    if not directory.is_dir():
        return None
    for path in sorted(directory.glob("*.md")):
        body = path.read_text(encoding="utf-8")
        for form in DECLARATION_FORMS:
            if re.search(form.format(key=re.escape(key)), body, re.MULTILINE):
                return path.name
    return None


def collect() -> list[tuple[str, bool, str]]:
    """Return (artifact, present, how it was checked)."""
    rows: list[tuple[str, bool, str]] = []

    for relpath, pattern in REQUIRED_SECTIONS:
        label = pattern.strip("^$").replace(r"#{2,3}\s+", "").replace(r"\b", "")
        rows.append((f"{relpath} § {label}", _section_present(relpath, pattern), "section exists"))

    for relpath in REQUIRED_FILES:
        rows.append((relpath, (REPO / relpath).is_file(), "file exists in HEAD"))

    for card, subject in PROMISED_ADRS:
        owner = _adr_owner(card)
        how = f"declared by {owner}" if owner else f"no file in {ADR_DIR}/ declares it"
        rows.append((f"ADR — {card} ({subject})", owner is not None, how))

    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 on any absence (ticket 17 wires this into the release check)",
    )
    args = parser.parse_args(argv)

    rows = collect()
    width = max(len(name) for name, _, _ in rows)
    missing = 0

    for name, present, how in rows:
        if not present:
            missing += 1
        print(f"{'OK  ' if present else 'MISS'}  {name:<{width}}  ({how})")

    print(f"\n{len(rows) - missing}/{len(rows)} present, {missing} missing.")
    if missing:
        print("Gate 4 is open. The v0.6.0 does not ship while any artifact is absent.")
    return 1 if (missing and args.strict) else 0


if __name__ == "__main__":
    raise SystemExit(main())
