# Pre-Publish Checklist

Before making the repository public, complete every item on this list.

---

## 1. Replace Placeholders

Run the following in the repo root (fill in your values first):

```bash
YOUR_GH=yourgithubusername
YOUR_DO=your_digitalocean_referral_code
YOUR_RAIL=your_railway_referral_code
YOUR_BMC=your_buymeacoffee_username

# GitHub username
find . -not -path './.git/*' -type f \
  -exec sed -i "s/YOUR_USERNAME/$YOUR_GH/g" {} +

# DigitalOcean referral code
find . -not -path './.git/*' -type f \
  -exec sed -i "s/YOUR_REFERRAL_CODE/$YOUR_DO/g" {} +

# Railway referral code
find . -not -path './.git/*' -type f \
  -exec sed -i "s/YOUR_CODE/$YOUR_RAIL/g" {} +

# Buy Me a Coffee username
find . -not -path './.git/*' -type f \
  -exec sed -i "s/YOUR_BMC_USERNAME/$YOUR_BMC/g" {} +
```

---

## 2. Referral & Monetization Accounts

- [ ] Sign up for [DigitalOcean](https://digitalocean.com) and find your referral link at **Account → Referrals**
- [ ] Sign up for [Railway](https://railway.app) and find your referral code at **Account → Referral**
- [ ] Create a [Buy Me a Coffee](https://buymeacoffee.com) account and set up your page
- [ ] Verify all referral links work by opening them in an incognito window

---

## 3. DigitalOcean One-Click Button

- [ ] Verify `app.yaml` is at `.do/app.yaml` in the repo root
- [ ] Test the deploy button URL format:
  ```
  https://cloud.digitalocean.com/apps/new?repo=https://github.com/YOUR_GH/helio-monitor
  ```
- [ ] Open the URL and confirm the App Platform wizard pre-populates correctly

---

## 4. Railway One-Click Button

- [ ] Verify the Railway template URL works:
  ```
  https://railway.app/new/template?template=https://github.com/YOUR_GH/helio-monitor
  ```

---

## 5. Repository Settings

On GitHub, after creating the repo:

- [x] Set repo to **Public**
- [x] Add a description: `The solar dashboard Enphase never built - historical comparisons, efficiency tracking, and degradation alerts.`
- [ ] Add a website URL (your Buy Me a Coffee page or a demo URL)
- [x] Add topics: `solar`, `enphase`, `self-hosted`, `docker`, `postgresql`, `fastapi`, `react`, `raspberry-pi`
- [x] Enable **Issues**
- [x] **Discussions: left off.** One maintainer means one inbox; splitting questions
      between Issues and Discussions on a low-traffic repo means one of the two goes
      unread. Support questions go in Issues under a `question` label. Revisit if the
      volume ever justifies it.
- [ ] Add a social preview image (screenshot of the dashboard)

The website URL stays empty until there is somewhere real to point it. There is no
demo instance, and the Buy Me a Coffee page does not exist yet.

---

## 6. Files Check

- [ ] `README.md` renders correctly on GitHub (check badges, buttons, tables)
- [ ] `.env` is NOT present in the repo (only `.env.example`)
- [ ] `.gitignore` is committed
- [ ] `LICENSE` file is present (MIT)
- [ ] `docs/` folder is fully populated
- [ ] `.do/app.yaml` is present

---

## 7. License

Create a `LICENSE` file with MIT license text:

```
MIT License

Copyright (c) 2026 YOUR_NAME

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 8. Final Check

- [ ] Clone the repo fresh into a temp directory and run `make init` — verify it works cleanly
- [ ] Confirm no credentials, tokens, or personal data are in any committed file
- [ ] Open the GitHub repo as a logged-out user — confirm it looks good
