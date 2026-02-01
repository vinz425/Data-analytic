"""
==============================================================================
TEST SUITE — End-to-End Validation
==============================================================================
Runs the full pipeline on synthetic data and asserts correctness of each
module. Execute with:  python test_pipeline.py
==============================================================================
"""

import sys
import numpy as np
import pandas as pd

# Adjust path for direct execution
sys.path.insert(0, ".")

from data_engineering import (
    generate_synthetic_pprs,
    parse_production_dates,
    flag_shut_in_months,
    convert_to_boe,
    OIL_TONNES_TO_BARRELS,
    GAS_MMSCF_TO_BOE,
)
from analytical_engine import (
    fit_decline_curve,
    build_reconciliation_table,
    arps_exponential,
)
from business_logic import (
    calculate_fiscal_impact,
    run_governance_audit,
    generate_fiscal_summary,
    sensitivity_sweep,
)


def test_synthetic_data_generation():
    """Module 1: Synthetic data has correct shape and shut-in injection."""
    df = generate_synthetic_pprs(months=84)
    assert len(df) == 84, "Expected 84 months"
    assert "oil_production" in df.columns
    assert "gas_production" in df.columns
    # At least some shut-in months exist (injected by generator)
    assert (df["oil_production"] == 0).sum() >= 1, "No shut-in months detected"
    print("  ✓ test_synthetic_data_generation passed")


def test_date_parsing():
    """Module 1: Date parsing produces valid Period column."""
    df = generate_synthetic_pprs(months=12)
    df = parse_production_dates(df)
    assert "report_month" in df.columns
    assert "days_in_month" in df.columns
    # Days in month should be between 28 and 31
    assert df["days_in_month"].min() >= 28
    assert df["days_in_month"].max() <= 31
    print("  ✓ test_date_parsing passed")


def test_shut_in_flagging():
    """Module 1: Shut-in flag is correctly set on zero-production months."""
    df = generate_synthetic_pprs(months=84)
    df = parse_production_dates(df)
    df = flag_shut_in_months(df)

    # Rows where both oil and gas are 0 (or NaN treated as 0) should be flagged
    zero_mask = (df["oil_production"].fillna(0) == 0) & (df["gas_production"].fillna(0) == 0)
    pd.testing.assert_series_equal(df["is_shut_in"], zero_mask, check_names=False)
    print("  ✓ test_shut_in_flagging passed")


def test_boe_conversion():
    """Module 1: BOE conversion uses correct factors and handles NaN."""
    df = generate_synthetic_pprs(months=24)
    df = parse_production_dates(df)
    df = flag_shut_in_months(df)
    df = convert_to_boe(df)

    # Check columns exist
    for col in ["oil_boe", "gas_boe", "total_boe"]:
        assert col in df.columns, f"Missing column: {col}"

    # Spot-check a non-null, non-shut-in row
    producing = df[(df["oil_production"] > 0) & df["gas_production"].notna()]
    if len(producing) > 0:
        row = producing.iloc[0]
        expected_oil_boe = row["oil_production"] * OIL_TONNES_TO_BARRELS
        expected_gas_boe = row["gas_production"] * row["days_in_month"] * GAS_MMSCF_TO_BOE
        assert abs(row["oil_boe"] - expected_oil_boe) < 0.01, "Oil BOE mismatch"
        assert abs(row["gas_boe"] - expected_gas_boe) < 0.01, "Gas BOE mismatch"
        assert abs(row["total_boe"] - (expected_oil_boe + expected_gas_boe)) < 0.01

    print("  ✓ test_boe_conversion passed")


def test_decline_curve_fitting():
    """Module 2: Curve fit returns plausible qi and di values."""
    df = generate_synthetic_pprs(months=84)
    df = parse_production_dates(df)
    df = flag_shut_in_months(df)
    df = convert_to_boe(df)

    time_index = np.arange(len(df))
    qi, di, pcov = fit_decline_curve(df["total_boe"], time_index)

    # qi should be in a sensible range (synthetic data starts ~12k tonnes oil)
    assert qi > 0, "qi must be positive"
    assert di > 0, "di must be positive"
    assert di < 0.5, "di > 0.5/month is physically implausible for North Sea"
    # Covariance matrix should be 2x2
    assert pcov.shape == (2, 2), "Covariance matrix shape incorrect"

    print(f"  ✓ test_decline_curve_fitting passed  (qi={qi:,.0f}, di={di:.4f})")


def test_arps_model_at_t0():
    """Module 2: Arps' model at t=0 returns qi exactly."""
    qi, di = 50000.0, 0.035
    result = arps_exponential(np.array([0]), qi, di)
    assert abs(result[0] - qi) < 1e-10, "q(0) should equal qi"
    print("  ✓ test_arps_model_at_t0 passed")


def test_reconciliation_table_structure():
    """Module 2: Reconciliation table has all required columns."""
    df = generate_synthetic_pprs(months=48)
    df = parse_production_dates(df)
    df = flag_shut_in_months(df)
    df = convert_to_boe(df)

    time_index = np.arange(len(df))
    qi, di, _ = fit_decline_curve(df["total_boe"], time_index)
    recon = build_reconciliation_table(df, qi, di)

    required_cols = [
        "report_month", "actual_boe", "forecast_boe",
        "variance_boe", "variance_pct", "is_shut_in",
    ]
    for col in required_cols:
        assert col in recon.columns, f"Missing column in reconciliation: {col}"

    # Variance = actual - forecast
    computed_var = recon["actual_boe"] - recon["forecast_boe"]
    pd.testing.assert_series_equal(
        recon["variance_boe"], computed_var, check_names=False, atol=0.01
    )

    print("  ✓ test_reconciliation_table_structure passed")


