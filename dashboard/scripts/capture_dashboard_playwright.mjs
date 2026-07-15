/**
 * Playwright evidence: dashboard load, setup wizard FAIL checks, demo-mode screenshot.
 * Run from dashboard/: pnpm exec node scripts/capture_dashboard_playwright.mjs
 */
import { chromium } from "playwright";
import { writeFileSync } from "fs";
import { join } from "path";

const SCRATCH =
  process.env.GOAL_SCRATCH ||
  "C:\\Users\\Keith\\AppData\\Local\\Temp\\grok-goal-3e705d8b50a4\\implementer";
const DASHBOARD_URL = process.env.DASHBOARD_URL || "http://127.0.0.1:5173";
const lines = [];

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));

  try {
    const response = await page.goto(DASHBOARD_URL, {
      waitUntil: "load",
      timeout: 60_000,
    });
    lines.push(`dashboard_origin=${DASHBOARD_URL}`);
    lines.push(`dashboard_load_status=${response?.status() ?? "no-response"}`);

    const tour = page.getByRole("dialog", { name: "Onboarding tour" });
    if (await tour.isVisible().catch(() => false)) {
      await page.getByRole("button", { name: "Skip" }).click();
      lines.push("onboarding_tour_dismissed=true");
    }

    await page.getByRole("heading", { name: "First-run setup" }).waitFor({ timeout: 30_000 });
    lines.push("wizard_overlay_visible=true");

    await page.getByText("Receive wallet").waitFor({ timeout: 30_000 });
    await page.getByText("FAIL").first().waitFor({ timeout: 30_000 });
    const failCount = await page.locator("text=FAIL").count();
    lines.push(`wizard_fail_checks=${failCount}`);
    lines.push(`wizard_fail_visible=${failCount > 0}`);

    const doctor = await page.evaluate(async () => {
      const res = await fetch("/api/doctor");
      return res.json();
    });
    lines.push(`doctor_api_ready=${doctor?.summary?.ready}`);
    lines.push(`doctor_api_fail=${doctor?.summary?.fail}`);
    const failIds = (doctor?.checks || [])
      .filter((c) => c.status === "fail")
      .map((c) => c.id);
    lines.push(`doctor_fail_ids=${failIds.join(",")}`);
    lines.push(`wizard_matches_doctor=${failIds.includes("pay_to")}`);

    await page.getByRole("button", { name: "Continue to dashboard" }).click();
    await page.getByLabel("Demo").check();
    await page.getByText("DEMO — sample data").waitFor({ timeout: 10_000 });
    lines.push("demo_mode_enabled=true");

    const panels = [
      ["hero", "Net position"],
      ["quota", "Quota"],
      ["activity", "Activity"],
      ["spend", "Spend ledger"],
      ["revenue", "Revenue ledger"],
      ["inspector", "402 Inspector"],
      ["mission", "Mission progress"],
    ];
    for (const [id, name] of panels) {
      const visible = await page.getByText(name, { exact: false }).first().isVisible();
      lines.push(`panel_${id}=${visible}`);
    }

    const shot = join(SCRATCH, "dashboard_demo.png");
    await page.screenshot({ path: shot, fullPage: true });
    lines.push(`screenshot_path=${shot}`);
    lines.push(`screenshot_exists=true`);

    lines.push(`page_errors=${errors.length}`);
    if (errors.length) lines.push(`page_error_sample=${errors[0]}`);
  } catch (err) {
    lines.push(`playwright_error=${err}`);
  } finally {
    await browser.close();
  }

  const logPath = join(SCRATCH, "playwright_capture.log");
  writeFileSync(logPath, lines.join("\n") + "\n", "utf-8");
  console.log(lines.join("\n"));
  process.exit(lines.some((l) => l.startsWith("playwright_error=")) ? 1 : 0);
}

main();