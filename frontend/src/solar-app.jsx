import { useState } from "react";

// ─── MOCK DATA ────────────────────────────────────────────────────────────────
const mockData = {
  today: { kwh: 38.2, date: "Apr 28, 2026" },
  sameDay1YearAgo: { kwh: 32.3, date: "Apr 28, 2025" },
  sameDay1MonthAgo: { kwh: 29.1, date: "Mar 28, 2026" },
  thisMonth: { kwh: 410, label: "April 2026" },
  lastMonth: { kwh: 391, label: "March 2026" },
  sameMonthLastYear: { kwh: 432, label: "April 2025" },
  thisYear: { kwh: 1820, label: "2026 YTD" },
  lastYear: { kwh: 4950, label: "Full 2025" },
  allTime: { kwh: 12340 },
  bestDay: { kwh: 52.1, date: "Jul 14, 2024" },
  worstDay: { kwh: 1.2, date: "Dec 3, 2024" },
  currentPower: 4.2,
  peakToday: 6.8,
  hourly: [0,0,0,0,0,0,0.2,1.1,2.8,4.5,5.9,6.8,6.5,5.8,4.9,3.6,2.1,0.8,0.1,0,0,0,0,0],
  hourlyLastYear: [0,0,0,0,0,0,0.1,0.9,2.3,3.8,5.1,5.9,5.7,5.1,4.2,3.0,1.7,0.5,0,0,0,0,0,0],
};

// Efficiency data: monthly Performance Ratio % over 3 years
const efficiencyHistory = [
  // 2023 (Year 1 — baseline)
  { month: "Jan 23", pr: 81.2, expected: 81.0 },
  { month: "Feb 23", pr: 82.5, expected: 82.0 },
  { month: "Mar 23", pr: 83.1, expected: 83.0 },
  { month: "Apr 23", pr: 84.0, expected: 84.0 },
  { month: "May 23", pr: 83.8, expected: 83.5 },
  { month: "Jun 23", pr: 84.2, expected: 84.0 },
  { month: "Jul 23", pr: 83.9, expected: 83.8 },
  { month: "Aug 23", pr: 84.1, expected: 83.8 },
  { month: "Sep 23", pr: 83.5, expected: 83.5 },
  { month: "Oct 23", pr: 82.8, expected: 82.5 },
  { month: "Nov 23", pr: 81.9, expected: 82.0 },
  { month: "Dec 23", pr: 80.5, expected: 81.0 },
  // 2024 (Year 2)
  { month: "Jan 24", pr: 80.8, expected: 80.4 },
  { month: "Feb 24", pr: 81.9, expected: 81.4 },
  { month: "Mar 24", pr: 82.5, expected: 82.3 },
  { month: "Apr 24", pr: 83.1, expected: 83.3 },
  { month: "May 24", pr: 82.7, expected: 82.9 },
  { month: "Jun 24", pr: 83.5, expected: 83.4 },
  { month: "Jul 24", pr: 83.0, expected: 83.2 },
  { month: "Aug 24", pr: 82.1, expected: 83.2 },  // anomaly — dirty panels
  { month: "Sep 24", pr: 82.8, expected: 82.9 },
  { month: "Oct 24", pr: 82.0, expected: 82.0 },
  { month: "Nov 24", pr: 81.1, expected: 81.5 },
  { month: "Dec 24", pr: 79.8, expected: 80.5 },
  // 2025 (Year 3)
  { month: "Jan 25", pr: 80.0, expected: 79.8 },
  { month: "Feb 25", pr: 81.2, expected: 80.8 },
  { month: "Mar 25", pr: 81.8, expected: 81.7 },
  { month: "Apr 25", pr: 82.5, expected: 82.6 },
  { month: "May 25", pr: 82.1, expected: 82.3 },
  { month: "Jun 25", pr: 82.8, expected: 82.8 },
  { month: "Jul 25", pr: 82.4, expected: 82.6 },
  { month: "Aug 25", pr: 82.6, expected: 82.6 },
  { month: "Sep 25", pr: 82.0, expected: 82.3 },
  { month: "Oct 25", pr: 81.3, expected: 81.4 },
  { month: "Nov 25", pr: 80.5, expected: 80.9 },
  { month: "Dec 25", pr: 79.1, expected: 79.9 },
  // 2026 YTD
  { month: "Jan 26", pr: 79.5, expected: 79.2 },
  { month: "Feb 26", pr: 80.6, expected: 80.2 },
  { month: "Mar 26", pr: 81.0, expected: 81.1 },
  { month: "Apr 26", pr: 81.8, expected: 81.9 },
];

// Panel-level mock (16 panels)
const panels = [
  { id: "P01", efficiency: 98.2 }, { id: "P02", efficiency: 97.8 },
  { id: "P03", efficiency: 96.1 }, { id: "P04", efficiency: 94.3 },
  { id: "P05", efficiency: 98.5 }, { id: "P06", efficiency: 97.2 },
  { id: "P07", efficiency: 82.1 }, { id: "P08", efficiency: 97.9 },
  { id: "P09", efficiency: 98.1 }, { id: "P10", efficiency: 96.8 },
  { id: "P11", efficiency: 97.5 }, { id: "P12", efficiency: 95.9 },
  { id: "P13", efficiency: 98.3 }, { id: "P14", efficiency: 97.1 },
  { id: "P15", efficiency: 96.4 }, { id: "P16", efficiency: 97.7 },
];

