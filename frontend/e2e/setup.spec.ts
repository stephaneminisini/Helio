import { expect, test } from "@playwright/test";
import { expectNoErrorState, openTab } from "./helpers";

test("the Setup page saves a changed setting and reloads it", async ({ page }) => {
  await openTab(page, "Setup");

  await expect(page.getByRole("heading", { name: "Setup" })).toBeVisible();
  await expectNoErrorState(page);

  // A fresh value every run, so a form that silently kept its previous contents
  // cannot pass this by accident.
  const systemName = `Helio smoke ${Date.now()}`;
  await page.locator("#name").fill(systemName);

  const saved = page.waitForResponse(
    (response) =>
      response.url().includes("/api/settings") &&
      response.request().method() === "PUT" &&
      response.ok()
  );
  await page.getByRole("button", { name: "Save Settings" }).click();
  await saved;

  // The tabs are component state, so a reload lands on Overview and the Setup
  // tab has to be opened again. The value can then only come from the API.
  await page.reload();
  await page.getByRole("button", { name: "Setup", exact: true }).click();

  await expect(page.locator("#name")).toHaveValue(systemName);
});
