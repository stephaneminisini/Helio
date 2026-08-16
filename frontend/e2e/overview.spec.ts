import { expect, test } from "@playwright/test";
import {
  comparisonCard,
  expectNoErrorState,
  figure,
  statCaption,
  statValue,
} from "./helpers";

test("the Overview page renders today's production and a comparison", async ({
  page,
}) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await expectNoErrorState(page);

  // The figure and the date it belongs to both come from the payload, so
  // neither an error state nor a hardcoded placeholder can satisfy this.
  await expect(statValue(page, "Today")).toHaveText(/^\d+(\.\d+)? kWh$/);
  await expect(statCaption(page, "Today")).toHaveText(/^\d{4}-\d{2}-\d{2}$/);

  // The seeder stops at yesterday, so today's own total is legitimately 0.0 kWh
  // on a seeded database. The all-time and best-day figures cover the stored
  // history, and both have to be real production.
  expect(await figure(statValue(page, "All Time"))).toBeGreaterThan(0);
  expect(await figure(statValue(page, "Best Day"))).toBeGreaterThan(0);

  // Both sides of this window are fully seeded, so it is the comparison that
  // must carry a measured delta rather than a dash.
  const monthly = comparisonCard(page, "This month vs last month");
  await expect(monthly.getByText(/^\d+\.\d kWh$/)).toBeVisible();
  await expect(monthly.getByText(/^vs \d+\.\d$/)).toBeVisible();
  await expect(monthly.getByText(/^[+-]?\d+\.\d%$/)).toBeVisible();
});