const defaultSetup = {
  systemSize: "8.4",
  installDate: "2023-01-15",
  location: "Montreal, QC",
  latitude: "45.5017",
  longitude: "-73.5673",
  panelCount: "16",
  panelWattage: "525",
  manufacturer: "Enphase",
  degradationRate: "0.5",
  enphaseApiKey: "",
  enphaseSystemId: "",
  irradianceSource: "nrel",
  tiltAngle: "35",
  azimuth: "180",
};

// ─── HELPERS ──────────────────────────────────────────────────────────────────
const pct = (a, b) => (((a - b) / b) * 100).toFixed(1);
const arrow = (a, b) => a >= b ? "↑" : "↓";
const posColor = (a, b) => a >= b ? "#a3e635" : "#f87171";
const hourLabels = ["12a","","","","","","6a","","","","","","12p","","","","","","6p","","","","",""];
const MAX_KW = 8;

const panelColor = (eff) => {
  if (eff >= 97) return "#a3e635";
  if (eff >= 94) return "#facc15";
  if (eff >= 88) return "#fb923c";
  return "#f87171";
};

// ─── STYLES ───────────────────────────────────────────────────────────────────
const fonts = `@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;600;700;800&display=swap');`;

const css = `
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg: #0a0f0d; --surface: #111a14; --surface2: #172019;
  --border: #1f3024; --accent: #a3e635; --accent2: #34d399;
  --accent3: #fb923c; --text: #e8f5e2; --muted: #5a7a62;
  --danger: #f87171; --warn: #facc15;
}
body { background: var(--bg); color: var(--text); font-family: 'Syne', sans-serif; min-height: 100vh; }

.app { max-width: 1100px; margin: 0 auto; padding: 32px 24px 64px; }

/* NAV */
.nav { display: flex; align-items: center; justify-content: space-between; margin-bottom: 36px; padding-bottom: 20px; border-bottom: 1px solid var(--border); }
.nav-logo { font-size: 11px; font-family: 'Space Mono', monospace; letter-spacing: 0.2em; color: var(--accent); text-transform: uppercase; }
.nav-title { font-size: 22px; font-weight: 800; }
.nav-tabs { display: flex; gap: 4px; background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 4px; }
.nav-tab { padding: 8px 18px; border-radius: 8px; font-size: 12px; font-family: 'Space Mono', monospace; cursor: pointer; border: none; background: transparent; color: var(--muted); transition: all 0.15s; white-space: nowrap; }
.nav-tab.active { background: var(--accent); color: #0a0f0d; font-weight: 700; }
.live-badge { display: flex; align-items: center; gap: 8px; background: var(--surface); border: 1px solid var(--border); border-radius: 100px; padding: 8px 16px; font-family: 'Space Mono', monospace; font-size: 12px; }
.live-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); animation: pulse 2s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }

/* CARDS */
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 24px; position: relative; overflow: hidden; transition: border-color 0.2s; }
.card:hover { border-color: var(--muted); }
.card-accent { background: linear-gradient(135deg,#1a2e1e,#111a14); border-color: #2a4030; }
.card-label { font-size: 10px; font-family: 'Space Mono', monospace; letter-spacing: 0.15em; text-transform: uppercase; color: var(--muted); margin-bottom: 12px; }
.card-value { font-size: 44px; font-weight: 800; line-height: 1; }
.card-value-med { font-size: 30px; font-weight: 800; line-height: 1; }
.val-unit { font-size: 16px; font-weight: 400; color: var(--muted); margin-left: 4px; }
.card-sub { font-size: 12px; color: var(--muted); margin-top: 6px; font-family: 'Space Mono', monospace; }
.delta { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; font-family: 'Space Mono', monospace; font-weight: 700; margin-top: 10px; padding: 4px 10px; border-radius: 100px; background: rgba(0,0,0,0.3); }
.corner-glow { position: absolute; top:-30px; right:-30px; width:100px; height:100px; background:radial-gradient(circle,rgba(163,230,53,0.08),transparent 70%); pointer-events:none; }

/* GRIDS */
.now-row { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 16px; margin-bottom: 20px; }
.compare-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 16px; margin-bottom: 20px; }
.records-row { display: grid; grid-template-columns: repeat(3,1fr); gap: 16px; margin-bottom: 20px; }
.eff-top { display: grid; grid-template-columns: repeat(2,1fr); gap: 16px; margin-bottom: 20px; }
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px; }

/* CHART */
.chart-wrap { background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 20px 24px 12px; margin-bottom: 20px; }
.chart-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.chart-title { font-size: 14px; font-weight: 700; }
.legend { display: flex; gap: 16px; }
.legend-item { display: flex; align-items: center; gap: 6px; font-size: 11px; font-family: 'Space Mono', monospace; color: var(--muted); }
.legend-dot { width: 8px; height: 8px; border-radius: 2px; }
.chart-area { display: flex; align-items: flex-end; gap: 3px; height: 120px; }
.bar-group { flex: 1; display: flex; align-items: flex-end; gap: 1px; height: 100%; }
.bar { flex: 1; border-radius: 3px 3px 0 0; transition: opacity 0.2s; cursor: pointer; }
.bar:hover { opacity: 0.8; }
.chart-labels { display: flex; gap: 3px; margin-top: 6px; }
.chart-label { flex: 1; text-align: center; font-size: 9px; font-family: 'Space Mono', monospace; color: var(--muted); }

/* EFFICIENCY LINE CHART */
.line-chart-wrap { position: relative; height: 160px; }
.line-svg { width: 100%; height: 100%; overflow: visible; }

/* COMPARE CARD */
.compare-card { background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 20px; }
.compare-period { font-size: 10px; font-family: 'Space Mono', monospace; letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted); margin-bottom: 16px; }
.compare-row { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--border); }
.compare-row:last-child { border-bottom: none; }
.compare-label { font-size: 11px; color: var(--muted); }
.compare-val { font-size: 14px; font-weight: 700; font-family: 'Space Mono', monospace; }
.compare-val.hl { color: var(--accent); }
.bar-compare { height: 4px; border-radius: 2px; margin-top: 10px; overflow: hidden; background: var(--border); display: flex; gap: 2px; }
.bar-compare-fill { height: 100%; border-radius: 2px; }

/* SECTION LABEL */
.section-label { font-size: 10px; font-family: 'Space Mono', monospace; letter-spacing: 0.2em; text-transform: uppercase; color: var(--muted); margin-bottom: 12px; margin-top: 4px; }

/* PANEL HEATMAP */
.panel-grid { display: grid; grid-template-columns: repeat(8,1fr); gap: 6px; }
.panel-cell { aspect-ratio: 1.6; border-radius: 6px; display: flex; flex-direction: column; align-items: center; justify-content: center; cursor: default; transition: transform 0.15s; position: relative; }
.panel-cell:hover { transform: scale(1.08); z-index: 10; }
.panel-id { font-size: 8px; font-family: 'Space Mono', monospace; color: rgba(0,0,0,0.7); font-weight: 700; }
.panel-pct { font-size: 10px; font-family: 'Space Mono', monospace; color: rgba(0,0,0,0.85); font-weight: 700; }
.panel-legend { display: flex; gap: 16px; margin-top: 12px; align-items: center; }
.panel-legend-item { display: flex; align-items: center; gap: 6px; font-size: 10px; font-family: 'Space Mono', monospace; color: var(--muted); }
.panel-legend-swatch { width: 12px; height: 12px; border-radius: 3px; }

/* DEGRADATION BAR */
.deg-bar-wrap { margin: 10px 0 4px; }
.deg-bar-track { height: 8px; background: var(--border); border-radius: 4px; overflow: hidden; }
.deg-bar-fill { height: 100%; border-radius: 4px; transition: width 0.6s ease; }
.deg-labels { display: flex; justify-content: space-between; font-size: 9px; font-family: 'Space Mono', monospace; color: var(--muted); margin-top: 4px; }

/* ANOMALY BADGE */
.anomaly { display: inline-flex; align-items: center; gap: 6px; background: rgba(248,113,113,0.1); border: 1px solid rgba(248,113,113,0.3); border-radius: 8px; padding: 6px 12px; font-size: 11px; font-family: 'Space Mono', monospace; color: var(--danger); margin-top: 8px; }

/* SETUP PAGE */
.setup-wrap { max-width: 700px; }
.setup-section { background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 24px; margin-bottom: 20px; }
.setup-section-title { font-size: 13px; font-weight: 700; color: var(--accent); margin-bottom: 20px; display: flex; align-items: center; gap: 8px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.form-group { display: flex; flex-direction: column; gap: 6px; }
.form-group.full { grid-column: 1 / -1; }
.form-label { font-size: 10px; font-family: 'Space Mono', monospace; letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted); }
.form-input { background: var(--surface2); border: 1px solid var(--border); border-radius: 8px; padding: 10px 14px; color: var(--text); font-family: 'Space Mono', monospace; font-size: 13px; outline: none; transition: border-color 0.15s; }
.form-input:focus { border-color: var(--accent); }
.form-input::placeholder { color: var(--muted); }
.form-select { background: var(--surface2); border: 1px solid var(--border); border-radius: 8px; padding: 10px 14px; color: var(--text); font-family: 'Space Mono', monospace; font-size: 13px; outline: none; appearance: none; cursor: pointer; }
.form-hint { font-size: 10px; color: var(--muted); font-family: 'Space Mono', monospace; }
.form-actions { display: flex; gap: 12px; margin-top: 8px; }
.btn { padding: 12px 28px; border-radius: 10px; font-size: 13px; font-family: 'Space Mono', monospace; font-weight: 700; cursor: pointer; border: none; transition: all 0.15s; }
.btn-primary { background: var(--accent); color: #0a0f0d; }
.btn-primary:hover { opacity: 0.9; transform: translateY(-1px); }
.btn-secondary { background: transparent; border: 1px solid var(--border); color: var(--muted); }
.btn-secondary:hover { border-color: var(--muted); color: var(--text); }
.status-pill { display: inline-flex; align-items: center; gap: 6px; padding: 4px 12px; border-radius: 100px; font-size: 10px; font-family: 'Space Mono', monospace; }
.status-ok { background: rgba(163,230,53,0.1); border: 1px solid rgba(163,230,53,0.3); color: var(--accent); }
.status-missing { background: rgba(248,113,113,0.1); border: 1px solid rgba(248,113,113,0.3); color: var(--danger); }
.info-box { background: rgba(163,230,53,0.05); border: 1px solid rgba(163,230,53,0.15); border-radius: 10px; padding: 14px 16px; font-size: 11px; font-family: 'Space Mono', monospace; color: var(--muted); line-height: 1.7; margin-top: 8px; }
.save-toast { position: fixed; bottom: 32px; left: 50%; transform: translateX(-50%); background: var(--accent); color: #0a0f0d; padding: 12px 28px; border-radius: 100px; font-family: 'Space Mono', monospace; font-size: 13px; font-weight: 700; z-index: 100; animation: toastIn 0.3s ease; }
@keyframes toastIn { from{opacity:0;transform:translateX(-50%) translateY(10px)} to{opacity:1;transform:translateX(-50%) translateY(0)} }
`;

