"""The hard errors of the declaration block.

Every one of them is rung 1 of the ladder of remedies (`CONTEXT.md`): a combination of fields
that can be judged without the data, refused at the constructor. What needs the data — a
declared column that is absent, a value outside `{0, 1}` — is rung 2 and belongs to bind.
"""


class SchemaError(ValueError):
    """A `DataSchema` whose roles contradict each other."""


class LabelRequired(ValueError):
    """A stage whose label cannot be derived from its rule, or is already taken."""


class PremiseError(ValueError):
    """A `Premise` whose fields contradict each other."""
