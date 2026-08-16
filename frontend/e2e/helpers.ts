import { Locator, Page, expect } from "@playwright/test";

/**
 * The value of the StatCard carrying `label`.
 *
 * StatCard renders the label, the value and the caption as sibling paragraphs,
 * so the value is the paragraph immediately after the label. The label is
 * matched exactly, which keeps "Today" from also matching the comparison card
 * headed "Today vs same day last year".
 */
export function statValue(page: Page, label: string): Locator {
  return page
    .getByText(label, { exact: true })
    .locator("xpath=following-sibling::p[1]");
}

/** The caption below a StatCard's value, which not every card has. */
export function statCaption(page: Page, label: string): Locator {
  return page
    .getByText(label, { exact: true })
    .locator("xpath=following-sibling::p[2]");
}

/** The ComparisonBar card carrying `label`, which is its first child. */
export function comparisonCard(page: Page, label: string): Locator {
  return page.getByText(label, { exact: true }).locator("xpath=..");
}

/**
 * The leading number of a rendered figure, e.g. 45.2 from "45.2 MWh".
 *
 * @throws Error If the element renders no leading number, since a NaN would
 *   otherwise pass a `toBeGreaterThan` check silently.
 */
export async function figure(locator: Locator): Promise<number> {
  const text = (await locator.innerText()).trim();
  const value = Number.parseFloat(text);
  if (Number.isNaN(value)) {
    throw new Error(`Expected a number at the start of "${text}"`);
  }
  return value;
}

/**
 * Open a dashboard tab from the header nav.
 *
 * The tabs are component state rather than routes, so there is no URL to visit
 * and a reload always lands back on Overview.
 */
export async function openTab(page: Page, name: string): Promise<void> {
  await page.goto("/");
  await page.getByRole("button", { name, exact: true }).click();
}

/**
 * Assert the page rendered content rather than its error state.
 *
 * Every page starts with `if (error) return <div>Error: ...</div>`, which type
 * checks and builds perfectly well, so this is the failure this suite exists to
 * catch.
 */
export async function expectNoErrorState(page: Page): Promise<void> {
  await expect(page.getByText(/^Error:/)).toHaveCount(0);
}
