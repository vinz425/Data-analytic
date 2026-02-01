"""
==============================================================================
MODULE 4: STREAMLIT DASHBOARD — "Production Forecast vs. Actual"
==============================================================================
Purpose : C-suite ready interactive dashboard that surfaces the fiscal
          leakage analysis built by Modules 1–3.

Layout  :
  ┌──────────────────────────────────────────────────────────────────────┐
  │  HEADER — Field name, analysis period, last-updated timestamp        │
  ├──────────┬──────────┬──────────┬────────────────────────────────────┤
  │ Metric 1 │ Metric 2 │ Metric 3 │ Metric 4                           │  ← KPI Cards
  │ Revenue  │ Total    │ Producing│ Governance                         │
  │ at Risk  │ Variance │ Months   │ Flags                              │
  ├──────────┴──────────┴──────────┴────────────────────────────────────┤
  │                                                                      │
  │  PLOTLY CHART — Decline Curve vs. Actual Production                  │
  │  (dual-axis: BOE left, Revenue Exposure £ right)                     │
  │                                                                      │
  ├──────────────────────────────────────────────────────────────────────┤
  │  SIDEBAR CONTROLS — Price slider, field selector, date range         │
  ├──────────────────────────────────────────────────────────────────────┤
  │  GOVERNANCE LOG — Flagged months table with severity badges          │
  ├──────────────────────────────────────────────────────────────────────┤
  │  SENSITIVITY PANEL — Bar chart of Revenue at Risk across prices      │
  └──────────────────────────────────────────────────────────────────────┘

Design : Dark-theme, petroleum-industry colour palette (deep navy, amber
         accent for alerts, green for positive performance). Plotly
         templates set to 'plotly_dark' for consistency.
==============================================================================

DEPENDENCIES:
    pip install streamlit pandas plotly scipy numpy

RUN:
    streamlit run dashboard.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- Internal module imports ---
from data_engineering import clean_pprs_data, generate_synthetic_pprs, parse_production_dates, flag_shut_in_months, convert_to_boe
from analytical_engine import fit_decline_curve, build_reconciliation_table, arps_exponential
from business_logic import (
    calculate_fiscal_impact,
    run_governance_audit,
    generate_fiscal_summary,
    sensitivity_sweep,
    DEFAULT_PRICE_PER_BARREL_GBP,
    GOVERNANCE_VARIANCE_THRESHOLD_PCT,
)


# ===========================================================================
# STREAMLIT PAGE CONFIG & STYLING
# ===========================================================================
st.set_page_config(
    page_title="NSTA PPRS — Fiscal Leakage Dashboard",
    page_icon="⛽",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Custom CSS for C-suite polish ---
# Business Logic: The visual language must signal "regulated, auditable,
# trustworthy" — not "startup demo". Navy + amber is the standard palette
# for energy sector executive dashboards.
CUSTOM_CSS = """
<style>
    /* Global dark theme */
    .reportview-container, .main, [data-testid="stAppViewContainer"] {
        background-color: #0a1628;
        color: #e2e8f0;
    }
    .sidebar .sidebar-content, [data-testid="stSidebar"] {
        background-color: #0f1e3d;
        color: #cbd5e1;
    }

    /* Metric cards */
    .metric-card {
        background: linear-gradient(135deg, #132945 0%, #1a3a6b 100%);
        border: 1px solid #2a4a7f;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        box-shadow: 0 4px 24px rgba(0,0,0,0.3);
    }
    .metric-card .label {
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: #64748b;
        margin-bottom: 8px;
    }
    .metric-card .value {
        font-size: 1.75rem;
        font-weight: 700;
        color: #f1f5f9;
    }
    .metric-card .value.negative { color: #f59e0b; }  /* Amber = at risk */
    .metric-card .value.positive { color: #34d399; }  /* Green = healthy */
    .metric-card .delta {
        font-size: 0.7rem;
        color: #64748b;
        margin-top: 4px;
    }

    /* Governance log table */
    .gov-table { width: 100%; border-collapse: collapse; margin-top: 12px; }
    .gov-table th {
        background: #1a3a6b;
        color: #94a3b8;
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        padding: 10px 12px;
        text-align: left;
        border-bottom: 1px solid #2a4a7f;
    }
    .gov-table td {
        padding: 10px 12px;
        border-bottom: 1px solid #1e3354;
        font-size: 0.82rem;
        color: #cbd5e1;
    }
    .gov-table tr:nth-child(even) td { background: #112240; }

    /* Severity badges */
    .badge { display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 0.7rem; font-weight: 600; }
    .badge-HIGH   { background: #7f1d1d; color: #fca5a5; }
    .badge-MEDIUM { background: #78350f; color: #fcd34d; }
    .badge-LOW    { background: #1e3a5f; color: #60a5fa; }

    /* Section headers */
    .section-header {
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        color: #64748b;
        border-bottom: 1px solid #2a4a7f;
        padding-bottom: 6px;
        margin: 24px 0 16px 0;
    }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ===========================================================================
# DATA LOADING (cached for performance)
# ===========================================================================
@st.cache_data(show_spinner="Loading production data...")
def load_data(field_name: str, use_synthetic: bool = True, filepath: str = None):
    """
    Orchestrates the full data pipeline.

    In production, set use_synthetic=False and provide a filepath to your
    NSTA PPRS CSV export. For demo purposes, synthetic data is generated.
    """
    if use_synthetic:
        raw = generate_synthetic_pprs(field_name=field_name, months=84)
        # Run the cleaning steps manually since we already have a DataFrame
        df = parse_production_dates(raw)
        df = flag_shut_in_months(df)
        df = convert_to_boe(df)
        df = df.sort_values("report_month").reset_index(drop=True)
    else:
        df = clean_pprs_data(filepath, field_name=field_name)

    return df


# ===========================================================================
# SIDEBAR — User Controls
# ===========================================================================
def render_sidebar():
    """Render the sidebar control panel. Returns user selections."""
    st.sidebar.markdown("### ⛽ Configuration", unsafe_allow_html=False)
    st.sidebar.markdown("---")

    # Field selector (in production, this would be a dynamic dropdown
    # populated from the PPRS dataset's unique reportingUnitName values)
    field_options = ["BRAE ALPHA", "FORTIES FIELD", "HUNTINGTON", "ANDREW FIELD"]
    selected_field = st.sidebar.selectbox("Reporting Unit", field_options)

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 💷 Fiscal Parameters")

    # Dynamic price slider — the key "what-if" lever for C-suite users
    # Business Logic: Allowing the price to be adjusted live means the
    # "Revenue at Risk" metric card updates instantly. This is the single
    # most-requested feature in operator fiscal dashboards.
    price_per_barrel = st.sidebar.slider(
        "Price per Barrel (£/bbl)",
        min_value=40.0,
        max_value=120.0,
        value=DEFAULT_PRICE_PER_BARREL_GBP,
        step=2.5,
        help="Brent equivalent settlement price. Adjust for scenario analysis.",
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔍 Governance Settings")

    variance_threshold = st.sidebar.slider(
        "Variance Flag Threshold (%)",
        min_value=5.0,
        max_value=30.0,
        value=GOVERNANCE_VARIANCE_THRESHOLD_PCT,
        step=1.0,
        help="Months exceeding this |variance| will be flagged for review.",
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "📌 Data Source: NSTA Open Data PPRS\n"
        "📅 Refresh: Monthly (PON 7 cycle)\n"
        "⚖️ Units: BOE (7.33 bbl/tonne oil; 175.8 BOE/MMscf gas)",
        unsafe_allow_html=False,
    )

    return selected_field, price_per_barrel, variance_threshold


# ===========================================================================
# METRIC CARDS
# ===========================================================================
def render_metric_cards(summary):
    """
    Render the four top-line KPI cards.

    Business Logic: These four numbers are chosen because they map directly
    to the questions a CFO or Head of Investor Relations will ask in the
    first 10 seconds of reviewing an energy production report:
      1. "How much money are we exposed to?" → Revenue at Risk
      2. "Is this a big or small problem?" → Total Variance (BOE)
      3. "How long has the field been running?" → Producing Months
      4. "Do we have any red flags?" → Governance Flags count
    """
    col1, col2, col3, col4 = st.columns(4)

    # --- Card 1: Total Revenue at Risk ---
    risk_value = summary.total_revenue_at_risk_gbp
    risk_class = "negative" if risk_value < 0 else "positive"
    risk_display = f"£{abs(risk_value):,.0f}"
    if abs(risk_value) >= 1_000_000:
        risk_display = f"£{abs(risk_value)/1_000_000:.2f}M"

    col1.markdown(f"""
        <div class="metric-card">
            <div class="label">💰 Total Revenue at Risk</div>
            <div class="value {risk_class}">{risk_display}</div>
            <div class="delta">{'Under-recovery' if risk_value < 0 else 'Over-recovery'} vs. forecast</div>
        </div>
    """, unsafe_allow_html=True)

    # --- Card 2: Total Variance (BOE) ---
    var_class = "negative" if summary.total_variance_boe < 0 else "positive"
    col2.markdown(f"""
        <div class="metric-card">
            <div class="label">📊 Total Variance</div>
            <div class="value {var_class}">{summary.total_variance_boe:+,.0f} BOE</div>
            <div class="delta">Cumulative deviation (excl. shut-ins)</div>
        </div>
    """, unsafe_allow_html=True)

    # --- Card 3: Producing Months ---
    col3.markdown(f"""
        <div class="metric-card">
            <div class="label">📅 Producing Months</div>
            <div class="value">{summary.producing_months}</div>
            <div class="delta">of {summary.months_analysed} total ({summary.months_shut_in} shut-in)</div>
        </div>
    """, unsafe_allow_html=True)

    # --- Card 4: Governance Flags ---
    flag_count = len(summary.governance_flags)
    high_count = sum(1 for f in summary.governance_flags if f.severity == "HIGH")
    flag_class = "negative" if high_count > 0 else ("positive" if flag_count == 0 else "")
    col4.markdown(f"""
        <div class="metric-card">
            <div class="label">🚩 Governance Flags</div>
            <div class="value {flag_class}">{flag_count}</div>
            <div class="delta">{high_count} HIGH severity</div>
        </div>
    """, unsafe_allow_html=True)


# ===========================================================================
# MAIN PLOTLY CHART — Decline Curve vs. Actual
# ===========================================================================
def render_main_chart(fiscal_df: pd.DataFrame, qi: float, di: float):
    """
    Interactive dual-axis Plotly chart:
      • Left Y-axis  : Production (BOE/month) — forecast curve + actual points
      • Right Y-axis : Cumulative Revenue Exposure (£)
      • Colour coding : Shut-in months are grey; flagged months are amber.

    Business Logic: The chart tells the story in one glance. The smooth
    decline curve represents "what the reservoir should do." The actual
    scatter points represent "what it actually did." The gap between them,
    shaded in amber, is the fiscal leakage signal. The cumulative £ line
    on the right axis converts that physical gap into money.
    """
    # Prepare month labels as strings for the x-axis
    x_labels = [str(m) for m in fiscal_df["report_month"]]

    fig = make_subplots(
        rows=1, cols=1,
        specs=[[{"secondary_y": True}]],
        subplot_titles=("",),
    )

    # --- Forecast curve (smooth line) ---
    fig.add_trace(
        go.Scatter(
            x=x_labels,
            y=fiscal_df["forecast_boe"],
            mode="lines",
            name="Arps' Decline Forecast",
            line=dict(color="#60a5fa", width=2.5, dash="dash"),
            legendgroup="forecast",
        ),
        secondary_y=False,
    )

    # --- Actual production (colour-coded points) ---
    # Split into producing, shut-in, and flagged for distinct styling
    producing_mask = (~fiscal_df["is_shut_in"]) & (fiscal_df["variance_pct"].abs() <= 15)
    flagged_mask = (~fiscal_df["is_shut_in"]) & (fiscal_df["variance_pct"].abs() > 15)
    shut_in_mask = fiscal_df["is_shut_in"]

    # Normal producing months — green dots
    fig.add_trace(
        go.Scatter(
            x=[x_labels[i] for i in range(len(fiscal_df)) if producing_mask.iloc[i]],
            y=fiscal_df.loc[producing_mask, "actual_boe"],
            mode="markers",
            name="Actual (Normal)",
            marker=dict(color="#34d399", size=8, line=dict(color="#0a1628", width=1.5)),
            legendgroup="actual_normal",
        ),
        secondary_y=False,
    )

    # Flagged months — amber diamonds
    fig.add_trace(
        go.Scatter(
            x=[x_labels[i] for i in range(len(fiscal_df)) if flagged_mask.iloc[i]],
            y=fiscal_df.loc[flagged_mask, "actual_boe"],
            mode="markers",
            name="Actual (Flagged >15%)",
            marker=dict(color="#f59e0b", size=12, symbol="diamond",
                        line=dict(color="#0a1628", width=1.5)),
            legendgroup="actual_flagged",
        ),
        secondary_y=False,
    )

    # Shut-in months — grey circles
    fig.add_trace(
        go.Scatter(
            x=[x_labels[i] for i in range(len(fiscal_df)) if shut_in_mask.iloc[i]],
            y=fiscal_df.loc[shut_in_mask, "actual_boe"],
            mode="markers",
            name="Shut-in",
            marker=dict(color="#475569", size=9, symbol="circle-open",
                        line=dict(color="#64748b", width=2)),
            legendgroup="shut_in",
        ),
        secondary_y=False,
    )

    # --- Shaded variance area (the "leakage" visual) ---
    fig.add_trace(
        go.Scatter(
            x=x_labels,
            y=fiscal_df["actual_boe"],
            mode="lines",
            line=dict(color="rgba(245,158,11,0)", width=0),
            showlegend=False,
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=x_labels,
            y=fiscal_df["forecast_boe"],
            mode="lines",
            line=dict(color="rgba(245,158,11,0)", width=0),
            fill="tonexty",
            fillcolor="rgba(245,158,11,0.12)",
            showlegend=False,
            name="Variance Zone",
        ),
        secondary_y=False,
    )

    # --- Cumulative Revenue Exposure (right axis) ---
    fig.add_trace(
        go.Scatter(
            x=x_labels,
            y=fiscal_df["cumulative_exposure_gbp"],
            mode="lines",
            name="Cumulative Exposure (£)",
            line=dict(color="#a78bfa", width=2),
            legendgroup="exposure",
        ),
        secondary_y=True,
    )

    # --- Layout & Styling ---
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0a1628",
        plot_bgcolor="#0f1e3d",
        font=dict(family="'Segoe UI', sans-serif", size=11, color="#94a3b8"),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.18,
            xanchor="center",
            x=0.5,
            bgcolor="rgba(15,30,61,0.8)",
            bordercolor="#2a4a7f",
            borderwidth=1,
        ),
        margin=dict(l=60, r=60, t=20, b=80),
        height=480,
        hovermode="x unified",
        xaxis=dict(
            title_text="Month",
            tickangle=-45,
            showgrid=True,
            gridcolor="#1e3354",
            title_font_color="#64748b",
        ),
    )

    fig.update_yaxes(
        title_text="Production (BOE / month)",
        secondary_y=False,
        showgrid=True,
        gridcolor="#1e3354",
        title_font_color="#60a5fa",
        zeroline=False,
    )
    fig.update_yaxes(
        title_text="Cumulative Exposure (£)",
        secondary_y=True,
        showgrid=False,
        title_font_color="#a78bfa",
        zeroline=False,
        tickprefix="£",
        tickformat=",.0f",
    )

    st.plotly_chart(fig, use_container_width=True)


# ===========================================================================
# GOVERNANCE LOG TABLE
# ===========================================================================
def render_governance_log(flags):
    """
    Render the auditable governance log as an HTML table with severity badges.

    Business Logic: This log is the "paper trail." In a real deployment,
    each row would link to the underlying PPRS return and the fiscal meter
    calibration record. The severity badges use the same colour conventions
    as NSTA's own compliance dashboards (red/amber/blue).
    """
    st.markdown('<div class="section-header">📋 Data Governance Log</div>', unsafe_allow_html=True)

    if not flags:
        st.markdown(
            '<p style="color:#34d399; font-size:0.85rem;">✓ No governance flags raised. '
            'All producing months within variance threshold.</p>',
            unsafe_allow_html=True,
        )
        return

    # Build HTML table
    rows_html = ""
    for f in flags:
        badge_class = f"badge badge-{f.severity}"
        exposure_str = f"£{abs(f.revenue_exposure_gbp):,.0f}"
        rows_html += f"""
        <tr>
            <td>{f.flag_id}</td>
            <td>{f.report_month}</td>
            <td>{f.actual_boe:,.0f}</td>
            <td>{f.forecast_boe:,.0f}</td>
            <td>{f.variance_pct:+.1f}%</td>
            <td>{exposure_str}</td>
            <td><span class="{badge_class}">{f.severity}</span></td>
            <td style="font-size:0.75rem; color:#94a3b8;">{f.flag_reason}</td>
        </tr>
        """

    table_html = f"""
    <table class="gov-table">
        <thead>
            <tr>
                <th>#</th>
                <th>Month</th>
                <th>Actual BOE</th>
                <th>Forecast BOE</th>
                <th>Variance</th>
                <th>Exposure</th>
                <th>Severity</th>
                <th>Assessment</th>
            </tr>
        </thead>
        <tbody>{rows_html}</tbody>
    </table>
    """
    st.markdown(table_html, unsafe_allow_html=True)


# ===========================================================================
# SENSITIVITY PANEL
# ===========================================================================
def render_sensitivity_panel(reconciliation_df: pd.DataFrame):
    """
    Bar chart showing how Total Revenue at Risk changes across price scenarios.
    """
    st.markdown('<div class="section-header">📈 Price Sensitivity Analysis</div>', unsafe_allow_html=True)

    sweep_df = sensitivity_sweep(reconciliation_df)

    fig = go.Figure(
        data=[
            go.Bar(
                x=[f"£{p:.0f}/bbl" for p in sweep_df["price_per_barrel_gbp"]],
                y=sweep_df["total_revenue_at_risk_gbp"],
                marker_color=[
                    "#34d399" if v >= 0 else "#f59e0b"
                    for v in sweep_df["total_revenue_at_risk_gbp"]
                ],
                text=[
                    f"£{abs(v)/1e6:.2f}M" if abs(v) >= 1e6 else f"£{abs(v):,.0f}"
                    for v in sweep_df["total_revenue_at_risk_gbp"]
                ],
                textposition="outside",
                textfont=dict(color="#e2e8f0", size=11),
            )
        ]
    )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0a1628",
        plot_bgcolor="#0f1e3d",
        font=dict(size=11, color="#94a3b8"),
        height=280,
        margin=dict(l=50, r=30, t=10, b=40),
        yaxis=dict(
            title_text="Revenue at Risk (£)",
            showgrid=True,
            gridcolor="#1e3354",
            tickprefix="£",
            tickformat=",.0f",
            zeroline=True,
            zerolinecolor="#2a4a7f",
        ),
        xaxis=dict(title_text="Brent Price Scenario"),
        showlegend=False,
    )

    st.plotly_chart(fig, use_container_width=True)


# ===========================================================================
# MAIN APP ORCHESTRATION
# ===========================================================================
def main():
    """
    Master render function — ties together sidebar, pipeline, and all
    dashboard panels in the correct sequence.
    """
    # --- Header ---
    st.markdown("""
        <div style="display:flex; justify-content:space-between; align-items:center;
                    padding: 12px 0; border-bottom: 1px solid #2a4a7f; margin-bottom: 20px;">
            <div>
                <h1 style="margin:0; font-size:1.4rem; color:#f1f5f9; font-weight:600;">
                    ⛽ Production Forecast Reconciliation
                </h1>
                <p style="margin:4px 0 0; font-size:0.75rem; color:#64748b;">
                    NSTA PPRS Fiscal Leakage Analysis — UK Continental Shelf
                </p>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # --- Sidebar controls ---
    selected_field, price_per_barrel, variance_threshold = render_sidebar()

    # --- Run the data pipeline ---
    cleaned_df = load_data(field_name=selected_field, use_synthetic=True)

    # --- Fit the decline curve ---
    time_index = np.arange(len(cleaned_df))
    qi, di, _ = fit_decline_curve(cleaned_df["total_boe"], time_index)

    # --- Build reconciliation and fiscal tables ---
    recon_df = build_reconciliation_table(cleaned_df, qi, di)
    fiscal_df = calculate_fiscal_impact(recon_df, price_per_barrel=price_per_barrel)
    gov_flags = run_governance_audit(fiscal_df, threshold_pct=variance_threshold)
    summary = generate_fiscal_summary(fiscal_df, gov_flags, price_per_barrel)

    # --- Model parameters badge (transparency for analysts) ---
    st.markdown(
        f'<div style="font-size:0.72rem; color:#64748b; margin-bottom:16px;">'
        f'  Fitted Model: qi = {qi:,.0f} BOE/mo &nbsp;|&nbsp; '
        f'di = {di:.4f}/mo ({di*12*100:.1f}% annual) &nbsp;|&nbsp; '
        f'Field: {selected_field} &nbsp;|&nbsp; Price: £{price_per_barrel:.2f}/bbl'
        f'</div>',
        unsafe_allow_html=True,
    )

    # --- Render panels ---
    render_metric_cards(summary)

    st.markdown('<div class="section-header">📉 Decline Curve vs. Actual Production</div>', unsafe_allow_html=True)
    render_main_chart(fiscal_df, qi, di)

    render_governance_log(gov_flags)
    render_sensitivity_panel(recon_df)


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()
