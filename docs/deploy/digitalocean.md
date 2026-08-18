# Deploy to DigitalOcean

DigitalOcean is the recommended platform for running Helio Monitor in the cloud. It offers a simple one-click deploy, reliable uptime, and a generous referral program for new users.

---

## 🎁 Get $200 Free Credit

If you are new to DigitalOcean, use the referral link below. You get **$200 in free credit over 60 days** — more than enough to run Helio Monitor for months before paying anything.

**[→ Sign up with $200 free credit](https://m.do.co/c/YOUR_REFERRAL_CODE)**

---

## One-Click Deploy

Click the button below to deploy Helio Monitor directly from GitHub to DigitalOcean App Platform:

[![Deploy to DigitalOcean](https://www.deploytodo.com/do-btn-blue.svg)](https://cloud.digitalocean.com/apps/new?repo=https://github.com/stephaneminisini/Helio)

You will be walked through a short configuration wizard. See [Step 3](#step-3--configure-environment-variables) below for the values you need.

---

## Manual Setup (Step by Step)

### Step 1 — Create a DigitalOcean Account

1. Go to [digitalocean.com](https://m.do.co/c/YOUR_REFERRAL_CODE) and sign up
2. Verify your email and add a payment method (required even with free credit)

### Step 2 — Create a New App

1. In the DigitalOcean dashboard, click **Create → Apps**
2. Choose **GitHub** as the source
3. Authorize DigitalOcean to access your GitHub account
4. Select the `Helio` repository and the `main` branch
5. Click **Next**

### Step 3 — Configure Environment Variables

In the **Environment Variables** section, add the following:

| Variable | Value | Encrypted |
|----------|-------|-----------|
| `ENPHASE_CLIENT_ID` | Your Enphase Client ID | ✅ Yes |
| `ENPHASE_CLIENT_SECRET` | Your Enphase Client Secret | ✅ Yes |
| `ENPHASE_SYSTEM_ID` | Your Enphase System ID | No |
| `FERNET_KEY` | Generated Fernet key (see below) | ✅ Yes |
| `IRRADIANCE_SOURCE` | `nasa` | No |
| `TZ` | Your timezone e.g. `America/Montreal` | No |
| `POLL_HOUR` | `4` | No |

**Generate a Fernet key** on your local machine:
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

> Mark sensitive variables as **Encrypted** — DigitalOcean stores them as secrets and never displays them again.

### Step 4 — Add a Managed Database

1. In the app wizard, click **Add Resource → Database**
2. Select **PostgreSQL**
3. Choose the **Basic** plan ($15/mo) or **Dev** plan ($7/mo for low-traffic personal use)
4. DigitalOcean will automatically inject `DATABASE_URL` into your app

### Step 5 — Choose a Plan

For personal use the **Basic** app plan works well:

| Component | Recommended Plan | Est. Cost/mo |
|-----------|-----------------|-------------|
| App (API + Frontend) | Basic — 512 MB RAM | $5 |
| Database (PostgreSQL) | Dev Database | $7 |
| **Total** | | **~$12/mo** |

> With the $200 referral credit, this runs free for roughly 16 months.

### Step 6 — Deploy

1. Click **Create Resources**
2. DigitalOcean will build and deploy the app (5–10 minutes on first deploy)
3. Once deployed, click the app URL to open your dashboard

### Step 7 — Authorize Enphase & Backfill

1. Open your app URL and go to the **Setup** tab
2. Click **Connect Enphase Account** and authorize via Enphase login
3. In the DigitalOcean console, open a **Console** session to your app and run:
   ```bash
   make backfill
   ```
4. Wait for the backfill to complete, then refresh the dashboard

---

## Updating

DigitalOcean App Platform automatically redeploys when you push to `main`. No manual steps needed.

To trigger a manual redeploy:
1. Go to your app in the DigitalOcean dashboard
2. Click **Actions → Force Rebuild and Deploy**

---

## Custom Domain (Optional)

1. In your app settings, go to **Domains**
2. Click **Add Domain**
3. Enter your domain (e.g. `solar.yourdomain.com`)
4. Add the provided CNAME record to your DNS provider
5. DigitalOcean provisions a free SSL certificate automatically

---

## Estimated Monthly Cost

| Scenario | Cost |
|----------|------|
| First ~16 months (with referral credit) | $0 |
| After credit expires | ~$12/mo |
| With custom domain and SSL | No extra charge |

---

## Referral Details

When you sign up via the referral link and spend $25, the project author receives a $25 credit. This helps cover the cost of maintaining Helio Monitor. Thank you! ☀️
