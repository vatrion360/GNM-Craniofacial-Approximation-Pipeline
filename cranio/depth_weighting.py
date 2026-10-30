"""Optional tissue-SD sensitivity weights; NumPy only, no imputed uncertainty.

Scalar multipliers are not calibrated 3-D observation covariances. SD is in mm,
not metres, and is not divided by sqrt(sample size).
"""
import numpy as np
from .validation import finite_array


def precision_factors(table, scope: str, labels) -> tuple[np.ndarray, dict, list[str]]:
    """Return 1/SD_mm**2 and audit rows; missing SD retains the base weight.

    Zero SD cannot define a finite weight. No floor or replacement SD is used.
    Only requested rows matter; repeated regional labels share one audit entry.
    """
    if scope not in ('landmarks', 'regions'):
        raise ValueError('Unknown tissue weighting scope')
    rows = table.document[scope]
    factors, records, warnings = [], {}, []
    for label in labels:
        if label not in records:
            row = rows.get(label)
            sd = None if row is None else row['sd_mm']
            reason = 'missing table row' if row is None else 'missing SD' if sd is None else None
            factor = 1.
            if sd is not None:
                if sd <= 0:
                    raise ValueError(f'{scope}.{label}: depth weighting requires SD > 0 mm')
                with np.errstate(over='ignore', under='ignore', divide='ignore', invalid='ignore'):
                    factor = float((np.float64(1.) / sd) / sd)
                if not np.isfinite(factor) or factor <= 0:
                    raise ValueError(f'{scope}.{label}: inverse SD squared is not representable')
            if reason:
                warnings.append(f'Depth weighting {scope}.{label}: {reason}; retaining existing base weight (no SD imputed).')
            records[label] = dict(sd_mm=sd, factor=factor, fallback=reason, table_row=row)
        factors.append(records[label]['factor'])
    return np.asarray(factors, dtype=float), records, warnings


def multiply_weights(base, factors) -> np.ndarray:
    """Reject unrepresentable effective weights rather than silently drop rows."""
    base = finite_array(base, 'base depth weights').reshape(-1)
    factors = finite_array(factors, 'depth precision factors', base.shape)
    with np.errstate(over='ignore', under='ignore', invalid='ignore'):
        effective = base * factors
    if np.any(base <= 0) or np.any(factors <= 0) or np.any(effective <= 0) or not np.isfinite(effective).all():
        raise ValueError('Depth-weighted rows must have finite positive effective weights')
    return effective


def marker_weights(table, labels, base) -> tuple[np.ndarray, dict, list[str]]:
    """Build solver weights without changing case targets or confidence values."""
    factors, rows, warnings = precision_factors(table, 'landmarks', labels)
    effective = multiply_weights(base, factors)
    for label, original, value in zip(labels, base, effective):
        rows[label].update(base_weight=float(original), effective_weight=float(value))
    record = dict(mode='sd', table=table.record(), landmarks=rows, regions={},
        formula='base_weight * 1 / SD_mm^2; missing SD retains base_weight',
        interpretation='Sensitivity weights, not calibrated uncertainty. One scalar on all three coordinates; no placement covariance. Targets and TPS confidence multipliers are unchanged.',
        dense_budget='Normalize using original marker confidence mass, then apply regional 1/SD_mm^2; no renormalization.')
    return effective, record, warnings


def region_factors(table, regions, nose_weight: float) -> tuple[np.ndarray, dict, list[str]]:
    """Skip zero-strength nasal rows; retain indexing for correspondence sampling."""
    regions = np.asarray(regions)
    active = (regions != 'punte_nazala') | (nose_weight > 0)
    factors = np.ones(len(regions))
    factors[active], rows, warnings = precision_factors(table, 'regions', regions[active])
    return factors, rows, warnings