// ─── LINE CHART (SVG) ─────────────────────────────────────────────────────────
function LineChart({ data }) {
  const W = 1000, H = 140, PAD = { t: 10, r: 10, b: 10, l: 10 };
  const iW = W - PAD.l - PAD.r, iH = H - PAD.t - PAD.b;
  const minPR = 76, maxPR = 86;

  const xScale = (i) => PAD.l + (i / (data.length - 1)) * iW;
  const yScale = (v) => PAD.t + iH - ((v - minPR) / (maxPR - minPR)) * iH;

  const pathActual = data.map((d, i) => `${i === 0 ? "M" : "L"}${xScale(i)},${yScale(d.pr)}`).join(" ");
  const pathExpected = data.map((d, i) => `${i === 0 ? "M" : "L"}${xScale(i)},${yScale(d.expected)}`).join(" ");

  const anomalies = data.filter(d => d.pr < d.expected - 1.2);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="line-svg" preserveAspectRatio="none">
      <defs>
        <linearGradient id="fillGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#a3e635" stopOpacity="0.15" />
          <stop offset="100%" stopColor="#a3e635" stopOpacity="0" />
        </linearGradient>
      </defs>
      {/* Fill under actual */}
      <path d={`${pathActual} L${xScale(data.length-1)},${yScale(minPR)} L${xScale(0)},${yScale(minPR)} Z`}
        fill="url(#fillGrad)" />
      {/* Expected dashed */}
      <path d={pathExpected} fill="none" stroke="#2d5a38" strokeWidth="1.5"
        strokeDasharray="6,4" strokeLinecap="round" />
      {/* Actual line */}
      <path d={pathActual} fill="none" stroke="#a3e635" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      {/* Anomaly markers */}
      {anomalies.map((d) => {
        const i = data.indexOf(d);
        return (
          <g key={i}>
            <circle cx={xScale(i)} cy={yScale(d.pr)} r="5" fill="#f87171" opacity="0.9" />
            <line x1={xScale(i)} y1={yScale(d.pr)-8} x2={xScale(i)} y2={yScale(d.pr)-16}
              stroke="#f87171" strokeWidth="1.5" />
          </g>
        );
      })}
      {/* Year labels */}
      {[0, 12, 24, 36].map((idx) => (
        <text key={idx} x={xScale(idx)} y={H - 2} fill="#5a7a62"
          fontSize="10" fontFamily="Space Mono" textAnchor="middle">
          {data[idx]?.month.split(" ")[1]}
        </text>
      ))}
    </svg>
  );
}