def test_fiscal_impact_calculation():
    """Module 3: Fiscal impact correctly zeros shut-in months."""
    df = generate_synthetic_pprs(months=48)
    df = parse_production_dates(df)
    df = flag_shut_in_months(df)
    df = convert_to_boe(df)

    time_index = np.arange(len(df))
    qi, di, _ = fit_decline_curve(df["total_boe"], time_index)
    recon = build_reconciliation_table(df, qi, di)

    price = 72.50
    fiscal = calculate_fiscal_impact(recon, price_per_barrel=price)

    # Shut-in months must have zero revenue exposure
    shut_in_exposure = fiscal.loc[fiscal["is_shut_in"], "revenue_exposure_gbp"]
    assert (shut_in_exposure == 0.0).all(), "Shut-in months should have zero exposure"

    # Producing months: exposure = variance × price
    producing = fiscal[~fiscal["is_shut_in"]]
    expected_exposure = producing["variance_boe"] * price
    pd.testing.assert_series_equal(
        producing["revenue_exposure_gbp"], expected_exposure,
        check_names=False, atol=0.01
    )

    print("  ✓ test_fiscal_impact_calculation passed")


def test_governance_flags():
    """Module 3: Governance audit flags months exceeding threshold."""
    df = generate_synthetic_pprs(months=84)
    df = parse_production_dates(df)
    df = flag_shut_in_months(df)
    df = convert_to_boe(df)

    time_index = np.arange(len(df))
    qi, di, _ = fit_decline_curve(df["total_boe"], time_index)
    recon = build_reconciliation_table(df, qi, di)
    fiscal = calculate_fiscal_impact(recon)

    flags = run_governance_audit(fiscal, threshold_pct=15.0)

    # Each flag should have a valid severity
    valid_severities = {"LOW", "MEDIUM", "HIGH"}
    for f in flags:
        assert f.severity in valid_severities, f"Invalid severity: {f.severity}"
        assert abs(f.variance_pct) > 15.0, "Flag raised below threshold"

    print(f"  ✓ test_governance_flags passed  ({len(flags)} flags raised)")


def test_sensitivity_sweep():
    """Module 3: Sensitivity sweep produces results for all price points."""
    df = generate_synthetic_pprs(months=48)
    df = parse_production_dates(df)
    df = flag_shut_in_months(df)
    df = convert_to_boe(df)

    time_index = np.arange(len(df))
    qi, di, _ = fit_decline_curve(df["total_boe"], time_index)
    recon = build_reconciliation_table(df, qi, di)

    prices = [50.0, 60.0, 70.0, 80.0, 90.0]
    sweep = sensitivity_sweep(recon, price_scenarios=prices)

    assert len(sweep) == len(prices), "One row expected per price scenario"
    assert list(sweep["price_per_barrel_gbp"]) == prices

    # Higher price should produce larger absolute exposure
    abs_exposures = sweep["total_revenue_at_risk_gbp"].abs()
    # With a consistent variance sign, exposure magnitude should scale with price
    assert abs_exposures.iloc[-1] > abs_exposures.iloc[0], \
        "Higher price should yield larger absolute exposure"

    print("  ✓ test_sensitivity_sweep passed")


def test_fiscal_summary_object():
    """Module 3: FiscalSummary object is fully populated."""
    df = generate_synthetic_pprs(months=48)
    df = parse_production_dates(df)
    df = flag_shut_in_months(df)
    df = convert_to_boe(df)

    time_index = np.arange(len(df))
    qi, di, _ = fit_decline_curve(df["total_boe"], time_index)
    recon = build_reconciliation_table(df, qi, di)
    fiscal = calculate_fiscal_impact(recon)
    flags = run_governance_audit(fiscal)
    summary = generate_fiscal_summary(fiscal, flags)

    assert summary.months_analysed == 48
    assert summary.months_shut_in + summary.producing_months == 48
    assert summary.price_per_barrel_gbp == 72.50
    assert summary.analysis_date is not None

    print("  ✓ test_fiscal_summary_object passed")


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  NSTA PPRS FISCAL LEAKAGE — PIPELINE VALIDATION")
    print("=" * 60 + "\n")

    print("📦 Module 1: Data Engineering")
    test_synthetic_data_generation()
    test_date_parsing()
    test_shut_in_flagging()
    test_boe_conversion()

    print("\n📐 Module 2: Analytical Engine")
    test_decline_curve_fitting()
    test_arps_model_at_t0()
    test_reconciliation_table_structure()

    print("\n💷 Module 3: Business Logic")
    test_fiscal_impact_calculation()
    test_governance_flags()
    test_sensitivity_sweep()
    test_fiscal_summary_object()

    print("\n" + "=" * 60)
    print("  ✅ ALL 11 TESTS PASSED")
    print("=" * 60 + "\n")
