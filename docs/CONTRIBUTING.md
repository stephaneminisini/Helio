# Contributing to Helio Monitor

Thank you for your interest in contributing! Helio Monitor is a personal project that welcomes community improvements.

---

## Ways to Contribute

- **Bug reports** — Open an issue describing what happened, what you expected, and your deployment method
- **Feature requests** — Open an issue with the `enhancement` label
- **Pull requests** — Bug fixes, documentation improvements, and small features are welcome
- **Translations** — Help make the UI accessible in other languages

---

## Development Setup

```bash
git clone https://github.com/YOUR_USERNAME/helio-monitor.git
cd helio-monitor
cp .env.example .env
# Fill in .env with test credentials or use the mock mode (see below)
make up
make migrate
```

### Mock Mode

If you don't have an Enphase system, you can run with seeded mock data:

```bash
make seed-mock
```

This inserts 3 years of synthetic production data so you can develop against a realistic dataset without API access.

Re-running it is safe: it overwrites the days it generated. It refuses to run, with exit code 3, against a database that already holds production intervals it did not write, because real measurements older than the Enphase retention window cannot be fetched again.

---

## Smoke Tests

The Playwright suite in `frontend/e2e/` opens the Overview, Efficiency and Setup pages in a real browser and asserts on what they render. It exists to catch the failure the unit tests cannot see: a page that type-checks and builds, then renders an error state because the API contract moved.

It needs a database with data in it, so seed one first:

```bash
make up
make migrate
make e2e-system   # creates the system row the seeder writes against
make seed-mock
make e2e
```

`make e2e` starts its own vite dev server on port 5173 and proxies `/api` to the API on port 8000, so the browser sees a single origin. Leave `VITE_API_BASE_URL` unset when running it — setting it makes the frontend call the API directly and the requests fail CORS.

Browsers are not installed by `npm ci`. Once per machine:

```bash
cd frontend && npx playwright install chromium
```

On a failure, the trace and screenshot land in `frontend/test-results/` and the HTML report in `frontend/playwright-report/` (`npx playwright show-report`). CI uploads both, plus the API log, as artifacts of the failed run.

---

## Pull Request Guidelines

1. Fork the repository and create a branch from `main`
2. Keep PRs focused — one feature or fix per PR
3. Add or update tests for any changed logic
4. Run `make test` and ensure all tests pass before submitting
5. Update relevant documentation if behavior changes
6. Write a clear PR description explaining what changed and why

---

## Code Style

- **Python:** Black formatting, isort for imports (`make lint` runs both)
- **TypeScript/React:** Prettier formatting (`make lint-frontend`)
- No commented-out code in PRs

---

## Reporting Security Issues

Please do not open public issues for security vulnerabilities. Email the maintainer directly (see GitHub profile). Security issues will be addressed within 72 hours.

---

## ☕ Non-Code Contributions

If this project has been useful to you but you don't want to contribute code, consider:

- ⭐ Starring the repo
- Sharing it with other solar owners
- [Buying me a coffee](https://www.buymeacoffee.com/YOUR_USERNAME)
