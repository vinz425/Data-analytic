import React, { useState, useEffect, useMemo } from 'react';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Area, AreaChart, ComposedChart } from 'recharts';
import { TrendingDown, AlertTriangle, DollarSign, Calendar, Activity, Target } from 'lucide-react';

/**
 * NSTA PPRS FISCAL LEAKAGE DASHBOARD
 * 
 * A production-grade React dashboard for UK North Sea production reconciliation.
 * Aesthetic Direction: "Industrial Precision" — inspired by oil rig control rooms,
 * naval bridge instrumentation, and 1960s petroleum engineering technical manuals.
 * 
 * Design Principles:
 * - Monospaced data displays (evokes metering readouts)
 * - Muted petroleum palette: deep slate, crude oil amber, North Sea grey
 * - Utilitarian grid with asymmetric emphasis panels
 * - Stencil-style typography for headers (industrial markings)
 * - Subtle scan-line texture overlay (control room CRT aesthetic)
 */

// ============================================================================
// DATA ENGINEERING & ANALYTICAL ENGINE
// ============================================================================

const CONSTANTS = {
  OIL_TONNES_TO_BARRELS: 7.33,
  GAS_MMSCF_TO_BOE: 175.8,
  DEFAULT_PRICE_PER_BARREL: 72.50,
  GOVERNANCE_THRESHOLD: 15.0,
};

// Generate synthetic PPRS data with realistic North Sea production profile
const generateSyntheticData = (months = 60) => {
  const data = [];
  const baseDate = new Date('2020-01-01');
  const qi = 12000; // Initial oil production (tonnes/month)
  const di = 0.038; // ~3.8% monthly decline
  
  for (let t = 0; t < months; t++) {
    const date = new Date(baseDate);
    date.setMonth(baseDate.getMonth() + t);
    
    // Natural exponential decline with noise
    const baseOil = qi * Math.exp(-di * t);
    const noise = (Math.random() - 0.5) * 400;
    let oilProduction = Math.max(0, baseOil + noise);
    
    // Associated gas (correlated with oil)
    let gasProduction = (oilProduction / 1200) * (1 + 0.15 * Math.sin(2 * Math.PI * t / 12));
    gasProduction += (Math.random() - 0.5) * 0.1;
    gasProduction = Math.max(0, gasProduction);
    
    // Inject shut-in months (3-5% of timeline)
    const isShutIn = Math.random() < 0.04 && t > 6;
    if (isShutIn) {
      oilProduction = 0;
      gasProduction = 0;
    }
    
    // Occasionally inject null gas readings
    if (Math.random() < 0.02 && !isShutIn) {
      gasProduction = null;
    }
    
    const daysInMonth = new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate();
    
    data.push({
      month: date.toISOString().slice(0, 7),
      t,
      oilProduction,
      gasProduction,
      daysInMonth,
      isShutIn,
    });
  }
  
  return data;
};

// Convert to BOE
const convertToBOE = (data) => {
  return data.map(row => {
    const oilBOE = row.oilProduction * CONSTANTS.OIL_TONNES_TO_BARRELS;
    const gasBOE = (row.gasProduction || 0) * row.daysInMonth * CONSTANTS.GAS_MMSCF_TO_BOE;
    const totalBOE = oilBOE + gasBOE;
    
    return { ...row, oilBOE, gasBOE, totalBOE };
  });
};

// Arps Exponential Decline Model
const arpsExponential = (t, qi, di) => qi * Math.exp(-di * t);

// Fit decline curve using simple log-linear regression
const fitDeclineCurve = (data) => {
  const producingData = data.filter(d => d.totalBOE > 0 && !d.isShutIn);
  
  if (producingData.length < 3) {
    return { qi: 100000, di: 0.03 };
  }
  
  // Log-linear regression: ln(q) = ln(qi) - di*t
  const n = producingData.length;
  let sumT = 0, sumLnQ = 0, sumTLnQ = 0, sumT2 = 0;
  
  producingData.forEach(d => {
    const lnQ = Math.log(d.totalBOE + 1);
    sumT += d.t;
    sumLnQ += lnQ;
    sumTLnQ += d.t * lnQ;
    sumT2 += d.t * d.t;
  });
  
  const di = Math.max(0.001, -(n * sumTLnQ - sumT * sumLnQ) / (n * sumT2 - sumT * sumT));
  const lnQi = (sumLnQ + di * sumT) / n;
  const qi = Math.exp(lnQi);
  
  return { qi, di };
};

