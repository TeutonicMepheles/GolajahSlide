import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { promisify } from "node:util";
import puppeteer from "puppeteer";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const harnessSource = resolve(projectRoot, "harnesses/footer-chapter-navigation/slides.md");
const workRoot = resolve(projectRoot, "work");
await mkdir(workRoot, { recursive: true });
const harnessOutputRoot = await mkdtemp(resolve(workRoot, "footer-chapter-navigation-"));
const harnessOutput = resolve(harnessOutputRoot, "index.html");
const harnessUrl = pathToFileURL(harnessOutput).href;
const screenshotPath = process.env.FOOTER_CHAPTER_NAVIGATION_SCREENSHOT;
const pythonExecutable = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
const execFileAsync = promisify(execFile);
const executablePath = [
  process.env.PUPPETEER_EXECUTABLE_PATH,
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
].find(candidate => candidate && existsSync(candidate));
let browser = null;

try {
  await execFileAsync(
    pythonExecutable,
    [resolve(projectRoot, "build_slides.py"), harnessSource, "-o", harnessOutput, "--strict"],
    { cwd: projectRoot, windowsHide: true }
  );
  browser = await puppeteer.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
  await page.goto(harnessUrl, { waitUntil: "load" });

  const generatedContract = await page.evaluate(() => {
    const active = document.querySelector(".slide.active");
    const basics = active.querySelectorAll(".section-footer-item")[0];
    const entries = [...basics.querySelectorAll(".section-footer-chapter")];
    return {
      debugSurface: Boolean(window.__SLIDE_FOOTER_CHAPTER_NAVIGATION__),
      chapterLabels: entries.map(entry => entry.querySelector(".section-footer-chapter-label").textContent.trim()),
      targets: entries.map(entry => Number(entry.dataset.slideTarget)),
      currentCount: basics.querySelectorAll('.section-footer-chapter[aria-current="location"]').length,
    };
  });
  assert.equal(generatedContract.debugSurface, true);
  assert.deepEqual(generatedContract.chapterLabels, ["概览", "配置"]);
  assert.deepEqual(generatedContract.targets, [0, 2]);
  assert.equal(generatedContract.currentCount, 1);

  const basicsTrigger = await page.$(".slide.active .section-footer-item:nth-child(1) [data-section-nav-trigger]");
  assert(basicsTrigger, "active slide should expose the first Section trigger");
  await basicsTrigger.hover();
  await page.waitForFunction(() =>
    document.querySelector(".slide.active .section-footer-item:nth-child(1)").classList.contains("is-open")
  );
  await page.waitForFunction(() => {
    const item = document.querySelector(".slide.active .section-footer-item:nth-child(1)");
    const menu = item.querySelector(".section-footer-menu");
    const footer = item.closest(".section-footer");
    return menu.getBoundingClientRect().bottom <= footer.getBoundingClientRect().top + 3;
  });
  const hoverGeometry = await page.evaluate(() => {
    const item = document.querySelector(".slide.active .section-footer-item:nth-child(1)");
    const footer = item.closest(".section-footer");
    const menu = item.querySelector(".section-footer-menu");
    const buttons = [...menu.querySelectorAll(".section-footer-chapter")];
    const footerRect = footer.getBoundingClientRect();
    const menuRect = menu.getBoundingClientRect();
    const buttonRects = buttons.map(button => button.getBoundingClientRect());
    return {
      expanded: item.querySelector("[data-section-nav-trigger]").getAttribute("aria-expanded"),
      menuHidden: menu.getAttribute("aria-hidden"),
      menuBottom: menuRect.bottom,
      footerTop: footerRect.top,
      vertical: buttonRects[1].top > buttonRects[0].bottom,
      pointerEvents: getComputedStyle(menu).pointerEvents,
    };
  });
  assert.equal(hoverGeometry.expanded, "true");
  assert.equal(hoverGeometry.menuHidden, "false");
  assert(hoverGeometry.menuBottom <= hoverGeometry.footerTop + 3, `menu should open upward: ${JSON.stringify(hoverGeometry)}`);
  assert.equal(hoverGeometry.vertical, true);
  assert.equal(hoverGeometry.pointerEvents, "auto");

  await page.click('.slide.active .section-footer-item:nth-child(1) [data-page-number="3"]');
  await page.waitForFunction(() => window.__SLIDE_PRESENTATION__.current === 2);
  assert.equal(await page.$eval("#currentPage", node => node.textContent), "3");
  assert.equal(new URL(page.url()).hash, "#3");

  const advancedTriggerSelector = ".slide.active .section-footer-item:nth-child(2) [data-section-nav-trigger]";
  await page.focus(advancedTriggerSelector);
  await page.keyboard.press("ArrowDown");
  await page.waitForFunction(() =>
    document.activeElement?.classList.contains("section-footer-chapter") &&
    document.activeElement?.textContent.includes("标题回退章节")
  );
  await page.keyboard.press("End");
  assert.equal(
    await page.evaluate(() => document.activeElement?.querySelector(".section-footer-chapter-label")?.textContent.trim()),
    "深入配置"
  );
  await page.keyboard.press("Escape");
  const keyboardClosed = await page.evaluate(selector => {
    const trigger = document.querySelector(selector);
    return {
      focusReturned: document.activeElement === trigger,
      expanded: trigger.getAttribute("aria-expanded"),
      open: trigger.closest("[data-section-nav-item]").classList.contains("is-open"),
    };
  }, advancedTriggerSelector);
  assert.deepEqual(keyboardClosed, { focusReturned: true, expanded: "false", open: false });

  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => window.__SLIDE_PRESENTATION__.current === 3);
  assert.equal(await page.$eval("#currentPage", node => node.textContent), "4");

  await page.keyboard.press("e");
  await page.waitForFunction(() => document.body.classList.contains("editor-open"));
  assert.equal(
    await page.$eval(".slide.active .section-footer-menu", node => getComputedStyle(node).display),
    "none",
    "editor mode should suppress the floating menu"
  );
  await page.keyboard.press("Escape");
  await page.emulateMediaType("print");
  assert.equal(
    await page.$eval(".slide.active .section-footer-menu", node => getComputedStyle(node).display),
    "none",
    "print mode should suppress the floating menu"
  );

  if (screenshotPath) {
    await page.emulateMediaType("screen");
    await page.evaluate(() => window.__SLIDE_PRESENTATION__.show(0, false));
    await (await page.$(".slide.active .section-footer-item:nth-child(1) [data-section-nav-trigger]")).hover();
    await mkdir(dirname(resolve(screenshotPath)), { recursive: true });
    await page.screenshot({ path: resolve(screenshotPath), fullPage: true });
  }

  console.log("Footer chapter navigation browser test passed.");
} finally {
  if (browser) await browser.close();
  await rm(harnessOutputRoot, { recursive: true, force: true });
}
