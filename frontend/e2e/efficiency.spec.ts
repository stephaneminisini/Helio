import { expect, test } from "@playwright/test";
import { expectNoErrorState, figure, openTab, statValue } from "./helpers";

/** The stroke colours EfficiencyPage gives the measured and expected series. */
const ACTUAL_STROKE = "#f59e0b";
const EXPECTED_STROKE = "#6b7280";

test("the Efficiency page renders the PR trend with both series", async ({
  page,
}) => {
  await openTab(page, "Efficiency");

  await expect(page.getByRole("heading", { name: "Efficiency" })).toBeVisible();
  await expectNoErrorState(page);

  expect(await figure(statValue(page, "Lost Production"))).toBeGreaterThanOrEqual(
    0
  );
  expect(await figure(statValue(page, "Warranty Threshold"))).toBeGreaterThan(0);

  const chart = page.locator(".recharts-wrapper");
  await expect(chart).toBeVisible();
  await expect(page.getByText("Performance Ratio history (%)")).toBeVisible();

  // Recharts draws one path per series, told apart by its stroke. Asserting on
  // the path data rather than its mere presence is what distinguishes a plotted
  // series from a chart that rendered its axes around an empty array: the lines
  // are monotone, so every segment between two points is a cubic curve.
  await expect(
    chart.locator(`path.recharts-line-curve[stroke="${ACTUAL_STROKE}"]`)
  ).toHaveAttribute("d", /^M[\d.,-]+C/);
  await expect(
    chart.locator(`path.recharts-line-curve[stroke="${EXPECTED_STROKE}"]`)
  ).toHaveAttribute("d", /^M[\d.,-]+C/);

  // Month labels on the axis prove the series were driven by the API's history.
  await expect(
    chart.locator(".recharts-xAxis .recharts-cartesian-axis-tick-value").first()
  ).toHaveText(/^\d{4}-\d{2}$/);
});
