import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import puppeteer from "puppeteer";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const exampleUrl = pathToFileURL(resolve(projectRoot, "examples/basic/index.html")).href;
const screenshotPath = process.env.PRESENTER_FOCUS_SCREENSHOT;
const executablePath = [
  process.env.PUPPETEER_EXECUTABLE_PATH,
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
].find(candidate => candidate && existsSync(candidate));
const browser = await puppeteer.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });

try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
  await page.goto(exampleUrl, { waitUntil: "load" });

  const slideIndex = await page.evaluate(() =>
    [...document.querySelectorAll(".slide")].findIndex(slide => slide.querySelector(".text-card"))
  );
  assert.notEqual(slideIndex, -1, "basic example should contain a text card");
  await page.evaluate(index => window.__SLIDE_PRESENTATION__.show(index, false), slideIndex);

  const target = await page.$(".slide.active .text-card[data-presenter-focus]");
  assert(target, "active slide should expose a semantic presenter-focus target");
  await target.hover();
  await page.waitForFunction(() =>
    getComputedStyle(document.querySelector(".slide.active"), "::after").opacity === "1"
  );

  const focused = await page.evaluate(() => {
    const slide = document.querySelector(".slide.active");
    const card = slide.querySelector(".text-card[data-presenter-focus]");
    const style = getComputedStyle(card);
    return {
      enabled: document.body.classList.contains("presenter-focus-enabled"),
      overlayOpacity: getComputedStyle(slide, "::after").opacity,
      outlineColor: style.outlineColor,
      scale: style.scale,
      zIndex: style.zIndex,
    };
  });
  assert.equal(focused.enabled, true);
  assert.equal(focused.overlayOpacity, "1");
  assert.equal(focused.zIndex, "21");
  assert.notEqual(focused.outlineColor, "rgba(0, 0, 0, 0)");
  assert(Number.parseFloat(focused.scale) > 1);

  const focusAncestors = await page.evaluate(() => {
    const card = document.querySelector(".slide.active .text-card[data-presenter-focus]");
    return [".content", ".split-layout", ".split-copy"].map(selector => ({
      selector,
      overflow: getComputedStyle(card.closest(selector)).overflow,
      hasHoveredFocus: card.closest(selector).matches(":has([data-presenter-focus]:not(.is-fullscreen):hover)"),
    }));
  });
  assert(
    focusAncestors.every(entry => entry.overflow === "visible"),
    `focused card ancestors should not clip its outline: ${JSON.stringify(focusAncestors)}`
  );

  const blockText = await page.$(".slide.active .text-card[data-presenter-focus] li:nth-child(2)[data-presenter-text]");
  assert(blockText, "list items should automatically become text-level focus targets");
  await blockText.hover();
  await page.waitForFunction(() =>
    getComputedStyle(document.querySelector(".slide.active li:nth-child(2)[data-presenter-text]")).zIndex === "22"
  );

  const inlineText = await page.$('.slide.active mark[data-presenter-text="inline"]');
  assert(inlineText, "==...== should render an inline text-level focus target");
  await inlineText.hover();
  await page.waitForFunction(() =>
    getComputedStyle(document.querySelector('.slide.active mark[data-presenter-text="inline"]')).zIndex === "22"
  );

  if (screenshotPath) {
    await mkdir(dirname(resolve(screenshotPath)), { recursive: true });
    await page.screenshot({ path: resolve(screenshotPath), fullPage: true });
  }

  await page.keyboard.press("h");
  await page.waitForFunction(() => !document.body.classList.contains("presenter-focus-enabled"));
  assert.equal(await page.$eval("#focus", node => node.getAttribute("aria-pressed")), "false");

  await page.keyboard.press("h");
  await page.keyboard.press("e");
  await page.waitForFunction(() => document.body.classList.contains("editor-open"));
  await page.waitForFunction(() =>
    getComputedStyle(document.querySelector(".slide.active"), "::after").opacity === "0"
  );
  assert.equal(
    await page.$eval(".slide.active", node => getComputedStyle(node, "::after").opacity),
    "0",
    "editor mode should suspend hover focus"
  );

  await page.keyboard.press("Escape");
  await page.emulateMediaFeatures([{ name: "prefers-reduced-motion", value: "reduce" }]);
  assert.equal(
    await page.$eval(".slide.active .text-card[data-presenter-focus]", node => getComputedStyle(node).scale),
    "1",
    "reduced-motion mode should remove focus scaling"
  );

  console.log("Presenter focus browser test passed.");
} finally {
  await browser.close();
}
