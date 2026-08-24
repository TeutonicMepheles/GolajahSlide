import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { promisify } from "node:util";
import puppeteer from "puppeteer";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const harnessSource = resolve(projectRoot, "harnesses/presenter-focus/slides.md");
const workRoot = resolve(projectRoot, "work");
await mkdir(workRoot, { recursive: true });
const harnessOutputRoot = await mkdtemp(resolve(workRoot, "presenter-focus-"));
const harnessOutput = resolve(harnessOutputRoot, "index.html");
const exampleUrl = pathToFileURL(harnessOutput).href;
const screenshotPath = process.env.PRESENTER_FOCUS_SCREENSHOT;
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
  await page.goto(exampleUrl, { waitUntil: "load" });

  const slideIndex = await page.evaluate(() =>
    [...document.querySelectorAll(".slide")].findIndex(slide => slide.querySelector(".text-card"))
  );
  assert.notEqual(slideIndex, -1, "basic example should contain a text card");
  await page.evaluate(index => window.__SLIDE_PRESENTATION__.show(index, false), slideIndex);

  const target = await page.$(".slide.active .text-card[data-presenter-focus]");
  assert(target, "active slide should expose a semantic presenter-focus target");
  assert.equal(await page.$eval("body", node => node.classList.contains("presenter-focus-enabled")), false);
  assert.equal(await page.$eval("#focus", node => node.getAttribute("aria-pressed")), "false");
  await page.keyboard.press("h");
  await page.waitForFunction(() => document.body.classList.contains("presenter-focus-enabled"));
  await target.hover();
  await page.waitForFunction(() =>
    getComputedStyle(document.querySelector(".slide.active"), "::after").opacity === "1"
  );
  await page.waitForFunction(() =>
    Number.parseFloat(getComputedStyle(document.querySelector(".presenter-pointer-cue")).opacity) > 0.8
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

  const pointerCue = await page.evaluate(() => {
    const cue = document.querySelector(".presenter-pointer-cue");
    const card = document.querySelector(".slide.active .text-card[data-presenter-focus]");
    const cueRect = cue.getBoundingClientRect();
    const cardRect = card.getBoundingClientRect();
    const style = getComputedStyle(cue);
    return {
      ariaHidden: cue.getAttribute("aria-hidden"),
      pointerEvents: style.pointerEvents,
      borderColor: style.borderColor,
      cueCenter: {x: cueRect.left + cueRect.width / 2, y: cueRect.top + cueRect.height / 2},
      cardCenter: {x: cardRect.left + cardRect.width / 2, y: cardRect.top + cardRect.height / 2},
    };
  });
  assert.equal(pointerCue.ariaHidden, "true");
  assert.equal(pointerCue.pointerEvents, "none");
  assert(Math.abs(pointerCue.cueCenter.x - pointerCue.cardCenter.x) < 2);
  assert(Math.abs(pointerCue.cueCenter.y - pointerCue.cardCenter.y) < 2);

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

  const blockText = await page.$(".slide.active .text-card[data-presenter-focus] li:nth-child(1)[data-presenter-text]");
  assert(blockText, "list items should automatically become text-level focus targets");
  await blockText.hover();
  await page.waitForFunction(() =>
    getComputedStyle(document.querySelector(".slide.active li:nth-child(1)[data-presenter-text]")).zIndex === "22" &&
    !getComputedStyle(document.querySelector(".slide.active li:nth-child(1)[data-presenter-text]")).outlineColor.includes("/")
  );
  const focusDepth = await page.evaluate(() => {
    const containerStyle = [...document.querySelectorAll(".slide.active [data-presenter-focus]:hover")]
      .map(node => getComputedStyle(node)).find(style => style.zIndex === "21");
    const textStyle = [...document.querySelectorAll(".slide.active [data-presenter-text]:hover")]
      .map(node => getComputedStyle(node)).find(style => style.zIndex === "22");
    const containerColor = containerStyle.outlineColor;
    const textColor = textStyle.outlineColor;
    const channels = color => {
      const rgb = color.match(/rgba?\(([^)]+)\)/);
      if (rgb) return rgb[1].split(/[ ,/]+/).slice(0, 3).map(Number);
      const srgb = color.match(/color\(srgb\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)/);
      if (srgb) return srgb.slice(1, 4).map(value => Number(value) * 255);
      throw new Error(`Unsupported computed color: ${color}`);
    };
    const distanceFromWhite = color => Math.hypot(...channels(color).map(channel => 255 - channel));
    return {
      containerColor,
      textColor,
      containerDepth: distanceFromWhite(containerColor),
      textDepth: distanceFromWhite(textColor),
    };
  });
  assert(
    focusDepth.textDepth > focusDepth.containerDepth + 25,
    `nested text should use a stronger theme color than its container: ${JSON.stringify(focusDepth)}`
  );

  const inlineText = await page.$('.slide.active mark[data-presenter-text="inline"]');
  assert(inlineText, "==...== should render an inline text-level focus target");
  await inlineText.hover();
  await page.waitForFunction(() =>
    getComputedStyle(document.querySelector('.slide.active mark[data-presenter-text="inline"]')).zIndex === "22" &&
    !getComputedStyle(document.querySelector('.slide.active mark[data-presenter-text="inline"]')).outlineColor.includes("/")
  );

  const colorsBeforeThemeChange = await page.evaluate(() => ({
    pointer: getComputedStyle(document.querySelector(".presenter-pointer-cue")).borderColor,
    container: getComputedStyle(document.querySelector(".slide.active [data-presenter-focus]:hover")).outlineColor,
    text: getComputedStyle(document.querySelector('.slide.active mark[data-presenter-text="inline"]')).outlineColor,
  }));
  await page.evaluate(() => {
    document.documentElement.style.setProperty("--accent", "#D1244F");
    document.documentElement.style.setProperty("--accent-soft", "#FFE8EE");
  });
  await page.waitForFunction(before =>
    getComputedStyle(document.querySelector(".presenter-pointer-cue")).borderColor !== before.pointer &&
    getComputedStyle(document.querySelector('.slide.active mark[data-presenter-text="inline"]')).outlineColor !== before.text,
    {}, colorsBeforeThemeChange
  );
  const colorsAfterThemeChange = await page.evaluate(() => ({
    pointer: getComputedStyle(document.querySelector(".presenter-pointer-cue")).borderColor,
    container: getComputedStyle(document.querySelector(".slide.active [data-presenter-focus]:hover")).outlineColor,
    text: getComputedStyle(document.querySelector('.slide.active mark[data-presenter-text="inline"]')).outlineColor,
  }));
  assert.notEqual(colorsAfterThemeChange.pointer, colorsBeforeThemeChange.pointer);
  assert.notEqual(colorsAfterThemeChange.container, colorsBeforeThemeChange.container);
  assert.notEqual(colorsAfterThemeChange.text, colorsBeforeThemeChange.text);

  if (screenshotPath) {
    await mkdir(dirname(resolve(screenshotPath)), { recursive: true });
    await page.screenshot({ path: resolve(screenshotPath), fullPage: true });
  }

  await page.keyboard.press("h");
  await page.waitForFunction(() => !document.body.classList.contains("presenter-focus-enabled"));
  assert.equal(await page.$eval("#focus", node => node.getAttribute("aria-pressed")), "false");
  assert.equal(await page.$eval(".presenter-pointer-cue", node => node.dataset.visible), "false");

  await page.keyboard.press("h");
  await page.keyboard.press("e");
  await page.waitForFunction(() => document.body.classList.contains("editor-open"));
  const layoutOptionPalette = await page.$$eval("#editorLayout option", options => options.map(option => ({
    enabled: !option.disabled,
    color: getComputedStyle(option).color,
    backgroundColor: getComputedStyle(option).backgroundColor,
  })));
  assert(layoutOptionPalette.some(option => option.enabled), "layout picker should expose enabled options");
  assert(
    layoutOptionPalette.filter(option => option.enabled).every(option =>
      option.color === "rgb(247, 246, 251)" && option.backgroundColor === "rgb(37, 35, 45)"
    ),
    `enabled layout options should remain legible in the native popup: ${JSON.stringify(layoutOptionPalette)}`
  );
  await page.waitForFunction(() =>
    getComputedStyle(document.querySelector(".slide.active"), "::after").opacity === "0"
  );
  assert.equal(
    await page.$eval(".slide.active", node => getComputedStyle(node, "::after").opacity),
    "0",
    "editor mode should suspend hover focus"
  );
  assert.equal(
    await page.$eval(".presenter-pointer-cue", node => getComputedStyle(node).opacity),
    "0",
    "editor mode should hide the pointer cue"
  );

  await page.click('[data-editor-category="global"] > summary');
  assert.equal(await page.$eval('[data-editor-category="global"]', node => node.open), true);
  await page.click("#editorPresenterFocusShortcut");
  await page.keyboard.press("k");
  assert.equal(await page.$eval("#editorPresenterFocusShortcut", node => node.value), "K");
  assert.equal(await page.$eval("#focus", node => node.getAttribute("aria-keyshortcuts")), "K");
  assert.match(await page.$eval("#focus", node => node.title), /（K）$/);
  assert.equal(
    await page.evaluate(() => window.__SLIDE_LAYOUT_EDITOR__.exportPayload().shortcuts.presenterFocus),
    "K",
    "global shortcut should be included in editor export payload"
  );

  await page.click("#editorPresenterFocusShortcut");
  await page.keyboard.press("e");
  assert.equal(
    await page.$eval("#editorPresenterFocusShortcut", node => node.value),
    "K",
    "reserved editor shortcut should not replace the focus shortcut"
  );
  assert.equal(await page.$eval("body", node => node.classList.contains("editor-open")), true);

  await page.keyboard.press("Escape");
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => !document.body.classList.contains("editor-open"));
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(() => {
    document.activeElement?.blur();
    resolve();
  }))));
  await page.keyboard.press("h");
  assert.equal(
    await page.$eval("body", node => node.classList.contains("presenter-focus-enabled")),
    true,
    "old shortcut should stop toggling after reassignment"
  );
  await page.keyboard.press("k");
  await page.waitForFunction(() => !document.body.classList.contains("presenter-focus-enabled"));
  await page.keyboard.press("k");
  await page.waitForFunction(() => document.body.classList.contains("presenter-focus-enabled"));
  await page.emulateMediaFeatures([{ name: "prefers-reduced-motion", value: "reduce" }]);
  await page.waitForFunction(() =>
    getComputedStyle(document.querySelector(".slide.active .text-card[data-presenter-focus]")).scale === "1"
  );
  assert.equal(
    await page.$eval(".slide.active .text-card[data-presenter-focus]", node => getComputedStyle(node).scale),
    "1",
    "reduced-motion mode should remove focus scaling"
  );

  await page.reload({ waitUntil: "load" });
  assert.equal(await page.$eval("#editorPresenterFocusShortcut", node => node.value), "K");
  assert.equal(await page.$eval("#focus", node => node.getAttribute("aria-keyshortcuts")), "K");
  assert.equal(await page.$eval("body", node => node.classList.contains("presenter-focus-enabled")), false);
  await page.keyboard.press("k");
  await page.waitForFunction(() => document.body.classList.contains("presenter-focus-enabled"));

  console.log("Presenter focus browser test passed.");
} finally {
  if (browser) await browser.close();
  await rm(harnessOutputRoot, { recursive: true, force: true });
}
