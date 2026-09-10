"""`DataSchema` — which column plays which role, and nothing else (§4.1)."""

from __future__ import annotations

from ._value import fields_of, value_type
from .errors import SchemaError


@value_type
class DataSchema:
    """The three columns the engine reads **by role**: approved, hired, outcome.

    The schema owns the names the engine reads by role. The policy names the columns its
    rules *reference* — a score, an income — and those travel inside the rule: role is not
    reference, so `.filter(col("score_5") >= 700)` naming `score_5` is no violation.

    Declaring `approved` makes `hired` mandatory (#116): the package never infers take-up
    from a book that did not say who was hired. Declaring nothing is legitimate — that is a
    standalone study over raw proposals.

    `outcome` accepts nulls in the data: null is the unobserved.

    Only what can be judged without the data is checked here. Presence, the `{0, 1}` domain,
    the approved → hired → outcome chain and zero coercion are bind (ticket 5).

    Reusing a schema on a base with other names is `dataclasses.replace` — no mechanism.
    """

    approved: str | None = None
    hired: str | None = None
    outcome: str | None = None

    def __post_init__(self) -> None:
        for role in fields_of(type(self)):
            column = getattr(self, role)
            if column is not None and (not isinstance(column, str) or not column):
                raise TypeError(
                    f"{role}= names a column: a non-empty string or None, got {column!r}"
                )
        if self.approved is not None and self.hired is None:
            raise SchemaError(
                f"approved={self.approved!r} is declared, so hired= is required: the engine "
                "never infers take-up from a book that does not say who was hired."
            )
