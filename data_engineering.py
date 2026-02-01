"""
==============================================================================
MODULE 1: DATA ENGINEERING
==============================================================================
Purpose : Ingest, clean, and normalise raw NSTA PPRS monthly production data.
Business : PPRS returns are the regulatory source of truth for UK North Sea
           production. Raw data contains missing months (planned/unplanned
           shut-ins), mixed reporting units (tonnes for oil, MMscfd for gas),
           and null fields for decommissioned assets. Any downstream forecast
           model is only as reliable as this cleaning layer.
Source   : NSTA Open Data — "UKCS Hydrocarbon Field Production, PPRS (WGS84)"
           Columns used (as exported via ArcGIS Hub / CSV download):
             reportingUnitName | productionMonth | oilProduction |
             gasProduction     | reportingUnitType
==============================================================================
"""

import pandas as pd
import numpy as np
from typing import Optional


# ---------------------------------------------------------------------------
# CONSTANTS — Industry-standard conversion factors
# ---------------------------------------------------------------------------
# 1 tonne of crude oil ≈ 7.33 barrels (API gravity ~35°, North Sea benchmark)
OIL_TONNES_TO_BARRELS: float = 7.33

# 1 MMscf of gas ≈ 175.8 BOE  (at standard conditions, 6 Mscf = 1 BOE)
# MMscfd → monthly volume = MMscfd × days_in_month; then × 175.8
GAS_MMSCF_TO_BOE: float = 175.8

# Threshold: months where production is zero are flagged as shut-in
SHUT_IN_THRESHOLD: float = 0.0


def load_pprs_csv(filepath: str) -> pd.DataFrame:
    """
    Load a raw PPRS CSV export from NSTA Open Data.

    The NSTA exports column names in camelCase (ArcGIS convention).
    We normalise to snake_case immediately on ingest for consistency
    across the pipeline.

    Parameters
    ----------
    filepath : str
        Path to the downloaded CSV file.

    Returns
    -------
    pd.DataFrame
        Raw DataFrame with normalised column names.
    """
    df = pd.read_csv(filepath, low_memory=False)

    # --- Normalise column names to snake_case ---
    # NSTA exports: reportingUnitName, productionMonth, oilProduction, etc.
    df.columns = (
        df.columns
        .str.replace(r"([a-z])([A-Z])", r"\1_\2", regex=True)
        .str.lower()
        .str.strip()
    )

    return df


def parse_production_dates(df: pd.DataFrame, date_col: str = "production_month") -> pd.DataFrame:
    """
    Convert the PPRS date string into a proper datetime index.

    NSTA exports dates as 'YYYY-MM-DD' (first of the reporting month).
    We convert to Period[M] for clean monthly time-series alignment — this
    avoids timezone/day-of-month edge cases common in fiscal reconciliation.

    Parameters
    ----------
    df       : pd.DataFrame
    date_col : str — the column containing the date string.

    Returns
    -------
    pd.DataFrame with 'report_month' as a Period column and an integer
    'days_in_month' helper for gas volume expansion.
    """
    df = df.copy()
    df["report_month"] = pd.to_datetime(df[date_col], errors="coerce")

    # Business Logic: days_in_month is critical for gas conversion.
    # Gas is reported as MMscfd (per-day rate). To get a monthly volume we
    # must multiply by the actual calendar days — February vs March matters
    # at this scale (≈ 5 % swing in revenue).
    df["days_in_month"] = df["report_month"].dt.days_in_month

    # Convert to Period for clean resampling later
    df["report_month"] = df["report_month"].dt.to_period("M")

    return df


def flag_shut_in_months(df: pd.DataFrame) -> pd.DataFrame:
    """
    Identify and flag shut-in months.

    Business Logic: In North Sea operations, a zero-production month is NOT
    the same as 'no data'. It usually means a planned shutdown (maintenance,
    well intervention) or an unplanned event (safety incident, pipeline
    failure). The decline model must EXCLUDE these months from curve-fitting
    — otherwise the exponential fit is artificially steepened and the
    forecast underestimates true producing-day capacity. The flag lets
    downstream modules make this distinction transparently.

    Parameters
    ----------
    df : pd.DataFrame — must contain 'oil_production' and 'gas_production'.

    Returns
    -------
    pd.DataFrame with a boolean 'is_shut_in' column.
    """
    df = df.copy()

    oil = df["oil_production"].fillna(0)
    gas = df["gas_production"].fillna(0)

    # A month is shut-in when BOTH oil and gas are at or below threshold
    df["is_shut_in"] = (oil <= SHUT_IN_THRESHOLD) & (gas <= SHUT_IN_THRESHOLD)

    return df


