import { expect, test } from "@playwright/test";
import path from "node:path";

const FIXTURE = path.join(__dirname, "fixtures", "hoodie.jpg");

test.beforeEach(async ({ context }) => {
  await context.addInitScript(() => localStorage.setItem("vai_consent_v1", JSON.stringify({ analytics: false })));
});

test("landing page sells the promise", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Tes photos Vinted");
  await expect(page.getByRole("link", { name: /Améliorer ma première photo/ }).first()).toBeVisible();
  await expect(page.getByRole("slider", { name: /Comparer/ }).first()).toBeVisible();
});

test("guest: upload → AI → compare → adjust → download", async ({ page }) => {
  await page.goto("/app/enhance");
  await page.locator("input[type=file]").setInputFiles(FIXTURE);
  await page.waitForURL(/\/app\/photos\//);
  await expect(page.getByText("Maintenir pour voir l'original")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/Fidélité couleur/)).toBeVisible();

  // live preview after changing the intensity
  const preview = page.waitForResponse((r) => r.url().includes("/preview") && r.status() === 200);
  await page.getByRole("button", { name: "Studio" }).first().click();
  await preview;

  // hold to see the original
  const hold = page.getByRole("button", { name: /Maintenir pour voir/ });
  await hold.dispatchEvent("pointerdown");
  await expect(page.getByRole("slider", { name: /Comparer/ })).toBeHidden(); // full original shown
  await hold.dispatchEvent("pointerup");
  await expect(page.getByRole("slider", { name: /Comparer/ })).toBeVisible();

  // export with automatic naming
  await page.getByRole("button", { name: /Télécharger/ }).last().click();
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("dialog").getByRole("button", { name: /Télécharger/ }).click(),
  ]);
  expect(download.suggestedFilename()).toBe("vinted_ai_01.jpg");
});
