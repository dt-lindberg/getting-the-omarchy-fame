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
LOGIT_MAX_ITER = 200


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
    columns, terms = {}, []
    for name in logged:
        x = np.log1p(df[name].astype(float))
        if x.std() > 0:
            columns[name] = x
            terms.append(Term(name, float(x.mean() - x.std() / 2), float(x.mean() + x.std() / 2)))
    for name in linear:
        x = df[name].astype(float)
        if x.std() > 0:
            columns[name] = x
            terms.append(Term(name, float(x.mean() - x.std() / 2), float(x.mean() + x.std() / 2)))
    for name in binary:
        x = df[name].astype(float)
        if 0 < x.mean() < 1:
            columns[name] = x
            terms.append(Term(name, 0.0, 1.0))
    return sm.add_constant(pd.DataFrame(columns, index=df.index), has_constant="add"), terms


def fit_logit(design: pd.DataFrame, y: pd.Series, clusters: pd.Series):
    """Fit a logit with author-clustered covariance.

    Args:
        design: Design matrix including the constant.
        y: 0/1 outcome.
        clusters: Author per row, defining the clusters.

    How:
        Returns None when either outcome class has fewer than MIN_EVENTS rows or
        the fit fails through perfect separation or a singular matrix.

    Returns:
        The fitted result, or None when the fit is impossible.
    """
    if y.sum() < MIN_EVENTS or (1 - y).sum() < MIN_EVENTS:
        return None
    try:
        return sm.Logit(y, design).fit(disp=0, maxiter=LOGIT_MAX_ITER, cov_type="cluster",
                                       cov_kwds={"groups": pd.factorize(clusters)[0]})
    except (PerfectSeparationError, LinAlgError, np.linalg.LinAlgError):
        return None


def _shifted_means(res, design: pd.DataFrame, term: Term):
    """Predict mean probabilities with one term set to its low and high value.

    Args:
        res: Fitted logit.
        design: Design matrix used in the fit.
        term: The term to shift.

    How:
        Sets the term's column to each value for every row, keeping the other
        covariates as observed, and averages the logit gradient too.

    Returns:
        For low then high: (mean probability, mean gradient, probabilities per row).
    """
    shifted = []
    for value in (term.low, term.high):
        shifted_design = design.copy()
        shifted_design[term.name] = value
        probabilities = res.predict(shifted_design).to_numpy()
        grad = (probabilities * (1 - probabilities))[:, None] * shifted_design.to_numpy()
        shifted.append((probabilities.mean(), grad.mean(axis=0), probabilities))
    return shifted


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
    sorted_durations, sorted_causes = durations[order], causes[order]
    times, first = np.unique(sorted_durations, return_index=True)
    at_risk = len(sorted_durations) - first
    counts = np.array([[np.sum(sorted_causes[first[i]:(first[i + 1] if i + 1 < len(first) else len(sorted_causes))] == k)
                        for k in range(len(cause_names) + 1)] for i in range(len(times))])
    events = counts[:, 1:].sum(axis=1)
    survival_before = np.concatenate([[1.0], np.cumprod(1 - events / at_risk)[:-1]])
    grid_index = np.searchsorted(times, grid, side="right") - 1
    incidence = {}
    for k, name in enumerate(cause_names, start=1):
        cumulative = np.cumsum(survival_before * counts[:, k] / at_risk)
        incidence[name] = [float(cumulative[i]) if i >= 0 else 0.0 for i in grid_index]
    return incidence


def round_sig(value, digits: int = 3):
    """Round floats to significant figures so a result is JSON-safe.

    Args:
        value: Any nested mix of dicts, sequences, numpy values and timestamps.
        digits: Significant figures to keep.

    How:
        Recurses through dicts and sequences; NaN and inf become None, numpy
        scalars become plain Python values and timestamps become ISO strings.

    Returns:
        The rounded structure.
    """
    if isinstance(value, dict):
        return {str(key): round_sig(item, digits) for key, item in value.items()}
    if isinstance(value, (list, tuple, np.ndarray, pd.Series)):
        return [round_sig(item, digits) for item in value]
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
