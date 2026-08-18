# Deploy on Raspberry Pi / Home Server

Running Helio Monitor on a Raspberry Pi or home server keeps everything local on your network — no cloud costs, no data leaving your home. A Pi 4 (2GB RAM) or any always-on Linux machine works well.

---

## Recommended Hardware

| Option | Notes |
|--------|-------|
| Raspberry Pi 4 (2GB+) | Best value for a dedicated device |
| Raspberry Pi 5 | Faster, runs cooler |
| Any Linux server/NAS | Works if it runs Docker |
| Old laptop or mini PC | Perfectly fine |

---

## Prerequisites

### Install Docker on Raspberry Pi

```bash
# Update packages
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Install Docker Compose plugin
sudo apt install -y docker-compose-plugin

# Verify
docker --version
docker compose version
```

Log out and back in for the group change to take effect.

### Install Git and Make

```bash
sudo apt install -y git make
```

---

## Installation

### Step 1 — Clone the repository

```bash
cd ~
git clone https://github.com/stephaneminisini/Helio.git
cd Helio
```

### Step 2 — Configure

```bash
cp .env.example .env
nano .env
```

Fill in your values (see [docs/INSTALL.md](../INSTALL.md#step-3--edit-env) for full variable reference).

Set `FRONTEND_BASE_URL` and `ENPHASE_REDIRECT_URI` to your Pi's address rather than `localhost`, so the Enphase consent flow can send your browser back:

```bash
FRONTEND_BASE_URL=http://<pi-ip>:3000
ENPHASE_REDIRECT_URI=http://<pi-ip>:3000/api/auth/enphase/callback
```

Port 3000 serves the dashboard and proxies `/api` to the API, so it is the only port to expose. Change it with `HELIO_PORT` — no rebuild needed.

Generate your Fernet key:
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Step 3 — Start

```bash
make up
```

First run pulls Docker images and may take 5–10 minutes on a Pi. Subsequent starts are fast.

### Step 4 — Create the database schema

```bash
make migrate
```

The API container starts `uvicorn` and nothing else, so this is a separate step.
Skip it and every endpoint answers 500, because the tables it queries do not
exist yet.

### Step 5 — Authorize and Backfill

```bash
# Open dashboard in browser at http://<your-pi-ip>:3000
# Go to Setup tab, fill in the form, click Create System
# Then click Connect to Enphase and authorize

# Then run the backfill
make backfill
```

---

## Find Your Pi's IP Address

```bash
hostname -I | awk '{print $1}'
```

Access the dashboard from any device on your network at `http://<pi-ip>:3000`.

---

## Auto-Start on Boot

Install the systemd service so Helio Monitor starts automatically when the Pi powers on:

```bash
make enable-autostart
```

This creates `/etc/systemd/system/helio-monitor.service` and enables it.

To check the service status:
```bash
sudo systemctl status helio-monitor
```

To view logs:
```bash
sudo journalctl -u helio-monitor -f
```

---

## Access From Outside Your Home (Optional)

By default the dashboard is only accessible on your local network. To access it remotely:

### Option A — Tailscale (Recommended, Free)

Tailscale creates a private VPN so you can reach your Pi from anywhere without opening firewall ports.

```bash
# Install Tailscale on the Pi
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# Install Tailscale on your phone/laptop and sign in
# Access dashboard at http://<tailscale-pi-ip>:3000
```

### Option B — Cloudflare Tunnel (Free)

```bash
# Install cloudflared
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
sudo dpkg -i cloudflared-linux-arm64.deb

# Authenticate and create tunnel
cloudflared tunnel login
cloudflared tunnel create helio-monitor
cloudflared tunnel route dns helio-monitor solar.yourdomain.com
cloudflared tunnel run helio-monitor
```

### Option C — Port Forwarding (Not recommended)

Opening ports directly to the internet exposes your Pi. Use Tailscale or Cloudflare instead.

---

## Storage Considerations

Solar data at 15-minute intervals grows slowly:

| Timeframe | Approximate DB Size |
|-----------|-------------------|
| 1 year | ~50 MB |
| 5 years | ~250 MB |
| 10 years | ~500 MB |

A standard Pi SD card or USB drive is more than sufficient for the lifetime of your system.

**Recommended:** Use a USB SSD instead of an SD card for better reliability and speed.

Container logs are capped as well, at 10 MB per file and 3 files per service, so an unattended stack cannot fill the disk with its own logs while the database keeps growing. See [Logs](../CONFIGURATION.md#logs) to change the limits.

---

## Backup

```bash
# Manual backup
make backup-db

# Backups saved to ./backups/helio_YYYYMMDD.dump
```

To automate daily backups, add to crontab:
```bash
crontab -e
# Add this line:
0 3 * * * cd /home/pi/Helio && make backup-db
```

---

## Keeping the Pi Healthy

```bash
# Check disk usage
df -h

# Check memory
free -h

# Check Docker container resource usage
docker stats
```

---

## Updating

```bash
cd ~/Helio
make update
```

Pulls latest code and images, runs migrations, restarts services.

---

## Estimated Cost

| Item | One-Time Cost |
|------|-------------|
| Raspberry Pi 4 (2GB) | ~$45 |
| Case + power supply | ~$15 |
| 32GB SD card or USB SSD | ~$15–$30 |
| **Total** | **~$75–$90** |

After the initial purchase, running cost is essentially zero — just the electricity to power the Pi (~$2–5/year).
