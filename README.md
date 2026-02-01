
UKCS-Pulse: Fiscal Assurance & Production Reconciliation
A Full-Stack Data Engine for North Sea Asset Performance Tracking

🎯 The Business Challenge

In the UK Continental Shelf (UKCS), a 0.5% metering inaccuracy can result in millions of pounds in fiscal exposure or misallocated tax obligations. Drawing from my experience in hydrocarbon reconciliation (Cakasa) and predictive analytics (Crystal Palace FC), I developed this tool to bridge the gap between raw NSTA (North Sea Transition Authority) production data and executive decision-making.

🛠️ The Tech Stack

Data Source: NSTA PPRS (Petroleum Production Reporting System) Open Data.

Infrastructure: Google BigQuery (Data Warehousing) & Python.

ML Engine: Arps’ Decline Curve Analysis (DCA) and Prophet for time-series forecasting.

Interface: Streamlit (Full-Stack Web App) with Plotly interactivity.

Governance: Data quality validation layer for sensor drift and outlier detection.

📈 Key Features & Logic

1. Predictive Asset Modeling
The engine applies Non-Linear Least Squares to historical production data to establish a "Technical Baseline."

2. Fiscal Gap Analysis (The "So What?")
The tool identifies the Variance between actual reported hydrocarbons and the predicted decline.

Logic: If Actual < Forecast, the system flags a "Revenue Leakage" event.

Impact: Quantifies the variance in GBP (£) based on real-time Brent Crude spot prices.

3. Data Governance & Integrity
Built-in checks to ensure "Audit Readiness":

Identification of "Shut-in" periods (zero production).

Detection of reporting anomalies (e.g., sudden pressure spikes without flow increases).

🚀 Business Impact (The "C-Suite" Summary)

Operational Transparency: Provides an instant health check on mature North Sea assets (e.g., Brent, Forties, Schiehallion).

Risk Mitigation: Flags potential metering errors before statutory audits, mirroring the 18–22% revenue safeguard I managed in previous roles.

Investment Intelligence: Identifies underperforming fields that may be candidates for Enhanced Oil Recovery (EOR) or decommissioning.
