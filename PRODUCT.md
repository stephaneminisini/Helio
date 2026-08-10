# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

**Primary:** a residential solar owner with an Enphase system who self-hosts this
dashboard on their own hardware or cloud account. Confirmed 2026-08-10: this is
designed as a **public self-hosted product**, not a private tool — strangers deploy
it in one click and judge it within the first minute, so first-run and empty states
carry as much weight as the data views. This resolves the contradiction between
`docs/brd.md` §4.2 (lists distribution as out of scope) and §10 (commits to GitHub
distribution, one-click deploy, and referral funding) in favor of §10.

**Entry gate:** using the product at all requires an Enphase system, an Enlighten
account, a free developer account at developer-v4.enphase.com, and an API key plus
System ID. Nobody sees real data without completing that first.

**Author and first operator:** Stephane (`docs/brd.md` §8), who owns requirements,
testing, and operations.

**Secondary:** community contributors (`docs/CONTRIBUTING.md`).

## Product Purpose

Collect, store, and visualize historical solar production so an owner can tell
whether their system is performing as expected, degrading faster than the warranty
allows, or hiding a failing panel — the questions the Enphase Enlighten app does
not answer. Enlighten covers real-time and recent production but offers no
prior-period comparison, no lifetime efficiency trend, no degradation verdict, and
no owner-controlled copy of the data.

Success, per `docs/brd.md` §9: every interval since the install date is stored
locally; day, month, and year-over-year comparisons are accurate; the Performance
Ratio trend spans the full system lifetime with anomaly flagging; the poller runs
unattended daily; and a degradation warning fires correctly when the annual rate
exceeds the configured threshold.

## Positioning

The product owns a complete local copy of 15-minute interval history since install
and derives weather-normalized Performance Ratio against it. A hosted monitoring
product could copy the charts but not the claim underneath them: the data lives in
the owner's own Postgres, on the owner's own host, with nothing reported back to
the project author.

## Operating Context

**Two confirmed usage scenes, both first-class (confirmed 2026-08-10):**

1. **Morning phone glance.** Checked once a day on a phone. The "did today beat the
   same day last year" answer has to land in one viewport with no scrolling.
2. **Desktop deep-dive.** Opened on a laptop when something looks off, where dense
   charts and multi-year context outrank glanceability.

Explicitly *not* designed around an always-on wall display or a monthly-only review
ritual; neither was selected.

**Data rhythm.** Ingestion is a single daily cron job (APScheduler, default 04:00
in the configured timezone) running inside the API process. The product is not
live: it presents yesterday as complete and today as partial. Nothing in the UI
should imply real-time telemetry.

**Deployment targets.** DigitalOcean App Platform (one-click via `.do/app.yaml`),
Railway template, Raspberry Pi or home server, and manual Docker Compose. Always a
single host. Internet access is required for polling; the dashboard stays reachable
on the LAN when the internet is down.

**First run.** Deploy, set environment variables, run migrations, then backfill from
the install date. Backfill walks day by day with a deliberate pause between days and
can take several minutes on a multi-year system — so a new deployment is opened
first with no data, then with partial data, before it is ever complete.

**Operations surface.** A Makefile plus `docs/`, not a UI. There is no admin screen.

## Capabilities and Constraints

**Built and working**

- Daily poll of 15-minute production intervals from Enphase API v4, with automatic
  OAuth token refresh, backoff on rate limits, gap detection, and a `poll_log`
  audit trail.
- Daily irradiance from NREL or NASA POWER, transposed to plane-of-array.
- Daily and monthly rollups; every API response reads from these summaries, never
  from raw intervals.
- Day, month, and year-to-date comparisons with percentage deltas.
- Lifetime Performance Ratio trend with an expected-PR degradation overlay.
- Anomaly flagging when actual PR falls more than 1.5% below expected.
- Annual degradation rate compared against a 0.7%/yr warranty threshold.
- Lost production estimate in kWh and dollars.
- System specification form: name, location, size, panel count and wattage, install
  date, tilt, azimuth, degradation rate (default 0.5%/yr), and irradiance source.

**Committed but unbuilt** (confirmed 2026-08-10)

- **Panel-level efficiency heatmap**, flagging microinverters more than 2 standard
  deviations below the fleet average (`docs/brd.md` G4, BR-15, BR-16; also
  advertised in `README.md`). No panel-level table, endpoint, or UI exists today;
  delivering it requires per-microinverter ingestion and a schema change. Future
  design work should plan for this surface.

**Dropped as commitments** (confirmed 2026-08-10)

- **Enphase credential entry through the UI** (BR-18). Credentials stay
  environment-only; `helio/core/crypto.py` exists for this and is currently unused.
- **Live / current power.** `current_power_w` is present in the API contract and the
  TypeScript interface but is always null. Either remove it from the contract or
  stop advertising it; do not design around it.

