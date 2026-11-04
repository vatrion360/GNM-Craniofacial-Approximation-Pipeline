"""Immutable result contracts for future source-confirmed anatomical rules.

Standard library only. These types validate representation, not scientific
accuracy. A missing prediction or SD is never represented by zero.
"""
from dataclasses import dataclass
import math


class NotConfigured(RuntimeError):
    """A rule has no executable, source-confirmed implementation in this release."""

    def __init__(self, rule_id: str, missing: tuple[str, ...]):
        self.rule_id = rule_id
        self.missing = tuple(missing)
        super().__init__(f'{rule_id}: NotConfigured; '+ '; '.join(self.missing))


def _finite(value: object, name: str) -> None:
    if type(value) not in (int, float):
        raise ValueError(f'{name}: a finite number is required, not a boolean or string')
    try:
        valid = math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f'{name}: a finite number is required')


@dataclass(frozen=True)
class Prediction:
    """A scalar quantity or a 3-D world-mm point, with explicit units.

    Vector values are immutable tuples. Scalar angles use degrees; unitless
    ratios use 'unitless'. A point must use mm and the world coordinate frame.
    Local-frame predictions require an explicit conversion before this contract.
    """
    value: float | tuple[float, float, float]
    units: str
    coordinate_space: str | None = None

    def __post_init__(self):
        if type(self.value) is tuple:
            if len(self.value) != 3 or self.units != 'mm' or self.coordinate_space != 'world':
                raise ValueError('Point prediction requires three world-mm coordinates')
            for value in self.value:
                _finite(value, 'prediction coordinate')
        else:
            _finite(self.value, 'prediction')
            if self.units not in ('mm', 'degrees', 'unitless') or self.coordinate_space is not None:
                raise ValueError('Scalar prediction requires explicit units and no coordinate frame')


@dataclass(frozen=True)
class RuleResult:
    """Unpack as (prediction, sd, applicable, notes).

    Applicability is tri-state: True assessed applicable, False assessed
    inapplicable, None unknown. Predictions require True. SD is optional and
    uses the prediction's units: scalar SD for scalars, three marginal coordinate
    SDs for points. No isotropic SD, covariance or interval is inferred.
    """
    prediction: Prediction | None
    sd: float | tuple[float, float, float] | None
    applicable: bool | None
    notes: tuple[str, ...]

    def __post_init__(self):
        if self.applicable is not None and type(self.applicable) is not bool:
            raise ValueError('Applicability must be True, False or None')
        if (type(self.notes) is not tuple or not self.notes
                or any(not isinstance(note, str) or not note.strip() for note in self.notes)):
            raise ValueError('Nonempty immutable explanatory notes required')
        if self.prediction is None:
            if self.sd is not None or self.applicable is True:
                raise ValueError('Unavailable prediction cannot have SD or claim applicability')
            return
        if not isinstance(self.prediction, Prediction) or self.applicable is not True:
            raise ValueError('A prediction requires an assessed applicable result')
        if self.sd is None:
            return
        if type(self.prediction.value) is tuple:
            if type(self.sd) is not tuple or len(self.sd) != 3:
                raise ValueError('Point SD requires three explicit marginal coordinate SDs')
            values = self.sd
        else:
            values = (self.sd,)
        for value in values:
            _finite(value, 'SD')
            if value < 0:
                raise ValueError('SD must be nonnegative')

    def __iter__(self):
        return iter((self.prediction, self.sd, self.applicable, self.notes))

    def as_dict(self) -> dict:
        """Return detached JSON-compatible data; absence stays null."""
        prediction = self.prediction
        return dict(prediction=None if prediction is None else dict(
            value=list(prediction.value) if type(prediction.value) is tuple else prediction.value,
            units=prediction.units, coordinate_space=prediction.coordinate_space),
            sd=list(self.sd) if type(self.sd) is tuple else self.sd,
            applicable=self.applicable, notes=list(self.notes))
