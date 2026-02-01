"""
==============================================================================
MODULE 2: ANALYTICAL ENGINE — Arps' Exponential Decline Curve Model
==============================================================================
Purpose : Fit an Arps' Exponential decline curve to historical production,
          then project a technical forecast forward in time. The gap between
          this forecast and actual reported production is the signal that
          drives the fiscal leakage analysis.

Business : Arps' decline curves are the industry-standard parametric model
           for reservoir depletion. The exponential variant assumes a constant
           fractional decline rate (di) — appropriate for solution-gas-drive
           and many North Sea chalk reservoirs in their mid-life phase.
           The model has two free parameters:
             • qi — initial (peak) production rate (BOE/month)
             • di — nominal decline rate (per month, dimensionless)
           scipy.optimize.curve_fit recovers these from historical data via
           non-linear least squares.

           Why this matters fiscally: If actual production EXCEEDS the
           decline curve, the operator may be drawing down reserves faster
           than the approved Development Programme (DP) allows — a potential
           regulatory flag. If actual production is BELOW the curve for
           sustained periods (excluding shut-ins), it may indicate metering
           under-reporting or unrecorded diversion — "fiscal leakage".
==============================================================================
"""

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit
from typing import Tuple


# ---------------------------------------------------------------------------
# Arps' Exponential Decline Model
# ---------------------------------------------------------------------------
def arps_exponential(t: np.ndarray, qi: float, di: float) -> np.ndarray:
    """
    Arps' Exponential Decline equation.

        q(t) = qi × exp(−di × t)

    Parameters
    ----------
    t  : np.ndarray — time in months since first production (t=0).
    qi : float      — initial production rate at t=0 (BOE/month).
    di : float      — nominal decline rate (fraction per month).
                      e.g. 0.035 = 3.5 % decline per month.

    Returns
    -------
    np.ndarray — predicted production at each time step.
    """
    return qi * np.exp(-di * t)


def fit_decline_curve(
    production_series: pd.Series,
    time_index: np.ndarray,
) -> Tuple[float, float, np.ndarray]:
    """
    Fit Arps' Exponential model to observed production using scipy curve_fit.

    Business Logic: We exclude shut-in months BEFORE fitting. Shut-in months
    represent operational interruptions, not reservoir behaviour. Including
    them would artificially inflate the estimated decline rate (di), which
    would then produce an overly pessimistic forecast — masking real
    under-performance in producing months.

    The fitting uses Levenberg-Marquardt (default for curve_fit) with
    sensible initial guesses and bounds to prevent physically impossible
    solutions (negative rates, negative decline).

    Parameters
    ----------
    production_series : pd.Series
        Total BOE production per month (NaN or 0 for shut-in months already
        flagged by the data engineering layer).
    time_index : np.ndarray
        Integer array [0, 1, 2, ...] representing months since first
        production.

    Returns
    -------
    qi         : float         — fitted initial rate (BOE/month).
    di         : float         — fitted decline rate (fraction/month).
    covariance : np.ndarray    — 2×2 covariance matrix from curve_fit
                                 (used for confidence intervals).

    Raises
    ------
    ValueError if fewer than 3 producing months are available (underdetermined).
    """
    # --- Filter out shut-in months (zero production) ---
    # Business Logic: Only months where the field was actively producing
    # carry information about the reservoir's natural decline behaviour.
    mask = production_series > 0
    t_fit = time_index[mask]
    q_fit = production_series.values[mask]

    if len(t_fit) < 3:
        raise ValueError(
            "Insufficient producing months for curve fitting. "
            "Need ≥3 non-zero production observations."
        )

    # --- Initial guesses ---
    # qi_0: use the maximum observed production as starting point
    # di_0: estimate from log-linear regression slope as a warm start
    qi_0 = float(q_fit.max())
    # Simple log-linear estimate: ln(q) = ln(qi) - di*t  →  slope ≈ -di
    log_q = np.log(q_fit + 1e-10)  # small epsilon avoids log(0)
    slope = np.polyfit(t_fit, log_q, 1)[0]
    di_0 = max(-slope, 0.005)  # floor at 0.5% to avoid zero decline

    # --- Bounds: physically meaningful constraints ---
    # qi must be positive; di must be in (0, 1) — 100% decline/month is
    # the absolute upper physical limit.
    bounds = ([0, 0], [np.inf, 1.0])

    popt, pcov = curve_fit(
        arps_exponential,
        t_fit,
        q_fit,
        p0=[qi_0, di_0],
        bounds=bounds,
        maxfev=10_000,
    )

    qi_fit, di_fit = popt

    return qi_fit, di_fit, pcov


