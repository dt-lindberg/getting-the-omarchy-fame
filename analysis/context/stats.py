"""Shared statistics: logit average marginal effects with author-clustered intervals,
Aalen-Johansen cumulative incidence, and JSON-safe rounding.

Kept apart so each analysis module only describes what it models.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm
from numpy.linalg import LinAlgError
from statsmodels.tools.sm_exceptions import PerfectSeparationError

Z95 = 1.96
MIN_EVENTS = 10


@dataclass
class Term:
    """One model term: a column and the two values compared (low to high)."""

    name: str
    low: float
    high: float


def standardise(df: pd.DataFrame, logged: list[str], binary: list[str],
                linear: list[str] = ()) -> tuple[pd.DataFrame, list[Term]]:
    """Build the design matrix and the comparison step for each term.

    Args:
        df: Rows to model.
        logged: Count-like columns, entered as log1p and compared at +1 SD.
        binary: Columns coded 0/1, compared 0 to 1.
        linear: Continuous columns entered as they are, compared at +1 SD.

    How:
        Logged terms use the sample's own SD so the step is "one typical
        difference between PRs in this sample"; binaries that are constant are
        dropped because they carry no information.

    Returns:
        (design frame with a constant, list of Terms).
    """
    cols, terms = {}, []
    for name in logged:
        x = np.log1p(df[name].astype(float))
        if x.std() > 0:
            cols[name] = x
            terms.append(Term(name, float(x.mean() - x.std() / 2), float(x.mean() + x.std() / 2)))
    for name in linear:
        x = df[name].astype(float)
        if x.std() > 0:
            cols[name] = x
            terms.append(Term(name, float(x.mean() - x.std() / 2), float(x.mean() + x.std() / 2)))
    for name in binary:
        x = df[name].astype(float)
        if 0 < x.mean() < 1:
            cols[name] = x
            terms.append(Term(name, 0.0, 1.0))
    return sm.add_constant(pd.DataFrame(cols, index=df.index), has_constant="add"), terms


def fit_logit(design: pd.DataFrame, y: pd.Series, clusters: pd.Series):
    """Logit with author-clustered covariance; None when the fit is impossible."""
    if y.sum() < MIN_EVENTS or (1 - y).sum() < MIN_EVENTS:
        return None
    try:
        return sm.Logit(y, design).fit(disp=0, maxiter=200, cov_type="cluster",
                                       cov_kwds={"groups": pd.factorize(clusters)[0]})
    except (PerfectSeparationError, LinAlgError, np.linalg.LinAlgError):
        return None


def _shifted_means(res, design: pd.DataFrame, term: Term):
    """Counterfactual mean probabilities and their gradients with the term at low and high."""
    out = []
    for value in (term.low, term.high):
        x = design.copy()
        x[term.name] = value
        p = res.predict(x).to_numpy()
        grad = (p * (1 - p))[:, None] * x.to_numpy()
        out.append((p.mean(), grad.mean(axis=0), p))
    return out


def marginal_effects(res, design: pd.DataFrame, terms: list[Term], only: list[str] | None = None) -> list[dict]:
    """Average marginal effect (pp) and rate ratio per term, with 95% intervals.

    Args:
        res: Fitted clustered logit.
        design: Design matrix used in the fit.
        terms: Comparison steps from standardise.
        only: Restrict to these term names (controls are not reported).

    How:
        Every row is predicted with the term set to its low and then high value,
        keeping other covariates as observed. The difference of the two means is
        the AME; the delta method with the clustered covariance gives the interval.

    Returns:
        One dictionary per term.
    """
    cov = res.cov_params().to_numpy()
    rows = []
    for term in terms:
        if only is not None and term.name not in only:
            continue
        (m0, g0, _), (m1, g1, _) = _shifted_means(res, design, term)
        grad = g1 - g0
        se = float(np.sqrt(grad @ cov @ grad))
        ame = (m1 - m0) * 100
        log_rr_grad = g1 / m1 - g0 / m0
        se_rr = float(np.sqrt(log_rr_grad @ cov @ log_rr_grad))
        rr = m1 / m0
        rows.append({"term": term.name, "ame_pp": ame, "lo": ame - Z95 * se * 100, "hi": ame + Z95 * se * 100,
                     "rr": rr, "rr_lo": rr * np.exp(-Z95 * se_rr), "rr_hi": rr * np.exp(Z95 * se_rr)})
    return rows


def aalen_johansen(durations: np.ndarray, causes: np.ndarray, cause_names: list[str],
                   grid: list[float]) -> dict[str, list[float]]:
    """Cumulative incidence of each cause on a day grid, treating cause 0 as censored.

    Args:
        durations: Days from opening to decision or to the end of follow-up.
        causes: Integer code per PR, 0 for censored, k for cause_names[k-1].
        cause_names: Labels for codes 1..K.
        grid: Days at which to read the curves.

    How:
        At each distinct time, the share of the surviving population that
        experiences cause k is added to its curve, weighted by the probability of
        having no event before that time. Curves are read as step functions.

    Returns:
        Mapping cause name to cumulative incidence at each grid day.
    """
    order = np.argsort(durations, kind="stable")
    t, c = durations[order], causes[order]
    times, first = np.unique(t, return_index=True)
    at_risk = len(t) - first
    counts = np.array([[np.sum(c[first[i]:(first[i + 1] if i + 1 < len(first) else len(c))] == k)
                        for k in range(len(cause_names) + 1)] for i in range(len(times))])
    events = counts[:, 1:].sum(axis=1)
    survival_before = np.concatenate([[1.0], np.cumprod(1 - events / at_risk)[:-1]])
    idx = np.searchsorted(times, grid, side="right") - 1
    out = {}
    for k, name in enumerate(cause_names, start=1):
        cum = np.cumsum(survival_before * counts[:, k] / at_risk)
        out[name] = [float(cum[i]) if i >= 0 else 0.0 for i in idx]
    return out


def round_sig(value, digits: int = 3):
    """Recursively round floats to significant figures; NaN and inf become None."""
    if isinstance(value, dict):
        return {str(k): round_sig(v, digits) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray, pd.Series)):
        return [round_sig(v, digits) for v in value]
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        if not np.isfinite(value):
            return None
        return float(f"{value:.{digits}g}")
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value
