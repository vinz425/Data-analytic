
🛢️ UKCS-Pulse: Production Assurance & Fiscal Reconciliation
Predictive Analytics for North Sea Hydrocarbon Governance

📌 Project Overview
In the energy sector, "Fiscal Tilt" or metering inaccuracies can lead to multimillion-pound revenue exposures. 
This project simulates a Production Assurance Engine for the UK Continental Shelf (UKCS).
Leveraging historical NSTA PPRS data, the application identifies "Revenue Leakage" by comparing actual field performance against technical Arps’ Decline Curve forecasts. 
It translates technical variance into commercial impact, providing a C-suite-ready view of asset health.

🚀 Key Features1. Automated ETL & Hydrocarbon NormalizationData Ingestion: 

Automated cleaning of NSTA monthly production reports.
Unit Standardization: Normalization of Oil (Tonnes) and Gas (kscm) into Barrels of Oil Equivalent (BOE) for standardized portfolio analysis.
Shut-in Detection: Identification of unplanned downtime and maintenance windows to prevent skewing the decline model.
2. Predictive Performance ModelingDecline Curve Analysis (DCA): Implementation of Exponential and Hyperbolic decline models using scipy.optimize.
Variance Logic: Calculation of the "Technical Gap"—the difference between a field's potential (forecast) and its actual delivery.
3. Fiscal Impact EngineMonetization: Real-time conversion of production gaps into GBP (£) using dynamic Brent Crude and NBP Gas price inputs.
Audit Readiness: Generation of "Variance Logs" to flag fields where production deviates by $>15\%$, signaling a need for meter re-validation or technical audit.

🛠️ Tech StackBackend: Python (Pandas, NumPy, Scipy)
Data Warehouse: Google BigQuery (SQL)Visualisation: Plotly & Streamlit
Business Intelligence: Tableau (Executive Dashboard)

📊 Exploratory Data Analysis (EDA) HighlightsDuring the analysis of major UKCS fields (e.g., Forties, Brent), several key insights were uncovered:
Decline Correlation: High correlation between ambient sea temperature fluctuations and gas-lift efficiency in specific blocks.
Economic Sensitivity: Identified "High-Risk" assets where a 10% drop in Brent prices renders the field economically unviable based on current lifting costs and decline rates.

💼 Business Value (The "Why")This tool replicates the fiscal safeguards I implemented during my tenure at Cakasa, where I managed over $50M in revenue exposure. It proves that:I can translate Big Data into Actionable Revenue Insights.
I understand the UK Regulatory Landscape (NSTA compliance).I bridge the gap between Operations (Field Data) and Finance (Market Intelligence).


