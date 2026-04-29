# Business Requirements Document
## Helio Monitor — Personal Solar Analytics Platform

**Version:** 1.0  
**Date:** April 28, 2026  
**Author:** Stephane  
**Status:** Draft

---

## 1. Executive Summary

Helio Monitor is a personal solar energy analytics platform built to address the limitations of the Enphase Enlighten app. The platform will collect, store, and visualize historical solar production data with a focus on meaningful time-based comparisons and long-term system health tracking — capabilities absent from the native Enphase experience.

---

## 2. Problem Statement

The Enphase Enlighten app provides basic real-time monitoring but lacks:

- The ability to compare production on the same day, month, or year-to-date against prior periods
- Any meaningful system efficiency or degradation tracking over time
- Panel-level performance trending
- Weather-normalized performance analysis
- A local copy of historical data the owner controls

As a result, the system owner has no reliable way to know whether their system is performing as expected, degrading faster than the warranty allows, or whether a specific panel may be failing.

---

## 3. Goals & Objectives

| # | Goal | Success Metric |
|---|------|----------------|
| G1 | Surface historical production comparisons | User can view today vs. same day 1yr ago within 1 click |
| G2 | Track system efficiency over time | PR % chart available from install date to present |
| G3 | Detect degradation anomalies | Alert when annual degradation exceeds warranty threshold |
| G4 | Identify underperforming panels | Panel heatmap flags outliers > 2 std deviations below mean |
| G5 | Own the data locally | All Enphase data stored in a self-hosted Postgres database |

---

## 4. Scope

### 4.1 In Scope

- Data ingestion from the Enphase API v4 (OAuth 2.0, personal account)
- Local PostgreSQL storage of raw interval data and derived summaries
- Web dashboard with three views: Overview, Efficiency, and Setup
- Historical comparison engine (day / month / year-over-year)
- Performance Ratio calculation with weather normalization via NREL or NASA POWER API
- Panel-level efficiency heatmap (where microinverter data is available)
- System configuration UI to capture data not available via API
- Degradation trending and warranty threshold alerting

### 4.2 Out of Scope

- Multi-user / multi-system support
- Mobile native app
- Integration with utility billing systems
- Battery/storage monitoring (future phase)
- Distribution or commercialization of the platform

---

## 5. Functional Requirements

### 5.1 Data Collection

- **BR-01:** The system shall poll the Enphase API daily and store all available production interval data (15-minute resolution)
- **BR-02:** The system shall refresh OAuth tokens automatically without user intervention
- **BR-03:** The system shall detect and handle API gaps gracefully, backfilling missed intervals on the next successful poll
- **BR-04:** The system shall collect irradiance data from an external weather API (NREL PVDAQ or NASA POWER) to support weather-normalized efficiency calculations

### 5.2 Historical Comparisons

- **BR-05:** The system shall display today's production alongside the same calendar day 1 year ago and 1 month ago
- **BR-06:** The system shall display current month production alongside the same month last year and the previous month
- **BR-07:** The system shall display year-to-date production alongside the equivalent period in prior years
- **BR-08:** The system shall show percentage deltas (positive/negative) for all comparison pairs

### 5.3 Efficiency & Degradation

- **BR-09:** The system shall calculate monthly Performance Ratio (PR) = actual kWh / theoretical max kWh, normalized by irradiance
- **BR-10:** The system shall plot PR over the full system lifetime as a trend line
- **BR-11:** The system shall overlay an expected degradation curve based on the configured degradation rate (default 0.5%/yr)
- **BR-12:** The system shall flag months where actual PR falls more than 1.5% below expected as anomalies
- **BR-13:** The system shall calculate annual degradation rate and compare against the manufacturer warranty threshold
- **BR-14:** The system shall estimate total production lost (kWh and dollar value) due to degradation

### 5.4 Panel-Level Monitoring

- **BR-15:** The system shall display a heatmap of individual panel efficiency where microinverter data is available
- **BR-16:** The system shall flag panels performing more than 2 standard deviations below the fleet average

### 5.5 Setup & Configuration

- **BR-17:** The user shall be able to enter system specifications not available via API (system size, install date, panel count, wattage, tilt, azimuth, degradation rate)
- **BR-18:** The user shall be able to configure Enphase API credentials through the UI
- **BR-19:** The user shall be able to select the irradiance data source
- **BR-20:** Configuration shall persist across sessions

---

## 6. Non-Functional Requirements

| Category | Requirement |
|----------|-------------|
| Performance | Dashboard loads within 2 seconds for any time range |
| Availability | Self-hosted; no uptime SLA required |
| Data Retention | All interval data retained indefinitely |
| Security | API credentials stored encrypted at rest; not exposed in UI |
| Portability | Runs on any Linux host with Python 3.11+ and PostgreSQL 15+ |
| Maintainability | Codebase documented; schema migrations versioned |

---

## 7. Assumptions & Constraints

- The Enphase Watt plan (free tier) provides sufficient API access for a single-system personal deployment
- The NREL PVDAQ or NASA POWER API provides adequate irradiance resolution for weather normalization
- The system will run on a single host (Raspberry Pi, home server, or VPS)
- Internet access is required for API polling; dashboard remains accessible on LAN if internet is unavailable

---

## 8. Stakeholders

| Role | Name | Responsibility |
|------|------|----------------|
| Owner / User | Stephane | Requirements, testing, operations |
| Developer | Stephane + AI Agents | Implementation |

---

## 9. Success Criteria

The project is considered successful when:

1. All Enphase production data from install date is stored locally in Postgres
2. The dashboard surfaces same-day, same-month, and same-year comparisons accurately
3. The PR trend chart covers the full system lifetime with anomaly flagging
4. The poller runs unattended daily without manual intervention
5. A degradation warning fires correctly when the annual rate exceeds the configured threshold

---

## 10. Distribution & Open Source

### 10.1 Distribution Model

Helio Monitor will be distributed as a free, open-source project on GitHub under the MIT license. The project sustains itself through two voluntary revenue streams:

- **Buy Me a Coffee** — one-time voluntary contributions from users who find the project valuable
- **Platform referrals** — DigitalOcean and Railway referral programs pay a small credit when users sign up via the project's referral links

### 10.2 One-Click Deploy Targets

| Platform | Deploy Method | Referral Benefit to User | Referral Benefit to Project |
|----------|--------------|-------------------------|----------------------------|
| DigitalOcean | "Deploy to DO" button + `app.yaml` | $200 free credit | $25 credit per qualifying signup |
| Railway | "Deploy on Railway" button | Free starter credit | Small credit per signup |
| Self-hosted | Docker Compose + Make | Free | None |

### 10.3 Documentation Requirements

The repository must include the following documentation to support self-service installation:

- **BR-21:** A `README.md` at repo root with one-click deploy buttons, referral links, and Buy Me a Coffee badge
- **BR-22:** A `docs/INSTALL.md` with step-by-step manual installation instructions covering all platforms
- **BR-23:** Platform-specific guides for DigitalOcean, Railway, and Raspberry Pi
- **BR-24:** A `docs/CONFIGURATION.md` with full environment variable reference
- **BR-25:** A `docs/CONTRIBUTING.md` for community contributors
- **BR-26:** A `.env.example` file with all variables documented and safe defaults

### 10.4 Constraints

- No user data is collected by the project author — the app is fully self-hosted
- Referral links are clearly disclosed in documentation
- Buy Me a Coffee is framed as optional; the app is fully functional without any payment
