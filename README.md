# ☀️ Helio Monitor

**The solar dashboard Enphase never built.**

Helio Monitor connects to your Enphase system and gives you the historical comparisons and efficiency tracking that the Enlighten app is missing — like knowing whether today's production beats the same day last year, whether your panels are degrading faster than the warranty allows, and which panel might be underperforming.

![The Helio Monitor Overview page, showing today's production, comparisons against the same day last year and last month, and year-to-date production for every year since install](docs/assets/preview.png)

<sub>The Overview page on the synthetic dataset `make seed-mock` generates. Current power reads "Unavailable" there because it is the one figure that comes from a live Enphase call rather than from stored history.</sub>

---

## What It Does

- **Historical comparisons** — Today so far vs. the same point in the same day last year, this month vs. same month last year, YTD vs. prior year
- **Efficiency tracking** — Performance Ratio trend since install, weather-normalized
- **Degradation alerts** — Flags when annual degradation exceeds your warranty threshold
- **Panel heatmap** — Spot underperforming microinverters at a glance
- **Owns your data** — Everything stored locally in PostgreSQL, no third-party cloud

### Efficiency

![The Helio Monitor Efficiency page, showing the Performance Ratio measured every month since install against the baseline the system was commissioned at, and the projection of that trend against the warranty threshold](docs/assets/efficiency.png)

Performance Ratio is the share of the energy available to the array that it actually delivered, so it separates a real decline from a cloudy month. The baseline it is judged against is the system's own first year, not a theoretical 100%, and the dotted line projects the measured trend forward so you can see it against your warranty before the warranty expires.

### Panels

![The Helio Monitor Panels page, showing a heatmap of thirty microinverters with one flagged as underperforming and a callout naming it](docs/assets/panels.png)

Every microinverter reports its own production, so a single shaded, soiled or failing panel shows up as a cold cell instead of disappearing into the system total.

---

## Deploy in One Click

### DigitalOcean (Recommended)

[![Deploy to DigitalOcean](https://www.deploytodo.com/do-btn-blue.svg)](https://cloud.digitalocean.com/apps/new?repo=https://github.com/stephaneminisini/Helio)

> 🎁 New to DigitalOcean? Use the referral link below for **$200 free credit** — enough to run Helio Monitor for months.
>
> **[→ Get $200 free credit on DigitalOcean](https://m.do.co/c/YOUR_REFERRAL_CODE)**

Full guide: [docs/deploy/digitalocean.md](docs/deploy/digitalocean.md)

### Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template?template=https://github.com/stephaneminisini/Helio)

> 🎁 New to Railway? Sign up with this link and get **$5 free credit**.
>
> **[→ Sign up on Railway](https://railway.app?referralCode=YOUR_CODE)**

Full guide: [docs/deploy/railway.md](docs/deploy/railway.md)

### Self-Host (Raspberry Pi / Home Server)

Prefer to keep everything local? Full guide: [docs/deploy/raspberry-pi.md](docs/deploy/raspberry-pi.md)

### Manual Docker Install

```bash
git clone https://github.com/stephaneminisini/Helio
cd Helio
make init          # copies .env.example to .env and generates FERNET_KEY
# Edit .env with your Enphase credentials
make up
make migrate
# Open http://localhost:3000, fill in the Setup tab, connect your Enphase account
make backfill
```

Full guide: [docs/INSTALL.md](docs/INSTALL.md)

---

## Prerequisites

- An Enphase solar system with an Enlighten account
- A free Enphase developer account at [developer-v4.enphase.com](https://developer-v4.enphase.com)
- Your Enphase API key and System ID

---

## ☕ Support This Project

Helio Monitor is free and open source. If it saves you money by catching a degrading panel early — or just makes your mornings a little more satisfying — consider buying me a coffee.

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-support-yellow?style=for-the-badge&logo=buy-me-a-coffee)](https://www.buymeacoffee.com/YOUR_USERNAME)

---

## Tech Stack

- **Backend:** Python 3.13, FastAPI, SQLAlchemy 2, APScheduler
- **Database:** PostgreSQL 15
- **Frontend:** React 18, Vite
- **Deployment:** Docker, Docker Compose

---

## Documentation

| Document | Description |
|----------|-------------|
| [docs/INSTALL.md](docs/INSTALL.md) | Full manual installation guide |
| [docs/deploy/digitalocean.md](docs/deploy/digitalocean.md) | DigitalOcean one-click deploy |
| [docs/deploy/railway.md](docs/deploy/railway.md) | Railway one-click deploy |
| [docs/deploy/raspberry-pi.md](docs/deploy/raspberry-pi.md) | Raspberry Pi / home server |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | All environment variables explained |
| [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) | How to contribute |

---

## License

MIT. Use it, change it, sell it; just keep the copyright notice. See [LICENSE](LICENSE).
