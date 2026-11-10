import importlib.util
import warnings

import numpy as np

from ..models import Metric


class InvalidDistribution(ValueError):
    pass


def validate_counts(counts, *, require_two_populated=True) -> np.ndarray:
    try:
        values = np.asarray(counts, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise InvalidDistribution("Income bins must form a rectangular numeric matrix") from exc
    if values.ndim != 2 or values.shape[0] < 2 or values.shape[1] < 2:
        raise InvalidDistribution("At least two areas and two income bins are required")
    if not np.isfinite(values).all() or (values < 0).any():
        raise InvalidDistribution("Missing, suppressed, negative or non-finite observations")
    if require_two_populated and np.count_nonzero(values.sum(axis=1)) < 2:
        raise InvalidDistribution("At least two nonempty areas are required")
    if not np.isfinite(values.sum()) or values.sum() > 1e15:
        raise InvalidDistribution("Counts exceed safe numerical limits")
    return values


def dissimilarity(low, high) -> float | None:
    values = validate_counts(np.column_stack([low, high]), require_two_populated=False)
    totals = values.sum(axis=0)
    if (totals == 0).any():
        return None
    return float(0.5 * np.abs(values[:, 0] / totals[0] - values[:, 1] / totals[1]).sum())


def interaction(low, target, total) -> float | None:
    low, target, total = (np.asarray(x, dtype=float) for x in [low, target, total])
    if low.ndim != 1 or low.shape != target.shape or low.shape != total.shape:
        raise InvalidDistribution("Interaction arrays must have the same one-dimensional shape")
    validate_counts(np.column_stack([low, target, total]), require_two_populated=False)
    if (low > total).any() or (target > total).any():
        raise InvalidDistribution("A group exceeds total households")
    if low.sum() == 0:
        return None
    shares = np.divide(target, total, out=np.zeros_like(target), where=total > 0)
    return float(np.dot(low / low.sum(), shares))


def entropy(proportions: np.ndarray) -> np.ndarray:
    log_p = np.zeros_like(proportions)
    np.log(proportions, out=log_p, where=proportions > 0)
    return -(proportions * log_p).sum(axis=-1)


def information_theory(counts) -> float | None:
    values = validate_counts(counts)
    totals = values.sum(axis=1)
    city_entropy = float(entropy(values.sum(axis=0) / totals.sum()))
    if city_entropy <= np.finfo(float).eps:
        return None
    shares = np.divide(
        values, totals[:, None], out=np.zeros_like(values), where=totals[:, None] > 0
    )
    result = 1 - np.dot(totals / totals.sum(), entropy(shares)) / city_entropy
    return float(np.clip(result, 0, 1))


def rank_order_information_theory(counts) -> tuple[float | None, str | None]:
    """Call the published PySAL implementation; never approximate it ourselves.

    Grouped bins yield a polynomial profile estimate, not raw household ranks.
    Empty citywide bins are removed without changing the order. Require five
    distinct cumulative cutpoints for a degree-four fit.
    """
    values = validate_counts(counts)
    values = values[:, values.sum(axis=0) > 0]
    values = values[values.sum(axis=1) > 0]
    if values.shape[1] < 6:
        return None, "Too few distinct income cutpoints for the reference polynomial fit"
    if importlib.util.find_spec("segregation") is None:
        return None, "Install the pinned rank extra (segregation==2.6.0) to enable this measure"
    import pandas as pd

    frame = pd.DataFrame(values, columns=[f"bin_{i}" for i in range(values.shape[1])])
    try:
        # PySAL's binary Entropy intentionally evaluates 0*log(0) then replaces
        # it with its zero limit. Its module sets NumPy error modes at import,
        # but NumPy modes are thread-local: importing in an async worker must
        # not make behavior depend on which thread imports first. Isolate the
        # reference's expected arithmetic modes and restore caller settings.
        # R-squared is undefined for a constant segregation profile; that fit
        # diagnostic is not the segregation statistic and is never reported.
        with (
            np.errstate(divide="ignore", invalid="ignore", under="ignore", over="raise"),
            warnings.catch_warnings(),
        ):
            warnings.simplefilter("error", RuntimeWarning)
            from segregation.rankorder import RankOrderInfoTheory

            fitted = RankOrderInfoTheory(frame, list(frame.columns), degree=4)
            result = float(fitted.statistic)
    except (ValueError, FloatingPointError, RuntimeWarning, np.linalg.LinAlgError):
        return None, "Reference rank-order fit was numerically unstable"
    if (
        len(fitted.profile) != values.shape[1] - 1
        or fitted.model.model.rank != 5
        or not np.isfinite(fitted.coefficients).all()
        or not np.isfinite(fitted.profile["statistic"]).all()
    ):
        return None, "Reference rank-order profile or polynomial fit is incomplete"
    if not np.isfinite(result) or result < -1e-10 or result > 1 + 1e-10:
        return None, "Reference polynomial fit produced a value outside its valid range"
    return float(np.clip(result, 0, 1)), None


def compute_metrics(counts, preferences=None) -> list[Metric]:
    values = validate_counts(counts)
    if values.shape[1] != 16:
        raise InvalidDistribution("This grouping requires the 16 ACS B19001 income bins")
    totals = values.sum(axis=1)
    low, high = values[:, :6].sum(axis=1), values[:, 12:].sum(axis=1)
    coverage = {
        "areas": len(values),
        "populated_areas": int((totals > 0).sum()),
        "households": int(totals.sum()),
        "fraction": 1.0,
    }
    caveats = [
        "ACS survey estimates; index confidence intervals are not computed.",
        "Results depend on tract zoning and aggregation (MAUP); not adjusted for sampling bias.",
    ]
    if len(values) < 20:
        caveats.append("Few spatial units: coarse zoning can conceal segregation.")
    metrics = []
    specs = [
        (
            "dissimilarity",
            "Dissimilarité",
            lambda: dissimilarity(low, high),
            "0.5 × Σ |lowᵢ/LOW − highᵢ/HIGH|",
            "0: identical spatial distributions; 1: complete separation of the two groups.",
            "Households <$35,000 versus ≥$100,000; middle incomes excluded",
        ),
        (
            "isolation",
            "Isolement",
            lambda: interaction(low, low, totals),
            "Σ (lowᵢ/LOW) × (lowᵢ/householdsᵢ)",
            "Low-income share of the tract of a typical low-income household; strongly depends on city composition.",
            "Households <$35,000; all households in area denominators",
        ),
        (
            "exposure",
            "Exposition",
            lambda: interaction(low, high, totals),
            "Σ (lowᵢ/LOW) × (highᵢ/householdsᵢ)",
            "High-income share of the tract of a typical low-income household; not a causal contact probability.",
            "Low <$35,000 to high ≥$100,000; all households in denominators",
        ),
        (
            "theil_h",
            "Information H",
            lambda: information_theory(values),
            "(E − Σ (tᵢ/T)Eᵢ) / E; E = −Σ pₖ ln(pₖ)",
            "Fraction of income-category diversity attributable to differences between tracts; 0 to 1.",
            "All 16 household-income categories",
        ),
    ]
    for key, label, fn, definition, interpretation, groups in specs:
        if preferences is not None and key not in preferences:
            continue
        # A valid full distribution can have no low/high households in populated areas.
        try:
            value = fn()
        except InvalidDistribution:
            value = None
        metrics.append(
            Metric(
                id=key,
                label=label,
                value=value,
                definition=definition,
                interpretation=interpretation,
                target_groups=groups,
                input_coverage=coverage,
                warnings=caveats,
                unavailable_reason="Required group or city entropy is zero"
                if value is None
                else None,
            )
        )
    if preferences is None or "rank_order_h" in preferences:
        value, reason = rank_order_information_theory(values)
        metrics.append(
            Metric(
                id="rank_order_h",
                label="H de rang",
                value=value,
                definition="PySAL segregation 2.6.0 RankOrderInfoTheory, polynomial degree 4 (Reardon)",
                interpretation="Grouped-income rank-order estimate; not an exact individual-rank measure.",
                target_groups="All ordered nonempty B19001 bins, including open tails",
                input_coverage=coverage,
                warnings=caveats
                + [
                    "Polynomial interpolation between observed cumulative income cutpoints; tails are not imputed."
                ],
                unavailable_reason=reason,
            )
        )
    return metrics
