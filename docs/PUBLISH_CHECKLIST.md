# Pre-Publish Checklist

Before making the repository public, complete every item on this list.

---

## 1. Replace Placeholders

Three placeholders are left in the Markdown, all of them account handles the
author has to create first. Run the following in the repo root (fill in your
values first):

```bash
YOUR_BMC=your_buymeacoffee_username
YOUR_DO=your_digitalocean_referral_code
YOUR_RAIL=your_railway_referral_code

# Tracked Markdown only, so the substitution cannot reach node_modules,
# package-lock.json or the screenshots. This checklist is excluded because it
# documents the placeholders it would otherwise rewrite.
FILES=$(git ls-files '*.md' | grep -v '^docs/PUBLISH_CHECKLIST.md$')

sed -i "s|YOUR_USERNAME|$YOUR_BMC|g" $FILES       # Buy Me a Coffee handle
sed -i "s|YOUR_REFERRAL_CODE|$YOUR_DO|g" $FILES   # DigitalOcean referral code
sed -i "s|YOUR_CODE|$YOUR_RAIL|g" $FILES          # Railway referral code
```

Then confirm nothing was missed — this should print lines from this file only:

```bash
git grep -n "YOUR_"
```

`YOUR_SYSTEM_ID` in `.env.example` is part of an example Enlighten URL showing
where to find your System ID. It is not a placeholder to substitute.

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
  https://cloud.digitalocean.com/apps/new?repo=https://github.com/stephaneminisini/Helio
  ```
- [ ] Open the URL and confirm the App Platform wizard pre-populates correctly

---

## 4. Railway One-Click Button

- [ ] Verify the Railway template URL works:
  ```
  https://railway.app/new/template?template=https://github.com/stephaneminisini/Helio
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

- [x] `README.md` renders correctly on GitHub (badges, buttons, tables, and all
      four screenshots load for a logged-out visitor)
- [x] `.env` is NOT present in the repo (only `.env.example`), and never was in
      any commit
- [x] `.gitignore` is committed
- [x] `LICENSE` file is present (MIT)
- [x] `docs/` folder is fully populated
- [x] `.do/app.yaml` is present

---

## 7. License

Done: `LICENSE` holds the MIT text below, with the copyright line reading
`Copyright (c) 2026 Stephane Minisini`.

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

Done on 2026-08-18 against a fresh clone of `develop` in a temp directory,
following `README.md` and `docs/INSTALL.md` literally (issue #32).

- [x] Clone the repo fresh into a temp directory and run `make init` — it reported
      success while leaving `FERNET_KEY` empty, so `make up` then failed startup
      validation. Fixed in #67; the recovery command the error suggested,
      `make generate-fernet-key`, failed the same way and is fixed there too
- [x] Confirm no credentials, tokens, or personal data are in any committed file —
      `gitleaks detect` over the full history reports no leaks, GitHub secret
      scanning reports no alerts, `.env` appears in no commit, and the test
      fixtures and coordinates are synthetic
- [x] Open the GitHub repo as a logged-out user — README renders, all four
      screenshots load, and every relative link resolves

What else the dry run turned up, all fixed alongside this checklist:

- `docs/INSTALL.md` claimed `make up` runs migrations. It does not: the API image
  starts `uvicorn` only, and every endpoint answered 500 on the unmigrated
  database until `make migrate` ran. `make migrate` is now its own documented step
  here, in the README quickstart, and in all three deploy guides
- The README quickstart went straight to `cp .env.example .env` and `make up`,
  never generating `FERNET_KEY`, and called `make backfill` before any system
  existed. It now runs `make init` and points at the Setup tab first
- `docs/INSTALL.md` said the Client ID and System ID are prefilled from `.env`.
  Nothing prefills them, and the form never asks for a Client ID
- The DigitalOcean and Railway guides told you to run `make backfill` in a
  platform console. The image has no Makefile; the commands are
  `alembic upgrade head` and `python -m helio.cli backfill`
- The Setup form rejected decimal System Size, Tilt, Azimuth and Degradation Rate,
  because a number input defaults to `step=1`

Still open at the time of the dry run:

- The three placeholders in section 1 and the website URL in section 5 wait on
  accounts that do not exist yet (#61)
- `ENPHASE_SYSTEM_ID` is documented as required in `.env.example`,
  `docs/CONFIGURATION.md`, `.do/app.yaml` and both cloud guides, but nothing reads
  it: the System ID lives on the `systems` row, entered through the Setup tab
- The Enphase authorize and real backfill legs need live Enphase credentials, so
  they were exercised with `make seed-mock` instead
