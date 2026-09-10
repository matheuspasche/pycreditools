"""`Premise` — one type, six fields (§4.4).

The premise declares what you ASSUME about who was not observed. It is declarative and inert:
the engine executes it, and no field of it grows a method.

Each axis takes either a sentinel that **names the mechanism** or a concrete value:
`take_up="binned"` or `0.7`; `outcome_from="parcelling"` or the name of your column. The
defaults are literals in the signature, so `help(Premise)` shows that parcelling runs and that
take-up is estimated — no default hides that a mechanism exists.

What is checked here is what needs no data. What needs it — the lens column exists, is
continuous or discrete, the stress ladder has one factor per bucket of the lens, a node's
values stay inside `[0, 1]` — is the bind of the premise, in ticket 6.
"""

from __future__ import annotations

import math
from dataclasses import KW_ONLY
from typing import Any, Literal

from ._nodes import Node, require_node
from ._value import set_field, value_type
from .errors import PremiseError

_BINNED = "binned"
_PARCELLING = "parcelling"
_POPULATIONS = ("global", "keep_in")


@value_type
class Premise:
    """What the study assumes about the unobserved.

    lens
        The risk axis, as an expression (`col("score_5")`). Continuous, it is cut into `bins`
        quantile buckets; discrete, its categories are the buckets. **Required when an axis
        discretizes** — `take_up="binned"` or `outcome_from="parcelling"` — and **refused when
        none does**, because nothing would consume it.
    bins
        How many buckets, when the lens is continuous. One setting serves every axis. When no
        axis discretizes, `repr` marks it *not consumed* — it is the one field whose default
        must be a visible literal, so declaring it can't be told from not declaring it.
    calibrate_on
        The population the score → rate ruler is taught on, for **edges and rates alike**:
        `"global"` (the whole observed book, invariant to the challenger) or `"keep_in"`
        (those the new policy also approves).
    take_up
        The contract axis: `"binned"` (estimated per bucket), a scalar in `[0, 1]` (flat), or
        an expression (a per-row probability).
    stress
        The inflation of the unobserved outcome: a scalar ("the rejected are 1.8× worse than
        the comparable approved"), a ladder with one factor per bucket of the lens, or an
        expression (one factor per row). `1.0` is no inflation.
    outcome_from
        Where the outcome comes from: `"parcelling"` (bucketed, the approved rate carried over,
        `stress` applied), a column name (a realized 0/1 outcome — a fact, not drawn), or an
        expression (a per-row probability — a hypothesis, drawn). With an outcome from outside
        there is nothing to inflate, so `stress` is refused.
    """

    _: KW_ONLY
    lens: Node | None = None
    bins: int = 5
    calibrate_on: Literal["global", "keep_in"] = "global"
    take_up: Literal["binned"] | float | Node = _BINNED
    stress: float | tuple[float, ...] | Node = 1.0
    outcome_from: Literal["parcelling"] | str | Node = _PARCELLING

    def __post_init__(self) -> None:
        if self.lens is not None:
            require_node(self.lens, "lens=")
        self._check_bins()
        if self.calibrate_on not in _POPULATIONS:
            raise PremiseError(f"calibrate_on= is 'global' or 'keep_in', got {self.calibrate_on!r}")
        self._check_take_up()
        self._check_stress()
        self._check_outcome_from()

        # The binding of the lens, in the shape of #116's (declared approved ⇒ hired required).
        if self.discretizes and self.lens is None:
            axes = [
                axis
                for axis, on in (
                    ("take_up='binned'", self.take_up == _BINNED),
                    ("outcome_from='parcelling'", self.outcome_from == _PARCELLING),
                )
                if on
            ]
            raise PremiseError(
                f"lens= is required: {' and '.join(axes)} bucket on the risk axis, and there is "
                "no honest default for it. Declare the axis, e.g. lens=col('score_5')."
            )
        if not self.discretizes and self.lens is not None:
            raise PremiseError(
                f"lens={self.lens!r} is declared but nothing consumes it: take-up is not "
                "'binned' and the outcome does not come from parcelling. Remove lens=."
            )
        if self.outcome_from != _PARCELLING and self.stress != 1.0:
            raise PremiseError(
                f"the outcome comes from outside (outcome_from={self.outcome_from!r}); "
                f"there is nothing to inflate. Remove stress={self.stress!r}."
            )

    @property
    def discretizes(self) -> bool:
        """Whether some axis buckets on the lens — which is what consumes `lens` and `bins`."""
        return self.take_up == _BINNED or self.outcome_from == _PARCELLING

    def _check_bins(self) -> None:
        if type(self.bins) is not int:
            raise TypeError(f"bins= is an int, got {self.bins!r}")
        if self.bins < 2:
            raise PremiseError(f"bins= is at least 2, got {self.bins}")

    def _check_take_up(self) -> None:
        take_up = self.take_up
        if isinstance(take_up, Node):
            return
        if isinstance(take_up, str):
            if take_up != _BINNED:
                raise PremiseError(
                    f"take_up= is 'binned', a number in [0, 1] or an expression, got {take_up!r}"
                )
            return
        if not _is_number(take_up):
            raise TypeError(f"take_up= is 'binned', a number or an expression, got {take_up!r}")
        if not 0.0 <= take_up <= 1.0:
            raise PremiseError(f"take_up= as a scalar is a probability in [0, 1], got {take_up}")
        set_field(self, "take_up", float(take_up))

    def _check_stress(self) -> None:
        stress = self.stress
        if isinstance(stress, Node):
            return
        if isinstance(stress, tuple):
            if not stress:
                raise PremiseError("stress= as a ladder has one factor per bucket; it is empty")
            set_field(self, "stress", tuple(_factor(f, "stress= ladder") for f in stress))
            return
        set_field(self, "stress", _factor(stress, "stress="))

    def _check_outcome_from(self) -> None:
        outcome_from = self.outcome_from
        if isinstance(outcome_from, Node):
            return
        if not isinstance(outcome_from, str) or not outcome_from:
            raise TypeError(
                "outcome_from= is 'parcelling', a column name or an expression, "
                f"got {outcome_from!r}"
            )

    def __repr__(self) -> str:
        return f"Premise({self.render()})"

    def render(self, *, lens_note: str = "") -> str:
        """The fields as the premise itself can report them; `Study` appends what it knows."""
        bins = f"bins={self.bins!r}" + ("" if self.discretizes else " (not consumed)")
        return ", ".join(
            [
                f"lens={self.lens!r}{lens_note}",
                bins,
                f"calibrate_on={self.calibrate_on!r}",
                f"take_up={self.take_up!r}",
                f"stress={self.stress!r}",
                f"outcome_from={self.outcome_from!r}",
            ]
        )


def _is_number(value: Any) -> bool:
    return type(value) in (int, float)


def _factor(value: Any, what: str) -> float:
    if not _is_number(value):
        raise TypeError(f"{what} takes numbers, got {value!r}")
    if not math.isfinite(value) or value <= 0:
        raise PremiseError(f"{what} factors are finite and positive, got {value!r}")
    return float(value)