def convert_to_boe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert raw PPRS volumes into a unified Barrels of Oil Equivalent (BOE).

    Business Logic: Fiscal metering (Cakasa / PON 7) settles oil and gas
    on different royalty schedules and ring-fence tax bases. However, for
    a *production forecast reconciliation*, we need a single comparable unit
    so that a shortfall in gas can be weighed against an over-performance in
    oil on the same axis. BOE is the industry-standard normalisation.

    Conversion rules applied:
      • Oil  : tonnes → barrels   (× 7.33)
      • Gas  : MMscfd → MMscf/month (× days_in_month) → BOE (× 175.8)
      • Total BOE = oil_boe + gas_boe

    NaN handling: If either stream is null, treat as 0 for that stream
    (but preserve the original NaN so auditors can trace it).

    Parameters
    ----------
    df : pd.DataFrame — must contain 'oil_production', 'gas_production',
         and 'days_in_month'.

    Returns
    -------
    pd.DataFrame with 'oil_boe', 'gas_boe', and 'total_boe' columns.
    """
    df = df.copy()

    # Preserve raw nulls for audit trail
    df["oil_raw_null"] = df["oil_production"].isna()
    df["gas_raw_null"] = df["gas_production"].isna()

    # Oil conversion: tonnes → barrels
    df["oil_boe"] = df["oil_production"].fillna(0) * OIL_TONNES_TO_BARRELS

    # Gas conversion: MMscfd (daily rate) → monthly volume → BOE
    # Step 1: daily rate × days = monthly MMscf
    # Step 2: monthly MMscf × 175.8 = BOE
    gas_monthly_mmscf = df["gas_production"].fillna(0) * df["days_in_month"]
    df["gas_boe"] = gas_monthly_mmscf * GAS_MMSCF_TO_BOE

    # Total BOE is the single number the forecast engine targets
    df["total_boe"] = df["oil_boe"] + df["gas_boe"]

    return df


def clean_pprs_data(
    filepath: str,
    field_name: Optional[str] = None,
) -> pd.DataFrame:
    """
    Master cleaning pipeline — orchestrates all steps above.

    Parameters
    ----------
    filepath   : str  — path to raw PPRS CSV.
    field_name : str  — optional filter to isolate a single reporting unit
                        (e.g. 'HUNTINGTON'). If None, returns all fields.

    Returns
    -------
    pd.DataFrame — cleaned, BOE-normalised, shut-in-flagged production data,
    sorted chronologically per field.
    """
    df = load_pprs_csv(filepath)
    df = parse_production_dates(df)

    # Filter to a single field if requested (common in reconciliation work)
    if field_name:
        mask = df["reporting_unit_name"].str.upper().str.strip() == field_name.upper().strip()
        df = df.loc[mask].copy()
        if df.empty:
            raise ValueError(f"No data found for field: '{field_name}'")

    df = flag_shut_in_months(df)
    df = convert_to_boe(df)

    # Sort chronologically per reporting unit for time-series integrity
    df = df.sort_values(["reporting_unit_name", "report_month"]).reset_index(drop=True)

    return df


# ---------------------------------------------------------------------------
# Demo / smoke-test harness (generates synthetic PPRS-like data)
# ---------------------------------------------------------------------------
def generate_synthetic_pprs(
    field_name: str = "BRAE ALPHA",
    start: str = "2018-01-01",
    months: int = 84,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Generate realistic synthetic PPRS data for testing without needing the
    actual (large) NSTA download.

    Simulates:
      • Natural exponential decline in oil production
      • Associated gas ratio with slight seasonal noise
      • 3 random shut-in months (maintenance windows)
      • 2 months with null gas readings (sensor failure)
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start=start, periods=months, freq="MS")

    # Simulate declining oil production (tonnes/month)
    t = np.arange(months)
    base_oil = 12_000 * np.exp(-0.04 * t)  # ~4% monthly decline
    noise = rng.normal(0, 200, months)
    oil_production = np.maximum(base_oil + noise, 0)

    # Associated gas (MMscfd) — correlated to oil with seasonal bump
    gas_production = (oil_production / 1200) * (1 + 0.15 * np.sin(2 * np.pi * t / 12))
    gas_production += rng.normal(0, 0.05, months)
    gas_production = np.maximum(gas_production, 0)

    # Inject 3 shut-in months
    shut_in_indices = rng.choice(months, size=3, replace=False)
    oil_production[shut_in_indices] = 0.0
    gas_production[shut_in_indices] = 0.0

    # Inject 2 null gas readings
    null_gas_indices = rng.choice(
        [i for i in range(months) if i not in shut_in_indices], size=2, replace=False
    )
    gas_series = pd.Series(gas_production)
    gas_series.iloc[null_gas_indices] = np.nan

    df = pd.DataFrame({
        "reporting_unit_name": field_name,
        "production_month": dates.strftime("%Y-%m-%d"),
        "oil_production": oil_production,
        "gas_production": gas_series.values,
        "reporting_unit_type": "Oil Field Exporting to Pipeline",
    })

    return df
