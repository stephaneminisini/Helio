/**
 * Capture the dashboard screenshots that README.md and docs/INSTALL.md embed,
 * plus the social preview card GitHub unfurls repository links with.
 *
 * Run against a stack seeded with `make seed-mock`, never against a real system:
 * the images are committed, so anything on screen is published. The mock seed is
 * also what makes them reproducible, since it generates the same three years of
 * data every time.
 *
 * Usage (from the repo root, with the stack up):
 *   make screenshots
 *
 * Or directly, to point at a different origin:
 *   HELIO_URL=http://localhost:5173 node scripts/capture-screenshots.mjs
 *
 * Exit codes: 1 if a page renders its error state, never reaches the API, or
 * leaves a chart unplotted, so a broken capture fails loudly instead of
 * committing a screenshot of an error message.
 */
import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT_DIR = resolve(HERE, "../../docs/assets");
const HELIO_URL = process.env.HELIO_URL ?? "http://localhost:3000";

/** Retina, so the image still looks sharp on a GitHub page at 2x. */
const VIEWPORT = { width: 1440, height: 900 };
const SCALE = 2;

/** The tabs to capture, and the file each one is written to. */
const PAGES = [
  { tab: "Overview", file: "preview.png" },
  { tab: "Efficiency", file: "efficiency.png" },
  { tab: "Panels", file: "panels.png" },
];

const SOCIAL_TEMPLATE = resolve(HERE, "social-preview.html");
const SOCIAL_FILE = "social-preview.png";
/** The size GitHub asks for, written at 1:1 because it downscales every unfurl. */
const SOCIAL_SIZE = { width: 1280, height: 640 };

/**
 * Wait for every chart on the page to finish drawing.
 *
 * Recharts reveals a line by animating `stroke-dasharray` over a path whose `d`
 * is final from the first frame, so watching `d` alone reports a half-drawn
 * curve as settled - which is exactly the screenshot this is here to prevent.
 * Both attributes are polled, and three identical reads in a row are required so
 * a single slow frame cannot pass for the end of the animation.
 */
async function waitForChartsToSettle(page) {
  const paths = page.locator(".recharts-wrapper path[d]");
  if ((await paths.count()) === 0) return;

  let previous = null;
  let stable = 0;
  for (let attempt = 0; attempt < 60; attempt += 1) {
    const current = await paths.evaluateAll((nodes) =>
      nodes
        .map((n) =>
          [
            n.getAttribute("d"),
            n.getAttribute("stroke-dasharray"),
            n.getAttribute("stroke-dashoffset"),
          ].join(",")
        )
        .join("|")
    );
    stable = current === previous ? stable + 1 : 0;
    if (stable >= 2) return;
    previous = current;
    await page.waitForTimeout(250);
  }
  throw new Error("Charts never stopped animating");
}

/**
 * Render the social preview card from the local template.
 *
 * Runs after the dashboard pages because the card embeds `preview.png`, and is
 * given its own context so the card lands at exactly 1280x640 rather than at
 * the retina scale the dashboard shots want.
 *
 * Throws if the embedded screenshot did not load, which would otherwise commit
 * a card with an empty right half.
 */
async function captureSocialPreview(browser) {
  const context = await browser.newContext({
    viewport: SOCIAL_SIZE,
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  await page.goto(pathToFileURL(SOCIAL_TEMPLATE).href, { waitUntil: "load" });

  const loaded = await page
    .locator(".shot img")
    .evaluate((img) => img.naturalWidth > 0);
  if (!loaded) {
    throw new Error("Social preview could not load docs/assets/preview.png");
  }

  await page.screenshot({ path: resolve(OUT_DIR, SOCIAL_FILE) });
  await context.close();
  console.log(`Rendered social preview -> docs/assets/${SOCIAL_FILE}`);
}

async function main() {
  await mkdir(OUT_DIR, { recursive: true });

  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: SCALE,
    // The dashboard renders relative timestamps and month labels, so the locale
    // and zone are pinned rather than inherited from whoever runs this.
    locale: "en-US",
    timezoneId: "America/Los_Angeles",
  });
  const page = await context.newPage();

  try {
    for (const { tab, file } of PAGES) {
      await page.goto(HELIO_URL, { waitUntil: "networkidle" });
      await page.getByRole("button", { name: tab, exact: true }).click();
      await page.getByRole("heading", { name: tab }).waitFor();

      const errors = page.getByText(/^Error:/);
      if ((await errors.count()) > 0) {
        throw new Error(`${tab} rendered an error: ${await errors.first().innerText()}`);
      }
      if ((await page.getByText("Loading...").count()) > 0) {
        await page.getByText("Loading...").first().waitFor({ state: "detached" });
      }
      await waitForChartsToSettle(page);

      // Cropped to where the content actually ends. The layout is min-h-screen,
      // so a plain viewport shot pads every page out to the same height with dead
      // background, and a short page gets a third of the image given to nothing.
      // main carries the layout's bottom padding, so its own edge is the margin.
      const content = await page.locator("main").boundingBox();
      const target = resolve(OUT_DIR, file);
      await page.screenshot({
        path: target,
        fullPage: true,
        // Finishes the tab pill's colour transition instead of catching it
        // mid-fade, which is what made two runs of the same page differ.
        animations: "disabled",
        clip: {
          x: 0,
          y: 0,
          width: VIEWPORT.width,
          height: Math.ceil(content.y + content.height),
        },
      });
      console.log(`Captured ${tab} -> docs/assets/${file}`);
    }
    await captureSocialPreview(browser);
  } finally {
    await browser.close();
  }
}

await main();
