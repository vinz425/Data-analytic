"""
==============================================================================
: BUSINESS LOGIC — Fiscal Impact & Data Governance Engine
==============================================================================
Purpose : Translate the physical production variance (BOE) into a monetary
          revenue exposure figure (GBP), and flag data-quality anomalies
          for governance review.

Business : This module bridges the gap between the technical decline model
           and the boardroom. A deviation of 50,000 BOE means nothing to a
           CFO — but a "£3.2 M revenue at risk" headline does.

           The fiscal impact calculation is intentionally simple and
           transparent: Δ_revenue = Δ_production × price_per_barrel.
           This mirrors how ring-fence Petroleum Revenue Tax (PRT) and
           Supplementary Charge (SC) exposures are estimated in pre-budget
           operator reports. The price_per_barrel input should be sourced
           from the relevant settlement period (e.g. Brent forward curve
           or actual realised price from the operator's fiscal return).

           The governance layer applies a >15 % variance threshold —
           a common materiality gate in NSTA compliance reviews — and
           produces an auditable log of flagged observations.
==============================================================================
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List
from datetime import datetime


# ---------------------------------------------------------------------------
# Configuration & Data Structures
# ---------------------------------------------------------------------------
# Default GBP/bbl price (Brent equivalent, illustrative — replace with live
# forward curve or operator's realised price for production use).
DEFAULT_PRICE_PER_BARREL_GBP: float = 72.50

# Governance threshold: flag any month where |variance_pct| exceeds this
GOVERNANCE_VARIANCE_THRESHOLD_PCT: float = 15.0


@dataclass
class GovernanceFlag:
    """
    Immutable record of a single governance flag event.

    Designed to be serialisable to JSON for audit trail export.
    """
    flag_id: int
    report_month: str          # Period string e.g. "2023-06"
    actual_boe: float
    forecast_boe: float
    variance_boe: float
    variance_pct: float
    revenue_exposure_gbp: float
    flag_reason: str           # Human-readable explanation
    severity: str              # LOW | MEDIUM | HIGH
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class FiscalSummary:
    """
    Top-level summary object — this is what gets rendered on the
    C-suite metric card.
    """
    total_revenue_at_risk_gbp: float
    total_variance_boe: float
    months_analysed: int
    months_shut_in: int
    producing_months: int
    avg_monthly_variance_pct: float
    governance_flags: List[GovernanceFlag]
    price_per_barrel_gbp: float
    analysis_date: str = field(default_factory=lambda: datetime.utcnow().strftime("%Y-%m-%d"))


# ---------------------------------------------------------------------------
# Core Fiscal Impact Functions
# ---------------------------------------------------------------------------
def calculate_fiscal_impact(
    reconciliation_df: pd.DataFrame,
    price_per_barrel: float = DEFAULT_PRICE_PER_BARREL_GBP,
) -> pd.DataFrame:
    """
    Calculate the monthly GBP revenue exposure from production variance.

    Business Logic:
        revenue_exposure = variance_boe × price_per_barrel

        • Positive exposure → the field produced MORE than forecast.
          In a ring-fence tax context this could mean higher tax liability
          than budgeted. In a commercial JV context it may trigger
          production-sharing true-ups.
        • Negative exposure → the field produced LESS than forecast.
          This is the "fiscal leakage" signal. Revenue that the operator
          expected to realise has not materialised. Causes:
            - Metering drift (uncalibrated fiscal meters)
            - Unrecorded diversion or flare volumes
            - Undisclosed shut-in periods
            - Genuine reservoir underperformance

        NOTE: Shut-in months are EXCLUDED from the cumulative revenue-at-risk
        total because they represent known operational interruptions, not
        unexplained deviations. They are retained in the DataFrame for
        transparency but zeroed in the fiscal column.

    Parameters
    ----------
    reconciliation_df : pd.DataFrame
        Output of analytical_engine.build_reconciliation_table().
    price_per_barrel  : float
        GBP per barrel of oil equivalent. Dynamic — can be updated per
        settlement period, scenario, or sensitivity run.

    Returns
    -------
    pd.DataFrame — reconciliation table augmented with:
        • revenue_exposure_gbp  — monthly fiscal impact
        • cumulative_exposure_gbp — running total (excludes shut-in months)
    """
    df = reconciliation_df.copy()

    # Business Logic: Shut-in months get zero fiscal exposure.
    # The variance during a shut-in is an artefact of comparing zero
    # production to a model that assumes continuous operation.
    df["revenue_exposure_gbp"] = np.where(
        df["is_shut_in"],
        0.0,
        df["variance_boe"] * price_per_barrel,
    )

    # Cumulative exposure — the "Total Revenue at Risk" headline metric
    df["cumulative_exposure_gbp"] = df["revenue_exposure_gbp"].cumsum()

    # Tag the price used (important for scenario comparisons)
    df["price_per_barrel_gbp"] = price_per_barrel

    return df


def run_governance_audit(
    fiscal_df: pd.DataFrame,
    threshold_pct: float = GOVERNANCE_VARIANCE_THRESHOLD_PCT,
) -> List[GovernanceFlag]:
    """
    Scan the fiscal impact table and flag months exceeding the variance
    materiality threshold.

    Business Logic: The 15 % threshold is derived from NSTA guidance on
    acceptable metering uncertainty bands for fiscal measurement points.
    Sustained breaches (3+ consecutive months) are classified as HIGH
    severity — these are the signals most likely to trigger a regulatory
    inquiry or an internal audit review.

    Severity classification:
        • LOW    — single month, |variance| between 15–25 %
        • MEDIUM — single month, |variance| > 25 %, OR 2 consecutive flags
        • HIGH   — 3+ consecutive flagged months (systematic issue)

    Parameters
    ----------
    fiscal_df    : pd.DataFrame — output of calculate_fiscal_impact().
    threshold_pct: float        — materiality gate (default 15 %).

    Returns
    -------
    List[GovernanceFlag] — ordered chronologically.
    """
    flags: List[GovernanceFlag] = []

    # Exclude shut-in months from governance scanning
    audit_df = fiscal_df[~fiscal_df["is_shut_in"]].copy().reset_index(drop=True)

    # Identify breaching months
    breaching_mask = audit_df["variance_pct"].abs() > threshold_pct
    breaching_df = audit_df[breaching_mask].copy()

    if breaching_df.empty:
        return flags

    # --- Consecutive-flag detection for severity escalation ---
    # Build a consecutive-run counter on the breaching mask
    consecutive_runs = []
    run_length = 0
    for val in breaching_mask:
        if val:
            run_length += 1
        else:
            run_length = 0
        consecutive_runs.append(run_length)
    audit_df["consecutive_flags"] = consecutive_runs

    # Generate flags
    for flag_id, (idx, row) in enumerate(
        audit_df[breaching_mask].iterrows(), start=1
    ):
        abs_var = abs(row["variance_pct"])
        consec = row["consecutive_flags"]

        # Severity logic
        if consec >= 3:
            severity = "HIGH"
            reason = (
                f"SYSTEMATIC: {consec} consecutive months exceeding "
                f"{threshold_pct:.0f}% variance threshold. "
                f"Indicates possible metering drift or unrecorded diversion."
            )
        elif consec >= 2 or abs_var > 25:
            severity = "MEDIUM"
            reason = (
                f"ELEVATED: Variance of {abs_var:.1f}% exceeds "
                f"{threshold_pct:.0f}% threshold. Monitor for recurrence."
            )
        else:
            severity = "LOW"
            direction = "under" if row["variance_boe"] < 0 else "over"
            reason = (
                f"SINGLE BREACH: Field {direction}-produced by {abs_var:.1f}% "
                f"vs. technical decline forecast."
            )

        flags.append(GovernanceFlag(
            flag_id=flag_id,
            report_month=str(row["report_month"]),
            actual_boe=round(row["actual_boe"], 1),
            forecast_boe=round(row["forecast_boe"], 1),
            variance_boe=round(row["variance_boe"], 1),
            variance_pct=round(row["variance_pct"], 2),
            revenue_exposure_gbp=round(row["revenue_exposure_gbp"], 2),
            flag_reason=reason,
            severity=severity,
        ))

    return flags


def generate_fiscal_summary(
    fiscal_df: pd.DataFrame,
    governance_flags: List[GovernanceFlag],
    price_per_barrel: float = DEFAULT_PRICE_PER_BARREL_GBP,
) -> FiscalSummary:
    """
    Produce the top-level executive summary object.

    This is the single object that feeds the C-suite metric cards on the
    Streamlit dashboard. All numbers here must be internally consistent
    and traceable back to the reconciliation table.

    Parameters
    ----------
    fiscal_df         : pd.DataFrame         — output of calculate_fiscal_impact().
    governance_flags  : List[GovernanceFlag] — output of run_governance_audit().
    price_per_barrel  : float                — price used in the run.

    Returns
    -------
    FiscalSummary dataclass instance.
    """
    producing = fiscal_df[~fiscal_df["is_shut_in"]]

    return FiscalSummary(
        total_revenue_at_risk_gbp=round(fiscal_df["cumulative_exposure_gbp"].iloc[-1], 2),
        total_variance_boe=round(producing["variance_boe"].sum(), 1),
        months_analysed=len(fiscal_df),
        months_shut_in=int(fiscal_df["is_shut_in"].sum()),
        producing_months=int((~fiscal_df["is_shut_in"]).sum()),
        avg_monthly_variance_pct=round(producing["variance_pct"].mean(), 2),
        governance_flags=governance_flags,
        price_per_barrel_gbp=price_per_barrel,
    )


# ---------------------------------------------------------------------------
# Sensitivity Analysis Helper
# ---------------------------------------------------------------------------
def sensitivity_sweep(
    reconciliation_df: pd.DataFrame,
    price_scenarios: list = None,
) -> pd.DataFrame:
    """
    Run the fiscal impact calculation across multiple price scenarios.

    Business Logic: Oil price volatility means the revenue-at-risk number
    is itself uncertain. A sensitivity sweep across plausible Brent prices
    gives the C-suite a range, not just a point estimate — critical for
    risk-appetite discussions.

    Parameters
    ----------
    reconciliation_df : pd.DataFrame
    price_scenarios   : list of float — GBP/bbl prices to test.
                        Defaults to a 5-point range around current Brent.

    Returns
    -------
    pd.DataFrame — one row per scenario with total revenue at risk.
    """
    if price_scenarios is None:
        price_scenarios = [55.0, 62.50, 72.50, 82.50, 95.0]

    results = []
    for price in price_scenarios:
        fiscal = calculate_fiscal_impact(reconciliation_df, price_per_barrel=price)
        total_risk = fiscal["cumulative_exposure_gbp"].iloc[-1]
        results.append({
            "price_per_barrel_gbp": price,
            "total_revenue_at_risk_gbp": round(total_risk, 2),
        })

    return pd.DataFrame(results)
