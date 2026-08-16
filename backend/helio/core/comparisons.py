"""Percentage arithmetic shared by the comparison endpoints."""


def pct_change(current: float, prior: float | None) -> float | None:
    """Compute percentage change from prior to current.

    Args:
        current: Current period value.
        prior: Prior period value (may be None or zero).

    Returns:
        Percentage change rounded to 1 decimal, or None when the prior side
        cannot be divided by: an unmeasured or zero period reads as unknown
        rather than as an infinite improvement.
    """
    if prior is None or prior == 0:
        return None
    return round((current - prior) / prior * 100, 1)
