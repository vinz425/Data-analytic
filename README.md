# NSTA PPRS — Production Forecast vs. Actual Reconciliation

**Fiscal Leakage Detection Dashboard for UK North Sea Hydrocarbon Fields**

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        dashboard.py                             │
│  Streamlit UI: Metric Cards · Plotly Charts · Governance Log    │
└───────────────────────┬─────────────────────────────────────────┘
                        │ orchestrates
        ┌───────────────┼───────────────────┐
        ▼               ▼                   ▼
┌──────────────┐ ┌─────────────────┐ ┌──────────────────┐
│ data_        │ │ analytical_     │ │ business_        │
│ engineering  │→│ engine          │→│ logic            │
│              │ │                 │ │                  │
│ • CSV ingest │ │ • Arps' fit     │ │ • Fiscal £ calc  │
│ • Shut-in    │ │ • Forecast gen  │ │ • Gov audit log  │
│   detection  │ │ • Recon table   │ │ • Sensitivity    │
│ • BOE convert│ │                 │ │   sweep          │
└──────────────┘ └─────────────────┘ └──────────────────┘
        ▲
        │ raw CSV
┌──────────────┐
│ NSTA Open    │
│ Data (PPRS)  │
└──────────────┘
```

## Modules

| # | File | Responsibility |
|---|------|----------------|
| 1 | `data_engineering.py` | Ingest raw PPRS CSV, detect shut-in months, convert oil (tonnes) and gas (MMscfd) to BOE |
| 2 | `analytical_engine.py` | Fit Arps' Exponential decline curve via `scipy.optimize.curve_fit`, generate forecast, build reconciliation table |
| 3 | `business_logic.py` | Multiply BOE variance by dynamic `price_per_barrel` to produce GBP revenue exposure; flag >15% variance months; produce executive summary |
| 4 | `dashboard.py` | Streamlit app rendering metric cards, dual-axis Plotly chart, governance log, and price sensitivity panel |

## Setup

```bash
pip install pandas numpy scipy plotly streamlit
```

## Run

```bash
# Launch the dashboard
streamlit run dashboard.py

# Run the test suite
python test_pipeline.py
```

## Connecting to Real NSTA Data

1. Visit the [NSTA Open Data portal](https://www.nstauthority.co.uk/data-centre/nsta-open-data/production/)
2. Select **"NSTA Field Production Points, PPRS (WGS84)"** (the Points version downloads faster)
3. Filter by your target `reportingUnitName` (e.g. `HUNTINGTON`)
4. Export as **CSV**
5. In `dashboard.py`, change the `load_data()` call:

```python
# Replace:
cleaned_df = load_data(field_name=selected_field, use_synthetic=True)

# With:
cleaned_df = load_data(
    field_name="HUNTINGTON",
    use_synthetic=False,
    filepath="path/to/your/pprs_export.csv"
)
```

## Key Design Decisions

**Why exclude shut-in months from curve fitting?** A shut-in is an operational event (maintenance, safety), not a reservoir signal. Including zeroes would steepen the fitted decline rate and produce a systematically pessimistic forecast — masking real under-performance in producing months.

**Why zero fiscal exposure on shut-in months?** The variance during a shut-in is an artefact: comparing zero production to a model that assumes continuous operation. Attributing revenue exposure to planned shutdowns would inflate the "at risk" number and erode board confidence in the metric.

**Why Arps' Exponential (not Hyperbolic or Harmonic)?** Exponential decline assumes a constant fractional decline rate — appropriate for solution-gas-drive reservoirs and many North Sea chalk fields in mid-life. For fields showing hyperbolic behaviour, the `arps_exponential` function can be swapped for `qi * (1 + b*di*t)**(-1/b)` with minimal pipeline changes.

## Conversion Factors

| Stream | Raw Unit | Factor | Output |
|--------|----------|--------|--------|
| Oil | Tonnes/month | × 7.33 | Barrels |
| Gas | MMscfd | × days_in_month × 175.8 | BOE |