// ─── OVERVIEW PAGE ────────────────────────────────────────────────────────────
function OverviewPage() {
  const d = mockData;
  const todayPct = pct(d.today.kwh, d.sameDay1YearAgo.kwh);
  return (
    <>
      {/* NOW ROW */}
      <div className="now-row">
        <div className="card card-accent">
          <div className="corner-glow" />
          <div className="card-label">Production Today</div>
          <div className="card-value">{d.today.kwh}<span className="val-unit">kWh</span></div>
          <div style={{display:"flex",gap:10,marginTop:12,flexWrap:"wrap"}}>
            <div className="delta" style={{color: posColor(d.today.kwh, d.sameDay1YearAgo.kwh)}}>
              {arrow(d.today.kwh, d.sameDay1YearAgo.kwh)} {Math.abs(todayPct)}% vs last year
            </div>
            <div className="delta" style={{color: posColor(d.today.kwh, d.sameDay1MonthAgo.kwh)}}>
              {arrow(d.today.kwh, d.sameDay1MonthAgo.kwh)} {Math.abs(pct(d.today.kwh, d.sameDay1MonthAgo.kwh))}% vs last month
            </div>
          </div>
        </div>
        <div className="card">
          <div className="card-label">Current Power</div>
          <div className="card-value-med" style={{color:"var(--accent)"}}>{d.currentPower}<span className="val-unit">kW</span></div>
          <div className="card-sub" style={{marginTop:10}}>Peak today</div>
          <div style={{fontSize:18,fontWeight:700,fontFamily:"Space Mono"}}>{d.peakToday} kW</div>
        </div>
        <div className="card">
          <div className="card-label">All-Time Total</div>
          <div className="card-value-med">{(d.allTime.kwh/1000).toFixed(1)}<span className="val-unit">MWh</span></div>
          <div className="card-sub" style={{marginTop:10}}>≈ {Math.round(d.allTime.kwh*0.85)} lbs CO₂ saved</div>
          <div style={{fontSize:12,color:"var(--accent2)",fontFamily:"Space Mono",marginTop:4}}>Since Jan 2023</div>
        </div>
      </div>

      {/* HOURLY CHART */}
      <div className="chart-wrap">
        <div className="chart-header">
          <div className="chart-title">Today vs. Same Day Last Year — Hourly (kW)</div>
          <div className="legend">
            <div className="legend-item"><div className="legend-dot" style={{background:"var(--accent)"}} /><span>Today</span></div>
            <div className="legend-item"><div className="legend-dot" style={{background:"#2d5a38"}} /><span>Apr 28, 2025</span></div>
          </div>
        </div>
        <div className="chart-area">
          {d.hourly.map((val, i) => (
            <div key={i} className="bar-group">
              <div className="bar" style={{background:"#2d5a38", height:`${(d.hourlyLastYear[i]/MAX_KW)*100}%`, minHeight: d.hourlyLastYear[i]>0?2:0}} />
              <div className="bar" style={{background:"var(--accent)", height:`${(val/MAX_KW)*100}%`, minHeight: val>0?2:0}} />
            </div>
          ))}
        </div>
        <div className="chart-labels">
          {hourLabels.map((l,i) => <div key={i} className="chart-label">{l}</div>)}
        </div>
      </div>

      {/* COMPARE */}
      <div className="section-label">Period Comparisons</div>
      <div className="compare-grid">
        <div className="compare-card">
          <div className="compare-period">📅 Today — {d.today.date}</div>
          <div className="compare-row"><div className="compare-label">Today</div><div className="compare-val hl">{d.today.kwh} kWh</div></div>
          <div className="compare-row"><div className="compare-label">Same day last year</div><div className="compare-val">{d.sameDay1YearAgo.kwh} kWh</div></div>
          <div className="compare-row"><div className="compare-label">Same day last month</div><div className="compare-val">{d.sameDay1MonthAgo.kwh} kWh</div></div>
          <div className="bar-compare">
            <div className="bar-compare-fill" style={{width:`${(d.sameDay1YearAgo.kwh/d.today.kwh)*50}%`,background:"#2d5a38"}} />
            <div className="bar-compare-fill" style={{width:"50%",background:"var(--accent)"}} />
          </div>
        </div>
        <div className="compare-card">
          <div className="compare-period">📆 {d.thisMonth.label}</div>
          <div className="compare-row"><div className="compare-label">This month</div><div className="compare-val hl">{d.thisMonth.kwh} kWh</div></div>
          <div className="compare-row"><div className="compare-label">Same month last year</div><div className="compare-val">{d.sameMonthLastYear.kwh} kWh</div></div>
          <div className="compare-row"><div className="compare-label">Last month</div><div className="compare-val">{d.lastMonth.kwh} kWh</div></div>
          <div className="bar-compare">
            <div className="bar-compare-fill" style={{width:`${(d.thisMonth.kwh/d.sameMonthLastYear.kwh)*50}%`,background:"var(--accent)"}} />
            <div className="bar-compare-fill" style={{width:"50%",background:"#2d5a38"}} />
          </div>
        </div>
        <div className="compare-card">
          <div className="compare-period">📈 {d.thisYear.label}</div>
          <div className="compare-row"><div className="compare-label">YTD (118 days)</div><div className="compare-val hl">{d.thisYear.kwh} kWh</div></div>
          <div className="compare-row"><div className="compare-label">Same period last year</div><div className="compare-val">{Math.round(d.lastYear.kwh/(365/118))} kWh</div></div>
          <div className="compare-row"><div className="compare-label">Full year 2025</div><div className="compare-val">{d.lastYear.kwh} kWh</div></div>
          <div className="bar-compare">
            <div className="bar-compare-fill" style={{width:"50%",background:"var(--accent)"}} />
            <div className="bar-compare-fill" style={{width:`${(Math.round(d.lastYear.kwh/(365/118))/d.thisYear.kwh)*50}%`,background:"#2d5a38"}} />
          </div>
        </div>
      </div>

      {/* RECORDS */}
      <div className="section-label">Records & Milestones</div>
      <div className="records-row">
        <div className="card" style={{background:"var(--surface2)"}}>
          <div className="card-label">🏆 Best Day Ever</div>
          <div style={{fontSize:28,fontWeight:800,color:"var(--accent)"}}>{d.bestDay.kwh} <span style={{fontSize:13,color:"var(--muted)",fontWeight:400}}>kWh</span></div>
          <div style={{fontSize:11,fontFamily:"Space Mono",color:"var(--muted)",marginTop:4}}>{d.bestDay.date}</div>
        </div>
        <div className="card" style={{background:"var(--surface2)"}}>
          <div className="card-label">🌧 Lowest Day (recent)</div>
          <div style={{fontSize:28,fontWeight:800,color:"var(--danger)"}}>{d.worstDay.kwh} <span style={{fontSize:13,color:"var(--muted)",fontWeight:400}}>kWh</span></div>
          <div style={{fontSize:11,fontFamily:"Space Mono",color:"var(--muted)",marginTop:4}}>{d.worstDay.date}</div>
        </div>
        <div className="card" style={{background:"var(--surface2)"}}>
          <div className="card-label">📊 Daily Avg — Last 30 Days</div>
          <div style={{fontSize:28,fontWeight:800,color:"var(--accent2)"}}>{(d.thisMonth.kwh/28).toFixed(1)} <span style={{fontSize:13,color:"var(--muted)",fontWeight:400}}>kWh</span></div>
          <div style={{fontSize:11,fontFamily:"Space Mono",color:"var(--muted)",marginTop:4}}>vs {(d.sameMonthLastYear.kwh/30).toFixed(1)} kWh last year</div>
        </div>
      </div>
    </>
  );
}

