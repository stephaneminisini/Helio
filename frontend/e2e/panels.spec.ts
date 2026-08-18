import { expect, test } from "@playwright/test";
import { expectNoErrorState, figure, openTab, statValue } from "./helpers";

test("the Panels page renders the heatmap with a flagged panel", async ({
  page,
}) => {
  await openTab(page, "Panels");

  await expect(page.getByRole("heading", { name: "Panels" })).toBeVisible();
  await expectNoErrorState(page);

  // The page swaps itself for an empty state when data_available is false, and
  // that state renders no error, so this is the assertion that says the seeded
  // per-panel readings actually reached the heatmap.
  await expect(
    page.getByText("Per-panel data is not available yet")
  ).toHaveCount(0);

  // Cell count against the API's own figure, so a heatmap that dropped panels
  // cannot pass by rendering a grid of the wrong size.
  const cells = page
    .getByRole("list", { name: "Panel efficiency heatmap" })
    .getByRole("listitem");
  const reporting = await figure(statValue(page, "Panels Reporting"));
  expect(reporting).toBeGreaterThan(0);
  await expect(cells).toHaveCount(reporting);
  await expect(cells.first()).toHaveText(/\d+%/);

  // The mock fleet holds one deliberately weak panel, so the flag and the advice
  // that goes with it are exercised rather than only the healthy path.
  expect(await figure(statValue(page, "Underperforming"))).toBeGreaterThanOrEqual(
    1
  );
  await expect(
    page.getByText(
      "Check these panels for shading, soiling or a microinverter fault."
    )
  ).toBeVisible();
});
