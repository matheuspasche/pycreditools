"""`Study` — the encounter of schema, policy and premise (§4.5)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import KW_ONLY
from typing import Any

from . import _value
from ._value import fields_of, value_type
from .policy import CreditPolicy
from .premise import Premise
from .schema import DataSchema

_REBUILD_REFUSED = (
    "Study.vary derives; it does not rebuild. Pass the fields to change as a mapping — "
    "{field}={{...}} — and every field you do not name is carried through. Rebuilding keeps "
    "only what its author remembered to copy."
)


@value_type
class Study:
    """Schema, policy and premise, with the seed and an optional name.

    The premise is **positional and required**: a default premise would hide that imputation
    runs. `seed` is required, so two policies compared in one study face the same draw and
    their difference is rule, never noise. `name` is optional; the reading verbs number the
    unnamed ones.

    `repr` is the inventory of what is declared — and of what is not.
    """

    schema: DataSchema
    policy: CreditPolicy
    premise: Premise
    _: KW_ONLY
    seed: int
    name: str | None = None

    def __post_init__(self) -> None:
        for field, cls in (("schema", DataSchema), ("policy", CreditPolicy), ("premise", Premise)):
            value = getattr(self, field)
            if not isinstance(value, cls):
                hint = (
                    " — a default premise would hide that imputation runs; declare one"
                    if field == "premise"
                    else ""
                )
                raise TypeError(f"{field} is a {cls.__name__}, got {type(value).__name__}{hint}")
        if type(self.seed) is not int or self.seed < 0:
            raise TypeError(f"seed= is a non-negative int, got {self.seed!r}")
        if self.name is not None and (not isinstance(self.name, str) or not self.name):
            raise TypeError(f"name= is a non-empty string or None, got {self.name!r}")

    def vary(self, **changes: Any) -> Study:
        """A derived study: any declared point overwritten, every other one carried through.

        `schema=` and `premise=` take a mapping of the fields to change; `policy=` takes a
        mapping of stage label to the fields of that stage; `seed=` and `name=` take the value.

            study.vary(premise={"stress": 2.2}, policy={"cut": {"expr": col("score_5") >= 720}})

        Rebuilding is not varying: a whole `DataSchema`, `CreditPolicy` or `Premise` is
        refused, because it would carry only what its author remembered to copy.
        """
        names = fields_of(Study)
        derived: dict[str, Any] = {}
        for field, change in changes.items():
            if field not in names:
                raise TypeError(f"Study has no field {field!r}; its fields are {list(names)}")
            if field in ("schema", "premise"):
                derived[field] = _value.replace(getattr(self, field), **_mapping(field, change))
            elif field == "policy":
                policy = self.policy
                for label, stage in _mapping(field, change).items():
                    policy = policy.set_stage(label, **_mapping(f"policy[{label!r}]", stage))
                derived[field] = policy
            else:
                derived[field] = change
        return _value.replace(self, **derived)

    def __repr__(self) -> str:
        schema = ", ".join(f"{f}={getattr(self.schema, f)!r}" for f in fields_of(DataSchema))
        return "\n".join(
            [
                f"<Study {self.name}>" if self.name else "<Study>",
                f"  Schema:  {schema}",
                f"  Policy:  {self._policy_line()}",
                f"  Premise: {self.premise.render(lens_note=self._lens_note())}",
                f"  Seed:    {self.seed}",
            ]
        )

    def _policy_line(self) -> str:
        count = len(self.policy.stages)
        line = f"{count} filter" + ("" if count == 1 else "s")
        draws = sum(stage.draw for stage in self.policy.stages)
        if draws:
            line += f" ({draws} draw)"
        columns = self.policy.columns()
        if columns:
            line += "  ·  " + ", ".join(columns)
        return line

    def _lens_note(self) -> str:
        # Only the study can know this: it needs the policy. The fact is reported, not judged —
        # cutting on one score and simulating under another is a legitimate mixed setup.
        lens = self.premise.lens
        if lens is None:
            return ""
        referenced = set(self.policy.columns())
        if all(column in referenced for column in lens.columns()):
            return ""
        return " (not referenced by the policy)"


def _mapping(field: str, change: Any) -> Mapping[str, Any]:
    if isinstance(change, Mapping):
        return change
    raise TypeError(_REBUILD_REFUSED.format(field=field))