def generate_forecast(
    qi: float,
    di: float,
    forecast_months: int,
    history_months: int = 0,
) -> pd.DataFrame:
    """
    Generate a forward-looking production forecast from fitted parameters.

    Parameters
    ----------
    qi              : float — fitted initial rate.
    di              : float — fitted decline rate.
    forecast_months : int   — number of months to project into the future.
    history_months  : int   — offset so that t=0 aligns with the original
                               first production month (preserves time axis).

    Returns
    -------
    pd.DataFrame with columns:
        • t_month       — integer month index from original t=0
        • forecast_boe  — Arps' model prediction at each month
    """
    t_range = np.arange(history_months, history_months + forecast_months)
    forecast_values = arps_exponential(t_range, qi, di)

    return pd.DataFrame({
        "t_month": t_range,
        "forecast_boe": forecast_values,
    })


def build_reconciliation_table(
    cleaned_df: pd.DataFrame,
    qi: float,
    di: float,
) -> pd.DataFrame:
    """
    Merge actual production with the decline curve forecast to produce
    the core reconciliation table used by the fiscal impact engine.

    Business Logic: This table is the "single source of truth" for the
    variance analysis. Every downstream metric — revenue at risk, governance
    flags, executive KPIs — is derived from this one DataFrame.

    Columns produced:
        • report_month   — Period[M] timestamp
        • actual_boe     — reported production (from PPRS)
        • forecast_boe   — Arps' model prediction
        • variance_boe   — actual − forecast (negative = under-performance)
        • variance_pct   — variance as % of forecast (key governance metric)
        • is_shut_in     — boolean flag from data engineering layer

    Parameters
    ----------
    cleaned_df : pd.DataFrame — output of data_engineering.clean_pprs_data().
    qi         : float        — fitted initial rate.
    di         : float        — fitted decline rate.

    Returns
    -------
    pd.DataFrame — the reconciliation table.
    """
    df = cleaned_df.copy()

    # Reconstruct time index (months since first production)
    df = df.reset_index(drop=True)
    df["t_month"] = np.arange(len(df))

    # Generate forecast aligned to the same time axis
    df["forecast_boe"] = arps_exponential(df["t_month"].values, qi, di)

    # Rename for clarity
    df = df.rename(columns={"total_boe": "actual_boe"})

    # --- Variance Calculation ---
    # Business Logic: Variance = Actual − Forecast.
    #   • Positive variance → field is outperforming the technical model
    #     (could indicate reserves being drawn faster than planned)
    #   • Negative variance → field is underperforming
    #     (potential metering issue, unrecorded diversion, or genuine
    #     reservoir weakness beyond the decline model)
    df["variance_boe"] = df["actual_boe"] - df["forecast_boe"]

    # Percentage variance relative to forecast (avoids division by zero)
    df["variance_pct"] = np.where(
        df["forecast_boe"] > 0,
        (df["variance_boe"] / df["forecast_boe"]) * 100,
        0.0,
    )

    # Select and order the output columns for the reconciliation table
    output_cols = [
        "report_month",
        "actual_boe",
        "forecast_boe",
        "variance_boe",
        "variance_pct",
        "is_shut_in",
        "t_month",
    ]

    return df[output_cols].copy()
