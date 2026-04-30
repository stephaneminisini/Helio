import { useState } from "react";

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

const pct = (a, b) => (((a - b) / b) * 100).toFixed(1);
const arrow = (a, b) => a >= b ? "↑" : "↓";
const color = (a, b) => a >= b ? "#4ade80" : "#f87171";

const fonts = `
  @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;600;700;800&display=swap');
`;

const styles = `
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg: #0a0f0d;
    --surface: #111a14;
    --surface2: #172019;
    --border: #1f3024;
    --accent: #a3e635;
    --accent2: #34d399;
    --accent3: #fb923c;
    --text: #e8f5e2;
    --muted: #5a7a62;
    --danger: #f87171;
  }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Syne', sans-serif;
    min-height: 100vh;
    padding: 0;
  }

  .app {
    max-width: 1100px;
    margin: 0 auto;
    padding: 32px 24px 64px;
  }

  /* HEADER */
  .header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: 40px;
    padding-bottom: 24px;
    border-bottom: 1px solid var(--border);
  }

  .header-left {}
  .logo {
    font-size: 11px;
    font-family: 'Space Mono', monospace;
    letter-spacing: 0.2em;
    color: var(--accent);
    text-transform: uppercase;
    margin-bottom: 6px;
  }
  .header-title {
    font-size: 32px;
    font-weight: 800;
    line-height: 1;
    color: var(--text);
  }
  .header-sub {
    font-size: 13px;
    color: var(--muted);
    margin-top: 6px;
    font-family: 'Space Mono', monospace;
  }

  .live-badge {
    display: flex;
    align-items: center;
    gap: 8px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 100px;
    padding: 10px 18px;
    font-family: 'Space Mono', monospace;
    font-size: 12px;
  }
  .live-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--accent);
    animation: pulse 2s infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
  }

  /* NOW ROW */
  .now-row {
    display: grid;
    grid-template-columns: 2fr 1fr 1fr;
    gap: 16px;
    margin-bottom: 20px;
  }

  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 24px;
    position: relative;
    overflow: hidden;
    transition: border-color 0.2s;
  }
  .card:hover { border-color: var(--muted); }

  .card-accent {
    background: linear-gradient(135deg, #1a2e1e 0%, #111a14 100%);
    border-color: #2a4030;
  }

  .card-label {
    font-size: 10px;
    font-family: 'Space Mono', monospace;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 12px;
  }

  .card-value {
    font-size: 48px;
    font-weight: 800;
    line-height: 1;
    color: var(--text);
  }
  .card-value span {
    font-size: 18px;
    font-weight: 400;
    color: var(--muted);
    margin-left: 4px;
  }

  .card-value-med {
    font-size: 32px;
    font-weight: 800;
    line-height: 1;
  }

  .card-value-sm {
    font-size: 22px;
    font-weight: 700;
    line-height: 1;
  }

  .card-sub {
    font-size: 12px;
    color: var(--muted);
    margin-top: 6px;
    font-family: 'Space Mono', monospace;
  }

  .delta {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 13px;
    font-family: 'Space Mono', monospace;
    font-weight: 700;
    margin-top: 10px;
    padding: 4px 10px;
    border-radius: 100px;
    background: rgba(0,0,0,0.3);
  }

  /* CHART */
  .chart-section {
    margin-bottom: 20px;
  }

  .chart-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
  }

  .chart-title {
    font-size: 14px;
    font-weight: 700;
    color: var(--text);
  }

  .legend {
    display: flex;
    gap: 16px;
  }
  .legend-item {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    font-family: 'Space Mono', monospace;
    color: var(--muted);
  }
  .legend-dot {
    width: 8px;
    height: 8px;
    border-radius: 2px;
  }

  .chart-wrap {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 20px 24px 12px;
    position: relative;
  }

  .chart-area {
    display: flex;
    align-items: flex-end;
    gap: 3px;
    height: 120px;
  }

  .bar-group {
    flex: 1;
    display: flex;
    align-items: flex-end;
    gap: 1px;
    height: 100%;
  }

  .bar {
    flex: 1;
    border-radius: 3px 3px 0 0;
    transition: opacity 0.2s;
    cursor: pointer;
    position: relative;
  }
  .bar:hover { opacity: 0.85; }
  .bar-today { background: var(--accent); }
  .bar-last-year { background: #2d5a38; }

  .chart-labels {
    display: flex;
    gap: 3px;
    margin-top: 6px;
  }
  .chart-label {
    flex: 1;
    text-align: center;
    font-size: 9px;
    font-family: 'Space Mono', monospace;
    color: var(--muted);
  }

  /* COMPARISON GRID */
  .section-title {
    font-size: 10px;
    font-family: 'Space Mono', monospace;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 12px;
  }

  .compare-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
    margin-bottom: 20px;
  }

  .compare-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 20px;
  }

  .compare-period {
    font-size: 10px;
    font-family: 'Space Mono', monospace;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 16px;
  }

  .compare-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 0;
    border-bottom: 1px solid var(--border);
  }
  .compare-row:last-child { border-bottom: none; }

  .compare-label {
    font-size: 11px;
    color: var(--muted);
  }

  .compare-val {
    font-size: 14px;
    font-weight: 700;
    font-family: 'Space Mono', monospace;
  }

  .compare-val.highlight {
    color: var(--accent);
  }

  .bar-compare {
    height: 4px;
    border-radius: 2px;
    margin-top: 10px;
    overflow: hidden;
    background: var(--border);
    display: flex;
    gap: 2px;
  }
  .bar-compare-fill {
    height: 100%;
    border-radius: 2px;
  }

  /* RECORDS ROW */
  .records-row {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
    margin-bottom: 20px;
  }

  .record-card {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  /* TABS */
  .tabs {
    display: flex;
    gap: 4px;
    margin-bottom: 20px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 4px;
    width: fit-content;
  }
  .tab {
    padding: 8px 20px;
    border-radius: 8px;
    font-size: 12px;
    font-family: 'Space Mono', monospace;
    cursor: pointer;
    border: none;
    background: transparent;
    color: var(--muted);
    transition: all 0.15s;
  }
  .tab.active {
    background: var(--accent);
    color: #0a0f0d;
    font-weight: 700;
  }

  .corner-glow {
    position: absolute;
    top: -30px;
    right: -30px;
    width: 100px;
    height: 100px;
    background: radial-gradient(circle, rgba(163,230,53,0.08) 0%, transparent 70%);
    pointer-events: none;
  }
`;