The docs and README still promise both. They should be corrected rather than
carried forward as product truth.

**Hard constraints**

- **Single system by design.** Every route and job selects one system. Multi-user
  and multi-system are out of scope.
- **"Weather-normalized" is only literally true on NASA POWER.** The default NREL
  source returns 30-year TMY annual averages and ignores the requested date, so PR
  trends computed against it are weather-insensitive by construction. Never claim
  per-day weather normalization for the default configuration.
- Freshness is daily, not live.
- The scheduler runs inside the API process, so a second API replica double-polls.
- The free Enphase "Watt" plan is assumed sufficient for one personal system.
- Credentials are encrypted at rest and never exposed in the UI.
- Interval data is retained indefinitely; all energy values are exact decimals.
- Runs on Linux with PostgreSQL 15+. Python: `backend/pyproject.toml` requires
  3.13+, while `docs/brd.md` still says 3.11+ — the packaging metadata is
  authoritative and the BRD line is stale.
- Dashboard performance target: loads within 2 seconds for any time range.

**Out of scope** (`docs/brd.md` §4.2): multi-user or multi-system support, a native
mobile app, utility billing integration, and battery/storage monitoring (named as a
future phase, not a current commitment).

**Explicitly undecided — do not invent an answer**

- No accessibility standard has been established for the project.
- No internationalization exists. `docs/CONTRIBUTING.md` invites translations, but
  there is no i18n framework and no committed language list.
- Whether to correct `docs/brd.md` §4.2 to match the confirmed public-product
  decision.

## Brand Commitments

- **Name:** Helio Monitor.
- **Tagline in use:** "The solar dashboard Enphase never built."
- **Committed repository description** (`docs/PUBLISH_CHECKLIST.md`): "The solar
  dashboard Enphase never built — historical comparisons, efficiency tracking, and
  degradation alerts."
- **MIT licensed, free, and open source.** The app must remain fully functional
  without any payment.
- **Funding is voluntary and disclosed:** Buy Me a Coffee plus DigitalOcean and
  Railway referral links, with referral relationships stated in the documentation.
- **No user data is collected by the author. No telemetry.** This is a positioning
  claim, so the product must never quietly break it.
- **Voice in existing docs:** plain, direct, second person, benefit-first, with
  light warmth ("makes your mornings a little more satisfying"). Not an enterprise
  register.
- No visual direction has been made binding by the user. Palette, typography, and
  visual system belong in DESIGN.md, not here.

## Evidence on Hand

**Real material that exists**

- Product and technical documentation: `docs/brd.md`, `docs/trd.md`,
  `docs/dev-plan.md`, `docs/INSTALL.md`, `docs/CONFIGURATION.md`,
  `docs/CONTRIBUTING.md`, `docs/PUBLISH_CHECKLIST.md`, and platform guides under
  `docs/deploy/`.
- Real-shaped Enphase API payloads: `backend/tests/fixtures/enphase_intervals.json`
  and `enphase_system.json`.
- Deployment spec: `.do/app.yaml`.
- Unreferenced design prototypes outside the build: `frontend/src/solar-app.jsx`
  and `frontend/src/solar-dashboard.jsx`.

**Absences that future work must not fabricate**

- **No screenshot or preview image.** `README.md` links `docs/assets/preview.png`;
  `docs/assets/` does not exist. `PUBLISH_CHECKLIST.md` also wants a social preview
  image that has not been made.
- **No LICENSE file**, despite MIT being claimed in the README and BRD.
- **The project is not published yet.** `YOUR_USERNAME`, `YOUR_REFERRAL_CODE`,
  `YOUR_CODE`, and `YOUR_BMC_USERNAME` are still unreplaced across the README,
  `.do/app.yaml`, and `docs/`. There is no live repo URL, no demo URL, no star
  count.
- **No testimonials, named users, install counts, benchmarks, case studies, or
  press.** None may be invented.
- **No real production dataset in the repo.** Mock/seed mode is documented in
  `docs/CONTRIBUTING.md` but was never implemented, so any screenshot or demo needs
  real or deliberately generated data first.

## Product Principles

1. **Answer the comparison question first.** The only reason to open this instead of
   Enlighten is "how does this compare to before." That answer outranks every other
   element on the surface.
2. **Never imply more confidence than the data supports.** Incomplete days, missing
   intervals, failed polls, and the NREL annual-average caveat must stay visible
   rather than being smoothed into a clean number.
3. **A stranger's first deploy is the product's first impression.** The dashboard
   will be opened with zero rows, then with a partial backfill. Empty and
   mid-backfill states are primary states, not fallbacks.
4. **Two scenes, both first-class.** A phone glance resolves in one viewport; a
   desktop session supports investigation across years. Neither is a degraded
   version of the other.
5. **The owner keeps their data.** Self-hosted, no telemetry, no third-party cloud.
   Any feature that would weaken this is off the table, not a tradeoff.