// Build reconciliation table
const buildReconciliation = (data, qi, di, pricePerBarrel) => {
  return data.map(row => {
    const forecastBOE = arpsExponential(row.t, qi, di);
    const actualBOE = row.totalBOE;
    const varianceBOE = actualBOE - forecastBOE;
    const variancePct = forecastBOE > 0 ? (varianceBOE / forecastBOE) * 100 : 0;
    const revenueExposure = row.isShutIn ? 0 : varianceBOE * pricePerBarrel;
    
    const isFlagged = !row.isShutIn && Math.abs(variancePct) > CONSTANTS.GOVERNANCE_THRESHOLD;
    let severity = null;
    if (isFlagged) {
      if (Math.abs(variancePct) > 25) severity = 'HIGH';
      else if (Math.abs(variancePct) > 20) severity = 'MEDIUM';
      else severity = 'LOW';
    }
    
    return {
      ...row,
      forecastBOE,
      actualBOE,
      varianceBOE,
      variancePct,
      revenueExposure,
      isFlagged,
      severity,
    };
  });
};

// ============================================================================
// REACT COMPONENTS
// ============================================================================

const FiscalDashboard = () => {
  const [pricePerBarrel, setPricePerBarrel] = useState(CONSTANTS.DEFAULT_PRICE_PER_BARREL);
  const [selectedField] = useState('BRAE ALPHA');
  const [showSensitivity, setShowSensitivity] = useState(false);
  
  // Generate and process data
  const rawData = useMemo(() => generateSyntheticData(60), []);
  const boeData = useMemo(() => convertToBOE(rawData), [rawData]);
  const { qi, di } = useMemo(() => fitDeclineCurve(boeData), [boeData]);
  const reconciliation = useMemo(() => 
    buildReconciliation(boeData, qi, di, pricePerBarrel),
    [boeData, qi, di, pricePerBarrel]
  );
  
  // Calculate summary metrics
  const summary = useMemo(() => {
    const producing = reconciliation.filter(d => !d.isShutIn);
    const totalRevenue = producing.reduce((sum, d) => sum + d.revenueExposure, 0);
    const totalVariance = producing.reduce((sum, d) => sum + d.varianceBOE, 0);
    const flags = reconciliation.filter(d => d.isFlagged);
    const highSeverity = flags.filter(f => f.severity === 'HIGH').length;
    
    return {
      totalRevenue,
      totalVariance,
      producingMonths: producing.length,
      shutInMonths: reconciliation.filter(d => d.isShutIn).length,
      totalMonths: reconciliation.length,
      flagCount: flags.length,
      highSeverity,
      avgVariancePct: producing.reduce((sum, d) => sum + Math.abs(d.variancePct), 0) / producing.length,
    };
  }, [reconciliation]);
  
  // Cumulative exposure for chart
  const chartData = useMemo(() => {
    let cumulative = 0;
    return reconciliation.map(d => {
      if (!d.isShutIn) cumulative += d.revenueExposure;
      return {
        ...d,
        cumulativeExposure: cumulative,
      };
    });
  }, [reconciliation]);
  
  // Sensitivity analysis
  const sensitivityData = useMemo(() => {
    const prices = [50, 60, 70, 80, 90, 100];
    return prices.map(price => {
      const recon = buildReconciliation(boeData, qi, di, price);
      const producing = recon.filter(d => !d.isShutIn);
      const totalRev = producing.reduce((sum, d) => sum + d.revenueExposure, 0);
      return { price, revenue: totalRev };
    });
  }, [boeData, qi, di]);
  
  return (
    <div className="dashboard-container">
      {/* Scan-line overlay for industrial CRT effect */}
      <div className="scanlines"></div>
      
      {/* Header */}
      <header className="header">
        <div className="header-left">
          <div className="header-badge">UKCS</div>
          <div className="header-title">
            <h1>PRODUCTION RECONCILIATION</h1>
            <div className="header-subtitle">NSTA PPRS Fiscal Leakage Analysis</div>
          </div>
        </div>
        <div className="header-right">
          <div className="field-indicator">
            <span className="label">FIELD</span>
            <span className="value">{selectedField}</span>
          </div>
          <div className="status-indicator">
            <div className="status-dot"></div>
            <span>LIVE</span>
          </div>
        </div>
      </header>
      
      {/* Metric Cards Grid */}
      <div className="metrics-grid">
        <MetricCard
          icon={<DollarSign size={20} />}
          label="REVENUE AT RISK"
          value={formatCurrency(summary.totalRevenue)}
          delta={summary.totalRevenue < 0 ? 'Under-recovery' : 'Over-recovery'}
          status={summary.totalRevenue < 0 ? 'alert' : 'positive'}
        />
        <MetricCard
          icon={<TrendingDown size={20} />}
          label="TOTAL VARIANCE"
          value={`${formatNumber(summary.totalVariance)} BOE`}
          delta="Cumulative deviation"
          status={summary.totalVariance < 0 ? 'alert' : 'neutral'}
        />
        <MetricCard
          icon={<Calendar size={20} />}
          label="PRODUCING MONTHS"
          value={summary.producingMonths}
          delta={`of ${summary.totalMonths} total (${summary.shutInMonths} shut-in)`}
          status="neutral"
        />
        <MetricCard
          icon={<AlertTriangle size={20} />}
          label="GOVERNANCE FLAGS"
          value={summary.flagCount}
          delta={`${summary.highSeverity} HIGH severity`}
          status={summary.highSeverity > 0 ? 'alert' : 'positive'}
        />
      </div>
      
      {/* Model Parameters */}
      <div className="model-params">
        <div className="param-group">
          <span className="param-label">FITTED MODEL</span>
          <span className="param-value">qi = {formatNumber(qi)} BOE/mo</span>
          <span className="param-separator">|</span>
          <span className="param-value">di = {(di * 100).toFixed(2)}%/mo ({(di * 12 * 100).toFixed(1)}% annual)</span>
        </div>
        <div className="param-group">
          <span className="param-label">PRICE</span>
          <input
            type="range"
            min="40"
            max="120"
            step="2.5"
            value={pricePerBarrel}
            onChange={(e) => setPricePerBarrel(parseFloat(e.target.value))}
            className="price-slider"
          />
          <span className="param-value price-display">£{pricePerBarrel.toFixed(2)}/bbl</span>
        </div>
      </div>
      
      {/* Main Chart */}
      <div className="chart-section">
        <div className="chart-header">
          <h2>DECLINE CURVE vs. ACTUAL PRODUCTION</h2>
          <div className="chart-controls">
            <button 
              className={showSensitivity ? 'active' : ''}
              onClick={() => setShowSensitivity(!showSensitivity)}
            >
              <Target size={16} />
              {showSensitivity ? 'Hide' : 'Show'} Sensitivity
            </button>
          </div>
        </div>
        
        <ResponsiveContainer width="100%" height={400}>
          <ComposedChart data={chartData} margin={{ top: 10, right: 30, left: 20, bottom: 60 }}>
            <defs>
              <linearGradient id="varianceGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#d97706" stopOpacity={0.2} />
                <stop offset="100%" stopColor="#d97706" stopOpacity={0.05} />
              </linearGradient>
              <linearGradient id="exposureGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#8b5cf6" stopOpacity={0.6} />
                <stop offset="100%" stopColor="#8b5cf6" stopOpacity={0.2} />
              </linearGradient>
            </defs>
            
            <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" opacity={0.3} />
            
            <XAxis
              dataKey="month"
              stroke="#64748b"
              tick={{ fill: '#94a3b8', fontSize: 10, fontFamily: 'Courier New' }}
              angle={-45}
              textAnchor="end"
              height={80}
            />
            
            <YAxis
              yAxisId="left"
              stroke="#3b82f6"
              tick={{ fill: '#94a3b8', fontSize: 11, fontFamily: 'Courier New' }}
              label={{ value: 'Production (BOE/month)', angle: -90, position: 'insideLeft', fill: '#3b82f6', fontSize: 11 }}
            />
            
            <YAxis
              yAxisId="right"
              orientation="right"
              stroke="#8b5cf6"
              tick={{ fill: '#94a3b8', fontSize: 11, fontFamily: 'Courier New' }}
              label={{ value: 'Cumulative Exposure (£)', angle: 90, position: 'insideRight', fill: '#8b5cf6', fontSize: 11 }}
              tickFormatter={(value) => `£${(value / 1000).toFixed(0)}k`}
            />
            
            <Tooltip
              contentStyle={{
                backgroundColor: '#0f172a',
                border: '1px solid #334155',
                borderRadius: '4px',
                fontSize: '11px',
                fontFamily: 'Courier New',
              }}
              labelStyle={{ color: '#cbd5e1', fontWeight: 'bold' }}
              formatter={(value, name) => {
                if (name === 'Cumulative Exposure') return [`£${formatNumber(value)}`, name];
                return [`${formatNumber(value)} BOE`, name];
              }}
            />
            
            <Legend
              wrapperStyle={{ fontSize: '11px', fontFamily: 'Courier New' }}
              iconType="line"
            />
            
            {/* Variance shaded area */}
            <Area
              yAxisId="left"
              type="monotone"
              dataKey="forecastBOE"
              fill="url(#varianceGradient)"
              stroke="none"
            />
            
            {/* Forecast line */}
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="forecastBOE"
              stroke="#3b82f6"
              strokeWidth={2}
              strokeDasharray="5 5"
              dot={false}
              name="Forecast"
            />
            
            {/* Actual production */}
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="actualBOE"
              stroke="#10b981"
              strokeWidth={2}
              dot={(props) => {
                const { cx, cy, payload } = props;
                if (payload.isShutIn) {
                  return <circle cx={cx} cy={cy} r={4} fill="none" stroke="#64748b" strokeWidth={2} />;
                }
                if (payload.isFlagged) {
                  return <polygon
                    points={`${cx},${cy - 6} ${cx + 5},${cy} ${cx},${cy + 6} ${cx - 5},${cy}`}
                    fill="#d97706"
                    stroke="#0f172a"
                    strokeWidth={1.5}
                  />;
                }
                return <circle cx={cx} cy={cy} r={3} fill="#10b981" stroke="#0f172a" strokeWidth={1.5} />;
              }}
              name="Actual"
            />
            
            {/* Cumulative exposure */}
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="cumulativeExposure"
              stroke="#8b5cf6"
              strokeWidth={2.5}
              dot={false}
              name="Cumulative Exposure"
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      
      {/* Sensitivity Panel */}
      {showSensitivity && (
        <div className="sensitivity-panel">
          <h3>PRICE SENSITIVITY ANALYSIS</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={sensitivityData} margin={{ top: 10, right: 30, left: 20, bottom: 40 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" opacity={0.3} />
              <XAxis
                dataKey="price"
                stroke="#64748b"
                tick={{ fill: '#94a3b8', fontSize: 11, fontFamily: 'Courier New' }}
                tickFormatter={(value) => `£${value}`}
                label={{ value: 'Brent Price (£/bbl)', position: 'insideBottom', offset: -10, fill: '#94a3b8', fontSize: 11 }}
              />
              <YAxis
                stroke="#64748b"
                tick={{ fill: '#94a3b8', fontSize: 11, fontFamily: 'Courier New' }}
                tickFormatter={(value) => `£${(value / 1000000).toFixed(1)}M`}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#0f172a',
                  border: '1px solid #334155',
                  fontSize: '11px',
                  fontFamily: 'Courier New',
                }}
                formatter={(value) => [`£${formatNumber(value)}`, 'Revenue at Risk']}
              />
              <Bar
                dataKey="revenue"
                fill="#d97706"
                radius={[4, 4, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      
      {/* Governance Log */}
      <div className="governance-log">
        <h3>DATA GOVERNANCE LOG</h3>
        {summary.flagCount === 0 ? (
          <div className="no-flags">
            ✓ No governance flags raised. All producing months within variance threshold.
          </div>
        ) : (
          <div className="flag-table">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>MONTH</th>
                  <th>ACTUAL</th>
                  <th>FORECAST</th>
                  <th>VARIANCE</th>
                  <th>EXPOSURE</th>
                  <th>SEVERITY</th>
                </tr>
              </thead>
              <tbody>
                {reconciliation
                  .filter(d => d.isFlagged)
                  .map((d, idx) => (
                    <tr key={d.month}>
                      <td>{idx + 1}</td>
                      <td>{d.month}</td>
                      <td>{formatNumber(d.actualBOE)}</td>
                      <td>{formatNumber(d.forecastBOE)}</td>
                      <td className={d.variancePct < 0 ? 'negative' : 'positive'}>
                        {d.variancePct > 0 ? '+' : ''}{d.variancePct.toFixed(1)}%
                      </td>
                      <td className={d.revenueExposure < 0 ? 'negative' : 'positive'}>
                        £{formatNumber(Math.abs(d.revenueExposure))}
                      </td>
                      <td>
                        <span className={`severity-badge ${d.severity.toLowerCase()}`}>
                          {d.severity}
                        </span>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      
      <style jsx>{`
        .dashboard-container {
          min-height: 100vh;
          background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%);
          color: #e2e8f0;
          font-family: 'Courier New', monospace;
          padding: 24px;
          position: relative;
          overflow-x: hidden;
        }
        
        /* Scan-line overlay for industrial CRT effect */
        .scanlines {
          position: fixed;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          pointer-events: none;
          background: repeating-linear-gradient(
            0deg,
            rgba(0, 0, 0, 0.05) 0px,
            rgba(0, 0, 0, 0.05) 1px,
            transparent 1px,
            transparent 2px
          );
          z-index: 1000;
          animation: scanline 8s linear infinite;
        }
        
        @keyframes scanline {
          0% { transform: translateY(0); }
          100% { transform: translateY(4px); }
        }
        
        /* Header */
        .header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 16px 20px;
          background: linear-gradient(90deg, #1e293b 0%, #334155 100%);
          border: 2px solid #475569;
          border-radius: 2px;
          margin-bottom: 24px;
          box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
        }
        
        .header-left {
          display: flex;
          align-items: center;
          gap: 16px;
        }
        
        .header-badge {
          background: #d97706;
          color: #0f172a;
          padding: 8px 14px;
          font-weight: 900;
          font-size: 14px;
          letter-spacing: 3px;
          border: 2px solid #0f172a;
          box-shadow: inset 0 2px 0 rgba(255, 255, 255, 0.2);
        }
        
        .header-title h1 {
          margin: 0;
          font-size: 22px;
          font-weight: 700;
          letter-spacing: 2px;
          color: #f1f5f9;
          text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.5);
        }
        
        .header-subtitle {
          font-size: 10px;
          color: #94a3b8;
          letter-spacing: 1px;
          margin-top: 2px;
        }
        
        .header-right {
          display: flex;
          gap: 20px;
          align-items: center;
        }
        
        .field-indicator {
          display: flex;
          flex-direction: column;
          align-items: flex-end;
        }
        
        .field-indicator .label {
          font-size: 9px;
          color: #64748b;
          letter-spacing: 1px;
        }
        
        .field-indicator .value {
          font-size: 14px;
          color: #3b82f6;
          font-weight: 700;
          letter-spacing: 1px;
        }
        
        .status-indicator {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 11px;
          color: #10b981;
          letter-spacing: 1px;
        }
        
        .status-dot {
          width: 8px;
          height: 8px;
          background: #10b981;
          border-radius: 50%;
          box-shadow: 0 0 8px #10b981;
          animation: pulse 2s ease-in-out infinite;
        }
        
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
        
        /* Metrics Grid */
        .metrics-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 16px;
          margin-bottom: 24px;
        }
        
        @media (max-width: 1200px) {
          .metrics-grid {
            grid-template-columns: repeat(2, 1fr);
          }
        }
        
        /* Model Parameters */
        .model-params {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 12px 20px;
          background: #1e293b;
          border: 1px solid #334155;
          border-radius: 2px;
          margin-bottom: 20px;
          font-size: 11px;
        }
        
        .param-group {
          display: flex;
          align-items: center;
          gap: 12px;
        }
        
        .param-label {
          color: #64748b;
          letter-spacing: 1px;
          font-weight: 700;
        }
        
        .param-value {
          color: #cbd5e1;
          font-weight: 600;
        }
        
        .param-separator {
          color: #475569;
        }
        
        .price-slider {
          width: 180px;
          height: 6px;
          background: #334155;
          outline: none;
          border-radius: 3px;
          cursor: pointer;
        }
        
        .price-slider::-webkit-slider-thumb {
          appearance: none;
          width: 18px;
          height: 18px;
          background: #d97706;
          border: 2px solid #0f172a;
          border-radius: 2px;
          cursor: pointer;
          box-shadow: 0 2px 4px rgba(0, 0, 0, 0.4);
        }
        
        .price-display {
          color: #d97706;
          font-weight: 900;
          font-size: 13px;
        }
        
        /* Chart Section */
        .chart-section {
          background: #1e293b;
          border: 1px solid #334155;
          border-radius: 2px;
          padding: 20px;
          margin-bottom: 20px;
          box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
        }
        
        .chart-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 16px;
        }
        
        .chart-header h2 {
          margin: 0;
          font-size: 13px;
          letter-spacing: 2px;
          color: #64748b;
          font-weight: 700;
        }
        
        .chart-controls button {
          background: #334155;
          border: 1px solid #475569;
          color: #cbd5e1;
          padding: 6px 12px;
          font-size: 11px;
          font-family: 'Courier New', monospace;
          cursor: pointer;
          display: flex;
          align-items: center;
          gap: 6px;
          transition: all 0.2s;
        }
        
        .chart-controls button:hover {
          background: #475569;
          border-color: #64748b;
        }
        
        .chart-controls button.active {
          background: #d97706;
          border-color: #d97706;
          color: #0f172a;
          font-weight: 700;
        }
        
        /* Sensitivity Panel */
        .sensitivity-panel {
          background: #1e293b;
          border: 1px solid #334155;
          border-radius: 2px;
          padding: 20px;
          margin-bottom: 20px;
          animation: slideDown 0.3s ease-out;
        }
        
        @keyframes slideDown {
          from {
            opacity: 0;
            transform: translateY(-10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        
        .sensitivity-panel h3 {
          margin: 0 0 16px 0;
          font-size: 12px;
          letter-spacing: 2px;
          color: #64748b;
          font-weight: 700;
        }
        
        /* Governance Log */
        .governance-log {
          background: #1e293b;
          border: 1px solid #334155;
          border-radius: 2px;
          padding: 20px;
          box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
        }
        
        .governance-log h3 {
          margin: 0 0 16px 0;
          font-size: 12px;
          letter-spacing: 2px;
          color: #64748b;
          font-weight: 700;
        }
        
        .no-flags {
          color: #10b981;
          font-size: 12px;
          padding: 12px;
          background: rgba(16, 185, 129, 0.1);
          border: 1px solid rgba(16, 185, 129, 0.3);
          border-radius: 2px;
        }
        
        .flag-table {
          overflow-x: auto;
        }
        
        .flag-table table {
          width: 100%;
          border-collapse: collapse;
          font-size: 11px;
        }
        
        .flag-table th {
          background: #334155;
          color: #94a3b8;
          padding: 10px 12px;
          text-align: left;
          font-weight: 700;
          letter-spacing: 1px;
          border-bottom: 2px solid #475569;
        }
        
        .flag-table td {
          padding: 10px 12px;
          border-bottom: 1px solid #334155;
          color: #cbd5e1;
        }
        
        .flag-table tr:nth-child(even) {
          background: rgba(51, 65, 85, 0.3);
        }
        
        .flag-table tr:hover {
          background: rgba(71, 85, 105, 0.3);
        }
        
        .flag-table .negative {
          color: #f59e0b;
        }
        
        .flag-table .positive {
          color: #10b981;
        }
        
        .severity-badge {
          display: inline-block;
          padding: 3px 10px;
          border-radius: 2px;
          font-size: 9px;
          font-weight: 900;
          letter-spacing: 1px;
        }
        
        .severity-badge.high {
          background: #7f1d1d;
          color: #fca5a5;
          border: 1px solid #991b1b;
        }
        
        .severity-badge.medium {
          background: #78350f;
          color: #fcd34d;
          border: 1px solid #92400e;
        }
        
        .severity-badge.low {
          background: #1e3a5f;
          color: #60a5fa;
          border: 1px solid #1e40af;
        }
      `}</style>
    </div>
  );
};

const MetricCard = ({ icon, label, value, delta, status }) => {
  return (
    <div className={`metric-card ${status}`}>
      <div className="metric-icon">{icon}</div>
      <div className="metric-content">
        <div className="metric-label">{label}</div>
        <div className="metric-value">{value}</div>
        <div className="metric-delta">{delta}</div>
      </div>
      
      <style jsx>{`
        .metric-card {
          background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
          border: 2px solid #475569;
          border-radius: 2px;
          padding: 18px;
          display: flex;
          gap: 14px;
          align-items: flex-start;
          position: relative;
          overflow: hidden;
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
          transition: all 0.3s ease;
        }
        
        .metric-card::before {
          content: '';
          position: absolute;
          top: 0;
          left: 0;
          width: 4px;
          height: 100%;
          background: #64748b;
        }
        
        .metric-card.alert::before {
          background: #d97706;
          box-shadow: 0 0 10px #d97706;
        }
        
        .metric-card.positive::before {
          background: #10b981;
          box-shadow: 0 0 10px #10b981;
        }
        
        .metric-card:hover {
          transform: translateY(-2px);
          box-shadow: 0 6px 20px rgba(0, 0, 0, 0.4);
        }
        
        .metric-icon {
          color: #64748b;
          padding: 8px;
          background: rgba(100, 116, 139, 0.15);
          border: 1px solid #475569;
          border-radius: 2px;
        }
        
        .metric-card.alert .metric-icon {
          color: #d97706;
          background: rgba(217, 119, 6, 0.15);
        }
        
        .metric-card.positive .metric-icon {
          color: #10b981;
          background: rgba(16, 185, 129, 0.15);
        }
        
        .metric-content {
          flex: 1;
        }
        
        .metric-label {
          font-size: 9px;
          color: #64748b;
          letter-spacing: 1.5px;
          font-weight: 700;
          margin-bottom: 6px;
        }
        
        .metric-value {
          font-size: 22px;
          font-weight: 900;
          color: #f1f5f9;
          letter-spacing: 0.5px;
          margin-bottom: 4px;
        }
        
        .metric-card.alert .metric-value {
          color: #fbbf24;
        }
        
        .metric-card.positive .metric-value {
          color: #34d399;
        }
        
        .metric-delta {
          font-size: 9px;
          color: #64748b;
          letter-spacing: 0.5px;
        }
      `}</style>
    </div>
  );
};

// Utility functions
const formatNumber = (num) => {
  if (num === null || num === undefined) return 'N/A';
  const absNum = Math.abs(num);
  if (absNum >= 1000000) return `${(num / 1000000).toFixed(2)}M`;
  if (absNum >= 1000) return `${(num / 1000).toFixed(1)}k`;
  return num.toFixed(0);
};

const formatCurrency = (num) => {
  if (num === null || num === undefined) return '£N/A';
  const absNum = Math.abs(num);
  const sign = num < 0 ? '-' : '';
  if (absNum >= 1000000) return `${sign}£${(absNum / 1000000).toFixed(2)}M`;
  if (absNum >= 1000) return `${sign}£${(absNum / 1000).toFixed(1)}k`;
  return `${sign}£${absNum.toFixed(0)}`;
};

export default FiscalDashboard;
