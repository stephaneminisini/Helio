# Deploy to Railway

Railway is a fast and developer-friendly alternative to DigitalOcean. It has a very simple one-click deploy experience and a generous free tier for low-traffic apps.

---

## 🎁 Free Credit

Sign up with the referral link below to start with free credit on Railway:

**[→ Sign up on Railway](https://railway.app?referralCode=YOUR_CODE)**

---

## One-Click Deploy

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template?template=https://github.com/stephaneminisini/Helio)

---

## Manual Setup (Step by Step)

### Step 1 — Create a Railway Account

1. Go to [railway.app](https://railway.app?referralCode=YOUR_CODE)
2. Sign up with GitHub (recommended — makes repo connection seamless)

### Step 2 — Create a New Project

1. In the Railway dashboard click **New Project**
2. Select **Deploy from GitHub repo**
3. Choose the `Helio` repository
4. Railway auto-detects Docker Compose and configures services

### Step 3 — Add PostgreSQL

1. In your project, click **New → Database → Add PostgreSQL**
2. Railway provisions the database and automatically sets `DATABASE_URL`

### Step 4 — Set Environment Variables

Click on the **api** service, then **Variables**, and add:

| Variable | Value |
|----------|-------|
| `ENPHASE_CLIENT_ID` | Your Enphase Client ID |
| `ENPHASE_CLIENT_SECRET` | Your Enphase Client Secret |
| `ENPHASE_SYSTEM_ID` | Your Enphase System ID |
| `FERNET_KEY` | Generated Fernet key |
| `IRRADIANCE_SOURCE` | `nasa` |
| `TZ` | e.g. `America/Montreal` |
| `POLL_HOUR` | `4` |

Generate your Fernet key locally:
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Step 5 — Deploy

1. Click **Deploy** — Railway builds and deploys in 3–5 minutes
2. Open a shell session on the **api** service and run `alembic upgrade head` to
   create the schema. The container runs `uvicorn` and nothing else, so this is a
   separate step; skip it and every endpoint answers 500 because the tables it
   queries do not exist yet. Repeat it after any deploy that ships a migration
3. Click the generated `.railway.app` URL to open your dashboard
4. Go to **Setup**, fill in the form and click **Create System**, then click
   **Connect to Enphase** and authorize
5. Back in the shell session, run `python -m helio.cli backfill`

> The Makefile is a convenience for local checkouts and is not in the image, so
> `make` targets do not work in a Railway shell. The commands above are what
> those targets run inside the container.

---

## Estimated Cost

Railway pricing is usage-based:

| Usage | Estimated Cost |
|-------|---------------|
| Hobby plan (personal use) | $5/mo flat |
| PostgreSQL add-on | included in Hobby |
| **Total** | **$5/mo** |

> Railway's Hobby plan is well suited for personal self-hosted apps with low traffic.

---

## Updating

Railway redeploys automatically on every push to `main`. No manual steps needed.

---

## Notes

- Railway assigns a public HTTPS URL automatically (e.g. `helio-monitor.up.railway.app`)
- SSL is included at no extra cost
- Custom domains are supported on the Hobby plan