// ─── EFFICIENCY PAGE ──────────────────────────────────────────────────────────
function EfficiencyPage() {
  const baseline = efficiencyHistory[0].pr;
  const current = efficiencyHistory[efficiencyHistory.length - 1].pr;
  const degradationTotal = baseline - current;
  const years = 3.25;
  const annualDeg = (degradationTotal / years).toFixed(2);
  const warrantyDeg = 0.5;
  const prNow = ((current / baseline) * 100).toFixed(1);
  const kWInstalled = 8.4;
  const lostKwh = Math.round((degradationTotal / 100) * kWInstalled * 4.5 * 365);

  return (
    <>
      {/* TOP STATS — 2x2 */}
      <div className="eff-top">
        <div className="card card-accent">
          <div className="corner-glow" />
          <div className="card-label">System Efficiency Now</div>
          <div className="card-value" style={{color:"var(--accent)"}}>{prNow}<span className="val-unit">%</span></div>
          <div className="card-sub" style={{marginTop:8}}>of baseline at install — Jan 2023</div>
          <div style={{marginTop:16,fontSize:13,fontFamily:"Space Mono",color:"var(--muted)",lineHeight:1.6}}>
            Panels have lost <span style={{color:"var(--warn)",fontWeight:700}}>{degradationTotal.toFixed(1)} PR points</span> over {years} years
          </div>
        </div>

        <div className="card">
          <div className="card-label">Performance Ratio</div>
          <div className="card-value">{current}<span className="val-unit">%</span></div>
          <div className="card-sub" style={{marginTop:8}}>vs {baseline}% at install</div>
          <div className="deg-bar-wrap" style={{marginTop:18}}>
            <div className="deg-bar-track" style={{height:10}}>
              <div className="deg-bar-fill" style={{width:`${(current/baseline)*100}%`,background:"var(--accent2)"}} />
            </div>
            <div className="deg-labels" style={{marginTop:6}}>
              <span>{baseline}% baseline</span>
              <span style={{color:"var(--accent2)"}}>{current}% now</span>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-label">Annual Degradation Rate</div>
          <div className="card-value" style={{color: parseFloat(annualDeg) > warrantyDeg ? "var(--warn)" : "var(--accent2)"}}>
            {annualDeg}<span className="val-unit">%/yr</span>
          </div>
          <div className="card-sub" style={{marginTop:8}}>Warranty threshold: {warrantyDeg}%/yr</div>
          {parseFloat(annualDeg) > warrantyDeg
            ? <div className="anomaly" style={{marginTop:16}}>⚠ Degrading faster than warranty allows</div>
            : <div style={{marginTop:16,fontSize:12,fontFamily:"Space Mono",color:"var(--accent2)"}}>&#x2713; Within warranty parameters</div>
          }
        </div>

        <div className="card">
          <div className="card-label">Est. Lost Production</div>
          <div className="card-value" style={{color:"var(--warn)"}}>{lostKwh}<span className="val-unit">kWh</span></div>
          <div className="card-sub" style={{marginTop:8}}>due to degradation since install</div>
          <div style={{marginTop:16,fontSize:13,fontFamily:"Space Mono",color:"var(--muted)"}}>
            Approx. <span style={{color:"var(--warn)",fontWeight:700}}>${Math.round(lostKwh*0.12)}</span> in lost value at $0.12/kWh
          </div>
        </div>
      </div>

      {/* LINE CHART */}
      <div className="chart-wrap">
        <div className="chart-header">
          <div className="chart-title">Performance Ratio Over Time (%)</div>
          <div className="legend">
            <div className="legend-item"><div className="legend-dot" style={{background:"var(--accent)"}} /><span>Actual PR</span></div>
            <div className="legend-item"><div className="legend-dot" style={{background:"#2d5a38",border:"1px dashed #4a8a5a"}} /><span>Expected (0.5%/yr)</span></div>
            <div className="legend-item"><div className="legend-dot" style={{background:"var(--danger)"}} /><span>Anomaly</span></div>
          </div>
        </div>
        <div className="line-chart-wrap">
          <LineChart data={efficiencyHistory} />
        </div>
        <div className="anomaly" style={{marginTop:12}}>
          ⚠ Aug 2024 — PR dropped 1.1% below expected. Possible cause: dirty panels or shading. Recovered after cleaning.
        </div>
      </div>

      {/* TWO COL: YoY + Panel heatmap */}
      <div className="two-col">
        {/* Year over Year */}
        <div className="card">
          <div className="card-label">Year-over-Year Efficiency</div>
          <div style={{marginTop:8,display:"flex",flexDirection:"column",gap:14}}>
            {[
              {year:"2023 (Baseline)", pr: 82.9, pct: 100},
              {year:"2024", pr: 82.1, pct: 99.0},
              {year:"2025", pr: 81.6, pct: 98.4},
              {year:"2026 YTD", pr: 80.7, pct: 97.3},
            ].map(row => (
              <div key={row.year}>
                <div style={{display:"flex",justifyContent:"space-between",marginBottom:5}}>
                  <span style={{fontSize:12,fontFamily:"Space Mono",color:"var(--muted)"}}>{row.year}</span>
                  <span style={{fontSize:13,fontWeight:700,fontFamily:"Space Mono",color: row.pct < 98 ? "var(--warn)" : "var(--accent)"}}>
                    {row.pct}% <span style={{color:"var(--muted)",fontWeight:400,fontSize:11}}>({row.pr}% PR)</span>
                  </span>
                </div>
                <div className="deg-bar-track">
                  <div className="deg-bar-fill" style={{
                    width:`${row.pct}%`,
                    background: row.pct >= 99 ? "var(--accent2)" : row.pct >= 98 ? "var(--accent)" : "var(--warn)"
                  }} />
                </div>
              </div>
            ))}
          </div>
          <div className="info-box" style={{marginTop:16}}>
            At current rate, system will reach 95% efficiency around <strong style={{color:"var(--text)"}}>2029</strong>. Manufacturer warranty guarantees 80% output at year 25.
          </div>
        </div>

        {/* Panel Heatmap */}
        <div className="card">
          <div className="card-label">Panel-Level Efficiency Heatmap</div>
          <div className="panel-grid" style={{marginTop:8}}>
            {panels.map(p => (
              <div key={p.id} className="panel-cell" style={{background: panelColor(p.efficiency)}}
                title={`${p.id}: ${p.efficiency}%`}>
                <div className="panel-id">{p.id}</div>
                <div className="panel-pct">{p.efficiency}%</div>
              </div>
            ))}
          </div>
          <div className="panel-legend">
            {[
              {color:"#a3e635", label:"≥97%"},
              {color:"#facc15", label:"94–97%"},
              {color:"#fb923c", label:"88–94%"},
              {color:"#f87171", label:"<88%"},
            ].map(l => (
              <div key={l.label} className="panel-legend-item">
                <div className="panel-legend-swatch" style={{background:l.color}} />
                {l.label}
              </div>
            ))}
          </div>
          <div className="anomaly" style={{marginTop:12}}>
            ⚠ P07 at 82.1% — significantly underperforming. Check for shading or microinverter fault.
          </div>
        </div>
      </div>
    </>
  );
}

