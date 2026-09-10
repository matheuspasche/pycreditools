"""`CreditPolicy` — `stages`, and nothing else (§4.2).

The policy declares what you DECIDE. It carries a tuple of stages, and a tuple of one verb is
still a type for three reasons a bare list would not carry: the labels (the key of `ranges=`
and the coordinate of the grid), the validation of composition without data, and the unit of
deploy.

**One verb, `.filter`.** `.cutoff` dies: a cutoff and a filter were the same computation; what
set the cutoff apart was being the numeric knob the sweep could address, and that property is
re-keyed on the AST (a literal compared in a hard mask) instead of on a class.

**One builder move, `set_stage`.** It swaps fields of one stage, addressed by label, and it is
a caller of the signature-driven `replace` — not a rebuild that lists the fields it remembers.
`drop_stage` / `reorder` stay out until a measured case: stage order is funnel semantics.
"""

from __future__ import annotations

from dataclasses import KW_ONLY
from typing import Any

from . import _value
from ._nodes import Node, require_node
from ._value import set_field, value_type
from .errors import LabelRequired


@value_type
class Filter:
    """One stage: a rule over the data that feeds `decision`.

    `draw=True` is the desk: the rule is then a per-row probability, drawn, and a row lost at
    the draw is rejected like any other — it counts in the published approval rate.
    `decision` stays a hard 0/1 either way.

    `label` is optional. Its default is **structural**: the column the rule references, when it
    references exactly one. A rule over two or more columns cannot name itself, and asks for a
    label rather than guessing one. The label is stored resolved, so it is an address that
    inserting a stage elsewhere never moves.
    """

    expr: Node
    _: KW_ONLY
    draw: bool = False
    label: str | None = None

    def __post_init__(self) -> None:
        require_node(self.expr, ".filter")
        if type(self.draw) is not bool:
            raise TypeError(f"draw= is True or False, got {self.draw!r}")
        if self.label is None:
            set_field(self, "label", _derived_label(self.expr))
        elif not isinstance(self.label, str) or not self.label:
            raise TypeError(f"label= is a non-empty string, got {self.label!r}")


def _derived_label(expr: Node) -> str:
    columns = expr.columns()
    if len(columns) != 1:
        raise LabelRequired(
            f"the rule {expr.pretty()} references {len(columns)} columns "
            f"({', '.join(columns)}), so it cannot name itself. Give it a label: "
            ".filter(..., label='regional_gate')."
        )
    return columns[0]


@value_type
class CreditPolicy:
    """The rules, and only them. Anonymous and reusable across bases and premises.

    Build it with `.filter`; derive from it with `.set_stage`. Both return a new policy.
    """

    stages: tuple[Filter, ...] = ()

    def __post_init__(self) -> None:
        taken: dict[str, int] = {}
        for index, stage in enumerate(self.stages):
            if not isinstance(stage, Filter):
                raise TypeError(
                    f"stage {index} is {type(stage).__name__}; stages are built with .filter(...)"
                )
            if stage.label in taken:
                first = self.stages[taken[stage.label]]
                raise LabelRequired(
                    f"label {stage.label!r} is taken by stage {taken[stage.label]} "
                    f"({first.expr.pretty()}) and again by stage {index} ({stage.expr.pretty()}). "
                    "A label is the address of ranges= and set_stage, so it is unique. "
                    "A range is two rules — name them: label='floor' / label='ceiling'."
                )
            taken[stage.label] = index

    def filter(self, expr: Any, *, draw: bool = False, label: str | None = None) -> CreditPolicy:
        """A new policy with one more stage at the end of the funnel."""
        stage = Filter(expr, draw=draw, label=label)
        return _value.replace(self, stages=(*self.stages, stage))

    def set_stage(self, label: str, /, **changes: Any) -> CreditPolicy:
        """A new policy with the stage at `label` derived: `changes` swapped, the rest kept.

        `policy.set_stage("cut", expr=col("score_5") >= 720)` keeps that stage's `draw` and
        `label` and every other stage, in order — nothing has to be copied by the caller.
        """
        index = self._index(label)
        stage = _value.replace(self.stages[index], **changes)
        return _value.replace(self, stages=(*self.stages[:index], stage, *self.stages[index + 1 :]))

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(stage.label for stage in self.stages)

    def columns(self) -> tuple[str, ...]:
        """Every column the rules reference, in funnel order."""
        return tuple(dict.fromkeys(c for stage in self.stages for c in stage.expr.columns()))

    def _index(self, label: str) -> int:
        for index, stage in enumerate(self.stages):
            if stage.label == label:
                return index
        raise KeyError(f"no stage is labelled {label!r}; the labels are {list(self.labels)}")

    def __repr__(self) -> str:
        calls = [_filter_call(stage) for stage in self.stages]
        if not calls:
            return "CreditPolicy()"
        if len(calls) == 1:
            return f"CreditPolicy(){calls[0]}"
        body = "\n".join(f"    {call}" for call in calls)
        return f"(CreditPolicy()\n{body})"


def _filter_call(stage: Filter) -> str:
    args = [repr(stage.expr)]
    if stage.draw:
        args.append("draw=True")
    columns = stage.expr.columns()
    if len(columns) != 1 or stage.label != columns[0]:
        args.append(f"label={stage.label!r}")
    return f".filter({', '.join(args)})"