const hourLabels = ["12a","","","","","","6a","","","","","","12p","","","","","","6p","","","","",""];
const MAX_KW = 8;

export default function SolarDashboard() {
  const [tab, setTab] = useState("day");
  const d = mockData;

  const todayPct = pct(d.today.kwh, d.sameDay1YearAgo.kwh);
  const monthPct = pct(d.thisMonth.kwh, d.sameMonthLastYear.kwh);
  const yearPct = pct(d.thisYear.kwh, d.lastYear.kwh / (365/118)); // YTD approx

  return (
    <>
      <style>{fonts}{styles}</style>
      <div className="app">

        {/* HEADER */}
        <div className="header">
          <div className="header-left">
            <div className="logo">☀ Helio Monitor</div>
            <div className="header-title">Solar Overview</div>
            <div className="header-sub">Last sync: 2 min ago · Apr 28, 2026</div>
          </div>
          <div className="live-badge">
            <div className="live-dot" />
            <span style={{color:"var(--accent)", fontWeight:700}}>{d.currentPower} kW</span>
            <span style={{color:"var(--muted)"}}>live</span>
          </div>
        </div>

        {/* NOW ROW */}
        <div className="now-row">
          <div className="card card-accent">
            <div className="corner-glow" />
            <div className="card-label">Production Today</div>
            <div className="card-value">{d.today.kwh}<span>kWh</span></div>
            <div style={{display:"flex", gap:10, marginTop:12, flexWrap:"wrap"}}>
              <div className="delta" style={{color: color(d.today.kwh, d.sameDay1YearAgo.kwh)}}>
                {arrow(d.today.kwh, d.sameDay1YearAgo.kwh)} {Math.abs(todayPct)}% vs last year
              </div>
              <div className="delta" style={{color: color(d.today.kwh, d.sameDay1MonthAgo.kwh)}}>
                {arrow(d.today.kwh, d.sameDay1MonthAgo.kwh)} {Math.abs(pct(d.today.kwh, d.sameDay1MonthAgo.kwh))}% vs last month
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-label">Current Power</div>
            <div className="card-value-med" style={{color:"var(--accent)"}}>{d.currentPower}<span style={{fontSize:14,color:"var(--muted)",marginLeft:4}}>kW</span></div>
            <div className="card-sub" style={{marginTop:10}}>Peak today</div>
            <div style={{fontSize:18, fontWeight:700, fontFamily:"Space Mono", color:"var(--text)"}}>{d.peakToday} kW</div>
          </div>

          <div className="card">
            <div className="card-label">All-Time Total</div>
            <div className="card-value-med">{(d.allTime.kwh/1000).toFixed(1)}<span style={{fontSize:14,color:"var(--muted)",marginLeft:4}}>MWh</span></div>
            <div className="card-sub" style={{marginTop:10}}>Since installation</div>
            <div style={{fontSize:12, color:"var(--accent2)", fontFamily:"Space Mono", marginTop:4}}>≈ {Math.round(d.allTime.kwh * 0.85)} lbs CO₂ saved</div>
          </div>
        </div>

        {/* HOURLY CHART */}
        <div className="chart-section">
          <div className="chart-wrap">
            <div className="chart-header">
              <div className="chart-title">Today vs. Same Day Last Year — Hourly (kW)</div>
              <div className="legend">
                <div className="legend-item">
                  <div className="legend-dot" style={{background:"var(--accent)"}} />
                  <span>Today</span>
                </div>
                <div className="legend-item">
                  <div className="legend-dot" style={{background:"#2d5a38"}} />
                  <span>Apr 28, 2025</span>
                </div>
              </div>
            </div>
            <div className="chart-area">
              {d.hourly.map((val, i) => (
                <div key={i} className="bar-group">
                  <div
                    className="bar bar-last-year"
                    style={{ height: `${(d.hourlyLastYear[i] / MAX_KW) * 100}%`, minHeight: d.hourlyLastYear[i] > 0 ? 2 : 0 }}
                    title={`${hourLabels[i]} last year: ${d.hourlyLastYear[i]} kW`}
                  />
                  <div
                    className="bar bar-today"
                    style={{ height: `${(val / MAX_KW) * 100}%`, minHeight: val > 0 ? 2 : 0 }}
                    title={`${hourLabels[i]}: ${val} kW`}
                  />
                </div>
              ))}
            </div>
            <div className="chart-labels">
              {hourLabels.map((l, i) => (
                <div key={i} className="chart-label">{l}</div>
              ))}
            </div>
          </div>
        </div>

        {/* PERIOD TABS */}
        <div className="tabs">
          {["day","month","year"].map(t => (
            <button key={t} className={`tab ${tab===t?"active":""}`} onClick={()=>setTab(t)}>
              {t.charAt(0).toUpperCase()+t.slice(1)}
            </button>
          ))}
        </div>

        {/* COMPARISON CARDS */}
        <div className="section-title">Period Comparisons</div>
        <div className="compare-grid">

          {/* TODAY */}
          <div className="compare-card">
            <div className="compare-period">📅 Today — {d.today.date}</div>
            <div className="compare-row">
              <div className="compare-label">Today</div>
              <div className="compare-val highlight">{d.today.kwh} kWh</div>
            </div>
            <div className="compare-row">
              <div className="compare-label">Same day last year</div>
              <div className="compare-val">{d.sameDay1YearAgo.kwh} kWh</div>
            </div>
            <div className="compare-row">
              <div className="compare-label">Same day last month</div>
              <div className="compare-val">{d.sameDay1MonthAgo.kwh} kWh</div>
            </div>
            <div className="bar-compare">
              <div className="bar-compare-fill" style={{width:`${(d.sameDay1YearAgo.kwh/d.today.kwh)*50}%`, background:"#2d5a38"}} />
              <div className="bar-compare-fill" style={{width:"50%", background:"var(--accent)"}} />
            </div>
          </div>

          {/* THIS MONTH */}
          <div className="compare-card">
            <div className="compare-period">📆 {d.thisMonth.label}</div>
            <div className="compare-row">
              <div className="compare-label">This month</div>
              <div className="compare-val highlight">{d.thisMonth.kwh} kWh</div>
            </div>
            <div className="compare-row">
              <div className="compare-label">Same month last year</div>
              <div className="compare-val">{d.sameMonthLastYear.kwh} kWh</div>
            </div>
            <div className="compare-row">
              <div className="compare-label">Last month</div>
              <div className="compare-val">{d.lastMonth.kwh} kWh</div>
            </div>
            <div className="bar-compare">
              <div className="bar-compare-fill" style={{width:`${(d.thisMonth.kwh/d.sameMonthLastYear.kwh)*50}%`, background:"var(--accent)"}} />
              <div className="bar-compare-fill" style={{width:"50%", background:"#2d5a38"}} />
            </div>
          </div>

          {/* THIS YEAR */}
          <div className="compare-card">
            <div className="compare-period">📈 {d.thisYear.label}</div>
            <div className="compare-row">
              <div className="compare-label">YTD (118 days)</div>
              <div className="compare-val highlight">{d.thisYear.kwh} kWh</div>
            </div>
            <div className="compare-row">
              <div className="compare-label">Same period last year</div>
              <div className="compare-val">{Math.round(d.lastYear.kwh / (365/118))} kWh</div>
            </div>
            <div className="compare-row">
              <div className="compare-label">Full year 2025</div>
              <div className="compare-val">{d.lastYear.kwh} kWh</div>
            </div>
            <div className="bar-compare">
              <div className="bar-compare-fill" style={{width:"50%", background:"var(--accent)"}} />
              <div className="bar-compare-fill" style={{width:`${(Math.round(d.lastYear.kwh/(365/118))/d.thisYear.kwh)*50}%`, background:"#2d5a38"}} />
            </div>
          </div>
        </div>

        {/* RECORDS */}
        <div className="section-title">Records & Milestones</div>
        <div className="records-row">
          <div className="record-card">
            <div className="card-label">🏆 Best Day Ever</div>
            <div style={{fontSize:28, fontWeight:800, color:"var(--accent)"}}>{d.bestDay.kwh} <span style={{fontSize:14, color:"var(--muted)", fontWeight:400}}>kWh</span></div>
            <div style={{fontSize:11, fontFamily:"Space Mono", color:"var(--muted)", marginTop:4}}>{d.bestDay.date}</div>
          </div>
          <div className="record-card">
            <div className="card-label">🌧 Lowest Day (recent)</div>
            <div style={{fontSize:28, fontWeight:800, color:"var(--danger)"}}>{d.worstDay.kwh} <span style={{fontSize:14, color:"var(--muted)", fontWeight:400}}>kWh</span></div>
            <div style={{fontSize:11, fontFamily:"Space Mono", color:"var(--muted)", marginTop:4}}>{d.worstDay.date}</div>
          </div>
          <div className="record-card">
            <div className="card-label">📊 Daily Avg — Last 30 Days</div>
            <div style={{fontSize:28, fontWeight:800, color:"var(--accent2)"}}>{(d.thisMonth.kwh/28).toFixed(1)} <span style={{fontSize:14, color:"var(--muted)", fontWeight:400}}>kWh</span></div>
            <div style={{fontSize:11, fontFamily:"Space Mono", color:"var(--muted)", marginTop:4}}>vs {(d.sameMonthLastYear.kwh/30).toFixed(1)} kWh last year</div>
          </div>
        </div>

      </div>
    </>
  );
}