// ─── SETUP PAGE ───────────────────────────────────────────────────────────────
function SetupPage() {
  const [form, setForm] = useState(defaultSetup);
  const [saved, setSaved] = useState(false);

  const set = (k, v) => setForm(f => ({...f, [k]: v}));

  const save = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  };

  const hasApi = form.enphaseApiKey.length > 0 && form.enphaseSystemId.length > 0;

  return (
    <div className="setup-wrap">

      {/* API Credentials */}
      <div className="setup-section">
        <div className="setup-section-title">
          🔑 Enphase API Connection
          <span className={`status-pill ${hasApi ? "status-ok" : "status-missing"}`}>
            {hasApi ? "✓ Connected" : "Not connected"}
          </span>
        </div>
        <div className="form-grid">
          <div className="form-group">
            <div className="form-label">API Key</div>
            <input className="form-input" type="password" placeholder="Your Enphase API key"
              value={form.enphaseApiKey} onChange={e => set("enphaseApiKey", e.target.value)} />
          </div>
          <div className="form-group">
            <div className="form-label">System ID</div>
            <input className="form-input" type="text" placeholder="e.g. 12345678"
              value={form.enphaseSystemId} onChange={e => set("enphaseSystemId", e.target.value)} />
          </div>
        </div>
        <div className="info-box" style={{marginTop:12}}>
          Find your API key at developer-v4.enphase.com → Your Apps. System ID is visible in your Enlighten URL: enlighten.enphaseenergy.com/web/<strong>SYSTEM_ID</strong>/today
        </div>
      </div>

      {/* System Info */}
      <div className="setup-section">
        <div className="setup-section-title">⚡ System Specifications</div>
        <div className="form-grid">
          <div className="form-group">
            <div className="form-label">System Size (kW)</div>
            <input className="form-input" type="number" step="0.1" placeholder="e.g. 8.4"
              value={form.systemSize} onChange={e => set("systemSize", e.target.value)} />
            <div className="form-hint">Total installed DC capacity</div>
          </div>
          <div className="form-group">
            <div className="form-label">Install Date</div>
            <input className="form-input" type="date"
              value={form.installDate} onChange={e => set("installDate", e.target.value)} />
            <div className="form-hint">Used to calculate age and degradation baseline</div>
          </div>
          <div className="form-group">
            <div className="form-label">Panel Count</div>
            <input className="form-input" type="number" placeholder="e.g. 16"
              value={form.panelCount} onChange={e => set("panelCount", e.target.value)} />
          </div>
          <div className="form-group">
            <div className="form-label">Panel Wattage (W)</div>
            <input className="form-input" type="number" placeholder="e.g. 525"
              value={form.panelWattage} onChange={e => set("panelWattage", e.target.value)} />
          </div>
          <div className="form-group">
            <div className="form-label">Manufacturer / Inverter</div>
            <input className="form-input" type="text" placeholder="e.g. Enphase IQ8+"
              value={form.manufacturer} onChange={e => set("manufacturer", e.target.value)} />
          </div>
          <div className="form-group">
            <div className="form-label">Expected Degradation (%/yr)</div>
            <input className="form-input" type="number" step="0.1" placeholder="e.g. 0.5"
              value={form.degradationRate} onChange={e => set("degradationRate", e.target.value)} />
            <div className="form-hint">Check your panel warranty — typically 0.5%/yr</div>
          </div>
        </div>
      </div>

      {/* Location & Irradiance */}
      <div className="setup-section">
        <div className="setup-section-title">📍 Location & Solar Data</div>
        <div className="form-grid">
          <div className="form-group full">
            <div className="form-label">Location Name</div>
            <input className="form-input" type="text" placeholder="e.g. Montreal, QC"
              value={form.location} onChange={e => set("location", e.target.value)} />
          </div>
          <div className="form-group">
            <div className="form-label">Latitude</div>
            <input className="form-input" type="number" step="0.0001" placeholder="e.g. 45.5017"
              value={form.latitude} onChange={e => set("latitude", e.target.value)} />
          </div>
          <div className="form-group">
            <div className="form-label">Longitude</div>
            <input className="form-input" type="number" step="0.0001" placeholder="e.g. -73.5673"
              value={form.longitude} onChange={e => set("longitude", e.target.value)} />
          </div>
          <div className="form-group">
            <div className="form-label">Panel Tilt (°)</div>
            <input className="form-input" type="number" placeholder="e.g. 35"
              value={form.tiltAngle} onChange={e => set("tiltAngle", e.target.value)} />
            <div className="form-hint">Roof pitch angle from horizontal</div>
          </div>
          <div className="form-group">
            <div className="form-label">Azimuth (°)</div>
            <input className="form-input" type="number" placeholder="180 = south"
              value={form.azimuth} onChange={e => set("azimuth", e.target.value)} />
            <div className="form-hint">Panel facing direction (180° = true south)</div>
          </div>
          <div className="form-group full">
            <div className="form-label">Irradiance Data Source</div>
            <select className="form-select" value={form.irradianceSource}
              onChange={e => set("irradianceSource", e.target.value)}>
              <option value="nrel">NREL PVDAQ (USA/Canada)</option>
              <option value="nasa">NASA POWER (Global)</option>
              <option value="manual">Manual (no weather normalization)</option>
            </select>
            <div className="form-hint" style={{marginTop:6}}>
              Used to normalize production data for weather — enables true efficiency comparison year over year
            </div>
          </div>
        </div>
      </div>

      <div className="form-actions">
        <button className="btn btn-primary" onClick={save}>Save Configuration</button>
        <button className="btn btn-secondary" onClick={() => setForm(defaultSetup)}>Reset to Defaults</button>
      </div>

      {saved && <div className="save-toast">✓ Configuration saved</div>}
    </div>
  );
}

// ─── ROOT APP ─────────────────────────────────────────────────────────────────
export default function App() {
  const [page, setPage] = useState("overview");

  return (
    <>
      <style>{fonts}{css}</style>
      <div className="app">
        <div className="nav">
          <div>
            <div className="nav-logo">☀ Helio Monitor</div>
            <div className="nav-title">Solar Dashboard</div>
          </div>
          <div className="nav-tabs">
            {[
              {id:"overview", label:"Overview"},
              {id:"efficiency", label:"Efficiency"},
              {id:"setup", label:"⚙ Setup"},
            ].map(t => (
              <button key={t.id} className={`nav-tab ${page===t.id?"active":""}`}
                onClick={() => setPage(t.id)}>{t.label}</button>
            ))}
          </div>
          {page !== "setup" && (
            <div className="live-badge">
              <div className="live-dot" />
              <span style={{color:"var(--accent)",fontWeight:700}}>4.2 kW</span>
              <span style={{color:"var(--muted)"}}>live</span>
            </div>
          )}
        </div>

        {page === "overview" && <OverviewPage />}
        {page === "efficiency" && <EfficiencyPage />}
        {page === "setup" && <SetupPage />}
      </div>
    </>
  );
}
