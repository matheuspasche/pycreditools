#!/usr/bin/env python3
"""Denylist for vocabulary the v0.6 surface must never reintroduce.

Two groups, decided in different places and cited separately below.

**Output vocabulary** — `CONTEXT.md` § *Language of the code* (#131). The engine
speaks one language, English, in every emitted column name and every value that
isn't presentation. The pt-BR names below are promised by
`to_decision_dataframe`'s docstring (`simulation.py:169-171`) and written by no
code path — 0 emissions each, measured. `Rating` capitalized is not pt-BR; it is
the same column spelled two ways by two modules, and the name is `rating`.

**API vocabulary** — names the v0.6 roadmap (§7 of `docs/engine/spec/
v06-architecture.md`) decided die. Inside the new surface these are wrong by
construction: they name mechanisms the surface exists to replace.

**Scope is deliberate.** This runs over `src/pycreditools/engine/` and
`tests/engine/`, not the whole tree. The old surface still legitimately holds
most of these and is deleted whole at the contraction, so flagging it now would
be work thrown away — and it would leave ticket 3, which has no blocker, unable
to land green. `CONTEXT.md` states the same scope in its own words: the v0.6
renames ship with v0.6, and "the rule governs new code from now on". At the
contraction, widen the paths in `.pre-commit-config.yaml`.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent

# The scope, declared once. `.pre-commit-config.yaml` encodes the same two roots
# in its `files:` pattern, and `tests/test_dead_vocabulary_gate.py` fails if the
# two ever disagree — a hook whose pattern drifts off the surface it guards
# covers nothing, and pre-commit reports that as a pass.
SCOPE_ROOTS: tuple[str, ...] = ("src/pycreditools/engine", "tests/engine")

# name -> what to write instead
OUTPUT_VOCABULARY: dict[str, str] = {
    "decisao": "decision",
    "motivo": "reason",
    "contratou": "hired",
    "inadimplente": "defaulted",
    "cenario": "scenario",
    "Aprovado": "an English value — 'Aprovado'/'Reprovado' are presentation",
    "Reprovado": "an English value — 'Aprovado'/'Reprovado' are presentation",
    "Rating": "rating (lowercase, like every other output column)",
}

API_VOCABULARY: dict[str, str] = {
    "score_cols": "the schema's declared lens / the stage's own column",
    "current_hired_col": "the schema's declared roles",
    "CutoffStage": ".filter over the AST — .cutoff dies",
    "calibration_score_col": "Premise(lens=...)",
    "calibration_base": "Premise(calibrate_on=...)",
    "calibration_bins": "Premise(bins=...)",
    "resolve_calibration_score_col": "the declared lens — the cascade dies, the axis stays",
    "optimize_cutoffs": "tradeoff(...) plus choose(...)",
    "TradeoffAnalyzer": "tradeoff(...)",
    "OptimizationResult": "the grid table tradeoff(...) returns",
    "compare_policies": "simulate(studies) plus delta_table(results, baseline=)",
    "target_default_rate": "choose(grid, criterion=...)",
    "min_approval_rate": "choose(grid, criterion=...)",
    "StressScenario": "Premise(stress=...) — scalar, per-bin ladder, or AST node",
    "AggravationStress": "Premise(stress=...)",
    "CustomStress": "Premise(stress=...)",
    "MonotonicStress": "Premise(outcome_from=...) — it replaces the PD, it never was a stress",
    "CalibrationReliabilityWarning": "a number in the result — the warning rung does not exist",
}

DENYLIST: dict[str, tuple[str, str]] = {
    **{k: ("output", v) for k, v in OUTPUT_VOCABULARY.items()},
    **{k: ("api", v) for k, v in API_VOCABULARY.items()},
}

# Whole-word match, so `calibrate_on` never trips `calibration_base` and
# `risk_rating` never trips `Rating`.
PATTERN = re.compile(r"\b(" + "|".join(map(re.escape, DENYLIST)) + r")\b")

SOURCE = {
    "output": "CONTEXT.md § Language of the code (#131)",
    "api": "docs/engine/spec/v06-architecture.md §7",
}


def check(path: pathlib.Path) -> list[str]:
    findings = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return [f"{path}: could not be read ({exc})"]

    for lineno, line in enumerate(lines, start=1):
        for match in PATTERN.finditer(line):
            word = match.group(1)
            group, replacement = DENYLIST[word]
            findings.append(
                f"{path}:{lineno}: dead vocabulary {word!r} — use {replacement}.\n"
                f"    {line.strip()}\n"
                f"    Decided in {SOURCE[group]}."
            )
    return findings


def scope_files() -> tuple[list[pathlib.Path], list[str]]:
    """Every .py file under the declared roots, plus the roots that don't exist yet."""
    found: list[pathlib.Path] = []
    absent: list[str] = []
    for root in SCOPE_ROOTS:
        directory = REPO / root
        if directory.is_dir():
            found.extend(sorted(directory.rglob("*.py")))
        else:
            absent.append(root)
    return found, absent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=pathlib.Path)
    parser.add_argument(
        "--scope",
        action="store_true",
        help="walk the declared scope roots instead of taking filenames, and say what was covered",
    )
    args = parser.parse_args(argv)

    if args.scope:
        paths, absent = scope_files()
    else:
        paths, absent = [p for p in args.paths if p.is_file()], []

    findings = [f for path in paths for f in check(path)]

    if findings:
        print("\n".join(findings), file=sys.stderr)

    # **Say what was covered, always.** A run over zero files is not a pass, and
    # reporting it as one is the silence this repo's own ladder of remedies
    # forbids. pre-commit skips a hook entirely when its `files:` pattern matches
    # nothing, and prints "Passed" — so coverage has to be visible from here.
    where = ", ".join(SCOPE_ROOTS)
    print(f"dead-vocabulary: checked {len(paths)} file(s) across {where}.", file=sys.stderr)
    for root in absent:
        print(f"dead-vocabulary: {root}/ does not exist yet — nothing covered there.", file=sys.stderr)
    if not paths:
        print(
            "dead-vocabulary: nothing was checked. If the v0.6 surface has files, "
            "the scope in scripts/check_dead_vocabulary.py and .pre-commit-config.yaml "
            "no longer points at it.",
            file=sys.stderr,
        )

    if findings:
        print(f"{len(findings)} use(s) of dead vocabulary in the v0.6 surface.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
